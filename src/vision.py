# src/vision.py
import cv2
import numpy as np
import win32gui, win32ui, win32con
import time
import collections
import queue
import pythoncom
import math
from win32com.client import Dispatch, GetActiveObject

from config import config
from utils.logger import print_at
from samples.UCwinRoadCOM import UCwinRoadComProxy
from samples.UCwinRoadUtils import Distance

def classify_speed_bump_type(Bump_Pattern, Measured_Height):
    cfg = config.CLASSIFICATION_THRESHOLDS
    
    if Bump_Pattern:
        if cfg['A_MIN_H'] <= Measured_Height <= cfg['A_MAX_H']:
            return "A"
        elif Measured_Height > cfg['A_MAX_H']:
            return "B"
        elif Measured_Height < cfg['D_MAX_H']:
            return "D"
    else:
        if Measured_Height >= cfg['C_MIN_H']:
            return "C"
    
    return "None"

def get_gt_depth(confirmed_type, ThreeDModelGT_cache, my_car):
    if not ThreeDModelGT_cache or not my_car: return 3.0

    relevant_bumps = [b for b in ThreeDModelGT_cache if b['type'] == confirmed_type]
    if not relevant_bumps: return 3.0

    try:
        car_pos = my_car.Position
        closest_bump = min(relevant_bumps, key=lambda b: Distance(car_pos, b['position']))
        return closest_bump['GT_Depth']
    except Exception:
        return 3.0
        
def capture_simulation_window(window_title):
    hwnd = win32gui.FindWindow(None, window_title)
    if hwnd == 0: return None
    left, top, right, bot = win32gui.GetClientRect(hwnd)
    w, h = right - left, bot - top
    if w < 2 or h < 2: return None
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)
    saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)
    bmpstr = saveBitMap.GetBitmapBits(True)
    frame = np.frombuffer(bmpstr, dtype=np.uint8).reshape((h, w, 4))
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC(); mfcDC.DeleteDC(); win32gui.ReleaseDC(hwnd, hwndDC)
    return frame[..., :3].copy()

def extract_road_roi(frame, roi_settings):
    h, w, _ = frame.shape
    top_y, bottom_y = int(h * roi_settings['top_y']), int(h * roi_settings['bottom_y'])
    top_x_start, top_x_end = int(w/2-(w*roi_settings['top_w']/2)), int(w/2+(w*roi_settings['top_w']/2))
    bottom_x_start, bottom_x_end = int(w/2-(w*roi_settings['bottom_w']/2)), int(w/2+(w*roi_settings['bottom_w']/2))
    roi_points = np.array([(top_x_start,top_y),(top_x_end,top_y),(bottom_x_end,bottom_y),(bottom_x_start,bottom_y)],dtype=np.int32)
    mask = np.zeros_like(frame[:,:,0]); cv2.fillPoly(mask,[roi_points],255)
    return roi_points, mask

def detect_bump_pattern(frame, roi_mask, pattern_settings):
    hsv_img = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower_yellow = np.array(pattern_settings['yellow_lower']); upper_yellow = np.array(pattern_settings['yellow_upper'])
    color_mask = cv2.inRange(hsv_img, lower_yellow, upper_yellow)
    detection_mask = cv2.bitwise_and(color_mask, roi_mask)
    return np.sum(detection_mask > 0) > pattern_settings['min_pixel_area']

def analyze_bump_height_map(frame, roi_mask):
    h, w, _ = frame.shape
    hsv_img = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV); h_channel = hsv_img[:,:,0]
    hue_mask = cv2.inRange(h_channel, config.HEIGHT_ANALYSIS_SETTINGS['hue_lower'], config.HEIGHT_ANALYSIS_SETTINGS['hue_upper'])
    analysis_mask = cv2.bitwise_and(hue_mask, roi_mask)
    contours, _ = cv2.findContours(analysis_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    Measured_Height, Measured_Distance = 0.0, 0.0
    if contours:
        all_points = np.concatenate(contours)
        if len(all_points) > 5:
            hull = cv2.convexHull(all_points)
            if cv2.contourArea(hull) > config.HEIGHT_ANALYSIS_SETTINGS['min_contour_area']:
                x,y,wc,hc = cv2.boundingRect(hull)
                if hc > 0 and (wc / hc) > config.HEIGHT_ANALYSIS_SETTINGS['min_aspect_ratio']:
                    hull_mask = np.zeros_like(analysis_mask); cv2.drawContours(hull_mask, [hull], -1, 255, -1)
                    hue_values = h_channel[np.nonzero(hull_mask)]
                    if hue_values.size > 0:
                        avg_hue = np.mean(hue_values)
                        h_points = config.HEIGHT_ANALYSIS_SETTINGS['height_interpolation_hue']
                        m_points = config.HEIGHT_ANALYSIS_SETTINGS['height_interpolation_m']
                        Measured_Height = np.interp(avg_hue, h_points, m_points)
                    
                    roi_s = config.ROI_SETTINGS_HEIGHT
                    roi_h = max(1,int(h*roi_s['bottom_y'])-int(h*roi_s['top_y']))
                    yb_norm = float(np.clip((y+hc-int(h*roi_s['top_y']))/roi_h,0.0,1.0))
                    dist_calib = config.HEIGHT_ANALYSIS_SETTINGS['distance_calibration']
                    y_points = sorted(dist_calib.keys()); dist_points = [dist_calib[y] for y in y_points]
                    Measured_Distance = float(np.interp(yb_norm,y_points,dist_points))
    return Measured_Height, Measured_Distance

def run_vision_processing(vision_to_control_queue, v2v_to_vision_queue, forward_vehicle_distance):
    pythoncom.CoInitialize()
    winRoadProxy, my_car = None, None
    ThreeDModelGT_cache = []

    try:
        winRoadProxy = UCwinRoadComProxy()
        driver = winRoadProxy.SimulationCore.TrafficSimulation.Driver
        project = winRoadProxy.Project
        
        target_names = ["typea", "typeb", "typec"]
        instance_count = project.ThreeDModelInstancesCount
        for i in range(instance_count):
            instance = project.ThreeDModelInstance(i)
            instance_name_lower = instance.Name.lower()
            if any(instance_name_lower.startswith(target) for target in target_names):
                height, depth = 0.0, 0.0
                try:
                    if instance.BoundingBoxesCount > 0:
                        bbox = instance.BoundingBox(0)
                        height = math.sqrt(bbox.yAxis.X**2 + bbox.yAxis.Y**2 + bbox.yAxis.Z**2) * 2
                        depth = math.sqrt(bbox.zAxis.X**2 + bbox.zAxis.Y**2 + bbox.zAxis.Z**2) * 2
                except Exception: pass
                
                bump_type = "UNKNOWN"
                if "typea" in instance_name_lower: bump_type = "A"
                elif "typeb" in instance_name_lower: bump_type = "B"
                elif "typec" in instance_name_lower: bump_type = "C"

                ThreeDModelGT_cache.append({ "id": instance.ID, "name": instance.Name, "type": bump_type, "position": instance.Position, "GT_Height": height, "GT_Depth": depth })
        
        t0 = time.time()
        while my_car is None and time.time() - t0 < 15.0:
            my_car = driver.CurrentCar
            time.sleep(0.2)
        if my_car is None and forward_vehicle_distance is not None: 
            raise RuntimeError()
    except Exception:
        if forward_vehicle_distance is not None:
            pythoncom.CoUninitialize()
            return

    Detection_History = collections.deque(maxlen=config.DETECTION_CONFIRM_FRAME_COUNT)

    while True:
        try:
            if my_car is None and forward_vehicle_distance is not None:
                 my_car = winRoadProxy.SimulationCore.TrafficSimulation.Driver.CurrentCar
                 time.sleep(0.5)
                 continue
            
            Is_V2V = False
            if forward_vehicle_distance is not None:
                Is_V2V = (forward_vehicle_distance.value <= 30.0)

            if Is_V2V:
                try:
                    v2v_data = v2v_to_vision_queue.get_nowait()
                    vehicle_name = v2v_data.get('vehicle_name', 'Vehicle')
                    bump_distance = v2v_data.get('distance_m', 0.0)
                    depth_m = v2v_data.get('width_m', 0.0)
                    
                    log_msg = f"[{v2v_data.get('source', 'V2V')}]{vehicle_name} | Dt:{bump_distance:.1f}m | Dp:{depth_m:.2f}m"
                    print_at('INFO_SOURCE', log_msg)
                    
                    data_packet = { 'type': v2v_data.get('type'), 'Measured_Height': v2v_data.get('height_m'), 'bump_distance': bump_distance, 'depth_m': depth_m, 'source': v2v_data.get('source', 'V2V') }
                    vision_to_control_queue.put_nowait(data_packet)
                except queue.Empty:
                    log_msg = f"[V2V]Forward Vehicle:{forward_vehicle_distance.value:.1f}m"
                    print_at('INFO_SOURCE', log_msg)
                    vision_to_control_queue.put_nowait({'type': 'None'})
            else:
                regular_frame = capture_simulation_window(config.REGULAR_VIEW_WINDOW_TITLE)
                height_frame = capture_simulation_window(config.HEIGHT_MAP_WINDOW_TITLE)
                if regular_frame is None or height_frame is None:
                    time.sleep(1)
                    continue

                _, road_mask_pattern = extract_road_roi(regular_frame, config.ROI_SETTINGS_PATTERN)
                _, road_mask_height = extract_road_roi(height_frame, config.ROI_SETTINGS_HEIGHT)
                
                Bump_Pattern = detect_bump_pattern(regular_frame, road_mask_pattern, config.PATTERN_ANALYSIS_SETTINGS)
                Measured_Height, Measured_Distance = analyze_bump_height_map(height_frame, road_mask_height)
                
                Bump_Type = classify_speed_bump_type(Bump_Pattern, Measured_Height)
                
                Detection_History.append(Bump_Type)
                confirmed_type = "None"
                if len(Detection_History) == config.DETECTION_CONFIRM_FRAME_COUNT and len(set(Detection_History)) == 1:
                    confirmed_type = Detection_History[0]
                if Bump_Type == "None":
                    Detection_History.clear()
                    
                GT_Depth_m = 0.0
                if confirmed_type != "None":
                    GT_Depth_m = get_gt_depth(confirmed_type, ThreeDModelGT_cache, my_car)
                
                if forward_vehicle_distance is not None:
                    log_msg = f"[Vision] H:{Measured_Height:.2f}m|Dt:{Measured_Distance:.1f}m|Dp:{GT_Depth_m:.2f}m|T:{confirmed_type}|P:{Bump_Pattern}"
                    print_at('INFO_SOURCE', log_msg)

                data_packet = { 'type': confirmed_type, 'Measured_Height': Measured_Height, 'bump_distance': Measured_Distance, 'depth_m': GT_Depth_m, 'source': 'Vision' }
                vision_to_control_queue.put_nowait(data_packet)

        except Exception:
            if forward_vehicle_distance is not None:
                my_car = None
                time.sleep(0.5)
        
        time.sleep(0.1)
    pythoncom.CoUninitialize()
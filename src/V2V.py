# src/V2V.py
import time
import pythoncom
import win32com.client
import math
import queue

from config import config
from samples.UCwinRoadCOM import UCwinRoadComProxy
from samples.UCwinRoadUtils import Distance

def run_v2v_simulation(v2v_to_vision_queue, Vehicle_Distance):
    pythoncom.CoInitialize()
    winRoadProxy = None
    my_car = None
    driver = None
    const = None
    ThreeDModelGT_cache = []
    
    try:
        winRoadProxy = UCwinRoadComProxy()
        driver = winRoadProxy.SimulationCore.TrafficSimulation.Driver
        project = winRoadProxy.Project
        const = win32com.client.constants
        
        target_names = ["typea", "typeb", "typec"]
        instance_count = project.ThreeDModelInstancesCount
        for i in range(instance_count):
            instance = project.ThreeDModelInstance(i)
            instance_name_lower = instance.Name.lower()
            if any(instance_name_lower.startswith(target) for target in target_names):
                height, depth = 0.0, 0.0
                if instance.BoundingBoxesCount > 0:
                    bbox = instance.BoundingBox(0)
                    height = math.sqrt(bbox.yAxis.X**2 + bbox.yAxis.Y**2 + bbox.yAxis.Z**2) * 2
                    depth = math.sqrt(bbox.zAxis.X**2 + bbox.zAxis.Y**2 + bbox.zAxis.Z**2) * 2
                ThreeDModelGT_cache.append({
                    "id": instance.ID, "name": instance.Name, "position": instance.Position,
                    "height": height, "width": depth
                })
    except Exception:
        pythoncom.CoUninitialize()
        return

    tracked_vehicle_id = -1
    bump_broadcast_status = {bump['id']: False for bump in ThreeDModelGT_cache}
    TRIGGER_DISTANCE_BUMP = 2.0

    while True:
        try:
            my_car = driver.CurrentCar
            if not my_car:
                Vehicle_Distance.value = 999.9
                time.sleep(0.5)
                continue

            front_car = my_car.DriverAheadInTraffic(const._primaryPath)
            if front_car and hasattr(front_car, 'TransientType') and front_car.TransientType == const._TransientCar and front_car.ID != 0:
                if tracked_vehicle_id != front_car.ID:
                    tracked_vehicle_id = front_car.ID
                    bump_broadcast_status = {bump['id']: False for bump in ThreeDModelGT_cache}
                
                my_pos = my_car.Position
                front_pos = front_car.Position
                Vehicle_Distance.value = Distance(my_pos, front_pos)
                
                if Vehicle_Distance.value <= 30.0:
                    for bump in ThreeDModelGT_cache:
                        if not bump_broadcast_status[bump['id']]:
                            dist_front_to_bump = Distance(front_pos, bump['position'])
                            if dist_front_to_bump < TRIGGER_DISTANCE_BUMP:
                                distance_to_bump = Distance(my_pos, bump['position'])
                                
                                name_lower = bump['name'].lower()
                                bump_type = "UNKNOWN"
                                if 'typea' in name_lower: bump_type = "A"
                                elif 'typeb' in name_lower: bump_type = "B"
                                elif 'typec' in name_lower: bump_type = "C"

                                data_packet = {
                                    'type': bump_type, 'height_m': bump['height'],
                                    'distance_m': distance_to_bump, 'width_m': bump['width'],
                                    'source': 'V2V', 'vehicle_name': front_car.Name
                                }
                                try:
                                    v2v_to_vision_queue.put_nowait(data_packet)
                                    bump_broadcast_status[bump['id']] = True
                                except queue.Full:
                                    pass
            else:
                Vehicle_Distance.value = 999.9
                tracked_vehicle_id = -1
        
        except Exception:
            Vehicle_Distance.value = 999.9
            tracked_vehicle_id = -1
            time.sleep(0.5)

        time.sleep(0.1)
    pythoncom.CoUninitialize()
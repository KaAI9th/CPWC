# utils/calibration.py
import os
import sys
import json
import time
import msvcrt
import pythoncom
import multiprocessing
import queue
from win32com.client import Dispatch, GetActiveObject

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.vision import run_vision_processing 
from config import config

def attach_or_launch():
    try:
        return GetActiveObject(config.UCWIN_PROG_ID)
    except:
        return Dispatch(config.UCWIN_PROG_ID)

def read_speed_kmh(car):
    try:
        return float(car.Speed(1))
    except:
        return 0.0

def restart_scenario(sim_core, proj, idx=0):
    try:
        if hasattr(sim_core, "StopAllScenarios"):
            sim_core.StopAllScenarios()
            time.sleep(0.3)
    except:
        pass
    sc = proj.Scenario(idx)
    sim_core.StartScenario(sc)
    time.sleep(0.8)

def run_calibration_session(target_speed):
    pythoncom.CoInitialize()
    
    if target_speed >= 50:
        brake_intensity = 1.0
    else:
        steps_down = (50 - target_speed) // 10
        brake_intensity = 1.0 - (steps_down * 0.1)
        brake_intensity = max(0.1, brake_intensity)
    
    print(f"Starting measurement for target speed {target_speed}km/h. (Calculated brake intensity: {brake_intensity:.1f})")

    try:
        ucwin = attach_or_launch()
        sim_core = ucwin.SimulationCore
        project = ucwin.Project
        driver = sim_core.TrafficSimulation.Driver
    except Exception as e:
        print(f"Failed to connect to UC-win/Road: {e}")
        pythoncom.CoUninitialize()
        return

    vision_to_calib_queue = multiprocessing.Queue(maxsize=1)
    vision_process = multiprocessing.Process(target=run_vision_processing, args=(vision_to_calib_queue, None, None))
    vision_process.start()

    measured_speeds = []
    
    restart_scenario(sim_core, project, 0)
    vehicle = None
    t0 = time.time()
    while vehicle is None and time.time() - t0 < 15.0:
        vehicle = driver.CurrentCar
        time.sleep(0.2)
    
    if vehicle is None:
        print("Vehicle not found. Exiting program.")
        if vision_process.is_alive():
            vision_process.terminate()
            vision_process.join()
        pythoncom.CoUninitialize()
        return

    while len(measured_speeds) < 3:
        print(f"\n--- Currently waiting for measurement {len(measured_speeds) + 1}/3 ---")
        
        print("Driving to reach target speed and for Vision detection...")
        is_braking = False
        braking_cancelled = False

        start_time = time.time()
        while time.time() - start_time < 90.0:
            current_speed = read_speed_kmh(vehicle)
            
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8').lower()
                if key == 'c' and is_braking:
                    speed = read_speed_kmh(vehicle)
                    vehicle.ParkingBrake = False
                    measured_speeds.append(round(speed, 2))
                    print(f"\n>> Collision! Speed ({speed:.2f} km/h) has been recorded. <<")
                    while not vision_to_calib_queue.empty(): vision_to_calib_queue.get()
                    break
                
                elif key == 'b' and is_braking:
                    vehicle.ParkingBrake = False
                    braking_cancelled = True
                    print("\n>> Wrong deceleration! This measurement is cancelled by pressing 'b'. <<")
                    while not vision_to_calib_queue.empty(): vision_to_calib_queue.get()
                    break

            if not is_braking:
                print(f"\rDriving... (Current speed: {current_speed:.1f} km/h)", end="")
                if current_speed >= target_speed:
                    try:
                        data = vision_to_calib_queue.get(timeout=0.01)
                        if data['type'] != "None":
                            print(f"\n>>> Speed bump detected! Starting braking (intensity:{brake_intensity:.1f}). (Record: 'c', Cancel: 'b') <<<")
                            is_braking = True
                    except queue.Empty:
                        pass
            
            if is_braking:
                on_time = 0.1 * brake_intensity
                off_time = 0.1 * (1.0 - brake_intensity)
                vehicle.Throttle = 0.0
                if on_time > 0:
                    vehicle.ParkingBrake = True; time.sleep(on_time)
                if off_time > 0:
                    vehicle.ParkingBrake = False; time.sleep(off_time)
        
        if braking_cancelled:
            continue
        if not is_braking and not measured_speeds:
             print("\nCould not detect a speed bump in time.")

    if vision_process.is_alive():
        vision_process.terminate()
        vision_process.join()

    if measured_speeds:
        try:
            with open(config.CALIBRATION_DATA_FILE_PATH, 'r') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        
        avg_speed = sum(measured_speeds) / len(measured_speeds)
        data[str(target_speed)] = round(avg_speed, 2)
        
        print(f"\n--- Final Result (Target Speed: {target_speed}km/h) ---")
        print(f"Number of valid measurements: {len(measured_speeds)}")
        print(f"Measured speeds: {measured_speeds}")
        print(f"Average speed: {avg_speed:.2f} km/h")

        output_dir = os.path.dirname(config.CALIBRATION_DATA_FILE_PATH)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(config.CALIBRATION_DATA_FILE_PATH, "w", encoding="utf-8") as f:
            sorted_data = {k: v for k, v in sorted(data.items(), key=lambda item: int(item[0]))}
            json.dump(sorted_data, f, indent=4)
        
        print(f"Results saved (accumulated) in '{config.CALIBRATION_DATA_FILE_PATH}'.")
    
    pythoncom.CoUninitialize()

if __name__ == '__main__':
    if sys.platform == "win32":
        multiprocessing.freeze_support()
    
    try:
        speed_in = int(input(">> Please enter the AI target speed (km/h) for the test: "))
    except ValueError as e:
        print(f"Input error: {e}")
        sys.exit(1)
        
    run_calibration_session(speed_in)
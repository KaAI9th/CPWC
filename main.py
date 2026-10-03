# main.py
import multiprocessing
import sys
import time
import pythoncom
from win32com.client import Dispatch, GetActiveObject

from config import config
from src.vision import run_vision_processing
from src.control import run_control_simulation
from src.V2V import run_v2v_simulation
from src.evaluate import run_evaluate_node
from utils.logger import setup_logging_area

def initialize_simulation():
    pythoncom.CoInitialize()
    try:
        ucwin = GetActiveObject(config.UCWIN_PROG_ID)
    except:
        ucwin = Dispatch(config.UCWIN_PROG_ID)

    sim_core = ucwin.SimulationCore
    project = ucwin.Project

    try:
        if hasattr(sim_core, "StopAllScenarios"):
            sim_core.StopAllScenarios()
            time.sleep(0.3)
    except:
        pass

    scenario = project.Scenario(0)
    sim_core.StartScenario(scenario)
    time.sleep(0.8)
    pythoncom.CoUninitialize()

if __name__ == '__main__':
    if sys.platform == "win32":
        multiprocessing.freeze_support()

    setup_logging_area()
    initialize_simulation()

    vision_to_control_queue = multiprocessing.Queue()
    v2v_to_vision_queue = multiprocessing.Queue()
    control_to_eval_queue = multiprocessing.Queue()
    eval_to_control_queue = multiprocessing.Queue()
    forward_vehicle_distance = multiprocessing.Value('d', 999.9)

    processes = [
        multiprocessing.Process(target=run_vision_processing, args=(vision_to_control_queue, v2v_to_vision_queue, forward_vehicle_distance)),
        multiprocessing.Process(target=run_control_simulation, args=(vision_to_control_queue, control_to_eval_queue, eval_to_control_queue)),
        multiprocessing.Process(target=run_v2v_simulation, args=(v2v_to_vision_queue, forward_vehicle_distance)),
        multiprocessing.Process(target=run_evaluate_node, args=(control_to_eval_queue, eval_to_control_queue))
    ]

    for p in processes:
        p.start()

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()
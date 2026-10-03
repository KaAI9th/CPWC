# src/evaluate.py
import math
import time
import queue
import pythoncom
from utils.logger import print_at
from config import config

def compute_rms(v_kmh, h_m, L_m):
    if not all([isinstance(v_kmh, (int, float)), isinstance(h_m, (int, float)), isinstance(L_m, (int, float))]):
        return 0.0
    if h_m <= 0 or L_m <= 0: return 0.0
    v = v_kmh / 3.6
    fixed_physical_gain = 0.050
    return fixed_physical_gain * (1.0 / math.sqrt(2.0)) * h_m * (v * math.pi / L_m)**2

def classify_rms(rms_value):
    if rms_value < 0.315: return "Very Comfortable"
    if rms_value < 0.5: return "Comfortable"
    if rms_value < 0.8: return "Normal"
    if rms_value < 1.25: return "Uncomfortable"
    return "Very Uncomfortable"

def run_evaluate_node(control_to_eval_queue, eval_to_control_queue):
    pythoncom.CoInitialize()
    
    while True:
        try:
            data = control_to_eval_queue.get()
            
            if data.get("msg") != "evaluate_request":
                continue

            current_speed = data.get('current_speed')
            target_speed = data.get('target_speed')
            prediction_RMS = data.get('prediction_RMS')
            GT_Height = data.get('GT_Height')
            GT_Depth = data.get('GT_Depth')
            current_pR_Calibration = data.get('current_pR_Calibration')
            current_PWM_Calibration = data.get('current_PWM_Calibration')

            actual_RMS = compute_rms(current_speed, GT_Height, GT_Depth)
            comfort_level = classify_rms(actual_RMS)
            
            result_log = (f"cS:{current_speed:.1f} | aR:{actual_RMS:.2f} "
                          f"(GT_H:{GT_Height*100:.1f}cm, GT_Dp:{GT_Depth:.2f}m) | Comfort: {comfort_level}")
            print_at('EVALUATE_RESULT', f"[Evaluate] {result_log}")

            er_error = (abs(prediction_RMS - actual_RMS) / prediction_RMS) * 100 if prediction_RMS > 0.01 else 0
            ts_error = (abs(target_speed - current_speed) / target_speed) * 100 if target_speed > 0.01 else 0
            accuracy_log = f"pR<>aR Error: {er_error:.1f}% | tS<>cS Error: {ts_error:.1f}%"
            print_at('EVALUATE_ACCURACY', f"[Evaluate] {accuracy_log}")

            target_gain = current_pR_Calibration * (actual_RMS / prediction_RMS) if prediction_RMS > 0.01 else current_pR_Calibration
            target_pwm_weight = current_PWM_Calibration * (current_speed / target_speed) if target_speed > 0.01 else current_PWM_Calibration

            alpha_pr = config.LEARNING_RATE_PR_CALIBRATION
            updated_pR_Calibration = (current_pR_Calibration * (1 - alpha_pr)) + (target_gain * alpha_pr)

            alpha_pwm = config.LEARNING_RATE_PWM_CALIBRATION
            updated_PWM_Calibration = (current_PWM_Calibration * (1 - alpha_pwm)) + (target_pwm_weight * alpha_pwm)

            response_data = {
                "msg": "final_correction_factors",
                "updated_pR_Calibration": updated_pR_Calibration,
                "updated_PWM_Calibration": updated_PWM_Calibration,
                "result_log": result_log,
                "accuracy_log": accuracy_log
            }
            eval_to_control_queue.put(response_data)

        except queue.Empty:
            continue
        except Exception:
            time.sleep(1)

    pythoncom.CoUninitialize()
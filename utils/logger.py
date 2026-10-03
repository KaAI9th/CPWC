# logger.py
import os
import sys
import datetime

if sys.platform == "win32":
    os.system("")

LINE_KEYS = {
    'INFO_SOURCE': 1,
    'CONTROL_RECV': 2,
    'CONTROL_PLAN': 3,
    'CONTROL_STATE': 4,
    'EVALUATE_RESULT': 5,
    'EVALUATE_ACCURACY': 6,
    'CONTROL_CORRECTION': 7,
    'DEBUG_DISTANCE': 9
}
CURSOR_SAVE = "\033[s"
CURSOR_RESTORE = "\033[u"
CLEAR_LINE = "\033[K"

def setup_logging_area():
    os.system('cls' if os.name == 'nt' else 'clear')
    sys.stdout.write("\n" * (len(LINE_KEYS) + 2))
    sys.stdout.flush()

def print_at(line_key, message):
    line = LINE_KEYS.get(line_key.upper())
    if line is None:
        return

    sys.stdout.write(CURSOR_SAVE)
    sys.stdout.write(f"\033[{line};0H")
    sys.stdout.write(CLEAR_LINE)
    sys.stdout.write(message)
    sys.stdout.write(CURSOR_RESTORE)
    sys.stdout.flush()

def log_sequence_to_file(log_data):
    try:
        with open("config/log.txt", "a", encoding="utf-8") as f:
            f.write("="*80 + "\n")
            f.write(f"Sequence Record Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("-"*80 + "\n")
            f.write(f"[DETECT]: {log_data.get('DETECT', '')}\n")
            f.write(f"[PLAN]: {log_data.get('PLAN', '')}\n")
            f.write(f"[RESULT]: {log_data.get('RESULT', '')}\n")
            f.write(f"[EVAL_ACCURACY]: {log_data.get('CORRECTION', '')}\n")
            f.write(f"[COLLISION]: {log_data.get('COLLISION', '')}\n")
            f.write("="*80 + "\n\n")
    except Exception:
        pass
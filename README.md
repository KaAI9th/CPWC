# Speed Bump Response System for Autonomous Driving
**Team:** AutoBump
**Project ID:** CPWC2025-0039

---

## Overview 📜
This project is a "Speed Bump Response System for Autonomous Driving." The system is designed to enable an autonomous vehicle to recognize and react to various types of speed bumps using sensor data and simulator-provided Ground Truth information, eliminating the need for pre-existing HD Maps.

It is a comprehensive response system that not only ensures ride comfort through smooth deceleration but also enhances driving efficiency by avoiding unnecessary braking. The core of the system is a **Self-Learning Loop** consisting of Perception -> Classification -> Control -> Evaluation -> Calibration. This loop allows the system to adapt to changing road conditions and optimize its performance over time as it gains more driving experience. 

---

## System Requirements 💻

### Hardware Requirements
* **CPU:** Intel Core i7 / AMD Ryzen 7 (10th Gen or newer)
* **RAM:** 32GB
* **GPU:** NVIDIA GeForce RTX 3060 or higher (VRAM 8GB+) 
* **Storage:** 50GB+ free space (SSD recommended) 

### Software Requirements
* **Operating System:** Windows 10/11 (64-bit) 
* **Simulator:** UC-win/Road Version 17.2.0 (32-bit)
* **Language:** Python 3.8.x (A **32-bit version is required** for API integration)
* **Libraries:** `numpy`

---

## Installation and Execution Guide 🚀

### Step 1: Prerequisites
1.  **Install UC-win/Road & Python:** Install UC-win/Road Version 17.2.0 and Python 3.8.x (32-bit). Please refer to the official UC-win/Road documentation to enable the Python API plugin. 
    > **⚠️ Important:** The bit version of your Python installation must match the bit version of your UC-win/Road installation for the API to function correctly.
2.  **Download the Project:** Clone the project repository from GitHub. (https://github.com/5suk/CPWC.git)
    ```bash
    git clone https://github.com/5suk/CPWC.git
    ```

### Step 2: Install Required Libraries
Navigate to the project directory and install the necessary Python libraries. 
```bash
pip install numpy
```
### Step 3: Vehicle Braking Calibration

Before running the main system, you must perform a one-time calibration to determine the vehicle's unique braking characteristics. This process generates a `speed_map.json` file that is essential for calculating the optimal braking force.

1.  Launch UC-win/Road by opening the `Autobump.rb` project file. Once loaded, press the **F10** key to hide the menu for a smoother experience.
2.  Set the initial driving speed within the UC-win/Road scenario to your desired test speed.
3.  Run the calibration script from your terminal.
    ```bash
    python utils/calibaration.py
    ```
4.  When prompted in the terminal, enter the test speed. For more detailed and accurate data, it is recommended to test a range of speeds. A good approach is to test speeds from **55 km/h to 80 km/h in 5 km/h increments**.
5.  The vehicle will automatically begin to decelerate when it detects a speed bump. When the vehicle **collides with the bump**, press the **`c`** key to signal the impact to the system. If you miss the timing or if the deceleration is incorrect, press **`b`** to discard the result for that run and try again.
6.  Repeat this process for all desired speeds. The system requires **three successful impacts** (three `c` presses) for each speed you test. The results are automatically saved and accumulated in the `speed_map.json` file.

### Step 4: Run the Main System
Once calibration is complete, you can run the main autonomous driving system.

1.  Launch UC-win/Road by opening the `Autobump.rb` project file. Once loaded, press the **F10** key to hide the menu for a smoother experience.
> **⚠️ Important:** You must verify that the <test> and <top> views are correctly displayed on the screen.
2.  Execute the `main.py` script from the terminal.
    ```bash
    python main.py
    ```

### Step 5: Verifying Logs
You can monitor the system's real-time performance and review results by checking the log file located at `config/log.txt`.
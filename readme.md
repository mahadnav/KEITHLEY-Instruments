# KEITHLEY-Instruments

A Python-based instrument control suite for Keithley measurement devices.  
This repository contains modules and scripts for interacting with Keithley instruments (e.g., Nanovoltmeter 2182, Picoammeter 6485 interfaced with Cureent Source 6221) via SCPI/pyVISA, logging data, and automating measurement workflows.

## 📂 Repository Structure

```
KEITHLEY-Instruments/
├── Nanovoltmeter/              # Code and executables for Nanovoltmeter
│   ├── src/
│   │   └── Nanovoltmeter_controller.py
│   └── dist/                   # Compiled Executables
├── Picoammeter/                # Code and executables for Picoammeter
│   ├── src/
│   │   └── pico_controller.py
│   └── dist/                   # Compiled Executables
├── requirements x32.txt # 32-bit env requirements
├── requirements x64.txt # 64-bit env requirements
```

## ✅ Features

- Connect to Keithley instruments using pyVISA over GPIB cable  
- Configure ranges, integration times, averaging, etc.  
- Acquire and log measurement data with timestamps  
- Instrument interfacing using user-friendly applications  
- 32-bit and 64-bit requirements provided  

## 🎯 Getting Started

### Prerequisites

- NI-VISA or another VISA backend
    - Link to install 64-bit drivers: https://www.tek.com/en/support/software/driver/9-2-0
- A Keithley instrument connected via GPIB  

### Installation

```bash
git clone https://github.com/mahadnav/KEITHLEY-Instruments.git
```

### Usage

   - Open the folder for your instrument type (Nanovoltmeter/ or Picoammeter/).

   - Make sure the VISA address in the script matches your instrument's address (e.g., "GPIB0::15::INSTR").

   - Run the executable application: 

        - Picoammeter
            - pico_controller x32.exe
            - pico_controller x64.exe

        - Nanovoltmeter
            - Nanovoltmeter_controller x32.exe
            - Nanovoltmeter_controller x64.exe

### Run via Python terminal

If you wish to modify the code or run it directly via Python, please use the recommended version for your architecture:

**Step 1: Install Python**

- **64-bit Systems:** Python 3.11.9 (Recommended)
- **32-bit Systems:** Python 3.11.4

**Step 2: Create a Virtual Environment**

Open your terminal/command prompt in the KEITHLEY-Instruments folder and run:

For 32-bit
```bash
python -m venv kiethley-x32
```

For 64-bit
```bash
python -m venv kiethley-x64
```
This will setup the virtual envrionment.

**Step 3: Activate the Environment**

Windows:

```keithley-XX\Scripts\activate```


(You should see (keithley-XX) appear at the start of your terminal line)


**Step 4: Install dependencies**

**For 64-bit Python**
```bash
pip install -r "requirements x64.txt"
```
**For 32-bit Python**
```bash
pip install -r "requirements x32.txt"
```

**Step 5: Run the Controller**

**For Picoammeter**

```bash
python Picoammeter/src/pico_controller.py ### for 64-bit python
```

**For Nanovoltmeter**
```bash
python Nanovoltmeter/src/Nanovoltmeter_controller.py
```

### Re-building the Executable

If you have modified the code and want to generate a new .exe file, use the included source files.

First, create a virtual envrionment explained in the section above, and install the required libraires in the ```requirements xYY.txt``` file (accoridng to your system).

Ensure pyinstaller is installed. 

Run ```PyInstaller``` pointing to the specific controller file:

```bash
# For Nanovoltmeter
cd Nanovoltmeter
pyinstaller --onefile --name "Nanovoltmeter_Controller x32" "src/Nanovoltmeter_controller.py" ### 32-bit env
pyinstaller --onefile --name "Nanovoltmeter_Controller x64" "src/Nanovoltmeter_controller.py" ### 64-bit env

# For Picoammeter
cd Picoammeter
pyinstaller --onefile --name "pico_controller x32" "src/pico_controller.py" ### 32-bit env
pyinstaller --onefile --name "pico_controller x64" "src/pico_controller.py" ### 64-bit env
```

The new executable will appear in the local ```dist/``` folder.


### Technical Team

- Developer: Mahad Naveed
- Supervisor: Dr. Sabieh Anwar
- Supported by: Hammad Gardezi

This is a project of PHYSLAB at the Physics Department of tht School of Science and Engineering, LUMS.
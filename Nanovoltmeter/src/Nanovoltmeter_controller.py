import sys
import threading
import time
from datetime import datetime

import pyvisa
import numpy as np
import pandas as pd

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QHBoxLayout,
    QFileDialog, QLabel, QLineEdit, QMessageBox, QGroupBox,
    QGridLayout, QStatusBar, QSpinBox, QDoubleSpinBox, QCheckBox
)
from PyQt5.QtGui import QFont, QPalette, QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# ---------------- Worker signals ----------------
class WorkerSignals(QObject):
    new_point = pyqtSignal(float, float, float)
    status = pyqtSignal(str)
    done = pyqtSignal()

# ---------------- Main app ----------------
class KeithleyDeltaApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keithley 6221/2182A Interface - Delta Mode Only")
        self.resize(1400, 700)

        # ----- Configuration defaults -----
        self.GPIB_ADDRESS = "GPIB0::15::INSTR"  # Change if needed
        self.REFRESH_INTERVAL = 0.1             
        self.NPLC = 1.0
        
        # ----- Instrument handles -----
        self.rm = None
        self.k6221 = None

        # ----- State -----
        self.running = False
        self.exiting = False 
        self.lock = threading.Lock()
        self.start_time = None
        self.times = []
        self.voltages = []
        self.currents = []

        # ----- signals -----
        self.signals = WorkerSignals()
        self.signals.new_point.connect(self.handle_new_point)
        self.signals.status.connect(self.set_status)
        self.signals.done.connect(self.run_done)

        # ----- UI -----
        self.init_ui()

        # ----- Connect instruments -----
        try:
            self.connect_instruments()
            self.set_status("Connected to 6221 (bridge to 2182A). Ready for Delta Mode.")
        except Exception as e:
            QMessageBox.critical(self, "Connection error", f"Failed to open 6221 resource: {e}")

        # ----- Worker thread -----
        self.worker = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker.start()

    # ---------------- UI building ----------------
    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # --- Plot Area ---
        self.fig = Figure(figsize=(8, 6))
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Delta Mode Measurement")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)", color="tab:blue")
        self.ax.tick_params(axis='y', labelcolor="tab:blue")
        
        self.line_v, = self.ax.plot([], [], "o-", color="tab:blue", label="Voltage (V)")
        
        # Create Twin Axis for Current
        self.ax2 = self.ax.twinx()
        self.ax2.set_ylabel("Current (A)", color="tab:red")
        self.ax2.yaxis.set_label_position("right") 
        self.ax2.yaxis.tick_right()                
        self.ax2.tick_params(axis='y', labelcolor="tab:red")
        
        self.line_i, = self.ax2.plot([], [], "s-", color="tab:red", label="Current (A)", alpha=0.4)
        
        self.fig.tight_layout()
        main_layout.addWidget(self.canvas, 3)

        # --- Control Panel ---
        panel = QGroupBox("Delta Configuration")
        panel.setMinimumWidth(320)
        palette = panel.palette()
        palette.setColor(QPalette.Window, QColor("#F6F6F6"))
        panel.setAutoFillBackground(True)
        panel.setPalette(palette)
        pl = QGridLayout()
        pl.setContentsMargins(12, 12, 12, 12)
        panel.setLayout(pl)
        main_layout.addWidget(panel, 1)

        font_btn = QFont("Segoe UI", 10, QFont.Bold)

        # 1. Common Settings
        pl.addWidget(QLabel("<b>Settings</b>"), 0, 0, 1, 2)
        
        pl.addWidget(QLabel("NPLC (2182A):"), 1, 0)
        self.nplc_spin = QDoubleSpinBox()
        self.nplc_spin.setDecimals(2)
        self.nplc_spin.setSingleStep(0.1)
        self.nplc_spin.setValue(self.NPLC)
        pl.addWidget(self.nplc_spin, 1, 1)

        # --- Checkbox to toggle Current Plot ---
        self.chk_show_current = QCheckBox("Show Current Trace")
        self.chk_show_current.setChecked(False)
        self.chk_show_current.toggled.connect(self.toggle_current_view)
        pl.addWidget(self.chk_show_current, 2, 0, 1, 2)

        # 2. Delta Parameters
        pl.addWidget(QLabel("<b>Delta Parameters</b>"), 3, 0, 1, 2)
        
        pl.addWidget(QLabel("Delta Current (A):"), 4, 0)
        self.delta_I = QDoubleSpinBox()
        self.delta_I.setDecimals(9)
        self.delta_I.setSingleStep(1e-6)
        self.delta_I.setValue(100e-6) 
        pl.addWidget(self.delta_I, 4, 1)

        pl.addWidget(QLabel("Count (pairs):"), 5, 0)
        self.delta_count = QSpinBox()
        self.delta_count.setMinimum(1)
        self.delta_count.setMaximum(65000)
        self.delta_count.setValue(20)
        pl.addWidget(self.delta_count, 5, 1)

        pl.addWidget(QLabel("Delay (s):"), 6, 0)
        self.delta_delay = QDoubleSpinBox()
        self.delta_delay.setDecimals(3)
        self.delta_delay.setValue(0.1)
        pl.addWidget(self.delta_delay, 6, 1)

        # 3. Action Buttons
        self.btn_start = QPushButton("▶ Start Delta")
        self.btn_start.setFont(font_btn)
        self.btn_start.setStyleSheet("background-color: #d4f7d4")
        
        self.btn_clear = QPushButton("Clear Plot")
        self.btn_clear.setFont(font_btn)
        
        self.btn_save = QPushButton("💾 Save CSV")
        self.btn_save.setFont(font_btn)
        
        self.btn_quit = QPushButton("Quit")
        self.btn_quit.setFont(font_btn)
        self.btn_quit.setStyleSheet("background-color: #f7d4d4")

        pl.addWidget(self.btn_start, 7, 0, 1, 2)
        pl.addWidget(self.btn_clear, 8, 0)
        pl.addWidget(self.btn_save, 8, 1)
        pl.addWidget(self.btn_quit, 9, 0, 1, 2)

        # 4. File settings
        pl.addWidget(QLabel("Default Filename:"), 10, 0)
        self.filename = QLineEdit("delta_data.csv")
        pl.addWidget(self.filename, 10, 1)

        pl.setRowStretch(11, 1) # Spacer

        # Signals
        self.btn_start.clicked.connect(self.start_clicked)
        self.btn_clear.clicked.connect(self.clear_clicked)
        self.btn_save.clicked.connect(self.save_clicked)
        self.btn_quit.clicked.connect(self.close)

        # Status Bar
        self.status = QStatusBar()
        outer = QVBoxLayout()
        outer.addLayout(main_layout)
        outer.addWidget(self.status)
        self.setLayout(outer)

    # ---------------- Toggle View Logic ----------------
    def toggle_current_view(self, checked):
        """Hides or shows the secondary Y-axis and the current line."""
        self.line_i.set_visible(checked)
        self.ax2.get_yaxis().set_visible(checked)
        
        # Also hide the legend entry for current if hidden
        if not checked:
            self.ax2.set_ylabel("") 
        else:
            self.ax2.set_ylabel("Current (A)", color="tab:red")
            self.ax2.yaxis.set_label_position("right")
            
        self.canvas.draw()

    # ---------------- Instrument connection ----------------
    def connect_instruments(self):
        self.rm = pyvisa.ResourceManager()
        self.k6221 = self.rm.open_resource(self.GPIB_ADDRESS)
        self.k6221.timeout = 10000 # 10s timeout
        
        # Reset 6221
        self.k6221.write("*RST")
        time.sleep(0.1)
        idn = self.k6221.query("*IDN?").strip()
        self.signals.status.emit(f"Connected: {idn}")
        
        # Send RST to 2182A via serial relay
        self._relay_send('*RST')
        time.sleep(0.5)

    def _relay_send(self, cmd):
        """Helper to send command to 2182A via 6221 Serial Bridge"""
        try:
            self.k6221.write(f'SYST:COMM:SER:SEND "{cmd}"')
            time.sleep(0.02)
        except Exception as e:
            self.signals.status.emit(f"Relay send failed: {e}")

    # ---------------- Button Handlers ----------------
    def start_clicked(self):
        if self.running:
            return
        with self.lock:
            if not self.running:
                # Starting fresh
                self.times = []
                self.voltages = []
                self.currents = []
                # Set start_time when INIT happens to avoid plotting setup time
                self.start_time = None 
            
            self.running = True
            self.NPLC = float(self.nplc_spin.value())
            
            self.btn_start.setEnabled(False)
            self.set_status("Starting Delta sequence...")

    def clear_clicked(self):
        with self.lock:
            self.running = False
            self.times.clear()
            self.voltages.clear()
            self.currents.clear()
            self.start_time = None

        # Clear Axes
        self.ax.clear()
        self.ax2.clear()
        
        self.ax.set_title("Delta Mode Measurement")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)", color="tab:blue")
        self.ax.tick_params(axis='y', labelcolor="tab:blue")
        self.line_v, = self.ax.plot([], [], "o-", color="tab:blue", label="Voltage (V)")
        
        self.ax2.set_ylabel("Current (A)", color="tab:red")
        self.ax2.yaxis.set_label_position("right") # FIX
        self.ax2.yaxis.tick_right()                # FIX
        self.ax2.tick_params(axis='y', labelcolor="tab:red")
        self.line_i, = self.ax2.plot([], [], "s-", color="tab:red", label="Current (A)", alpha=0.4)
        
        # Respect the checkbox state after clearing
        is_checked = self.chk_show_current.isChecked()
        self.line_i.set_visible(is_checked)
        self.ax2.get_yaxis().set_visible(is_checked)
        if not is_checked:
            self.ax2.set_ylabel("")

        self.canvas.draw()

        self.btn_start.setEnabled(True)
        self.set_status("Data cleared.")

    def save_clicked(self):
        default_fname = self.filename.text().strip()
        if not default_fname:
            default_fname = f"delta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        fname, _ = QFileDialog.getSaveFileName(self, "Save Data", default_fname, "CSV Files (*.csv)")
        
        if not fname:
            return
        
        try:
            df = pd.DataFrame({"Time (s)": self.times, "Voltage (V)": self.voltages, "Current (A)": self.currents})
            df.to_csv(fname, index=False)
            self.set_status(f"Saved to {fname}")
            QMessageBox.information(self, "Saved", f"Data saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save data: {e}")

    # ---------------- Data Handling ----------------
    def handle_new_point(self, elapsed, voltage, current):
        self.times.append(elapsed)
        self.voltages.append(voltage)
        self.currents.append(current)

        t = np.array(self.times)
        v = np.array(self.voltages)
        c = np.array(self.currents)
        
        # Filter for plotting
        v_finite = v[np.isfinite(v)]
        c_finite = c[np.isfinite(c)]
        
        show_current = self.chk_show_current.isChecked()

        self.line_v.set_data(t, v)
        self.line_i.set_data(t, c)
        
        if len(t) > 0:
            t_max = t[-1]
            # Force X-axis to start at 0
            self.ax.set_xlim(0, max(0.1, t_max * 1.05))
            
            # Scale Voltage Axis (Left)
            if len(v_finite) > 0:
                v_min, v_max = v_finite.min(), v_finite.max()
                vpad = max(1e-9, 0.1 * (v_max - v_min)) if (v_max - v_min) > 0 else 1e-9
                self.ax.set_ylim(v_min - vpad, v_max + vpad)
            else:
                self.ax.set_ylim(-1, 1)
            
            # Scale Current Axis (Right) ONLY if visible
            if show_current:
                if len(c_finite) > 0:
                    c_min, c_max = c_finite.min(), c_finite.max()
                    cpad = max(1e-12, 0.1 * (c_max - c_min)) if (c_max - c_min) > 0 else 1e-12
                    self.ax2.set_ylim(c_min - cpad, c_max + cpad)
                else:
                    self.ax2.set_ylim(-1e-6, 1e-6)

        self.canvas.draw()
        self.set_status(f"V={voltage:.4e} V  I={current:.4e} A")

    def run_done(self):
        self.set_status("Delta Sequence Complete.")
        with self.lock:
            self.running = False
            self.btn_start.setEnabled(True)

    # ---------------- Worker Logic ----------------
    def worker_loop(self):
        """Main background loop. Only runs Delta Mode logic."""
        while not self.exiting:
            time.sleep(0.05)
            
            # Check if we should run
            with self.lock:
                should_run = self.running
            
            if not should_run:
                continue

            # If running, execute the Delta logic
            self._run_delta_mode()
            
            # Once finished (buffer full or error), signal done
            self.signals.done.emit()

    def _run_delta_mode(self):
        """
        Configure Delta Mode, run it, and stream buffer data to GUI.
        """
        I = float(self.delta_I.value())
        count_pairs = int(self.delta_count.value())
        delay = float(self.delta_delay.value())
        nplc = float(self.nplc_spin.value())
        
        expected = count_pairs

        self.signals.status.emit("Configuring Delta Mode on 6221/2182A...")
        
        try:
            # 1. Reset 6221
            self.k6221.write("*RST")
            time.sleep(0.5)
            
            # 2. Reset 2182A
            self._relay_send("*RST")
            time.sleep(1.5)

            # 3. Verify 2182A link
            try:
                nvpr = int(self.k6221.query("SOUR:DELT:NVPR?").strip())
                if nvpr != 1:
                    raise Exception("NVPR!=1")
            except Exception:
                raise ConnectionError("2182A not detected. Check RS-232 cable.")

            self.signals.status.emit("Instruments synced. Sending parameters...")

            # 4. Configure 2182A
            self._relay_send("SENS:FUNC 'VOLT'")
            self._relay_send(f"SENS:VOLT:NPLC {nplc}")
            self._relay_send("TRIG:SOUR EXT")
            self._relay_send("TRIG:COUNT INF")
            time.sleep(0.5)

            # 5. Configure 6221 Delta
            self.k6221.write(f"SOUR:DELT:HIGH {I}")
            self.k6221.write(f"SOUR:DELT:LOW {-I}")
            self.k6221.write(f"SOUR:DELT:DEL {delay}")
            self.k6221.write(f"SOUR:DELT:COUN {expected}")
            self.k6221.write("SOUR:DELT:CAB ON")
            self.k6221.write(f"TRAC:POIN {expected}")
            self.k6221.write("FORM:ELEM READ")
            
            # Arm
            self.k6221.write("SOUR:DELT:ARM")
            time.sleep(2) 
            
        except Exception as e:
            self.signals.status.emit(f"Setup Error: {e}")
            return

        # Start
        self.signals.status.emit("Running Delta...")
        try:
            self.k6221.write("INIT:IMM")
            
            # Lock the start time, right after we tell it to start. 
            with self.lock:
                self.start_time = time.time()

            last_len = 0
            
            # Poll Loop
            while True:
                # Read buffer
                try:
                    raw = self.k6221.query("TRAC:DATA?").strip()
                    if raw:
                        vals = [float(x) for x in raw.split(",") if x.strip()]
                    else:
                        vals = []
                except Exception:
                    vals = []

                # Stream new points
                if len(vals) > last_len:
                    now = time.time()
                    with self.lock:
                        base = self.start_time
                    if base is None: base = now 

                    for i in range(last_len, len(vals)):
                        elapsed = max(0.0, (now - base)) 
                        # Even index = High, Odd index = Low (approx)
                        cur = I if (i % 2 == 0) else -I
                        self.signals.new_point.emit(elapsed, vals[i], cur)
                    last_len = len(vals)

                # Completion check
                if len(vals) >= expected:
                    self.signals.status.emit("Buffer full. Finishing...")
                    try:
                        self.k6221.write("*RST")
                    except:
                        pass
                    return 

                time.sleep(self.REFRESH_INTERVAL)
        
        except Exception as e:
            self.signals.status.emit(f"Runtime Error: {e}")

    def set_status(self, text):
        self.status.showMessage(text)

    def closeEvent(self, event):
        # Clean Shutdown
        with self.lock:
            self.running = False
        self.exiting = True
        
        # Wait for worker
        if self.worker.is_alive():
            self.worker.join(timeout=1.0)
        
        # Reset Instruments
        try:
            if self.k6221:
                self.k6221.write("OUTP OFF")
                self.k6221.write("*RST")
                self.k6221.close()
            if self.rm:
                self.rm.close()
        except:
            pass
        
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = KeithleyDeltaApp()
    w.show()
    sys.exit(app.exec_())
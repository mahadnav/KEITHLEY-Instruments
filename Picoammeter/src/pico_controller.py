import sys
import threading
import time
import os
import pyvisa
import pandas as pd
from datetime import datetime

from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QHBoxLayout,
    QFileDialog, QLabel, QLineEdit, QMessageBox, QGroupBox,
    QGridLayout, QStatusBar
)
from PyQt5.QtGui import QFont, QPalette, QColor
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


class WorkerSignals(QObject):
    new_data = pyqtSignal(float, float)
    status = pyqtSignal(str)


class KeithleyApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keithley 6485 Picoammeter Control Panel")
        self.resize(1400, 700)

        # VISA setup
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource("GPIB0::14::INSTR")
        print("Connected to:", self.inst.query("*IDN?").strip())
        self.inst.timeout = 10000
        self.setup_instrument()

        # Data
        self.readings = []
        self.timestamps = []
        self.running = False
        self.paused = False
        
        self.total_run_time = 0.0
        self.last_resume_time = None
        self.lock = threading.Lock()

        # Worker signals
        self.signals = WorkerSignals()
        self.signals.new_data.connect(self.handle_new_data)
        self.signals.status.connect(self.update_status)

        self.init_ui()

        # Thread for data acquisition
        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

    def setup_instrument(self):
        self.inst.write("*RST")
        self.inst.write("*CLS")
        time.sleep(0.3)
        self.inst.write("FUNC 'CURR:DC'")
        self.inst.write("CONF:CURR")
        self.inst.write("SENS:CURR:RANG:AUTO ON")
        self.inst.write("SENS:CURR:NPLC 3")
        self.inst.write("SENS:AVER:STAT ON")
        self.inst.write("SENS:AVER:COUN 5")
        self.inst.write("SENS:AVER:TCON REP")
        self.inst.write("TRIG:SOUR IMM")
        self.inst.write("TRIG:COUN 1")

    def init_ui(self):
        main_layout = QHBoxLayout(self)

        # Plot area
        self.fig = Figure()
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("Current vs Time")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Current (A)")
        main_layout.addWidget(self.canvas, 3)

        # Controls group box
        controls_box = QGroupBox("Controls")
        controls_box.setMinimumWidth(300)

        palette = controls_box.palette()
        palette.setColor(QPalette.Window, QColor("#D3D3D3"))
        controls_box.setAutoFillBackground(True)
        controls_box.setPalette(palette)

        controls_layout = QGridLayout()
        controls_layout.setContentsMargins(20, 20, 20, 20)
        controls_layout.setHorizontalSpacing(20)
        controls_layout.setVerticalSpacing(15)
        controls_box.setLayout(controls_layout)
        main_layout.addWidget(controls_box, 1)

        font_button = QFont("Segoe UI", 14, QFont.Bold)

        self.btn_play = QPushButton("▶ Play")
        self.style_button(self.btn_play, font_button, bg_color="#89A88A")

        self.btn_pause = QPushButton("⏸ Pause")
        self.style_button(self.btn_pause, font_button, bg_color="#CAB063")
        self.btn_pause.setEnabled(False)

        self.btn_clear = QPushButton("🧹 Clear")
        self.style_button(self.btn_clear, font_button, bg_color="#AA4E47")

        self.btn_save = QPushButton("💾 Save CSV")
        self.style_button(self.btn_save, font_button, bg_color="#558AB6")

        self.btn_quit = QPushButton("❌ Quit")
        self.style_button(self.btn_quit, font_button, bg_color="#FFFFFF", fg_color="#000000")

        filename_label = QLabel("Filename:")
        filename_label.setFont(QFont("Segoe UI", 12))
        self.filename_input = QLineEdit("readings.csv")
        self.filename_input.setFont(QFont("Segoe UI", 12))
        self.filename_input.setMinimumHeight(35)

        self.btn_browse = QPushButton("Browse...")
        self.style_button(self.btn_browse, font_button, bg_color="#607D8B")

        self.btn_play.clicked.connect(self.play_reading)
        self.btn_pause.clicked.connect(self.pause_reading)
        self.btn_clear.clicked.connect(self.clear_data)
        self.btn_save.clicked.connect(self.save_data)
        self.btn_quit.clicked.connect(self.close)
        self.btn_browse.clicked.connect(self.browse_file)

        controls_layout.addWidget(self.btn_play, 0, 0)
        controls_layout.addWidget(self.btn_pause, 0, 1)
        controls_layout.addWidget(self.btn_clear, 1, 0)
        controls_layout.addWidget(self.btn_save, 1, 1)
        controls_layout.addWidget(filename_label, 2, 0)
        controls_layout.addWidget(self.filename_input, 2, 1)
        controls_layout.addWidget(self.btn_browse, 3, 0, 1, 2)
        controls_layout.addWidget(self.btn_quit, 4, 0, 1, 2)

        self.status_bar = QStatusBar()
        layout_with_status = QVBoxLayout()
        layout_with_status.addLayout(main_layout)
        layout_with_status.addWidget(self.status_bar)
        self.setLayout(layout_with_status)

        self.update_status("Ready")

    def style_button(self, button, font, bg_color="#E0E0E0", fg_color="#FFFFFF"):
        button.setFont(font)
        button.setMinimumHeight(50)
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                border: none;
                border-radius: 12px;
                color: {fg_color};
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: #555555;
            }}
            QPushButton:pressed {{
                background-color: #222222;
            }}
            QPushButton:disabled {{
                background-color: #BDBDBD;
                color: #757575;
            }}
        """)

    def update_status(self, message):
        self.status_bar.showMessage(message)

    def browse_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Select file to save CSV",
            self.filename_input.text(),
            "CSV Files (*.csv);;All Files (*)",
            options=options
        )
        if filename:
            self.filename_input.setText(filename)


    def play_reading(self):
        with self.lock:
            if self.running and not self.paused:
                self.update_status("Already running.")
                return

            if not self.running and not self.paused:
                self.setup_instrument()

            self.running = True
            self.paused = False
            self.last_resume_time = time.time()

        self.btn_play.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.signals.status.emit("Measurement started or resumed.")


    def pause_reading(self):
        with self.lock:
            if not self.running or self.paused:
                self.update_status("Not running or already paused.")
                return

            self.paused = True
            run_duration = time.time() - self.last_resume_time
            self.total_run_time += run_duration
        
        self.btn_pause.setEnabled(False)
        self.btn_play.setEnabled(True)
        self.signals.status.emit("Measurement paused.")

    def clear_data(self):
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all data? This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.readings.clear()
            self.timestamps.clear()
            self.ax.clear()
            self.ax.set_title("Current vs Time")
            self.ax.set_xlabel("Time (s)")
            self.ax.set_ylabel("Current (A)")
            self.canvas.draw()

            self.running = False
            self.paused = False
            
            self.total_run_time = 0.0
            self.last_resume_time = None

            self.btn_play.setEnabled(True)
            self.btn_pause.setEnabled(False)

            self.update_status("Data cleared.")
            QMessageBox.information(self, "Cleared", "Data cleared.")

    def save_data(self):
        filename = self.filename_input.text().strip()
        if not filename:
            self.update_status("Please enter a filename.")
            return

        if os.path.exists(filename):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime("%Y-%m-%d_at_%H:%M:%S")
            filename = f"{base}_{timestamp}{ext}"

        df = pd.DataFrame({
            "Time": self.timestamps,
            "current_A": self.readings
        })
        df.to_csv(filename, index=False)
        self.update_status(f"Data saved to {filename}")
        QMessageBox.information(self, "Saved", "Data saved.")

    def handle_new_data(self, elapsed, reading):
        self.timestamps.append(elapsed)
        self.readings.append(reading)
        self.update_plot()
        self.update_status(f"Reading: {reading:.3e} A @ {elapsed:.1f} s")

    def update_plot(self):
        self.ax.clear()
        self.ax.plot(self.timestamps, self.readings, marker='o', linestyle='-')
        self.ax.set_title("Current vs Time")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Current (A)")
        self.canvas.draw()

    def update_loop(self):
        while True:
            is_running = False
            is_paused = True
            
            with self.lock:
                is_running = self.running
                is_paused = self.paused
                if is_running and not is_paused:
                    total_time = self.total_run_time
                    resume_time = self.last_resume_time

            if is_running and not is_paused:
                try:
                    # Perform slow I/O operations OUTSIDE the lock
                    val_str = self.inst.query("READ?").strip().split(",")[0]
                    val = float(val_str.replace("A", "").strip())
                    
                    now = time.time()
                    current_run_duration = now - resume_time
                    elapsed = total_time + current_run_duration

                    self.signals.new_data.emit(elapsed, val)
                    time.sleep(0.1)
                except Exception as e:
                    self.signals.status.emit(f"Error: {e}")
                    with self.lock:
                        self.running = False
                        self.paused = False
                    self.btn_play.setEnabled(True)
                    self.btn_pause.setEnabled(False)
            else:
                time.sleep(0.3)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = KeithleyApp()
    window.show()
    sys.exit(app.exec_())
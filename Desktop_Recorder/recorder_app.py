import sys
import os
import datetime
import subprocess
import threading
import configparser
import time
import cv2
import requests
import pygame
import shutil
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget,
                             QLineEdit, QPushButton, QHBoxLayout, QDialog, QFormLayout,
                             QSpinBox, QMessageBox, QMenuBar, QSlider, QComboBox,
                             QListWidget, QListWidgetItem, QAbstractItemView)
from PyQt6.QtGui import QImage, QPixmap, QFont, QAction, QIcon, QColor
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot, QTimer

# --- ฟังก์ชันจัดการไฟล์ Config ---
CONFIG_FILE = 'config.ini'
HISTORY_FOLDER = 'history_videos' # โฟลเดอร์เก็บไฟล์ย้อนหลัง
DAYS_TO_KEEP_HISTORY = 7  # เก็บไฟล์ไว้นานสุดกี่วัน (เกินกว่านี้ลบทิ้ง)

if not os.path.exists(HISTORY_FOLDER):
    os.makedirs(HISTORY_FOLDER)

def load_config():
    """
    โหลดค่าตั้งค่าจากไฟล์ config.ini
    หากไฟล์ไม่มีอยู่ หรือมีค่าไม่ครบ จะสร้าง/เพิ่มเติมค่าเริ่มต้นให้โดยอัตโนมัติ
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    config_updated = False

    # กำหนดค่าเริ่มต้นทั้งหมดที่โปรแกรมต้องการ
    default_configs = {
        'API': {
            'server_ip': '127.0.0.1'
        },
        'CAMERA': {
            'camera_index': '0',
            'resolution': '1280x720',
            'brightness': '128'
        }
    }

    # ตรวจสอบและเติมค่าที่ขาดหายไป
    for section, options in default_configs.items():
        if not config.has_section(section):
            config.add_section(section)
            config_updated = True
        for option, value in options.items():
            if not config.has_option(section, option):
                config.set(section, option, value)
                config_updated = True

    # หากมีการอัปเดตค่า ให้บันทึกไฟล์
    if config_updated:
        save_config(config)

    return config

def save_config(config):
    """บันทึกค่าลงในไฟล์ config.ini"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
        config.write(configfile)

# --- ระบบจัดการไฟล์เก่าอัตโนมัติ (Auto-Cleanup) ---
def cleanup_old_videos():
    """ลบไฟล์วิดีโอที่เก่าเกินกำหนดเพื่อประหยัดพื้นที่"""
    print("Running auto-cleanup...")
    try:
        now = time.time()
        cutoff = now - (DAYS_TO_KEEP_HISTORY * 86400) # 86400 วินาที = 1 วัน
        
        count = 0
        for filename in os.listdir(HISTORY_FOLDER):
            file_path = os.path.join(HISTORY_FOLDER, filename)
            if os.path.isfile(file_path) and filename.endswith(".mp4"):
                file_mtime = os.path.getmtime(file_path)
                if file_mtime < cutoff:
                    try:
                        os.remove(file_path)
                        count += 1
                        print(f"Deleted old file: {filename}")
                    except OSError as e:
                        print(f"Error deleting {filename}: {e}")
        
        if count > 0:
            print(f"Cleanup complete: Deleted {count} old files.")
        else:
            print("Cleanup complete: No old files found.")
            
    except Exception as e:
        print(f"Error during cleanup: {e}")


# --- หน้าต่างสำหรับตั้งค่า ---
class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ตั้งค่าโปรแกรม")
        self.config = config

        # --- UI Elements ---
        self.server_ip_input = QLineEdit(self.config.get('API', 'server_ip'))
        self.camera_index_input = QSpinBox()
        self.camera_index_input.setValue(self.config.getint('CAMERA', 'camera_index'))

        self.resolution_input = QComboBox()
        self.resolution_input.addItems(['640x480', '800x600', '1280x720', '1920x1080'])
        self.resolution_input.setCurrentText(self.config.get('CAMERA', 'resolution'))

        brightness_layout = QHBoxLayout()
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 255)
        self.brightness_slider.setValue(self.config.getint('CAMERA', 'brightness'))
        self.brightness_label = QLabel(str(self.brightness_slider.value()))
        self.brightness_label.setMinimumWidth(30)
        brightness_layout.addWidget(self.brightness_slider)
        brightness_layout.addWidget(self.brightness_label)
        self.brightness_slider.valueChanged.connect(lambda v: self.brightness_label.setText(str(v)))

        save_button = QPushButton("บันทึก")
        cancel_button = QPushButton("ยกเลิก")

        # --- Layout ---
        form_layout = QFormLayout()
        form_layout.addRow("Server IP:", self.server_ip_input)
        form_layout.addRow("Camera Index:", self.camera_index_input)
        form_layout.addRow("Resolution:", self.resolution_input)
        form_layout.addRow("Brightness:", brightness_layout)

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form_layout)
        main_layout.addLayout(button_layout)

        # Signals
        save_button.clicked.connect(self.save_settings)
        cancel_button.clicked.connect(self.reject)

    def save_settings(self):
        self.config.set('API', 'server_ip', self.server_ip_input.text())
        self.config.set('CAMERA', 'camera_index', str(self.camera_index_input.value()))
        self.config.set('CAMERA', 'resolution', self.resolution_input.currentText())
        self.config.set('CAMERA', 'brightness', str(self.brightness_slider.value()))
        save_config(self.config)
        self.accept()


# --- เสียงแจ้งเตือน ---
if not os.path.exists("start.wav"): open("start.wav", "w").close()
if not os.path.exists("stop.wav"): open("stop.wav", "w").close()
if not os.path.exists("success.wav"): open("success.wav", "w").close()
if not os.path.exists("error.wav"): open("error.wav", "w").close()
SOUND_START, SOUND_STOP, SOUND_SUCCESS, SOUND_ERROR = "start.wav", "stop.wav", "success.wav", "error.wav"

pygame.mixer.init()
def play_wav_sound(sound_file):
    try:
        if os.path.getsize(sound_file) > 0:
            pygame.mixer.music.load(sound_file)
            pygame.mixer.music.play()
    except Exception as e: print(f"Could not play sound {sound_file}: {e}")


# --- Worker สำหรับสร้างและอัปโหลดวิดีโอ ---
class VideoCreationWorker(QObject):
    # เพิ่ม output_path ใน signal เพื่อส่งกลับไปที่ UI
    finished = pyqtSignal(str, bool, str, str) # message, success, tracking_no, file_path

    @pyqtSlot(str, str, list, str)
    def create_and_upload(self, numeric_order_id, tracking_no, frames, upload_api_url):
        if not frames:
            self.finished.emit("ไม่มีเฟรมภาพให้บันทึก", False, tracking_no, "")
            return

        # ตั้งชื่อไฟล์และ path
        filename = f"pack_evidence_{tracking_no}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        output_filepath = os.path.join(HISTORY_FOLDER, filename)
        
        # ใช้ path ชั่วคราวก่อน แล้วค่อยย้าย (หรือเขียนลง folder เลยก็ได้)
        # เขียนลง folder เลยเพื่อความง่าย
        
        height, width, _ = frames[-1].shape
        fps = 60
        command = ['ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}', '-r', str(fps), '-i', '-', '-an', '-vcodec', 'libx264', '-crf', '28', '-preset', 'veryfast', output_filepath]

        try:
            creationflags = 0
            if sys.platform == 'win32':
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)

            for frame in frames:
                process.stdin.write(frame.tobytes())

            out, err = process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg error: {err.decode('utf-8', errors='ignore')}")

            # อัปโหลด
            with open(output_filepath, 'rb') as f:
                files = {'file': (filename, f, 'video/mp4')}
                data = {'order_id': numeric_order_id}
                response = requests.post(upload_api_url, files=files, data=data, timeout=120)
            
            response.raise_for_status()
            self.finished.emit(f"อัปโหลดสำเร็จ: {tracking_no}", True, tracking_no, output_filepath)
            
        except Exception as e:
            # ถึงอัปโหลดไม่ผ่าน แต่ไฟล์วิดีโอยังอยู่ ให้สามารถดูได้
            self.finished.emit(f"อัปโหลดพลาด: {e}", False, tracking_no, output_filepath)


# --- Thread สำหรับอ่านวิดีโอจากกล้อง (V.3 Robust) ---
class VideoThread(QThread):
    frame_ready = pyqtSignal(object)       
    status_changed = pyqtSignal(bool, str) 

    def __init__(self, camera_index, resolution, brightness, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.resolution_str = resolution
        self.brightness = brightness
        self.running = True
        self.is_connected = False
        self.error_count = 0 

    def run(self):
        cap = None
        
        while self.running:
            # --- 1. การเชื่อมต่อ (Connection) ---
            if cap is None or not cap.isOpened():
                if self.is_connected: 
                    self.is_connected = False
                    self.status_changed.emit(False, "กล้องหลุดการเชื่อมต่อ (Camera Lost)")
                
                try:
                    temp_cap = cv2.VideoCapture(self.camera_index)
                    
                    if temp_cap.isOpened():
                        cap = temp_cap
                        try:
                            width, height = map(int, self.resolution_str.split('x'))
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                            cap.set(cv2.CAP_PROP_BRIGHTNESS, self.brightness)
                        except:
                            pass
                        
                        self.is_connected = True
                        self.error_count = 0
                        self.status_changed.emit(True, "เชื่อมต่อกล้องสำเร็จ")
                    else:
                        if not self.is_connected:
                             self.status_changed.emit(False, "กำลังค้นหากล้อง... (Searching...)")
                        time.sleep(2) 
                        continue
                except Exception as e:
                    print(f"Connect error: {e}")
                    time.sleep(2)
                    continue

            # --- 2. การอ่านภาพ (Reading) ---
            try:
                ret, frame = cap.read()
                if ret:
                    self.frame_ready.emit(frame)
                    self.error_count = 0 
                else:
                    self.error_count += 1
                    if self.error_count > 20:
                        cap.release()
                        cap = None
                        self.is_connected = False
                        self.status_changed.emit(False, "สัญญาณภาพขาดหาย (No Signal)")
                        time.sleep(1)
            except Exception as e:
                self.error_count += 1
                if self.error_count > 20:
                    if cap: cap.release()
                    cap = None
                    self.is_connected = False

        if cap and cap.isOpened():
            cap.release()

    def stop(self):
        self.running = False
        self.wait()


# --- หน้าต่างหลักของโปรแกรม ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()

        # เรียกใช้ Cleanup ทันทีที่เปิดโปรแกรม
        threading.Thread(target=cleanup_old_videos, daemon=True).start()

        server_ip = self.config.get('API', 'server_ip')
        self.scan_api_url = f"http://{server_ip}:5000/orders/api/scan_to_initiate"
        self.upload_api_url = f"http://{server_ip}:5000/orders/api/upload_pack_evidence"

        self.recorded_frames = []
        self.setWindowTitle("OMS Recorder - Fixed Double Input Lock")
        self.setGeometry(100, 100, 1100, 700) # ขยายความกว้างหน้าต่าง
        
        self.state = "READY"
        self.current_order_id = None
        self.current_numeric_id = None
        self.input_buffer = ""

        self.setup_ui()
        self.start_camera_thread()

    def setup_ui(self):
        # --- Menu Bar ---
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        
        file_menu = menu_bar.addMenu("File")
        
        reconnect_action = QAction("Force Reconnect Camera", self)
        reconnect_action.triggered.connect(self.restart_camera_thread)
        file_menu.addAction(reconnect_action)
        
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)

        open_history_action = QAction("Open Video Folder", self)
        open_history_action.triggered.connect(self.open_history_folder)
        file_menu.addAction(open_history_action)

        # --- Main Layout (Horizontal split) ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QHBoxLayout(self.central_widget)

        # === LEFT PANEL: Camera & Controls ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 5, 0) # Margin right นิดหน่อยให้ห่างจาก list

        # 1. Image Display
        self.image_label = QLabel("กำลังเริ่มต้นระบบ...", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFont(QFont('Arial', 20))
        self.image_label.setStyleSheet("background-color: #222; color: #888; border-radius: 5px; border: 2px dashed #444;")
        left_layout.addWidget(self.image_label, 1) # Stretch factor 1

        # 2. Manual Input Row
        manual_input_layout = QHBoxLayout()
        self.manual_input = QLineEdit(self)
        self.manual_input.setFont(QFont('Arial', 14))
        self.manual_input.setPlaceholderText("Scan/Type Tracking No (หรือปล่อยว่างเพื่อ Auto-ID)")
        self.manual_input.returnPressed.connect(self.handle_manual_submit)

        self.submit_button = QPushButton("ยืนยัน", self)
        self.submit_button.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        self.submit_button.clicked.connect(self.handle_manual_submit)
        # ป้องกันปุ่มขโมยโฟกัสจาก Barcode Scanner
        self.submit_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        manual_input_layout.addWidget(self.manual_input)
        manual_input_layout.addWidget(self.submit_button)
        left_layout.addLayout(manual_input_layout)

        # 3. BIG TOGGLE BUTTON
        self.toggle_button = QPushButton("เริ่มบันทึก (REC)", self)
        self.toggle_button.setFont(QFont('Arial', 16, QFont.Weight.Bold))
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setFixedHeight(60) 
        self.toggle_button.clicked.connect(self.handle_toggle_button)
        # ป้องกันปุ่มขโมยโฟกัสจาก Barcode Scanner
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.update_toggle_button_style("READY") 
        left_layout.addWidget(self.toggle_button)

        # 4. Status Label
        self.status_label = QLabel(self)
        self.status_label.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.status_label)

        # === RIGHT PANEL: History List ===
        right_panel = QWidget()
        right_panel.setFixedWidth(300) # ความกว้างคงที่สำหรับ Sidebar
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 0, 0, 0)

        history_header = QLabel("ประวัติการบันทึก (History)")
        history_header.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        history_header.setStyleSheet("color: #ddd; padding-bottom: 5px;")
        right_layout.addWidget(history_header)

        self.history_list = QListWidget()
        self.history_list.setFont(QFont('Arial', 11))
        self.history_list.setStyleSheet("""
            QListWidget {
                background-color: #333;
                color: #eee;
                border: 1px solid #555;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #444;
            }
            QListWidget::item:selected {
                background-color: #444;
            }
        """)
        self.history_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.history_list.itemDoubleClicked.connect(self.play_history_video)
        # ป้องกัน List ขโมยโฟกัส
        self.history_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        right_layout.addWidget(self.history_list)

        help_label = QLabel("Double-Click เพื่อดูวิดีโอ")
        help_label.setStyleSheet("color: #888; font-size: 11px;")
        help_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_layout.addWidget(help_label)

        # Add panels to main layout
        main_layout.addWidget(left_panel, 1) # Expandable
        main_layout.addWidget(right_panel, 0) # Fixed width

        self.update_status("พร้อมสแกน (Ready to Scan)", "#4CAF50")

    def handle_toggle_button(self):
        """จัดการเมื่อกดปุ่มใหญ่"""
        if self.state == "RECORDING":
            self.stop_recording_process()
        elif self.state == "READY":
            code = self.manual_input.text().strip()
            if not code:
                code = f"MANUAL_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # กดปุ่มก็ต้องเคลียร์และล็อคเหมือนกัน
            self.manual_input.setText(code) # เผื่อกรณี Manual
            self.handle_manual_submit()

    def update_toggle_button_style(self, state):
        if state == "RECORDING":
            self.toggle_button.setText("⏹ หยุดบันทึก (STOP)")
            self.toggle_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; border-radius: 5px; border: 2px solid #d32f2f; } QPushButton:hover { background-color: #d32f2f; }")
        else:
            self.toggle_button.setText("⏺ เริ่มบันทึก (REC)")
            self.toggle_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; border-radius: 5px; border: 2px solid #388E3C; } QPushButton:hover { background-color: #45a049; }")

    def start_camera_thread(self):
        camera_index = self.config.getint('CAMERA', 'camera_index')
        resolution = self.config.get('CAMERA', 'resolution')
        brightness = self.config.getint('CAMERA', 'brightness')
        
        self.video_thread = VideoThread(camera_index, resolution, brightness, self)
        self.video_thread.frame_ready.connect(self.process_new_frame)
        self.video_thread.status_changed.connect(self.update_camera_status)
        self.video_thread.start()

    def restart_camera_thread(self):
        if hasattr(self, 'video_thread') and self.video_thread.isRunning():
            self.video_thread.stop()
        self.start_camera_thread()
        self.image_label.setText("กำลังรีเซ็ตระบบกล้อง...")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        dialog.setStyleSheet("""
            QDialog { background-color: #2a2a2a; }
            QLabel { color: #eee; font-size: 14px; }
            QLineEdit, QSpinBox, QComboBox {
                background-color: #333;
                color: #eee;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-size: 14px;
            }
        """)
        if dialog.exec():
            QMessageBox.information(self, "บันทึกสำเร็จ", "บันทึกค่าแล้ว กล้องจะรีโหลดอัตโนมัติ")
            self.config = load_config()
            self.restart_camera_thread()

    def update_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"background-color: {color}; color: white; padding: 15px; border-radius: 5px; margin-top: 10px;")

    @pyqtSlot(bool, str)
    def update_camera_status(self, is_connected, message):
        if not is_connected:
            self.image_label.setText(message)
            self.image_label.setStyleSheet("background-color: #330000; color: #ff5555; border: 2px solid #ff0000;")
            if self.state == "RECORDING":
                self.state = "READY"
                self.recorded_frames.clear()
                self.update_status("การบันทึกล้มเหลว (Camera Lost)", "#f44336")
                self.update_toggle_button_style("READY")
                threading.Thread(target=play_wav_sound, args=(SOUND_ERROR,)).start()
        else:
            self.image_label.setText("")
            self.image_label.setStyleSheet("background-color: #000;")

    @pyqtSlot(object)
    def process_new_frame(self, frame):
        if self.state == "RECORDING":
            self.recorded_frames.append(frame)

        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        p = qt_img.scaled(self.image_label.width(), self.image_label.height(), Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(QPixmap.fromImage(p))

    def start_recording_process(self, order_id):
        self.state = "RECORDING"
        self.current_order_id = order_id
        self.recorded_frames.clear()
        
        self.update_status(f"กำลังบันทึก: {self.current_order_id}", "#ff9800")
        self.update_toggle_button_style("RECORDING")
        
        threading.Thread(target=play_wav_sound, args=(SOUND_START,)).start()

    def stop_recording_process(self):
        self.state = "UPLOADING"
        self.update_status(f"กำลังประมวลผล: {self.current_order_id}", "#2196F3")
        self.update_toggle_button_style("READY")
        
        threading.Thread(target=play_wav_sound, args=(SOUND_STOP,)).start()
        self.start_video_creation_worker(list(self.recorded_frames))
        self.recorded_frames.clear()
        
        # เคลียร์ช่องอีกครั้งเพื่อความแน่ใจ
        self.manual_input.clear()

    def start_video_creation_worker(self, frames_to_process):
        self.creation_thread = QThread()
        self.worker = VideoCreationWorker()
        self.worker.moveToThread(self.creation_thread)
        # ส่งข้อมูลทั้งหมดที่จำเป็นไปให้ worker
        self.creation_thread.started.connect(lambda: self.worker.create_and_upload(
            str(self.current_numeric_id), 
            self.current_order_id, 
            frames_to_process, 
            self.upload_api_url
        ))
        self.worker.finished.connect(self.on_upload_finished)
        self.worker.finished.connect(self.creation_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.creation_thread.finished.connect(self.creation_thread.deleteLater)
        self.creation_thread.start()

    def handle_manual_submit(self):
        scanned_code = self.manual_input.text().strip()
        if scanned_code:
            # 1. Clear & Lock: ปิดช่องทันที เพื่อป้องกันข้อมูลแทรก
            self.manual_input.clear()
            self.manual_input.setEnabled(False)
            self.submit_button.setEnabled(False)
            QApplication.processEvents() # บังคับให้หน้าจออัปเดตสถานะ "ปิด" ทันที
            
            try:
                # 2. Process: ทำงานหลัก (ซึ่งอาจจะค้างชั่วขณะที่ติดต่อ Server)
                self.handle_scan(scanned_code)
            finally:
                # 3. Unlock & Cleanup: เปิดช่องคืน และล้างขยะที่อาจตกค้าง
                self.manual_input.setEnabled(True)
                self.submit_button.setEnabled(True)
                self.manual_input.setFocus()
                self.input_buffer = "" # ล้างบัฟเฟอร์กันเหนียว

    def keyPressEvent(self, event):
        if self.manual_input.hasFocus():
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if self.input_buffer:
                self.handle_scan(self.input_buffer.strip())
                self.input_buffer = ""
        else:
            self.input_buffer += event.text()

    def handle_scan(self, scanned_code):
        if self.state == "READY":
            self.initiate_order_on_server(scanned_code)
        
        elif self.state == "RECORDING":
            # --- FIX: ตรวจจับเลขซ้อน (Double String Detection) ---
            # หากเลขยาวเป็น 2 เท่าของเลขเดิม และขึ้นต้นด้วยเลขเดิม ให้ถือว่าเป็นเลขเดิม
            if self.current_order_id and len(scanned_code) > len(self.current_order_id):
                 if scanned_code == self.current_order_id + self.current_order_id:
                     print(f"Detected double input glitch: {scanned_code} -> {self.current_order_id}")
                     scanned_code = self.current_order_id

            if scanned_code == self.current_order_id:
                self.stop_recording_process()
            else:
                print(f"Auto-switching from {self.current_order_id} to {scanned_code}")
                self.stop_recording_process() 
                self.initiate_order_on_server(scanned_code)
    
    def initiate_order_on_server(self, tracking_no):
        self.update_status(f"กำลังติดต่อเซิร์ฟเวอร์: {tracking_no}", "#00bcd4")
        try:
            response = requests.post(self.scan_api_url, json={'tracking_no': tracking_no}, timeout=10)
            response.raise_for_status()
            
            response_data = response.json()
            numeric_order_id = response_data.get('order_id')

            if not numeric_order_id:
                raise ValueError("ไม่ได้รับ Order ID ที่ถูกต้องจากเซิร์ฟเวอร์")

            self.current_numeric_id = numeric_order_id
            self.start_recording_process(tracking_no)
            
        except Exception as e:
            self.update_status(f"การเชื่อมต่อล้มเหลว: {e}", "#f44336")
            self.update_toggle_button_style("READY") 
            threading.Thread(target=play_wav_sound, args=(SOUND_ERROR,)).start()

    def on_upload_finished(self, message, success, tracking_no, file_path):
        threading.Thread(target=play_wav_sound, args=(SOUND_SUCCESS if success else SOUND_ERROR,)).start()
        
        # --- Add to History List ---
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        status_icon = "✅" if success else "❌"
        display_text = f"{status_icon} [{timestamp}]\n{tracking_no}"
        
        item = QListWidgetItem(display_text)
        # กำหนดสีพื้นหลังตามสถานะ
        if success:
            item.setBackground(QColor("#1e3a1e")) # Dark Green
        else:
            item.setBackground(QColor("#3a1e1e")) # Dark Red
            
        # เก็บ path ของไฟล์ไว้ใน UserRole เพื่อดึงมาเล่นทีหลัง
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        
        self.history_list.insertItem(0, item) # Insert at top
        
        # --- State Management ---
        if self.state == "UPLOADING" or self.state == "READY":
            self.update_status(message, "#4CAF50" if success else "#f44336")
            self.current_order_id, self.state = None, "READY"
            self.current_numeric_id = None
            self.update_toggle_button_style("READY")
            threading.Timer(3.0, lambda: self.update_status("พร้อมสแกน (Ready to Scan)", "#4CAF50") if self.state == "READY" else None).start()
        
        elif self.state == "RECORDING":
            print(f"Background upload finished: {message}")
            self.status_label.setText(f"{message} (บันทึกงานใหม่ต่อ...)")
            self.status_label.setStyleSheet(f"background-color: {'#4CAF50' if success else '#f44336'}; color: white; padding: 15px; border-radius: 5px; margin-top: 10px;")
            
            current_active_id = self.current_order_id
            def restore_recording_status():
                if self.state == "RECORDING" and self.current_order_id == current_active_id:
                    self.update_status(f"กำลังบันทึก: {current_active_id}", "#ff9800")
            threading.Timer(2.0, restore_recording_status).start()

    def play_history_video(self, item):
        """เปิดไฟล์วิดีโอเมื่อดับเบิ้ลคลิก"""
        file_path = item.data(Qt.ItemDataRole.UserRole)
        if file_path and os.path.exists(file_path):
            try:
                if sys.platform == 'win32':
                    os.startfile(file_path)
                elif sys.platform == 'darwin':
                    subprocess.call(['open', file_path])
                else:
                    subprocess.call(['xdg-open', file_path])
            except Exception as e:
                QMessageBox.warning(self, "Error", f"ไม่สามารถเปิดไฟล์ได้: {e}")
        else:
            QMessageBox.warning(self, "Error", "ไม่พบไฟล์วิดีโอ (อาจถูกลบหรือย้ายไปแล้ว)")

    def open_history_folder(self):
        """เปิดโฟลเดอร์เก็บไฟล์"""
        try:
            path = os.path.abspath(HISTORY_FOLDER)
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.call(['open', path])
            else:
                subprocess.call(['xdg-open', path])
        except Exception as e:
            print(f"Cannot open folder: {e}")

    def closeEvent(self, event):
        if hasattr(self, 'video_thread'):
            self.video_thread.stop()
        pygame.mixer.quit()
        event.accept()

if __name__ == '__main__':
    try:
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, text=True, creationflags=creationflags)
    except (FileNotFoundError, subprocess.CalledProcessError):
        app = QApplication(sys.argv)
        QMessageBox.critical(None, "ข้อผิดพลาด", "ไม่พบโปรแกรม FFmpeg ในระบบ!\nกรุณาติดตั้ง FFmpeg และเพิ่มลงใน PATH ของระบบก่อนใช้งาน")
        sys.exit(1)

    app = QApplication(sys.argv)

    app.setStyleSheet("""
        QMainWindow, QDialog {
            background-color: #2d2d2d;
        }
        QMenuBar {
            background-color: #3c3c3c;
            color: #f0f0f0;
        }
        QMenuBar::item:selected {
            background-color: #5a5a5a;
        }
        QMenu {
            background-color: #3c3c3c;
            color: #f0f0f0;
            border: 1px solid #5a5a5a;
        }
        QMenu::item:selected {
            background-color: #5a5a5a;
        }
        QLineEdit {
            padding: 8px;
            border: 1px solid #5a5a5a;
            border-radius: 5px;
            background-color: #3c3c3c;
            color: #f0f0f0;
            font-size: 14px;
        }
        QPushButton {
            background-color: #007bff;
            color: white;
            padding: 8px 15px;
            border: none;
            border-radius: 5px;
            font-size: 14px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #0056b3;
        }
    """)

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

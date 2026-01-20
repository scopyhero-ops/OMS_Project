import sys
import os
import datetime
import subprocess
import threading
import configparser
import cv2
import requests
import pygame
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget,
                             QLineEdit, QPushButton, QHBoxLayout, QDialog, QFormLayout,
                             QSpinBox, QMessageBox, QMenuBar, QSlider, QComboBox)
from PyQt6.QtGui import QImage, QPixmap, QFont, QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, pyqtSlot

# --- ฟังก์ชันจัดการไฟล์ Config ---
CONFIG_FILE = 'config.ini'

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
    finished = pyqtSignal(str, bool)

    @pyqtSlot(str, list, str, str)
    def create_and_upload(self, order_id, frames, output_filename, upload_api_url):
        if not frames:
            self.finished.emit("ไม่มีเฟรมภาพให้บันทึก", False)
            return

        height, width, _ = frames[-1].shape
        fps = 60
        command = ['ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}', '-r', str(fps), '-i', '-', '-an', '-vcodec', 'libx264', '-crf', '28', '-preset', 'veryfast', output_filename]

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

            with open(output_filename, 'rb') as f:
                files = {'file': (output_filename, f, 'video/mp4')}
                data = {'order_id': order_id}
                response = requests.post(upload_api_url, files=files, data=data, timeout=120)
            response.raise_for_status()
            self.finished.emit(f"อัปโหลดสำเร็จ: {order_id}", True)
        except Exception as e:
            self.finished.emit(f"เกิดข้อผิดพลาด: {e}", False)
        finally:
            if os.path.exists(output_filename):
                os.remove(output_filename)


# --- Thread สำหรับอ่านวิดีโอจากกล้อง ---
class VideoThread(QThread):
    frame_ready = pyqtSignal(object)

    def __init__(self, camera_index, resolution, brightness, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.resolution_str = resolution
        self.brightness = brightness
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.frame_ready.emit(None)
            return

        try:
            width, height = map(int, self.resolution_str.split('x'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        except ValueError:
            print(f"Invalid resolution format: {self.resolution_str}")

        cap.set(cv2.CAP_PROP_BRIGHTNESS, self.brightness)

        while self.running:
            ret, frame = cap.read()
            if ret: self.frame_ready.emit(frame)
        cap.release()

    def stop(self): self.running = False; self.wait()


# --- หน้าต่างหลักของโปรแกรม ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()

        server_ip = self.config.get('API', 'server_ip')
        self.scan_api_url = f"http://{server_ip}:5000/orders/api/scan_to_initiate"
        self.upload_api_url = f"http://{server_ip}:5000/orders/api/upload_pack_evidence"

        self.recorded_frames = []
        self.setWindowTitle("OMS & Evidence System - Recorder")
        self.setGeometry(100, 100, 800, 650)
        
        # ✨ ขั้นตอนที่ 1: เพิ่มตัวแปรสำหรับเก็บ Numeric ID
        self.state = "READY"
        self.current_order_id = None      # สำหรับเก็บ Tracking No. ที่เป็นข้อความ
        self.current_numeric_id = None    # สำหรับเก็บ ID ที่เป็นตัวเลขจาก Server
        self.input_buffer = ""

        self.setup_ui()

        camera_index = self.config.getint('CAMERA', 'camera_index')
        resolution = self.config.get('CAMERA', 'resolution')
        brightness = self.config.getint('CAMERA', 'brightness')
        self.video_thread = VideoThread(camera_index, resolution, brightness, self)

        self.video_thread.frame_ready.connect(self.process_new_frame)
        self.video_thread.start()

    def setup_ui(self):
        # --- Menu Bar ---
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        file_menu = menu_bar.addMenu("File")
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)

        # --- UI Elements ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)

        self.image_label = QLabel("กำลังค้นหากล้อง...", self)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFont(QFont('Arial', 20))
        self.image_label.setStyleSheet("background-color: #333; color: #eee; border-radius: 5px;")
        main_layout.addWidget(self.image_label, 1)

        manual_input_layout = QHBoxLayout()
        self.manual_input = QLineEdit(self)
        self.manual_input.setFont(QFont('Arial', 14))
        self.manual_input.setPlaceholderText("กรอกเลข Tracking ที่นี่...")
        self.manual_input.returnPressed.connect(self.handle_manual_submit)

        self.submit_button = QPushButton("ยืนยัน", self)
        self.submit_button.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        self.submit_button.clicked.connect(self.handle_manual_submit)

        manual_input_layout.addWidget(self.manual_input)
        manual_input_layout.addWidget(self.submit_button)
        main_layout.addLayout(manual_input_layout)

        self.status_label = QLabel(self)
        self.status_label.setFont(QFont('Arial', 24, QFont.Weight.Bold))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        self.update_status("พร้อมสแกน (Ready to Scan)", "#4CAF50")

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
            QSlider::groove:horizontal {
                border: 1px solid #bbb;
                background: white;
                height: 8px;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #007bff;
                border: 1px solid #007bff;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 15px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #0056b3; }
        """)
        if dialog.exec():
            QMessageBox.information(self, "บันทึกสำเร็จ", "ค่าที่ตั้งไว้ถูกบันทึกแล้ว\nกรุณาปิดและเปิดโปรแกรมใหม่เพื่อให้การเปลี่ยนแปลงสมบูรณ์")
            self.config = load_config()
            server_ip = self.config.get('API', 'server_ip')
            self.scan_api_url = f"http://{server_ip}:5000/orders/api/scan_to_initiate"
            self.upload_api_url = f"http://{server_ip}:5000/orders/api/upload_pack_evidence"

    def update_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"background-color: {color}; color: white; padding: 15px; border-radius: 5px; margin-top: 10px;")

    @pyqtSlot(object)
    def process_new_frame(self, frame):
        if frame is None:
            self.image_label.setText("ไม่สามารถเปิดกล้องได้!"); self.image_label.setStyleSheet("background-color: #f44336; color: white; border-radius: 5px;")
            return

        if self.state == "RECORDING":
            self.recorded_frames.append(frame)

        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        p = qt_img.scaled(self.image_label.width(), self.image_label.height(), Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(QPixmap.fromImage(p))

    def start_recording_process(self, order_id):
        self.state = "RECORDING"; self.current_order_id = order_id
        self.recorded_frames.clear()
        self.update_status(f"กำลังบันทึก: {self.current_order_id}", "#ff9800")
        threading.Thread(target=play_wav_sound, args=(SOUND_START,)).start()

    def stop_recording_process(self):
        self.state = "UPLOADING"
        self.update_status(f"กำลังประมวลผล: {self.current_order_id}", "#2196F3")
        threading.Thread(target=play_wav_sound, args=(SOUND_STOP,)).start()
        self.start_video_creation_worker(list(self.recorded_frames))
        self.recorded_frames.clear()

    # ✨ ขั้นตอนที่ 3: แก้ไขฟังก์ชันนี้ให้ส่ง Numeric ID ไปยัง Worker
    def start_video_creation_worker(self, frames_to_process):
        output_filename = f"pack_evidence_{self.current_order_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.mp4"
        self.creation_thread = QThread()
        self.worker = VideoCreationWorker()
        self.worker.moveToThread(self.creation_thread)
        # แก้ไข: ส่ง self.current_numeric_id (ที่เป็นตัวเลข) ไปให้ Worker แทน
        self.creation_thread.started.connect(lambda: self.worker.create_and_upload(str(self.current_numeric_id), frames_to_process, output_filename, self.upload_api_url))
        self.worker.finished.connect(self.on_upload_finished)
        self.worker.finished.connect(self.creation_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.creation_thread.finished.connect(self.creation_thread.deleteLater)
        self.creation_thread.start()

    def handle_manual_submit(self):
        scanned_code = self.manual_input.text().strip()
        if scanned_code:
            self.handle_scan(scanned_code)
            self.manual_input.clear()

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
        elif self.state == "RECORDING" and scanned_code == self.current_order_id:
            self.stop_recording_process()
    
    # ✨ ขั้นตอนที่ 2: แก้ไขฟังก์ชันนี้ทั้งหมดเพื่ออ่านและเก็บ Numeric ID
    def initiate_order_on_server(self, tracking_no):
        self.update_status(f"กำลังติดต่อเซิร์ฟเวอร์: {tracking_no}", "#00bcd4")
        try:
            # 1. ส่ง request และรับการตอบกลับ
            response = requests.post(self.scan_api_url, json={'tracking_no': tracking_no}, timeout=10)
            response.raise_for_status()
            
            # 2. แปลงข้อมูล JSON และดึงค่า numeric_id ออกมา
            response_data = response.json()
            numeric_order_id = response_data.get('order_id')

            # 3. ตรวจสอบว่าได้รับ ID มาหรือไม่
            if not numeric_order_id:
                raise ValueError("ไม่ได้รับ Order ID ที่ถูกต้องจากเซิร์ฟเวอร์")

            # 4. เก็บค่าทั้งสอง และเริ่มการบันทึก
            self.current_numeric_id = numeric_order_id   # เก็บ ID ที่เป็นตัวเลข (เช่น 56)
            self.start_recording_process(tracking_no) # เริ่มบันทึกโดยใช้ Tracking No. เดิม
            
        except Exception as e:
            self.update_status(f"การเชื่อมต่อล้มเหลว: {e}", "#f44336")
            threading.Thread(target=play_wav_sound, args=(SOUND_ERROR,)).start()

    def on_upload_finished(self, message, success):
        self.update_status(message, "#4CAF50" if success else "#f44336")
        threading.Thread(target=play_wav_sound, args=(SOUND_SUCCESS if success else SOUND_ERROR,)).start()
        self.current_order_id, self.state = None, "READY"
        self.current_numeric_id = None # ✨ เพิ่ม: ล้างค่า numeric_id เมื่อจบงาน
        # เพิ่มการตรวจสอบ self.state ก่อนที่จะเรียก update_status หลัง Timer เพื่อหลีกเลี่ยงการอัปเดตที่ไม่ต้องการหากมีการสแกนใหม่
        threading.Timer(3.0, lambda: self.update_status("พร้อมสแกน (Ready to Scan)", "#4CAF50") if self.state == "READY" else None).start()

    def closeEvent(self, event):
        self.video_thread.stop()
        pygame.mixer.quit()
        event.accept()

if __name__ == '__main__':
    # ตรวจสอบหา ffmpeg ก่อนเริ่มโปรแกรม
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

    # --- กำหนด Stylesheet กลางให้กับ Application ---
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
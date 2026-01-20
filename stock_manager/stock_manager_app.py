import sys
import os
import configparser
import threading
import requests
import pygame
import random
import datetime
import io
import barcode
from barcode.writer import ImageWriter

from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget,
                             QLineEdit, QPushButton, QHBoxLayout, QFrame, QMessageBox,
                             QRadioButton, QButtonGroup, QStackedWidget, QTableWidget,
                             QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog,
                             QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, QDialog,
                             QTextEdit, QScrollArea, QListWidget, QListWidgetItem, QSizePolicy,
                             QGraphicsOpacityEffect)
from PyQt6.QtGui import QPixmap, QFont, QImage, QColor, QPainter, QPen, QIcon, QCursor
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QPropertyAnimation, QPoint, QTimer, QEasingCurve
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

# --- Config & Sound ---
CONFIG_FILE = 'config.ini'
SOUND_SUCCESS = "success.wav"
SOUND_ERROR = "error.wav"

if not os.path.exists(SOUND_SUCCESS): open(SOUND_SUCCESS, "w").close()
if not os.path.exists(SOUND_ERROR): open(SOUND_ERROR, "w").close()

pygame.mixer.init()

def play_sound(status):
    try:
        sound_file = SOUND_SUCCESS if status else SOUND_ERROR
        if os.path.getsize(sound_file) > 0:
            pygame.mixer.music.load(sound_file)
            pygame.mixer.music.play()
    except Exception: pass

def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE, encoding='utf-8')
    if not config.has_section('API'):
        config.add_section('API')
        config.set('API', 'server_ip', '127.0.0.1')
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: config.write(f)
    return config

# --- Stylesheet (CSS) ---
MODERN_STYLE = """
/* Global */
QMainWindow { background-color: #f4f6f9; }
QWidget { font-family: 'Segoe UI', sans-serif; font-size: 14px; color: #333; }

/* Sidebar */
QListWidget#Sidebar {
    background-color: #2c3e50;
    border: none;
    outline: none;
    padding-top: 20px;
}
QListWidget#Sidebar::item {
    color: #bdc3c7;
    padding: 15px 20px;
    margin: 5px 10px;
    border-radius: 8px;
    font-weight: bold;
}
QListWidget#Sidebar::item:hover {
    background-color: #34495e;
    color: white;
}
QListWidget#Sidebar::item:selected {
    background-color: #3498db;
    color: white;
}

/* Cards (White Box) */
QFrame#Card {
    background-color: white;
    border-radius: 10px;
    border: 1px solid #e0e0e0;
}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit {
    border: 1px solid #ced4da;
    border-radius: 6px;
    padding: 8px 12px;
    background: #fff;
    selection-background-color: #3498db;
}
QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {
    border: 2px solid #3498db;
}

/* Buttons */
QPushButton {
    background-color: #ecf0f1;
    border: 1px solid #bdc3c7;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    color: #2c3e50;
}
QPushButton:hover { background-color: #dfe6e9; }
QPushButton#PrimaryBtn {
    background-color: #3498db; color: white; border: none;
}
QPushButton#PrimaryBtn:hover { background-color: #2980b9; }

QPushButton#SuccessBtn {
    background-color: #2ecc71; color: white; border: none;
}
QPushButton#SuccessBtn:hover { background-color: #27ae60; }

QPushButton#DangerBtn {
    background-color: #e74c3c; color: white; border: none;
}
QPushButton#DangerBtn:hover { background-color: #c0392b; }

/* Tables */
QTableWidget {
    background-color: white;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    gridline-color: #f0f0f0;
    selection-background-color: #e8f6fe;
    selection-color: #2c3e50;
}
QHeaderView::section {
    background-color: #f8f9fa;
    padding: 10px;
    border: none;
    border-bottom: 2px solid #3498db;
    font-weight: bold;
    color: #555;
}
"""

# --- Custom Toast Notification (แจ้งเตือนแบบเด้ง) ---
class ToastNotification(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background-color: #333; color: white; border-radius: 8px; padding: 10px;")
        
        self.layout = QHBoxLayout(self)
        self.label = QLabel("")
        self.label.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        self.layout.addWidget(self.label)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.hide()

    def show_message(self, message, is_success=True):
        color = "#2ecc71" if is_success else "#e74c3c"
        self.setStyleSheet(f"background-color: {color}; border-radius: 8px;")
        self.label.setText(message)
        self.adjustSize()
        
        # Position at bottom right
        parent_rect = self.parent().rect()
        self.move(parent_rect.width() - self.width() - 20, parent_rect.height() - self.height() - 20)
        
        self.show()
        self.animation.setDuration(300)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        
        QTimer.singleShot(3000, self.fade_out)

    def fade_out(self):
        self.animation.setDuration(500)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.hide)
        self.animation.start()

# --- Workers (คงเดิม) ---
class AdjustStockWorker(QThread):
    result_ready = pyqtSignal(dict, bool)
    def __init__(self, api_url, sku, mode):
        super().__init__()
        self.api_url = api_url; self.sku = sku; self.mode = mode
    def run(self):
        try:
            resp = requests.post(self.api_url, json={'sku': self.sku, 'mode': self.mode}, timeout=5)
            data = resp.json()
            self.result_ready.emit(data, resp.status_code == 200 and data.get('success'))
        except Exception as e: self.result_ready.emit({'message': str(e)}, False)

class ProductListWorker(QThread):
    data_ready = pyqtSignal(list)
    def __init__(self, api_url, keyword=""):
        super().__init__()
        self.api_url = api_url; self.keyword = keyword
    def run(self):
        try:
            resp = requests.get(self.api_url, params={'q': self.keyword}, timeout=5)
            if resp.status_code == 200: self.data_ready.emit(resp.json().get('products', []))
            else: self.data_ready.emit([])
        except: self.data_ready.emit([])

class BarcodeGenWorker(QThread):
    result_ready = pyqtSignal(str, bool)
    def __init__(self, api_url, sku):
        super().__init__()
        self.api_url = api_url; self.sku = sku
    def run(self):
        try:
            resp = requests.get(self.api_url, params={'sku': self.sku}, timeout=5)
            data = resp.json()
            if resp.status_code == 200 and data.get('success'): self.result_ready.emit(data.get('barcode_url'), True)
            else: self.result_ready.emit(data.get('message', 'Error'), False)
        except Exception as e: self.result_ready.emit(str(e), False)

class CreateProductWorker(QThread):
    result_ready = pyqtSignal(str, bool)
    def __init__(self, api_url, data):
        super().__init__()
        self.api_url = api_url; self.data = data
    def run(self):
        try:
            resp = requests.post(self.api_url, json=self.data, timeout=5)
            res_data = resp.json()
            if resp.status_code == 200 and res_data.get('success'): self.result_ready.emit(res_data.get('message'), True)
            else: self.result_ready.emit(res_data.get('message', 'Failed'), False)
        except Exception as e: self.result_ready.emit(str(e), False)

# --- Dialog: พิมพ์บาร์โค้ด ---
class GridBarcodePrintDialog(QDialog):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self.setWindowTitle(f"🖨️ Print Settings")
        self.resize(500, 450)
        self.setStyleSheet("background-color: white;")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        lbl = QLabel(f"พิมพ์บาร์โค้ดจำนวน {len(self.items)} รายการ")
        lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #3498db;")
        layout.addWidget(lbl)

        grp = QGroupBox("การจัดวาง (Layout)")
        grp.setStyleSheet("QGroupBox { border: 1px solid #ccc; border-radius: 5px; margin-top: 10px; font-weight: bold; }")
        form = QFormLayout(grp)
        
        self.spn_copies = QSpinBox(); self.spn_copies.setRange(1, 999); self.spn_copies.setValue(1)
        self.spn_cols = QSpinBox(); self.spn_cols.setRange(1, 10); self.spn_cols.setValue(3)
        self.spn_rows = QSpinBox(); self.spn_rows.setRange(1, 20); self.spn_rows.setValue(8)
        
        form.addRow("จำนวนดวง/สินค้า:", self.spn_copies)
        form.addRow("คอลัมน์ (แนวนอน):", self.spn_cols)
        form.addRow("แถว (แนวตั้ง):", self.spn_rows)
        layout.addWidget(grp)
        
        btn_layout = QHBoxLayout()
        self.btn_print = QPushButton("สั่งพิมพ์ (Print)"); self.btn_print.setObjectName("PrimaryBtn")
        self.btn_print.clicked.connect(self.print_process)
        btn_cancel = QPushButton("ยกเลิก"); btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_print)
        layout.addLayout(btn_layout)

    def generate_pixmap(self, sku):
        try:
            EAN = barcode.get_barcode_class('code128') 
            writer = ImageWriter(); writer.set_options({'dpi': 300}) 
            ean = EAN(sku, writer=writer)
            buffer = io.BytesIO()
            options = {'write_text': True, 'module_height': 15.0, 'module_width': 0.4, 'font_size': 14, 'quiet_zone': 2.0}
            ean.write(buffer, options=options)
            buffer.seek(0)
            return QPixmap.fromImage(QImage.fromData(buffer.getvalue()))
        except: return None

    def print_process(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            page_w, page_h = rect.width(), rect.height()
            cols, rows = self.spn_cols.value(), self.spn_rows.value()
            cell_w, cell_h = page_w / cols, page_h / rows
            items_per_page = cols * rows
            
            print_queue = []
            for item in self.items:
                pix = self.generate_pixmap(item['sku'])
                if pix:
                    for _ in range(self.spn_copies.value()): print_queue.append(pix)
            
            for i, pix in enumerate(print_queue):
                if i > 0 and i % items_per_page == 0: printer.newPage()
                idx_on_page = i % items_per_page
                c = idx_on_page % cols
                r = idx_on_page // cols
                x, y = int(c * cell_w), int(r * cell_h)
                padding = 50
                draw_w, draw_h = int(cell_w - (padding * 2)), int(cell_h - (padding * 2))
                
                if draw_w > 0 and draw_h > 0:
                    scaled = pix.scaled(draw_w, draw_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    x_center = x + padding + int((draw_w - scaled.width()) / 2)
                    y_center = y + padding + int((draw_h - scaled.height()) / 2)
                    painter.drawPixmap(x_center, y_center, scaled)
            painter.end()
            self.accept()

# --- Main Modern App ---
class ModernStockWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        server_ip = self.config.get('API', 'server_ip')
        
        # API URLs
        self.api_adjust = f"http://{server_ip}:5000/products/api/quick_adjust_stock"
        self.api_list = f"http://{server_ip}:5000/products/api/list"
        self.api_barcode = f"http://{server_ip}:5000/products/api/generate_barcode"
        self.api_add = f"http://{server_ip}:5000/products/api/add"
        self.img_base = f"http://{server_ip}:5000/static/product_images/"

        self.input_buffer = ""
        self.setWindowTitle("Stock Manager Pro - Dashboard")
        self.setGeometry(100, 100, 1200, 800)
        self.setStyleSheet(MODERN_STYLE)

        # Main Layout: Sidebar + Content
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(220)
        
        # Menu Items
        items = [
            ("⚡ Scan In/Out", 0),
            ("📦 Stock List", 1),
            ("🏷️ Manage & Barcode", 2)
        ]
        for name, idx in items:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.sidebar.addItem(item)
        
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.change_page)
        main_layout.addWidget(self.sidebar)

        # 2. Content Area (Stacked)
        self.pages = QStackedWidget()
        self.pages.setContentsMargins(20, 20, 20, 20)
        
        self.page_scan = QWidget(); self.setup_scan_page(); self.pages.addWidget(self.page_scan)
        self.page_list = QWidget(); self.setup_list_page(); self.pages.addWidget(self.page_list)
        self.page_manage = QWidget(); self.setup_manage_page(); self.pages.addWidget(self.page_manage)
        
        main_layout.addWidget(self.pages)

        # Toast Notification Overlay
        self.toast = ToastNotification(self)

    def change_page(self, index):
        self.pages.setCurrentIndex(index)
        if index == 0: self.txt_scan.setFocus()
        if index == 1: self.load_list()

    # --- PAGE 1: SCANNER ---
    def setup_scan_page(self):
        layout = QVBoxLayout(self.page_scan)
        
        # Header
        lbl_head = QLabel("⚡ Quick Scan"); lbl_head.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        layout.addWidget(lbl_head)

        # Mode Selection (Switch Style)
        mode_frame = QFrame(); mode_frame.setObjectName("Card"); mode_frame.setFixedHeight(80)
        mode_layout = QHBoxLayout(mode_frame)
        
        self.btn_in = QPushButton("📥 รับสินค้าเข้า (IN)"); self.btn_in.setCheckable(True); self.btn_in.setChecked(True)
        self.btn_out = QPushButton("📤 เบิกสินค้าออก (OUT)"); self.btn_out.setCheckable(True)
        
        self.btn_in.setFixedHeight(50); self.btn_out.setFixedHeight(50)
        self.btn_in.setStyleSheet("font-size: 16px;")
        self.btn_out.setStyleSheet("font-size: 16px;")

        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.btn_in); self.btn_group.addButton(self.btn_out)
        self.btn_group.buttonClicked.connect(self.update_scan_mode_ui)
        
        mode_layout.addWidget(self.btn_in)
        mode_layout.addWidget(self.btn_out)
        layout.addWidget(mode_frame)

        # Product Display Card
        prod_card = QFrame(); prod_card.setObjectName("Card")
        prod_layout = QVBoxLayout(prod_card)
        
        self.scan_img = QLabel("📷 No Image"); self.scan_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scan_img.setFixedSize(200, 200); self.scan_img.setStyleSheet("background: #f8f9fa; border-radius: 8px; color: #ccc;")
        
        info_layout = QHBoxLayout()
        info_layout.addWidget(self.scan_img)
        
        # Details
        details_layout = QVBoxLayout()
        self.lbl_scan_name = QLabel("Waiting for scan..."); self.lbl_scan_name.setFont(QFont('Segoe UI', 22, QFont.Weight.Bold))
        self.lbl_scan_name.setWordWrap(True)
        
        stock_display = QHBoxLayout()
        self.lbl_old = QLabel("0"); self.lbl_old.setFont(QFont('Segoe UI', 30)); self.lbl_old.setStyleSheet("color: #95a5a6;")
        arrow = QLabel("➜"); arrow.setFont(QFont('Segoe UI', 30)); arrow.setStyleSheet("color: #bdc3c7;")
        self.lbl_new = QLabel("0"); self.lbl_new.setFont(QFont('Segoe UI', 40, QFont.Weight.Bold))
        
        stock_display.addWidget(self.lbl_old)
        stock_display.addWidget(arrow)
        stock_display.addWidget(self.lbl_new)
        stock_display.addStretch()

        details_layout.addWidget(self.lbl_scan_name)
        details_layout.addLayout(stock_display)
        details_layout.addStretch()
        
        info_layout.addLayout(details_layout)
        prod_layout.addLayout(info_layout)
        layout.addWidget(prod_card)

        # Input Area
        self.txt_scan = QLineEdit(); self.txt_scan.setPlaceholderText("🔎 Scan barcode here...")
        self.txt_scan.setFixedHeight(50)
        self.txt_scan.setStyleSheet("font-size: 18px; padding-left: 15px;")
        self.txt_scan.returnPressed.connect(self.process_scan)
        layout.addWidget(self.txt_scan)
        
        self.update_scan_mode_ui()
        layout.addStretch()

    def update_scan_mode_ui(self):
        if self.btn_in.isChecked():
            self.btn_in.setStyleSheet("background-color: #2ecc71; color: white; border: none; font-size: 16px; font-weight: bold;")
            self.btn_out.setStyleSheet("background-color: #ecf0f1; color: #7f8c8d; font-size: 16px;")
            self.lbl_new.setStyleSheet("color: #2ecc71")
        else:
            self.btn_out.setStyleSheet("background-color: #e74c3c; color: white; border: none; font-size: 16px; font-weight: bold;")
            self.btn_in.setStyleSheet("background-color: #ecf0f1; color: #7f8c8d; font-size: 16px;")
            self.lbl_new.setStyleSheet("color: #e74c3c")
        self.txt_scan.setFocus()

    def process_scan(self):
        sku = self.txt_scan.text().strip()
        if not sku: return
        mode = 'in' if self.btn_in.isChecked() else 'out'
        self.txt_scan.setEnabled(False)
        self.worker_scan = AdjustStockWorker(self.api_adjust, sku, mode)
        self.worker_scan.result_ready.connect(self.on_scan_done)
        self.worker_scan.start()

    def on_scan_done(self, data, success):
        self.txt_scan.setEnabled(True); self.txt_scan.clear(); self.txt_scan.setFocus()
        threading.Thread(target=play_sound, args=(success,)).start()
        
        if success:
            p = data.get('product', {})
            self.lbl_scan_name.setText(p.get('name', 'Unknown'))
            self.lbl_old.setText(str(p.get('old_stock')))
            self.lbl_new.setText(str(p.get('new_stock')))
            
            img_url = p.get('image')
            if img_url: self.load_img_url(self.scan_img, self.img_base + img_url)
            else: self.scan_img.setText("No Image")
            
            self.toast.show_message(f"Success: {data.get('message')}", True)
        else:
            self.toast.show_message(f"Error: {data.get('message')}", False)

    # --- PAGE 2: LIST ---
    def setup_list_page(self):
        layout = QVBoxLayout(self.page_list)
        lbl_head = QLabel("📦 Inventory List"); lbl_head.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        layout.addWidget(lbl_head)
        
        # Search Bar
        h = QHBoxLayout()
        self.txt_search = QLineEdit(); self.txt_search.setPlaceholderText("Search product name or SKU...")
        self.txt_search.returnPressed.connect(self.load_list)
        btn_refresh = QPushButton("Refresh"); btn_refresh.setObjectName("PrimaryBtn")
        btn_refresh.clicked.connect(self.load_list)
        h.addWidget(self.txt_search); h.addWidget(btn_refresh)
        layout.addLayout(h)
        
        # Table
        self.table = QTableWidget(); self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SKU", "Product Name", "Stock", "Price"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(40) # Taller rows
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

    def load_list(self):
        self.worker_list = ProductListWorker(self.api_list, self.txt_search.text().strip())
        self.worker_list.data_ready.connect(self.fill_table)
        self.worker_list.start()

    def fill_table(self, products):
        self.table.setRowCount(len(products))
        for r, p in enumerate(products):
            self.table.setItem(r, 0, QTableWidgetItem(str(p.get('sku'))))
            self.table.setItem(r, 1, QTableWidgetItem(str(p.get('name'))))
            
            stock_val = p.get('stock')
            stk_item = QTableWidgetItem(str(stock_val))
            stk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Badge logic
            if stock_val <= 0: stk_item.setBackground(QColor("#ffebee")); stk_item.setForeground(QColor("#c62828"))
            elif stock_val < 10: stk_item.setBackground(QColor("#fff8e1")); stk_item.setForeground(QColor("#f57f17"))
            else: stk_item.setForeground(QColor("#2e7d32"))
                
            self.table.setItem(r, 2, stk_item)
            self.table.setItem(r, 3, QTableWidgetItem(f"{p.get('price',0):,.2f}"))

    # --- PAGE 3: MANAGE ---
    def setup_manage_page(self):
        layout = QHBoxLayout(self.page_manage)
        
        # LEFT: Selection & Print
        left_card = QFrame(); left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.addWidget(QLabel("📝 Select Products to Print Barcode", styleSheet="font-weight:bold; font-size:16px;"))
        
        h_s = QHBoxLayout()
        self.txt_bc_search = QLineEdit(); self.txt_bc_search.setPlaceholderText("Search...")
        self.txt_bc_search.returnPressed.connect(self.search_bc)
        btn_s = QPushButton("Go"); btn_s.clicked.connect(self.search_bc)
        h_s.addWidget(self.txt_bc_search); h_s.addWidget(btn_s)
        left_layout.addLayout(h_s)
        
        self.bc_table = QTableWidget(); self.bc_table.setColumnCount(2)
        self.bc_table.setHorizontalHeaderLabels(["SKU", "Name"])
        self.bc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.bc_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bc_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        left_layout.addWidget(self.bc_table)
        
        btn_print = QPushButton("🖨️ Print Selected (Batch)"); btn_print.setObjectName("PrimaryBtn")
        btn_print.setFixedHeight(40)
        btn_print.clicked.connect(self.batch_print)
        left_layout.addWidget(btn_print)
        
        # RIGHT: Add New Product Form
        right_card = QFrame(); right_card.setObjectName("Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.addWidget(QLabel("✨ Add New Product", styleSheet="font-weight:bold; font-size:16px; color:#27ae60;"))
        
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        form_widget = QWidget()
        form = QFormLayout(form_widget); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.inp_name = QLineEdit()
        self.inp_sku = QLineEdit(); self.inp_sku.setPlaceholderText("Leave empty for Auto-Gen")
        self.inp_cat = QLineEdit()
        self.inp_price = QDoubleSpinBox(); self.inp_price.setRange(0, 100000)
        self.inp_cost = QDoubleSpinBox(); self.inp_cost.setRange(0, 100000)
        self.inp_stock = QSpinBox(); self.inp_stock.setRange(0, 10000)
        
        form.addRow("Product Name:", self.inp_name)
        form.addRow("SKU:", self.inp_sku)
        form.addRow("Category:", self.inp_cat)
        form.addRow("Sell Price:", self.inp_price)
        form.addRow("Cost:", self.inp_cost)
        form.addRow("Initial Stock:", self.inp_stock)
        
        scroll.setWidget(form_widget)
        right_layout.addWidget(scroll)
        
        btn_add = QPushButton("✅ Create Product"); btn_add.setObjectName("SuccessBtn")
        btn_add.setFixedHeight(45)
        btn_add.clicked.connect(self.submit_product)
        right_layout.addWidget(btn_add)
        
        layout.addWidget(left_card, 60)
        layout.addWidget(right_card, 40)

    def search_bc(self):
        self.worker_bc = ProductListWorker(self.api_list, self.txt_bc_search.text().strip())
        self.worker_bc.data_ready.connect(self.fill_bc_table)
        self.worker_bc.start()

    def fill_bc_table(self, products):
        self.bc_table.setRowCount(len(products))
        for r, p in enumerate(products):
            self.bc_table.setItem(r, 0, QTableWidgetItem(str(p.get('sku'))))
            self.bc_table.setItem(r, 1, QTableWidgetItem(str(p.get('name'))))

    def batch_print(self):
        rows = sorted(set(idx.row() for idx in self.bc_table.selectedIndexes()))
        if not rows: return QMessageBox.warning(self, "Warning", "Please select items first.")
        items = [{'sku': self.bc_table.item(r,0).text(), 'name': self.bc_table.item(r,1).text()} for r in rows]
        GridBarcodePrintDialog(items, self).exec()

    def submit_product(self):
        name = self.inp_name.text().strip()
        sku = self.inp_sku.text().strip()
        if not name: return QMessageBox.warning(self, "Missing", "Product Name is required!")
        if not sku:
             # Auto Gen SKU if empty
             sku = f"885{datetime.datetime.now().strftime('%y%m%d')}{random.randint(1000,9999)}"
        
        data = {
            'name': name, 'sku': sku,
            'price': self.inp_price.value(), 'cost': self.inp_cost.value(),
            'stock': self.inp_stock.value(), 'category': self.inp_cat.text()
        }
        self.worker_add = CreateProductWorker(self.api_add, data)
        self.worker_add.result_ready.connect(self.on_added)
        self.worker_add.start()

    def on_added(self, msg, success):
        if success:
            self.toast.show_message("Product Created Successfully!", True)
            self.inp_name.clear(); self.inp_sku.clear(); self.inp_price.setValue(0); self.inp_stock.setValue(0)
            self.search_bc() # Refresh list
        else:
            QMessageBox.critical(self, "Error", msg)

    # Utils
    def load_img_url(self, label, url):
        try:
            data = requests.get(url, timeout=3).content
            pix = QPixmap.fromImage(QImage.fromData(data))
            label.setPixmap(pix.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except: label.setText("Image Error")

    def keyPressEvent(self, e):
        # Override scanner input handling for page 0
        if self.pages.currentIndex() == 0 and not self.txt_scan.hasFocus():
             if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                 self.txt_scan.setText(self.input_buffer)
                 self.process_scan()
                 self.input_buffer = ""
             else:
                 self.input_buffer += e.text()
        else:
             super().keyPressEvent(e)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Optional: Font setup
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = ModernStockWindow()
    window.show()
    sys.exit(app.exec())
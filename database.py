import sqlite3
from datetime import datetime
import os
from werkzeug.security import generate_password_hash
from flask import current_app
from cryptography.fernet import Fernet

def get_db():
    """เชื่อมต่อกับฐานข้อมูลและคืนค่า connection object"""
    db = sqlite3.connect(current_app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db

def get_cipher():
    """สร้าง cipher จาก key ใน config"""
    key = current_app.config['ENCRYPTION_KEY'].encode('utf-8')
    return Fernet(key)

def encrypt_data(data_string):
    """เข้ารหัสข้อความ (เช่น password) ก่อนบันทึกลง DB"""
    if not data_string:
        return None
    cipher = get_cipher()
    encrypted_data = cipher.encrypt(data_string.encode('utf-8'))
    return encrypted_data.decode('utf-8')

def decrypt_data(encrypted_string):
    """ถอดรหัสข้อความจาก DB เพื่อนำไปใช้งาน"""
    if not encrypted_string:
        return None
    try:
        cipher = get_cipher()
        decrypted_data = cipher.decrypt(encrypted_string.encode('utf-8'))
        return decrypted_data.decode('utf-8')
    except Exception as e:
        print(f"Error decrypting data: {e}")
        return None

def get_setting(setting_name):
    """ดึงค่าการตั้งค่าจากตาราง settings"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT setting_value FROM settings WHERE setting_name = ?', (setting_name,))
        value = c.fetchone()
        return value[0] if value else None

def set_setting(setting_name, setting_value):
    """บันทึกหรืออัปเดตค่าการตั้งค่าในตาราง settings"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO settings (setting_name, setting_value) VALUES (?, ?)', (setting_name, setting_value))
        conn.commit()

def init_db():
    """
    ฟังก์ชันสำหรับเริ่มต้นฐานข้อมูล
    """
    with get_db() as conn:
        c = conn.cursor()

        # --- สร้างตารางทั้งหมด (Schema Definition) ---
        c.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, first_name TEXT NOT NULL, last_name TEXT,
                email TEXT, phone TEXT, address TEXT, date_of_birth TEXT, created_at TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT,
                price REAL NOT NULL, cost REAL NOT NULL DEFAULT 0.0,
                stock INTEGER NOT NULL, sku TEXT UNIQUE, category TEXT, color TEXT, size TEXT,
                image_filename TEXT, created_at TEXT
            )
        ''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (setting_name TEXT PRIMARY KEY, setting_value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payment_methods (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sales_channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, order_date TEXT NOT NULL,
                subtotal_before_discount REAL NOT NULL DEFAULT 0,
                item_discount_total REAL NOT NULL DEFAULT 0,
                discount_amount REAL NOT NULL DEFAULT 0,
                global_discount_percentage REAL DEFAULT 0, 
                vat_percentage REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                total_amount REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL, 
                payment_status TEXT NOT NULL DEFAULT 'ยังไม่ชำระ', 
                tracking_no TEXT,
                tracking_provider TEXT, 
                buyer_notes TEXT, 
                payment_method_id INTEGER, 
                sales_channel_id INTEGER,
                pack_video_filename TEXT, 
                paid_time TEXT, 
                shipped_time TEXT, 
                delivered_time TEXT,
                shipping_fee REAL DEFAULT 0, 
                platform_total_amount REAL DEFAULT 0,
                FOREIGN KEY (customer_id) REFERENCES customers(id), 
                FOREIGN KEY (payment_method_id) REFERENCES payment_methods(id),
                FOREIGN KEY (sales_channel_id) REFERENCES sales_channels(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL, unit_price REAL NOT NULL, discount REAL DEFAULT 0,
                platform_discount REAL DEFAULT 0, seller_discount REAL DEFAULT 0,
                FOREIGN KEY (order_id) REFERENCES orders(id), FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS automation_settings (
                platform TEXT PRIMARY KEY, username TEXT, password TEXT, is_active INTEGER DEFAULT 0,
                schedule_times TEXT, line_notify_token TEXT, last_run_status TEXT, last_run_time TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS automation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, platform TEXT NOT NULL,
                status TEXT NOT NULL, message TEXT
            )
        ''')

        # --- ส่วนของการเพิ่มข้อมูลเริ่มต้น (Initial Data Seeding) ---
        c.execute("SELECT * FROM users WHERE username = 'admin'")
        if not c.fetchone():
            hashed_password = generate_password_hash('admin123')
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", ('admin', hashed_password))
        
        default_settings = {
            'shop_name': 'ร้านค้าออนไลน์ของฉัน', 'shop_address': 'ที่อยู่ร้านค้า', 'shop_phone': 'เบอร์โทรศัพท์',
            'shop_tax_id': '-', 'default_vat_percentage': '7.0', 'default_global_discount_percentage': '0.0'
        }
        for name, value in default_settings.items():
            c.execute("INSERT OR IGNORE INTO settings (setting_name, setting_value) VALUES (?, ?)", (name, value))

        for method in ['โอนเงิน', 'เก็บเงินปลายทาง (COD)', 'บัตรเครดิต', 'พร้อมเพย์']:
            c.execute("INSERT OR IGNORE INTO payment_methods (name) VALUES (?)", (method,))
        
        for channel in ['Facebook', 'Line', 'TikTok Shop', 'Shopee', 'Lazada', 'หน้าร้าน']:
            c.execute("INSERT OR IGNORE INTO sales_channels (name) VALUES (?)", (channel,))

        c.execute("SELECT id FROM customers WHERE id = 1")
        if not c.fetchone():
            c.execute('''INSERT OR IGNORE INTO customers (id, first_name, last_name, address, created_at) VALUES (?, ?, ?, ?, ?)''',
                      (1, 'ลูกค้า', 'แพลตฟอร์ม', 'N/A', datetime.now().isoformat()))

        for platform in ['tiktok', 'shopee', 'lazada']:
            c.execute("INSERT OR IGNORE INTO automation_settings (platform) VALUES (?)", (platform,))

        conn.commit()
    print("Database initialized/updated successfully.")


# --- ส่วนที่เพิ่มเข้ามา ---
def run_migrations():
    """
    ฟังก์ชันสำหรับบังคับอัปเดตโครงสร้างฐานข้อมูลที่มีอยู่
    """
    try:
        with get_db() as conn:
            c = conn.cursor()
            print("--- Running Database Migrations ---")

            # ตรวจสอบและเพิ่มคอลัมน์ cost ในตาราง products
            c.execute("PRAGMA table_info(products)")
            product_columns = [col[1] for col in c.fetchall()]
            if 'cost' not in product_columns:
                print("Found missing 'cost' column in 'products'. Adding it now...")
                c.execute("ALTER TABLE products ADD COLUMN cost REAL NOT NULL DEFAULT 0.0")
                print("'cost' column added successfully.")
            else:
                print("'cost' column already exists in 'products'.")

            # ตรวจสอบและเพิ่มคอลัมน์อื่นๆ ที่อาจขาดไปในตาราง orders
            c.execute("PRAGMA table_info(orders)")
            order_columns = [col[1] for col in c.fetchall()]
            new_order_cols = {
                'pack_video_filename': 'TEXT', 'paid_time': 'TEXT', 'shipped_time': 'TEXT', 
                'delivered_time': 'TEXT', 'shipping_fee': 'REAL DEFAULT 0', 'platform_total_amount': 'REAL DEFAULT 0'
            }
            for col, col_type in new_order_cols.items():
                if col not in order_columns:
                    print(f"Found missing '{col}' column in 'orders'. Adding it now...")
                    c.execute(f"ALTER TABLE orders ADD COLUMN {col} {col_type}")
                    print(f"'{col}' column added successfully.")
            
            # ตรวจสอบและเพิ่มคอลัมน์ในตาราง order_items
            c.execute("PRAGMA table_info(order_items)")
            order_item_columns = [col[1] for col in c.fetchall()]
            new_order_item_cols = {
                'platform_discount': 'REAL DEFAULT 0', 'seller_discount': 'REAL DEFAULT 0'
            }
            for col, col_type in new_order_item_cols.items():
                if col not in order_item_columns:
                    c.execute(f"ALTER TABLE order_items ADD COLUMN {col} {col_type}")

            conn.commit()
        return "อัปเดตโครงสร้างฐานข้อมูลสำเร็จ!"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"เกิดข้อผิดพลาดระหว่างการอัปเดตฐานข้อมูล: {e}"
# --- จบส่วนที่เพิ่ม ---
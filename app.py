import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from flask import Flask, render_template, request, redirect, url_for, flash, session
import logging
from datetime import datetime

# Import ส่วนประกอบต่างๆ ของแอป
from config import Config
from database import init_db, run_migrations
from routes import register_blueprints
from extensions import csrf

# --- ส่วนการเริ่มต้นแอปพลิเคชัน ---

# ตั้งค่า Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# สร้าง Flask app instance
app = Flask(__name__)

# 2. โหลดค่า Config จากไฟล์ config.py
app.config.from_object(Config)

# --- ✨ เพิ่มส่วนนี้เข้ามา ---
# ตรวจสอบและสร้างโฟลเดอร์สำหรับอัปโหลดวิดีโอ หากยังไม่มี
os.makedirs(app.config['EVIDENCE_UPLOAD_FOLDER'], exist_ok=True)
# -------------------------

# 3. เริ่มต้นการทำงานของ CSRF กับแอปพลิเคชัน
csrf.init_app(app)

# 4. ลงทะเบียน Blueprints (Routes) ทั้งหมด
register_blueprints(app)

# --- ส่วนของ Context Processors และ Routes อื่นๆ ใน app.py ---

@app.context_processor
def inject_datetime():
    return dict(datetime=datetime)

# Route สำหรับเรียกใช้ init_db ด้วยตนเอง
@app.route('/init_db')
def init_db_route():
    with app.app_context():
        init_db()
    flash('ฐานข้อมูลถูกเริ่มต้น/อัปเดตสำเร็จ!', 'info')
    return redirect(url_for('auth.login'))

# สร้าง Route พิเศษสำหรับบังคับอัปเดตฐานข้อมูล
@app.route('/update_database_now')
def update_db_route():
    with app.app_context():
        message = run_migrations()
    flash(message, 'info')
    return redirect(url_for('dashboard.view_dashboard'))

# --- ส่วนการรันแอปพลิเคชัน ---

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
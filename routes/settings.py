import os
import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from database import get_db, get_setting, set_setting, encrypt_data
from routes.auth import login_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

# --- ส่วนของการตั้งค่าการอัปโหลดไฟล์ ---
UPLOAD_FOLDER = 'static/uploads/logo'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Route หลักสำหรับแสดงหน้าการตั้งค่า ---
@settings_bp.route('/', methods=['GET'])
@login_required
def settings_page():
    with get_db() as conn:
        c = conn.cursor()

        # 1. ดึงข้อมูล Settings ทั้งหมด
        # สร้าง List ของ keys ที่ต้องการ
        setting_keys = [
            'shop_name', 'shop_address', 'shop_phone', 'shop_tax_id', 'shop_logo',
            'default_vat_percentage', 'prices_include_vat', 'default_shipping_fee',
            'receipt_footer_notes', 'automation_line_token'
        ]
        settings = {key: get_setting(key) or '' for key in setting_keys}
        
        # 2. ดึงข้อมูล Automation
        automation_settings = {row['platform']: dict(row) for row in c.execute('SELECT * FROM automation_settings')}

        # 3. ดึงข้อมูล Management
        users = c.execute('SELECT id, username FROM users').fetchall()
        payment_methods = c.execute('SELECT id, name FROM payment_methods ORDER BY name ASC').fetchall()
        sales_channels = c.execute('SELECT id, name FROM sales_channels ORDER BY name ASC').fetchall()

    return render_template('settings.html',
                           settings=settings,
                           automation_settings=automation_settings,
                           users=users,
                           payment_methods=payment_methods,
                           sales_channels=sales_channels)

# --- Route สำหรับบันทึกการตั้งค่าหลัก (รวมหลายแท็บ) ---
@settings_bp.route('/save', methods=['POST'])
@login_required
def save_settings():
    # --- Tab 1: ร้านค้าและข้อมูลทั่วไป ---
    if 'shop_logo_file' in request.files:
        file = request.files['shop_logo_file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # สร้าง path ที่สมบูรณ์
            logo_path = os.path.join(UPLOAD_FOLDER, filename)
            # สร้างโฟลเดอร์ถ้ายังไม่มี
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(logo_path)
            set_setting('shop_logo', filename)

    # วนลูปบันทึกค่าอื่นๆ จาก Form
    settings_to_save = [
        'shop_name', 'shop_address', 'shop_phone', 'shop_tax_id',
        'default_vat_percentage', 'default_shipping_fee', 'receipt_footer_notes',
        'automation_line_token'
    ]
    for key in settings_to_save:
        if key in request.form:
            set_setting(key, request.form[key])
    
    # บันทึกค่า Checkbox แยก
    prices_include_vat = '1' if 'prices_include_vat' in request.form else '0'
    set_setting('prices_include_vat', prices_include_vat)

    # --- Tab 4: ระบบอัตโนมัติ ---
    # (สามารถย้ายมาบันทึกรวมที่นี่ได้ทั้งหมด)
    with get_db() as conn:
        c = conn.cursor()
        tiktok_username = request.form.get('tiktok_username')
        tiktok_password = request.form.get('tiktok_password')
        tiktok_is_active = 1 if 'tiktok_is_active' in request.form else 0
        
        c.execute('UPDATE automation_settings SET username = ?, is_active = ? WHERE platform = "tiktok"',
                  (tiktok_username, tiktok_is_active))
        
        if tiktok_password:
            encrypted_password = encrypt_data(tiktok_password)
            c.execute('UPDATE automation_settings SET password = ? WHERE platform = "tiktok"', (encrypted_password,))
        conn.commit()
    
    flash('บันทึกการตั้งค่าสำเร็จ!', 'success')
    return redirect(url_for('settings.settings_page'))


# --- Routes สำหรับจัดการ Users, Payment Methods, Sales Channels ---
# (โค้ดส่วนนี้ยังคงเดิม แต่ปรับปรุง Redirect ให้กลับไปถูกแท็บ)

@settings_bp.route('/add_user', methods=['POST'])
@login_required
def add_user():
    username = request.form['username']
    password = request.form['password']
    if not username or not password:
        flash('กรุณากรอกชื่อผู้ใช้และรหัสผ่าน', 'danger')
    else:
        hashed_password = generate_password_hash(password)
        with get_db() as conn:
            try:
                conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
                conn.commit()
                flash(f'เพิ่มผู้ใช้งาน "{username}" สำเร็จ!', 'success')
            except sqlite3.IntegrityError:
                flash(f'ชื่อผู้ใช้งาน "{username}" มีอยู่แล้ว!', 'danger')
    return redirect(url_for('settings.settings_page') + '#management')

@settings_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('ไม่สามารถลบผู้ใช้งานที่กำลังใช้งานอยู่ได้!', 'danger')
    else:
        with get_db() as conn:
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            flash('ลบผู้ใช้งานสำเร็จ!', 'success')
    return redirect(url_for('settings.settings_page') + '#management')

@settings_bp.route('/payment_methods/add', methods=['POST'])
@login_required
def add_payment_method():
    name = request.form.get('name')
    if name:
        with get_db() as conn:
            try:
                conn.execute("INSERT INTO payment_methods (name) VALUES (?)", (name,))
                conn.commit()
                flash(f'เพิ่มช่องทางการชำระเงิน "{name}" สำเร็จ!', 'success')
            except sqlite3.IntegrityError:
                flash(f'ช่องทางการชำระเงิน "{name}" มีอยู่แล้ว!', 'danger')
    return redirect(url_for('settings.settings_page') + '#management')

@settings_bp.route('/payment_methods/delete/<int:id>', methods=['POST'])
@login_required
def delete_payment_method(id):
    with get_db() as conn:
        try:
            conn.execute('DELETE FROM payment_methods WHERE id = ?', (id,))
            conn.commit()
            flash('ลบช่องทางการชำระเงินสำเร็จ!', 'success')
        except sqlite3.IntegrityError:
            flash('ไม่สามารถลบช่องทางนี้ได้ เนื่องจากมีคำสั่งซื้อที่ใช้อยู่!', 'danger')
    return redirect(url_for('settings.settings_page') + '#management')

@settings_bp.route('/sales_channels/add', methods=['POST'])
@login_required
def add_sales_channel():
    name = request.form.get('name')
    if name:
        with get_db() as conn:
            try:
                conn.execute("INSERT INTO sales_channels (name) VALUES (?)", (name,))
                conn.commit()
                flash(f'เพิ่มช่องทางการขาย "{name}" สำเร็จ!', 'success')
            except sqlite3.IntegrityError:
                flash(f'ช่องทางการขาย "{name}" มีอยู่แล้ว!', 'danger')
    return redirect(url_for('settings.settings_page') + '#management')

@settings_bp.route('/sales_channels/delete/<int:id>', methods=['POST'])
@login_required
def delete_sales_channel(id):
    with get_db() as conn:
        try:
            conn.execute('DELETE FROM sales_channels WHERE id = ?', (id,))
            conn.commit()
            flash('ลบช่องทางการขายสำเร็จ!', 'success')
        except sqlite3.IntegrityError:
            flash('ไม่สามารถลบช่องทางนี้ได้ เนื่องจากมีคำสั่งซื้อที่ใช้อยู่!', 'danger')
    return redirect(url_for('settings.settings_page') + '#management')
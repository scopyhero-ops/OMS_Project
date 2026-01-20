# Server_App/routes/automation.py

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
import threading
from routes.auth import login_required
from database import get_db # <--- เพิ่มการ import get_db

# --- นำเข้า Worker และ OTP_CACHE ---
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from automation.worker import run_tiktok_automation, OTP_CACHE


automation_bp = Blueprint('automation', __name__, url_prefix='/automation')

@automation_bp.route('/otp', methods=['GET', 'POST'])
def otp_input():
    """
    หน้าสำหรับให้พนักงานกรอก OTP ที่ได้รับทางมือถือ
    """
    if request.method == 'POST':
        platform = request.form.get('platform')
        otp_code = request.form.get('otp_code')
        if not platform or not otp_code:
            flash('ข้อมูลไม่ถูกต้อง', 'danger')
            return render_template('otp_input.html', platform=platform)
        
        # เก็บ OTP ไว้ใน Cache เพื่อให้ Worker ดึงไปใช้
        OTP_CACHE[platform] = otp_code
        
        flash(f'รับรหัส OTP สำหรับ {platform.upper()} เรียบร้อยแล้ว! ระบบกำลังดำเนินการต่ออัตโนมัติ', 'success')
        return render_template('otp_input.html', success=True)
        
    platform = request.args.get('platform', 'tiktok') # default to tiktok
    return render_template('otp_input.html', platform=platform)


@automation_bp.route('/run/tiktok_test')
@login_required
def run_tiktok_test():
    """
    Route สำหรับทดสอบการทำงานของ TikTok Automation ด้วยตนเอง
    พร้อมตรวจสอบว่ามีการตั้งค่าที่จำเป็นแล้วหรือยัง
    """
    # --- ส่วนที่เพิ่มเข้ามา: ตรวจสอบการตั้งค่าก่อนเริ่มทำงาน ---
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT username, password FROM automation_settings WHERE platform = 'tiktok'")
        settings = c.fetchone()

    if not settings or not settings['username'] or not settings['password']:
        flash('กรุณากรอก Username และ Password ของ TikTok และกด "บันทึกการตั้งค่า Automation" ก่อนทำการทดสอบ', 'danger')
        return redirect(url_for('settings.settings_page') + '#automation-pane')
    # --- จบส่วนที่เพิ่มเข้ามา ---

    # รัน Worker ใน Thread ใหม่เพื่อไม่ให้หน้าเว็บค้าง
    thread = threading.Thread(target=run_tiktok_automation)
    thread.start()
    
    flash('กำลังเริ่มกระบวนการดึงข้อมูล TikTok... กรุณาเปิดหน้าสำหรับกรอก OTP เพื่อดำเนินการต่อ', 'info')
    return redirect(url_for('settings.settings_page') + '#automation-pane')


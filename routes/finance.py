import pandas as pd
from flask import (
    Blueprint, render_template, request, flash, redirect, url_for
)
from database import get_db
from .utils import login_required # ใช้ login_required ตัวเดิม

# 1. สร้าง Blueprint ใหม่สำหรับส่วนการเงิน
finance_bp = Blueprint('finance', __name__, url_prefix='/finance')

# 2. สร้าง Route สำหรับหน้า Dashboard การเงิน
@finance_bp.route('/')
@login_required
def dashboard():
    # ในหน้านี้ คุณสามารถดึงข้อมูลสรุปทางการเงินจาก DB มาแสดงได้
    # เช่น ยอดรวมรายรับ, กำไรสุทธิ, ค่าธรรมเนียมทั้งหมด
    # (ตอนนี้ปล่อยว่างไว้ก่อน หรือแสดงข้อความธรรมดา)
    db = get_db()
    # ตัวอย่างการดึงข้อมูลสรุป
    finance_summary = db.execute("""
        SELECT
            SUM(net_income) as total_net_income,
            SUM(transaction_fee) as total_transaction_fee,
            SUM(platform_commission_fee) as total_commission
        FROM orders
        WHERE status = 'Completed'
    """).fetchone()

    return render_template('finance/dashboard.html', summary=finance_summary)

# 3. สร้าง Route สำหรับหน้าอัปโหลดไฟล์ (แสดงฟอร์ม)
@finance_bp.route('/import')
@login_required
def import_page():
    # หน้านี้จะมีแค่ฟอร์มให้อัปโหลดไฟล์
    return render_template('finance/import.html')


# 4. สร้าง Route สำหรับ "รับไฟล์" ที่อัปโหลด (ใช้โค้ดจากคำตอบที่แล้ว)
@finance_bp.route('/import', methods=['POST'])
@login_required
def handle_import():
    file = request.files.get('financial_report')
    if not file or not file.filename.endswith(('.xlsx', '.csv')):
        flash('กรุณาเลือกไฟล์ .xlsx หรือ .csv ที่ถูกต้อง', 'danger')
        return redirect(url_for('finance.import_page'))

    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            # ระบุ sheet_name ให้ถูกต้อง
            df = pd.read_excel(file, sheet_name='Order details') 
        
        db = get_db()
        update_count = 0

        # *** ชื่อคอลัมน์ในไฟล์ Excel/CSV ต้องตรงกับที่ระบุในโค้ด ***
        for index, row in df.iterrows():
            order_id = row['หมายเลขคำสั่งซื้อ']
            net_income = row['รายรับของคำสั่งซื้อ']
            transaction_fee = row['ค่าธรรมเนียมธุรกรรม']
            # เพิ่มคอลัมน์อื่นๆ ตามต้องการ

            res = db.execute("""
                UPDATE orders
                SET net_income = ?, transaction_fee = ?
                WHERE platform_order_id = ?
            """, (net_income, transaction_fee, order_id))
            
            if res.rowcount > 0:
                update_count += 1
        
        db.commit()
        flash(f'อัปเดตข้อมูลการเงินสำเร็จ {update_count} รายการ', 'success')

    except Exception as e:
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('finance.dashboard'))
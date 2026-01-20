from flask import Blueprint, render_template
from .utils import login_required
from database import get_db
import traceback

debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/health_check')
@login_required
def health_check():
    """
    หน้านี้จะทำการ Query ข้อมูลเพื่อตรวจสอบความสมบูรณ์ของการเชื่อมโยง
    """
    orders_with_details = []
    try:
        with get_db() as conn:
            # 1. ดึง 5 ออเดอร์ล่าสุด
            latest_orders = conn.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 5').fetchall()
            
            for order in latest_orders:
                order_details = dict(order)
                items_from_db = conn.execute('SELECT * FROM order_items WHERE order_id = ?', (order['id'],)).fetchall()
                
                # สร้าง List ใหม่สำหรับเก็บ item ที่ประมวลผลแล้ว
                processed_items = []
                for item_row in items_from_db:
                    item_dict = dict(item_row) # แปลง sqlite3.Row เป็น dict ปกติ
                    
                    # ค้นหาสินค้าที่ตรงกัน
                    product_info = conn.execute('SELECT * FROM products WHERE id = ?', (item_dict['product_id'],)).fetchone()
                    
                    # เพิ่มผลการค้นหาเข้าไปใน item_dict
                    item_dict['product_found'] = dict(product_info) if product_info else None
                    processed_items.append(item_dict)
                
                # ใช้ key ชื่อ `items_list` เพื่อไม่ให้ซ้ำกับเมธอด .items()
                order_details['items_list'] = processed_items
                orders_with_details.append(order_details)

    except Exception as e:
        print("--- ERROR IN HEALTH CHECK ---")
        traceback.print_exc()
        
    return render_template('health_check.html', orders_data=orders_with_details)
import os
import sqlite3
import uuid
from datetime import datetime, date, timedelta
from flask import Blueprint, Response, render_template, request, redirect, url_for, flash, jsonify, current_app
from werkzeug.utils import secure_filename
from database import get_db, get_setting
from .utils import login_required
from extensions import csrf
from flask_wtf.csrf import generate_csrf
import pandas as pd
import math
import traceback
from io import StringIO
import barcode
from barcode.writer import ImageWriter

order_bp = Blueprint('order', __name__, url_prefix='/orders')

# ===================================================================
# 1. Helper Functions
# ===================================================================

def get_status_badge_class(status):
    """แปลง status เป็น class สีของ Bootstrap Badge"""
    return {
        'Awaiting Shipment': 'bg-warning-subtle text-warning-emphasis',
        'บันทึกวิดีโอแล้ว': 'bg-secondary-subtle text-secondary-emphasis',
        'Awaiting Collection': 'bg-info-subtle text-info-emphasis',
        'Shipped': 'bg-primary-subtle text-primary-emphasis',
        'Completed': 'bg-success-subtle text-success-emphasis',
        'Cancelled': 'bg-danger-subtle text-danger-emphasis',
    }.get(status, 'bg-light-subtle text-light-emphasis')

def track_url(provider, tracking_no):
    """สร้าง URL สำหรับติดตามพัสดุ"""
    if not provider or not tracking_no:
        return "#"
    if 'flash' in provider.lower():
        return f"https://www.flashexpress.co.th/tracking/?track_no={tracking_no}"
    if 'kerry' in provider.lower():
        return f"https://th.kerryexpress.com/th/track/?track={tracking_no}"
    if 'thailand post' in provider.lower() or 'ไปรษณีย์ไทย' in provider:
        return f"https://track.thailandpost.co.th/?trackNumber={tracking_no}"
    return "#"

def _allowed_file(filename):
    if not filename: return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx', 'xls'}

def _find_column(df_columns, possible_names):
    for name in possible_names:
        for col in df_columns:
            if col.strip().lower() == name.strip().lower(): return col
    return None

def _to_float(value, default=0.0):
    num = pd.to_numeric(value, errors='coerce')
    return default if pd.isna(num) else float(num)

def _to_int(value, default=0):
    num = pd.to_numeric(value, errors='coerce')
    return default if pd.isna(num) else int(num)

def _to_iso_datetime(value):
    if pd.isna(value) or not str(value).strip():
        return datetime.now().isoformat()
    try:
        return pd.to_datetime(str(value).strip(), dayfirst=True).isoformat()
    except (ValueError, TypeError):
        return datetime.now().isoformat()

def _parse_file_to_dataframe(file_stream, filename):
    try:
        if filename.lower().endswith('.xlsx'):
            return pd.read_excel(file_stream, engine='openpyxl')
        elif filename.lower().endswith('.xls'):
             return pd.read_excel(file_stream)
        else:
            file_content = file_stream.read()
            encodings_to_try = ['utf-8', 'utf-8-sig', 'cp874', 'latin1']
            for enc in encodings_to_try:
                try:
                    return pd.read_csv(StringIO(file_content.decode(enc)), thousands=',')
                except (UnicodeDecodeError, pd.errors.ParserError):
                    continue
            raise ValueError("ไม่สามารถอ่านไฟล์ CSV ด้วย Encoding ที่รู้จักได้")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดร้ายแรงขณะอ่านไฟล์: {e}", "danger")
        return None

def num_to_thai_text(number):
    if number is None:
        return ""
    num_str = f"{number:.2f}"
    integer_part, decimal_part = num_str.split('.')
    thai_numbers = {
        '0': 'ศูนย์', '1': 'หนึ่ง', '2': 'สอง', '3': 'สาม', '4': 'สี่',
        '5': 'ห้า', '6': 'หก', '7': 'เจ็ด', '8': 'แปด', '9': 'เก้า'
    }
    thai_units = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน', 'ล้าน']
    def read_integer(n):
        if n == '0': return ''
        length = len(n)
        result = []
        for i, digit in enumerate(n):
            if digit == '0': continue
            pos = length - i - 1
            if pos == 1 and digit == '2': result.append('ยี่')
            elif pos == 1 and digit == '1': pass
            elif pos == 0 and length > 1 and digit == '1': result.append('เอ็ด')
            else: result.append(thai_numbers[digit])
            if pos > 0: result.append(thai_units[pos])
        return ''.join(result)
    integer_text = read_integer(integer_part)
    if not integer_text: integer_text = "ศูนย์"
    result_text = f"{integer_text}บาท"
    if decimal_part != '00':
        satang_text = read_integer(decimal_part)
        result_text += f"{satang_text}สตางค์"
    else:
        result_text += "ถ้วน"
    return result_text

def _process_imported_orders(conn, orders_df, platform):
    STATUS_HIERARCHY = {
        'Unpaid': 0, 'Awaiting Shipment': 10, 'รอดำเนินการ': 10, 'To Ship': 10,
        'Awaiting Collection': 15, 'บันทึกวิดีโอแล้ว': 20, 'Shipped': 30,
        'กำลังจัดส่ง': 30, 'In Transit': 30, 'Cancelled': 99, 'ยกเลิก': 99,
        'Completed': 100, 'จัดส่งสำเร็จ': 100, 'Delivered': 100
    }
    COLUMN_MAPS = {
        'tiktok': {
    'order_id': ['Order ID'],
    'tracking': ['Tracking ID'],
    'recipient': ['Recipient'],
    'phone': ['Phone #'],
    'address': ['Detail Address'],
    'prod_name': ['Product Name'],
    'sku': ['Seller SKU'],
    'qty': ['Quantity'],
    'price': ['SKU Unit Original Price'],
    'paid_time': ['Paid Time'],
    'shipping_fee': ['Shipping Fee After Discount'],
    'platform_total': ['Order Amount'],
    'item_platform_discount': ['SKU Platform Discount'],
    'item_seller_discount': ['SKU Seller Discount'],
    'order_status': ['Order Status']
},
        'shopee': {
            'order_id': ['หมายเลขคำสั่งซื้อ', 'Order SN'],
            'tracking': ['หมายเลขติดตามพัสดุ','*หมายเลขติดตามพัสดุ','Tracking Number'],
            'recipient': ['ชื่อผู้รับ', 'Receiver Name'],
            'phone': ['เบอร์โทรศัพท์','หมายเลขโทรศัพท์','Phone Number'],
            'address': ['ที่อยู่ในการจัดส่ง', 'Shipping Address'],
            'prod_name': ['ชื่อสินค้า', 'Product Name'],
            'sku': ['SKU (ตัวเลือกสินค้า)','เลขอ้างอิง SKU (SKU Reference No.)', 'Product Option SKU', 'SKU สินค้าหลัก', 'ชื่อตัวเลือกสินค้า'],
            'qty': ['จำนวน', 'Quantity'],
            'price': ['ราคาเต็มของสินค้า','ราคาขาย','Original Price'],
            'paid_time': ['เวลาที่ชำระเงิน', 'Order Paid Time'],
            'shipping_fee': ['ค่าจัดส่งที่ผู้ซื้อจ่ายจริง','ค่าจัดส่งที่ชำระโดยผู้ซื้อ','Actual Shipping Fee', 'Estimated Shipping Fee'],
            'platform_total': ['ยอดรวม','จำนวนเงินทั้งหมด','Total Amount'],
            'item_platform_discount': ['ส่วนลดสินค้า (Shopee)','โค้ดส่วนลดชำระโดย Shopee','Shopee Product Discount'],
            'item_seller_discount': ['ส่วนลดสินค้า (ผู้ขาย)', 'Seller Product Discount'],
            'order_status': ['สถานะของคำสั่งซื้อ','สถานะการสั่งซื้อ','Order Status']
        }
    }
    column_map = COLUMN_MAPS.get(platform)

    if not column_map:
        flash(f"ไม่รองรับการนำเข้าสำหรับแพลตฟอร์ม '{platform}' หรือเลือกแพลตฟอร์มไม่ถูกต้อง", "danger")
        return 0, 0, 0

    actual_cols = {key: _find_column(orders_df.columns, names) for key, names in column_map.items()}
    required_keys = ['order_id', 'sku', 'qty', 'price', 'tracking', 'phone', 'order_status']
    for key in required_keys:
        if not actual_cols.get(key):
            flash(f"ไม่พบคอลัมน์สำคัญ '{' หรือ '.join(column_map.get(key, [key]))}' ในไฟล์", "danger")
            return 0, 0, 0

    c = conn.cursor()
    all_tracking_nos = [str(t).strip() for t in orders_df[actual_cols['tracking']].dropna().unique()]
    all_phones = [str(p).strip() for p in orders_df[actual_cols['phone']].dropna().unique()]
    all_skus = [str(s).strip() for s in orders_df[actual_cols['sku']].dropna().unique()]

    if not all_tracking_nos:
        flash("ไฟล์นำเข้าไม่มีข้อมูล Tracking ID", "warning")
        return 0, 0, 0

    placeholders_track = ','.join('?' for _ in all_tracking_nos)
    existing_orders = {row['tracking_no']: dict(row) for row in c.execute(f"SELECT id, tracking_no, status, customer_id FROM orders WHERE tracking_no IN ({placeholders_track})", all_tracking_nos)}

    placeholders_phone = ','.join('?' for _ in all_phones)
    customer_map = {row['phone']: row['id'] for row in c.execute(f"SELECT id, phone FROM customers WHERE phone IN ({placeholders_phone})", all_phones)}
    placeholders_sku = ','.join('?' for _ in all_skus)
    product_map = {row['sku']: {'id': row['id'], 'stock': row['stock']} for row in c.execute(f"SELECT id, sku, stock FROM products WHERE sku IN ({placeholders_sku})", all_skus)}

    sales_channel_row = c.execute("SELECT id FROM sales_channels WHERE name LIKE ?", (f'%{platform}%',)).fetchone()
    sales_channel_id = sales_channel_row['id'] if sales_channel_row else None

    new_customers_to_insert = []
    new_customer_phones = set()
    for _, row in orders_df.drop_duplicates(subset=[actual_cols['phone']]).iterrows():
        phone = str(row.get(actual_cols['phone'], '')).replace("'", "").strip()
        if phone and phone not in customer_map and phone not in new_customer_phones:
            new_customer_phones.add(phone)
            new_customers_to_insert.append((str(row.get(actual_cols['recipient'], 'N/A')), f'({platform.capitalize()})', phone, str(row.get(actual_cols['address'], '')), datetime.now().isoformat()))

    new_products_to_insert = []
    new_product_skus = set()
    for _, row in orders_df.drop_duplicates(subset=[actual_cols['sku']]).iterrows():
        sku = str(row.get(actual_cols['sku'], '')).strip()
        if sku and sku not in product_map and sku not in new_product_skus:
            new_product_skus.add(sku)
            new_products_to_insert.append((str(row.get(actual_cols['prod_name'], 'Unknown Product')), sku, _to_float(row.get(actual_cols['price'])), 1.0, 999, datetime.now().isoformat()))

    imported_count, updated_count, skipped_count = 0, 0, 0
    orders_to_fully_update = []
    customers_to_update = []
    stock_adjustments = {}
    with conn:
        if new_customers_to_insert:
            c.executemany("INSERT INTO customers (first_name, last_name, phone, address, created_at) VALUES (?, ?, ?, ?, ?)", new_customers_to_insert)
            new_phones_placeholders = ','.join('?' for _ in new_customer_phones)
            refreshed_customers = {row['phone']: row['id'] for row in c.execute(f"SELECT id, phone FROM customers WHERE phone IN ({new_phones_placeholders})", list(new_customer_phones))}
            customer_map.update(refreshed_customers)

        if new_products_to_insert:
            c.executemany('INSERT INTO products (name, sku, price, cost, stock, created_at) VALUES (?, ?, ?, ?, ?, ?)', new_products_to_insert)
            new_skus_placeholders = ','.join('?' for _ in new_product_skus)
            refreshed_products = {row['sku']: {'id': row['id']} for row in c.execute(f"SELECT id, sku FROM products WHERE sku IN ({new_skus_placeholders})", list(new_product_skus))}
            product_map.update(refreshed_products)

        for _, group in orders_df.groupby(actual_cols['order_id']):
            first_row = group.iloc[0]
            tracking_no = str(first_row.get(actual_cols['tracking'])).strip() if pd.notna(first_row.get(actual_cols['tracking'])) else None
            status_from_file = str(first_row.get(actual_cols['order_status'])).strip()

            if not tracking_no:
                skipped_count += 1
                continue
            
            if tracking_no in existing_orders:
                existing_order_info = existing_orders[tracking_no]
                order_id_to_update = existing_order_info['id']
                old_items = c.execute("SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id_to_update,)).fetchall()
                for item in old_items:
                    stock_adjustments[item['product_id']] = stock_adjustments.get(item['product_id'], 0) + item['quantity']
                
                c.execute("DELETE FROM order_items WHERE order_id = ?", (order_id_to_update,))
                customer_id_to_update = existing_order_info['customer_id']
                customers_to_update.append({
                    "first_name": str(first_row.get(actual_cols['recipient'], '')),
                    "address": str(first_row.get(actual_cols['address'], '')),
                    "id": customer_id_to_update
                })

                platform_discount_col = actual_cols.get('item_platform_discount')
                seller_discount_col = actual_cols.get('item_seller_discount')
                platform_discount_series = pd.to_numeric(group[platform_discount_col], 'coerce').fillna(0) if platform_discount_col and platform_discount_col in group else pd.Series(0, index=group.index)
                seller_discount_series = pd.to_numeric(group[seller_discount_col], 'coerce').fillna(0) if seller_discount_col and seller_discount_col in group else pd.Series(0, index=group.index)
                item_discount_total = (platform_discount_series + seller_discount_series).sum()
                
                orders_to_fully_update.append({
                    "status": status_from_file,
                    "subtotal_before_discount": _to_float((pd.to_numeric(group[actual_cols['qty']], 'coerce').fillna(0) * pd.to_numeric(group[actual_cols['price']], 'coerce').fillna(0)).sum()),
                    "item_discount_total": _to_float(item_discount_total),
                    "platform_total_amount": _to_float(first_row.get(actual_cols['platform_total'])),
                    "total_amount": _to_float(first_row.get(actual_cols['platform_total'])),
                    "shipping_fee": _to_float(first_row.get(actual_cols['shipping_fee'])),
                    "id": order_id_to_update
                })

                items_to_insert = []
                for _, item_row in group.iterrows():
                    sku = str(item_row.get(actual_cols['sku'], '')).strip()
                    if not sku or sku not in product_map: continue
                    product_id = product_map[sku]['id']
                    qty = _to_int(item_row[actual_cols['qty']])
                    
                    platform_discount = _to_float(item_row.get(platform_discount_col)) if platform_discount_col and platform_discount_col in item_row and pd.notna(item_row.get(platform_discount_col)) else 0
                    seller_discount = _to_float(item_row.get(seller_discount_col)) if seller_discount_col and seller_discount_col in item_row and pd.notna(item_row.get(seller_discount_col)) else 0
                    total_item_discount = platform_discount + seller_discount

                    items_to_insert.append((order_id_to_update, product_id, qty, _to_float(item_row[actual_cols['price']]), total_item_discount, platform_discount, seller_discount))
                    stock_adjustments[product_id] = stock_adjustments.get(product_id, 0) - qty
                
                if items_to_insert:
                    c.executemany('INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount, platform_discount, seller_discount) VALUES (?, ?, ?, ?, ?, ?, ?)', items_to_insert)

                updated_count += 1
                continue

            customer_phone = str(first_row.get(actual_cols['phone'], '')).replace("'", "").strip()
            customer_id = customer_map.get(customer_phone)
            if not customer_id:
                skipped_count += 1
                continue

            paid_time = _to_iso_datetime(first_row.get(actual_cols['paid_time']))
            initial_status = 'Awaiting Shipment' if STATUS_HIERARCHY.get(status_from_file, 0) < 99 else status_from_file
            
            platform_discount_col = actual_cols.get('item_platform_discount')
            seller_discount_col = actual_cols.get('item_seller_discount')
            platform_discount_series = pd.to_numeric(group[platform_discount_col], 'coerce').fillna(0) if platform_discount_col and platform_discount_col in group else pd.Series(0, index=group.index)
            seller_discount_series = pd.to_numeric(group[seller_discount_col], 'coerce').fillna(0) if seller_discount_col and seller_discount_col in group else pd.Series(0, index=group.index)
            item_discount_total = (platform_discount_series + seller_discount_series).sum()

            order_values = {
                "customer_id": customer_id, "order_date": paid_time, "status": initial_status,
                "payment_status": "ชำระแล้ว", "tracking_no": tracking_no, "sales_channel_id": sales_channel_id,
                "paid_time": paid_time,
                "subtotal_before_discount": _to_float((pd.to_numeric(group[actual_cols['qty']], 'coerce').fillna(0) * pd.to_numeric(group[actual_cols['price']], 'coerce').fillna(0)).sum()),
                "item_discount_total": _to_float(item_discount_total),
                "platform_total_amount": _to_float(first_row.get(actual_cols['platform_total'])),
                "total_amount": _to_float(first_row.get(actual_cols['platform_total'])),
                "shipping_fee": _to_float(first_row.get(actual_cols['shipping_fee']))
            }
            cols = ', '.join(order_values.keys())
            placeholders = ', '.join('?' for _ in order_values)
            order_cursor = c.execute(f'INSERT INTO orders ({cols}) VALUES ({placeholders})', tuple(order_values.values()))
            order_id = order_cursor.lastrowid

            items_to_insert = []
            for _, item_row in group.iterrows():
                sku = str(item_row.get(actual_cols['sku'], '')).strip()
                if not sku or sku not in product_map: continue
                product_id = product_map[sku]['id']
                qty = _to_int(item_row[actual_cols['qty']])
                
                platform_discount = _to_float(item_row.get(platform_discount_col)) if platform_discount_col and platform_discount_col in item_row and pd.notna(item_row.get(platform_discount_col)) else 0
                seller_discount = _to_float(item_row.get(seller_discount_col)) if seller_discount_col and seller_discount_col in item_row and pd.notna(item_row.get(seller_discount_col)) else 0
                total_item_discount = platform_discount + seller_discount

                items_to_insert.append((order_id, product_id, qty, _to_float(item_row[actual_cols['price']]), total_item_discount, platform_discount, seller_discount))
                stock_adjustments[product_id] = stock_adjustments.get(product_id, 0) - qty

            if items_to_insert:
                c.executemany('INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount, platform_discount, seller_discount) VALUES (?, ?, ?, ?, ?, ?, ?)', items_to_insert)

            imported_count += 1

        if customers_to_update:
            unique_customer_updates = {d['id']: d for d in customers_to_update}.values()
            c.executemany("UPDATE customers SET first_name = :first_name, address = :address WHERE id = :id", unique_customer_updates)

        if orders_to_fully_update:
            update_query = """
                UPDATE orders SET
                    status = :status,
                    subtotal_before_discount = :subtotal_before_discount,
                    item_discount_total = :item_discount_total,
                    platform_total_amount = :platform_total_amount,
                    total_amount = :total_amount,
                    shipping_fee = :shipping_fee
                WHERE id = :id
            """
            c.executemany(update_query, orders_to_fully_update)

        if stock_adjustments:
            stock_update_list = [(change, pid) for pid, change in stock_adjustments.items()]
            c.executemany("UPDATE products SET stock = stock + ? WHERE id = ?", stock_update_list)

    return imported_count, updated_count, skipped_count


# ===================================================================
# 2. Routes
# ===================================================================

@order_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_orders():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ไม่พบไฟล์ใน request', 'danger'); return redirect(request.url)
        file = request.files['file']
        platform = request.form.get('platform', '').strip().lower()
        if not file or not file.filename:
            flash('กรุณาเลือกไฟล์', 'danger'); return redirect(request.url)
        if not platform:
            flash('กรุณาเลือกแพลตฟอร์ม', 'danger'); return redirect(request.url)

        if _allowed_file(file.filename):
            try:
                orders_df = _parse_file_to_dataframe(file.stream, file.filename)
                if orders_df is not None and not orders_df.empty:
                    with get_db() as conn:
                        imported, updated, skipped = _process_imported_orders(conn, orders_df, platform)
                        if imported > 0 or updated > 0 or skipped > 0:
                            flash(f'นำเข้าสำเร็จ! เพิ่มใหม่ {imported}, อัปเดต {updated}, ข้าม {skipped} รายการ', 'success')
                        elif imported == 0 and updated == 0 and skipped == 0:
                            pass
                        else:
                            flash('ประมวลผลไฟล์สำเร็จ แต่ไม่พบข้อมูลใหม่หรือการอัปเดต', 'info')
                else:
                    flash('ไฟล์ว่างเปล่าหรือไม่สามารถอ่านข้อมูลได้', 'warning')
                return redirect(url_for('order.orders_list'))
            except Exception as e:
                traceback.print_exc()
                flash(f"เกิดข้อผิดพลาดรุนแรงระหว่างการนำเข้า: {e}", "danger")
                return redirect(url_for('order.import_orders'))
        else:
            flash('ประเภทไฟล์ไม่ถูกต้อง (.csv, .xlsx, .xls เท่านั้น)', 'warning')
            return redirect(request.url)
    return render_template('import_orders.html')


@order_bp.route('/')
@login_required
def orders_list():
    def safe_format_date(iso_string):
        if not iso_string or not isinstance(iso_string, str): return "N/A"
        try: return datetime.fromisoformat(iso_string.strip()).strftime('%d/%m/%Y %H:%M')
        except ValueError: return "Invalid Date"

    per_page = request.args.get('per_page', 20, type=int)
    page = request.args.get('page', 1, type=int)
    offset = (page - 1) * per_page
    status_tab = request.args.get('tab', 'ทั้งหมด').strip()
    keyword = request.args.get('q', '').strip()
    shipping_provider = request.args.get('shipping_provider', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()
    sales_channel_id = request.args.get('sales_channel', type=int)

    query_params = request.args.copy()
    query_params.pop('page', None)


    with get_db() as conn:
        sales_channels = conn.execute("SELECT id, name FROM sales_channels ORDER BY name").fetchall()
        
        base_query = " FROM orders o LEFT JOIN customers c ON o.customer_id = c.id LEFT JOIN sales_channels sc ON o.sales_channel_id = sc.id"
        where_clauses = []
        params = []

        if keyword:
            where_clauses.append("""
                (CAST(o.id AS TEXT) LIKE ? OR c.first_name LIKE ? OR o.tracking_no LIKE ?
                 OR o.id IN (SELECT DISTINCT oi.order_id FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE p.sku LIKE ?))
            """)
            params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
        
        if start_date:
            where_clauses.append("date(o.order_date) >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("date(o.order_date) <= ?")
            params.append(end_date)

        status_mapping = {
            'ที่จะจัดส่ง': 'Awaiting Shipment',
            'จัดส่งแล้ว': 'Shipped',
            'เสร็จสิ้น': 'Completed',
            'ยกเลิกแล้ว': 'Cancelled',
            'บันทึกวิดีโอแล้ว': 'บันทึกวิดีโอแล้ว',
            'รอรถเข้ารับ': 'Awaiting Collection'
        }

        if status_tab in status_mapping:
             where_clauses.append("o.status = ?")
             params.append(status_mapping[status_tab])

        if shipping_provider:
            where_clauses.append("o.tracking_provider = ?")
            params.append(shipping_provider)
        
        if sales_channel_id:
            where_clauses.append("o.sales_channel_id = ?")
            params.append(sales_channel_id)

        final_where = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        total_rows_query = "SELECT COUNT(o.id)" + base_query + final_where
        total_rows = conn.execute(total_rows_query, tuple(params)).fetchone()[0]
        total_pages = math.ceil(total_rows / per_page)

        data_query = f"""
            SELECT o.id, o.order_date, o.total_amount, o.status, o.tracking_no, o.pack_video_filename,
                   c.first_name AS customer_name, sc.name AS sales_channel_name, o.tracking_provider,
                   (SELECT COUNT(id) FROM order_items WHERE order_id = o.id) as item_count
            {base_query} {final_where} ORDER BY o.id DESC LIMIT ? OFFSET ?
        """
        final_params = params + [per_page, offset]
        orders_raw = conn.execute(data_query, tuple(final_params)).fetchall()
        
        orders = [dict(row) for row in orders_raw]
        order_ids = [order['id'] for order in orders]
        if order_ids:
            placeholders = ','.join('?' for _ in order_ids)
            items_query = f"""
                SELECT oi.order_id, p.name, p.sku, p.image_filename, oi.quantity
                FROM order_items oi JOIN products p ON oi.product_id = p.id
                WHERE oi.order_id IN ({placeholders})
                AND oi.id IN (SELECT MIN(id) FROM order_items WHERE order_id IN ({placeholders}) GROUP BY order_id)
            """
            first_items = conn.execute(items_query, order_ids * 2).fetchall()
            items_map = {item['order_id']: dict(item) for item in first_items}
            
            for order in orders:
                order['first_item'] = items_map.get(order['id'])

        count_pending = conn.execute("SELECT COUNT(id) FROM orders WHERE status = 'Awaiting Shipment'").fetchone()[0]
        two_days_ago = date.today() - timedelta(days=2)
        count_overdue = conn.execute("SELECT COUNT(id) FROM orders WHERE status = 'Awaiting Shipment' AND date(order_date) < ?", (two_days_ago.isoformat(),)).fetchone()[0]
        count_video_recorded = conn.execute("SELECT COUNT(id) FROM orders WHERE status = 'บันทึกวิดีโอแล้ว'").fetchone()[0]
        count_awaiting_collection = conn.execute("SELECT COUNT(id) FROM orders WHERE status = 'Awaiting Collection'").fetchone()[0]

        summary_counts = {
            'pending': count_pending,
            'overdue': count_overdue,
            'video_recorded': count_video_recorded,
            'awaiting_collection': count_awaiting_collection
        }

    return render_template('orders.html',
                           orders=orders,
                           current_page=page,
                           total_pages=total_pages,
                           keyword=keyword,
                           status_tab=status_tab,
                           summary_counts=summary_counts,
                           safe_format_date=safe_format_date,
                           start_date=start_date,
                           end_date=end_date,
                           sales_channels=sales_channels,
                           get_status_badge_class=get_status_badge_class,
                           track_url=track_url,
                           query_params=query_params,
                           csrf_token=generate_csrf()
                           )


@order_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_order_page():
    if request.method == 'POST':
        try:
            customer_id = request.form.get('customer_id')
            first_name = request.form.get('first_name')
            phone = request.form.get('phone')
            address = request.form.get('address')
            product_ids = request.form.getlist('product_ids[]')
            quantities = request.form.getlist('quantities[]')
            prices = request.form.getlist('prices[]')
            order_discount = float(request.form.get('order_discount', 0))
            shipping_fee = float(request.form.get('shipping_fee', 0))
            apply_vat = 'apply_vat' in request.form

            if not first_name or not phone or not address:
                flash('กรุณากรอกข้อมูลลูกค้าให้ครบถ้วน', 'danger')
                return redirect(url_for('order.create_order_page'))
            
            if not product_ids:
                flash('กรุณาเพิ่มสินค้าอย่างน้อย 1 รายการ', 'danger')
                return redirect(url_for('order.create_order_page'))

            with get_db() as conn:
                with conn:
                    if not customer_id:
                        cursor = conn.execute(
                            'INSERT INTO customers (first_name, phone, address, created_at) VALUES (?, ?, ?, ?)',
                            (first_name, phone, address, datetime.now().isoformat())
                        )
                        customer_id = cursor.lastrowid
                    
                    cursor = conn.execute(
                        'INSERT INTO orders (customer_id, order_date, status, payment_status, discount_amount, shipping_fee) VALUES (?, ?, ?, ?, ?, ?)',
                        (customer_id, datetime.now().isoformat(), 'Awaiting Shipment', 'ชำระแล้ว', order_discount, shipping_fee)
                    )
                    order_id = cursor.lastrowid

                    subtotal = 0
                    for i in range(len(product_ids)):
                        product_id = int(product_ids[i])
                        quantity = int(quantities[i])
                        price = float(prices[i])
                        
                        conn.execute(
                            'INSERT INTO order_items (order_id, product_id, quantity, unit_price, discount) VALUES (?, ?, ?, ?, ?)',
                            (order_id, product_id, quantity, price, 0)
                        )
                        conn.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (quantity, product_id))
                        subtotal += quantity * price
                    
                    subtotal_after_discount = subtotal - order_discount
                    tax_amount = 0
                    if apply_vat:
                        tax_amount = subtotal_after_discount * 0.07

                    grand_total = subtotal_after_discount + shipping_fee + tax_amount

                    conn.execute('UPDATE orders SET subtotal_before_discount=?, tax_amount=?, total_amount=?, platform_total_amount=? WHERE id=?',
                                 (subtotal, tax_amount, grand_total, grand_total, order_id))

            flash(f'สร้างคำสั่งซื้อ #{order_id} สำเร็จ!', 'success')
            return redirect(url_for('order.view_order', id=order_id))

        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการสร้างคำสั่งซื้อ: {e}', 'danger')
            traceback.print_exc()

    return render_template('create_order.html')


@order_bp.route('/view/<int:id>')
@login_required
def view_order(id):
    with get_db() as conn:
        order_data = conn.execute("SELECT o.*, c.first_name AS customer_name, c.phone as customer_phone, c.address as customer_address FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.id = ?", (id,)).fetchone()
        if not order_data:
            flash('ไม่พบคำสั่งซื้อ!', 'danger'); return redirect(url_for('order.orders_list'))
        
        order_details = dict(order_data)
        
        order_details['product_items'] = conn.execute("SELECT oi.*, p.name as product_name, p.sku, p.image_filename, (oi.quantity * oi.unit_price) - oi.discount as item_total FROM order_items oi JOIN products p ON oi.product_id = p.id WHERE oi.order_id = ?", (id,)).fetchall()
    
    return render_template('view_order.html', order=order_details)


@order_bp.route('/view/<int:id>/update_status', methods=['POST'])
@login_required
def update_order_status(id):
    new_status = request.form.get('new_status')
    tracking_no = request.form.get('tracking_no', '').strip()

    with get_db() as conn:
        if new_status:
            conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, id))
            flash(f'เปลี่ยนสถานะออเดอร์ #{id} เป็น "{new_status}" สำเร็จ!', 'success')

        if tracking_no:
             conn.execute("UPDATE orders SET tracking_no = ? WHERE id = ?", (tracking_no, id))
             flash(f'อัปเดต Tracking No. สำหรับออเดอร์ #{id} สำเร็จ!', 'success')
        
        conn.commit()

    return redirect(url_for('order.view_order', id=id))


@order_bp.route('/bulk_action', methods=['POST'])
@login_required
def bulk_action():
    action = request.form.get('action')
    selected_ids_str = request.form.getlist('order_ids[]')
    if not action or not selected_ids_str:
        flash('กรุณาเลือกการกระทำและรายการที่ต้องการ', 'warning')
        return redirect(request.referrer or url_for('order.orders_list'))
    try:
        selected_ids = [int(id_str) for id_str in selected_ids_str]
    except ValueError:
        flash('ID ของคำสั่งซื้อไม่ถูกต้อง', 'danger')
        return redirect(request.referrer or url_for('order.orders_list'))
        
    with get_db() as conn:
        placeholders = ','.join('?' for _ in selected_ids)
        try:
            with conn:
                if action == 'set_video_recorded':
                    conn.execute(f"UPDATE orders SET status = 'บันทึกวิดีโอแล้ว' WHERE id IN ({placeholders})", selected_ids)
                elif action == 'set_awaiting_collection':
                     conn.execute(f"UPDATE orders SET status = 'Awaiting Collection' WHERE id IN ({placeholders})", selected_ids)
                elif action == 'set_shipped':
                    conn.execute(f"UPDATE orders SET status = 'Shipped' WHERE id IN ({placeholders})", selected_ids)
                elif action == 'set_delivered':
                    conn.execute(f"UPDATE orders SET status = 'Completed' WHERE id IN ({placeholders})", selected_ids)
                elif action == 'delete':
                    items_to_restock = conn.execute(f"SELECT product_id, quantity FROM order_items WHERE order_id IN ({placeholders})", selected_ids).fetchall()
                    for item in items_to_restock:
                        if item['product_id'] and item['quantity']:
                            conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (item['quantity'], item['product_id']))
                    conn.execute(f"DELETE FROM order_items WHERE order_id IN ({placeholders})", selected_ids)
                    conn.execute(f"DELETE FROM orders WHERE id IN ({placeholders})", selected_ids)
            
            action_map = {
                'set_video_recorded': 'เปลี่ยนเป็น "บันทึกวิดีโอแล้ว"',
                'set_awaiting_collection': 'เปลี่ยนเป็น "รอรถเข้ารับ"',
                'set_shipped': 'เปลี่ยนเป็น "จัดส่งแล้ว"',
                'set_delivered': 'เปลี่ยนเป็น "เสร็จสิ้น"',
                'delete': 'ลบรายการ'
            }
            action_text = action_map.get(action, action)
            flash(f'ดำเนินการ "{action_text}" กับ {len(selected_ids)} รายการสำเร็จ!', 'success')

        except sqlite3.Error as e:
            flash(f'เกิดข้อผิดพลาดกับฐานข้อมูล: {e}', 'danger'); conn.rollback()
    return redirect(request.referrer or url_for('order.orders_list'))


# --- API Routes ---

# ✨ แก้ไขแล้ว: ปรับแก้ฟังก์ชันนี้ทั้งหมดเพื่อรองรับ Workflow การสร้างออเดอร์ใหม่เมื่อสแกนไม่เจอ
@order_bp.route('/api/scan_to_initiate', methods=['POST'])
@csrf.exempt
def scan_to_initiate():
    data = request.json
    if not data or 'tracking_no' not in data:
        return jsonify({'success': False, 'message': 'Invalid data provided, missing tracking_no'}), 400

    scan_data = data['tracking_no']
    
    with get_db() as conn:
        order = conn.execute("SELECT id, status FROM orders WHERE tracking_no = ?", (scan_data,)).fetchone()

        if order:
            # กรณีเจอออเดอร์ (ทำงานเหมือนเดิม)
            return jsonify({
                'success': True, 
                'message': 'Order found.',
                'order_id': order['id'],
                'status': order['status']
            }), 200
        else:
            # ถ้าไม่เจอ ให้สร้างออเดอร์ใหม่
            try:
                with conn: # ใช้ transaction เพื่อความปลอดภัย
                    # 1. หาหรือสร้าง "ลูกค้าชั่วคราว"
                    default_customer_phone = "000-000-0000"
                    customer = conn.execute("SELECT id FROM customers WHERE phone = ?", (default_customer_phone,)).fetchone()
                    if not customer:
                        cursor = conn.execute(
                            "INSERT INTO customers (first_name, phone, created_at) VALUES (?, ?, ?)",
                            ("Awaiting Import", default_customer_phone, datetime.now().isoformat())
                        )
                        customer_id = cursor.lastrowid
                    else:
                        customer_id = customer['id']

                    # 2. สร้างออเดอร์ใหม่ในสถานะรออัปเดต
                    new_order_status = 'Awaiting Shipment' # หรืออาจตั้งเป็นสถานะพิเศษเช่น 'Awaiting Update'
                    cursor = conn.execute(
                        "INSERT INTO orders (customer_id, order_date, status, tracking_no, payment_status) VALUES (?, ?, ?, ?, ?)",
                        (customer_id, datetime.now().isoformat(), new_order_status, scan_data, 'ยังไม่ชำระ')
                    )
                    new_order_id = cursor.lastrowid
                
                # 3. ตอบกลับว่าสร้างสำเร็จ และส่ง ID ใหม่ไปให้ Client
                return jsonify({
                    'success': True,
                    'message': f'Placeholder for order {scan_data} created. Awaiting file import.',
                    'order_id': new_order_id,
                    'status': new_order_status
                }), 201 # 201 Created
            except sqlite3.IntegrityError:
                # กรณีที่เกิดการสแกนซ้ำกันในเวลาใกล้เคียงกันมาก
                return jsonify({'success': False, 'message': 'Order might be created by another process. Please try again.'}), 409

@order_bp.route('/api/upload_pack_evidence', methods=['POST'])
@csrf.exempt
def upload_pack_evidence():
    """
    API สำหรับรับไฟล์วิดีโอหลักฐานการแพ็ค
    """
    # --- เพิ่มโค้ดดีบัก ---
    print("\n--- DEBUG: ได้รับ Request ที่ /api/upload_pack_evidence ---")
    # --------------------

    if 'file' not in request.files:
        print("--- DEBUG: ไม่พบ 'file' ใน request.files ---")
        return jsonify({'success': False, 'message': 'No file part in the request'}), 400
    
    file = request.files['file']
    order_id = request.form.get('order_id')

    # --- เพิ่มโค้ดดีบัก ---
    print(f"--- DEBUG: Order ID ที่ได้รับ = {order_id}")
    print(f"--- DEBUG: ชื่อไฟล์ที่ได้รับ = {file.filename}")
    # --------------------

    if not order_id:
        print("--- DEBUG: ไม่ได้รับ Order ID ---")
        return jsonify({'success': False, 'message': 'Missing order_id'}), 400

    if file.filename == '':
        print("--- DEBUG: ชื่อไฟล์ว่างเปล่า ---")
        return jsonify({'success': False, 'message': 'No selected file'}), 400

    if file:
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{order_id}_{uuid.uuid4().hex[:8]}_{filename}"
            
            upload_folder = current_app.config['EVIDENCE_UPLOAD_FOLDER']
            filepath = os.path.join(upload_folder, unique_filename)

            # --- เพิ่มโค้ดดีบัก ---
            print(f"--- DEBUG: เตรียมบันทึกไฟล์ไปที่: {filepath}")
            # --------------------

            file.save(filepath)

            # --- เพิ่มโค้ดดีบัก ---
            print(f"--- DEBUG: บันทึกไฟล์สำเร็จ! กำลังอัปเดตฐานข้อมูล...")
            # --------------------
            
            with get_db() as conn:
                conn.execute(
                    "UPDATE orders SET pack_video_filename = ?, status = 'บันทึกวิดีโอแล้ว' WHERE id = ?",
                    (unique_filename, order_id)
                )
                conn.commit()
            
            print("--- DEBUG: อัปเดตฐานข้อมูลสำเร็จ ---")
            return jsonify({'success': True, 'message': f'File for order {order_id} uploaded successfully.'}), 200

        except Exception as e:
            # --- เพิ่มโค้ดดีบัก ---
            print(f"--- DEBUG: !!! เกิดข้อผิดพลาดร้ายแรงใน try..except !!!")
            traceback.print_exc()
            # --------------------
            return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 500
            
    return jsonify({'success': False, 'message': 'Unknown error'}), 500


@order_bp.route('/api/update_video_status', methods=['POST'])
@login_required
def update_video_status():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "ข้อมูลไม่ถูกต้อง"}), 400

    order_id = data.get('order_id')
    tracking_no = data.get('tracking_no')
    video_filename = data.get('video_filename')

    if not order_id and not tracking_no:
        return jsonify({"success": False, "message": "ข้อมูลไม่ถูกต้อง, ต้องการ order_id หรือ tracking_no"}), 400

    with get_db() as conn:
        try:
            if order_id:
                identifier = order_id
                cursor = conn.execute("UPDATE orders SET status = 'บันทึกวิดีโอแล้ว', pack_video_filename = ? WHERE id = ?", (video_filename, order_id))
            else:
                identifier = tracking_no
                cursor = conn.execute("UPDATE orders SET status = 'บันทึกวิดีโอแล้ว', pack_video_filename = ? WHERE tracking_no = ?", (video_filename, tracking_no))
            
            conn.commit()

            if cursor.rowcount == 0:
                return jsonify({"success": False, "message": f"ไม่พบออเดอร์สำหรับ ID: {identifier}"}), 404
            else:
                return jsonify({"success": True, "message": f"บันทึกวิดีโอสำหรับออเดอร์ {identifier} สำเร็จ"}), 200
        except sqlite3.Error as e:
            return jsonify({"success": False, "message": f"เกิดข้อผิดพลาดกับฐานข้อมูล: {e}"}), 500

@order_bp.route('/api/search_customers')
@login_required
def search_customers_api():
    query = request.args.get('q', '').strip()
    with get_db() as conn:
        if query:
            customers = conn.execute(
                "SELECT id, first_name, phone, address FROM customers WHERE first_name LIKE ? OR phone LIKE ? LIMIT 10",
                (f'%{query}%', f'%{query}%')
            ).fetchall()
        else:
            customers = []
    return jsonify([dict(c) for c in customers])


@order_bp.route('/api/search_products')
@login_required
def search_products_api():
    query = request.args.get('q', '').strip()
    with get_db() as conn:
        if query:
            products = conn.execute("SELECT id, name, price, cost, stock, sku, image_filename FROM products WHERE name LIKE ? OR sku LIKE ? LIMIT 10", (f'%{query}%', f'%{query}%')).fetchall()
        else:
            products = conn.execute("SELECT id, name, price, cost, stock, sku, image_filename FROM products ORDER BY id DESC LIMIT 10").fetchall()
    return jsonify([dict(p) for p in products])


# --- Operations & Financial Routes ---
@order_bp.route('/shipments/manage')
@login_required
def manage_shipments():
    with get_db() as conn:
        pending_orders_raw = conn.execute("SELECT o.id, o.order_date, o.total_amount, c.first_name AS customer_name, o.tracking_no, o.status FROM orders o JOIN customers c ON o.customer_id = c.id WHERE o.status IN ('Awaiting Shipment', 'บันทึกวิดีโอแล้ว', 'Awaiting Collection') ORDER BY o.id DESC").fetchall()
        pending_orders = [dict(row) for row in pending_orders_raw]
    return render_template('manage_shipments.html', orders=pending_orders)


@order_bp.route('/shipments/process_batch', methods=['POST'])
@login_required
def process_batch_shipments():
    """
    รับรายการ order IDs มาเพื่อสร้างใบปะหน้าแบบ PDF รวมกัน
    และอัปเดตสถานะของออเดอร์เหล่านั้น
    """
    selected_ids = request.form.getlist('selected_orders')
    
    if not selected_ids:
        return jsonify({'error': 'กรุณาเลือกอย่างน้อย 1 รายการ'}), 400

    try:
        # สำหรับการทดสอบตอนนี้ เราจะสร้างไฟล์ข้อความธรรมดาเพื่อจำลองการทำงาน
        pdf_content = f"ใบปะหน้าสำหรับออเดอร์: {', '.join(selected_ids)}\n"
        pdf_content += "ส่วนนี้จะถูกแทนที่ด้วยข้อมูล PDF จริงในอนาคต"
        
        # อัปเดตสถานะในฐานข้อมูล (ตัวอย่าง)
        with get_db() as conn:
            with conn:
                placeholders = ','.join('?' for _ in selected_ids)
                # สมมติว่าหลังจากพิมพ์ใบปะหน้าแล้ว สถานะจะเปลี่ยนเป็น "รอรถเข้ารับ"
                conn.execute(f"UPDATE orders SET status = 'Awaiting Collection' WHERE id IN ({placeholders})", selected_ids)

        # ส่งไฟล์ PDF จำลองกลับไป
        return Response(
            pdf_content.encode('utf-8'),
            mimetype="application/pdf",
            headers={"Content-disposition": "attachment; filename=shipping_labels.pdf"}
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@order_bp.route('/view/<int:id>/shipping_label')
@login_required
def shipping_label(id):
    with get_db() as conn:
        shop_info = {
            'name': get_setting('shop_name'),
            'address': get_setting('shop_address'),
            'phone': get_setting('shop_phone')
        }
        order_data = conn.execute("""
            SELECT o.*, c.first_name AS customer_name, c.phone as customer_phone, c.address as customer_address
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.id = ?
        """, (id,)).fetchone()

        if not order_data:
            flash('ไม่พบคำสั่งซื้อ!', 'danger')
            return redirect(url_for('order.orders_list'))

        order_details = dict(order_data)

        order_details['product_items'] = conn.execute("""
            SELECT oi.quantity, p.name as product_name, p.sku
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        """, (id,)).fetchall()

    try:
        barcode_dir = os.path.join('static', 'barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        CODE39 = barcode.get_barcode_class('code39')
        writer_options = {'module_height': 10.0, 'font_size': 0, 'write_text': False, 'quiet_zone': 2.0}

        order_id_str = str(order_details['id'])
        order_id_barcode_path = os.path.join(barcode_dir, f"order_{order_id_str}.png")
        code39_order = CODE39(order_id_str, writer=ImageWriter())
        code39_order.write(order_id_barcode_path, options=writer_options)
        order_details['order_id_barcode_file'] = f"barcodes/order_{order_id_str}.png"

        tracking_no_str = order_details.get('tracking_no')
        if tracking_no_str:
            tracking_no_upper = tracking_no_str.upper().replace('-', '')
            tracking_barcode_path = os.path.join(barcode_dir, f"track_{tracking_no_upper}.png")
            code39_track = CODE39(tracking_no_upper, writer=ImageWriter())
            code39_track.write(tracking_barcode_path, options=writer_options)
            order_details['tracking_no_barcode_file'] = f"barcodes/track_{tracking_no_upper}.png"
        else:
            order_details['tracking_no_barcode_file'] = None

    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการสร้างบาร์โค้ด: {e}', 'danger')
        order_details['order_id_barcode_file'] = None
        order_details['tracking_no_barcode_file'] = None

    return render_template(
        'shipping_label.html',
        order=order_details,
        shop_name=shop_info['name'],
        shop_address=shop_info['address'],
        shop_phone=shop_info['phone']
    )


@order_bp.route('/view/<int:id>/receipt')
@login_required
def receipt(id):
    with get_db() as conn:
        shop_info = {
            'name': get_setting('shop_name'),
            'address': get_setting('shop_address'),
            'tax_id': get_setting('shop_tax_id')
        }
        order_data = conn.execute("""
            SELECT o.*, c.first_name, c.address as customer_address
            FROM orders o JOIN customers c ON o.customer_id = c.id
            WHERE o.id = ?
        """, (id,)).fetchone()

        if not order_data:
            flash('ไม่พบคำสั่งซื้อ!', 'danger')
            return redirect(url_for('order.orders_list'))

        order_details = dict(order_data)
        
        order_details['product_items'] = conn.execute("""
            SELECT oi.quantity, p.name as product_name, oi.unit_price, 
                   ((oi.quantity * oi.unit_price) - oi.discount) as item_total
            FROM order_items oi JOIN products p ON oi.product_id = p.id 
            WHERE oi.order_id = ?
        """, (id,)).fetchall()

        subtotal_before_tax = order_details['total_amount'] - order_details['tax_amount']
        grand_total_text = num_to_thai_text(order_details['total_amount'])

    return render_template(
        'receipt_template.html',
        order=order_details,
        shop=shop_info,
        subtotal_before_tax=subtotal_before_tax,
        grand_total_text=grand_total_text
    )


@order_bp.route('/bulk_shipping_label')
@login_required
def bulk_shipping_label():
    order_ids_str = request.args.get('ids', '')
    if not order_ids_str:
        flash('ไม่พบ ID ของรายการที่เลือก', 'warning')
        return redirect(url_for('order.orders_list'))
    
    order_ids = order_ids_str.split(',')
    flash(f'กำลังเตรียมพิมพ์ใบปะหน้าสำหรับ {len(order_ids)} รายการ (ฟังก์ชันยังไม่สมบูรณ์)', 'info')
    return redirect(request.referrer or url_for('order.orders_list'))

@order_bp.route('/export_packing_list')
@login_required
def export_packing_list():
    order_ids_str = request.args.get('ids', '')
    if not order_ids_str:
        flash('ไม่พบ ID ของรายการที่เลือก', 'warning')
        return redirect(url_for('order.orders_list'))

    flash(f'กำลังส่งออกรายการสำหรับจัดของ (ฟังก์ชันยังไม่สมบูรณ์)', 'info')
    return redirect(request.referrer or url_for('order.orders_list'))
# File: routes/data_transformer.py
import pandas as pd
from io import StringIO

# --- ส่วนของการตั้งค่า (Configuration) ---

# 1. กำหนดชื่อคอลัมน์มาตรฐานที่เราต้องการในขั้นตอนสุดท้าย
FINAL_COLUMNS = [
    'order_id', 'tracking_no', 'order_status', 'customer_name',
    'customer_phone', 'customer_address', 'product_name', 'sku',
    'quantity', 'price', 'paid_time', 'shipping_fee', 'platform_total_amount',
    'item_platform_discount', 'item_seller_discount'
]

# 2. กำหนดการแมปชื่อคอลัมน์จากไฟล์ดิบ -> ชื่อมาตรฐาน
TIKTOK_COLUMN_MAP = {
    'order_id': ['Order ID'],
    'tracking_no': ['Tracking ID'],
    'order_status': ['Order Status', 'สถานะ'],
    'customer_name': ['Recipient'],
    'customer_phone': ['Phone #'],
    'customer_address': ['Detail Address'],
    'product_name': ['Product Name'],
    'sku': ['Seller SKU'],
    'quantity': ['Quantity'],
    'price': ['SKU Unit Original Price'],
    'paid_time': ['Paid Time'],
    'shipping_fee': ['Shipping Fee After Discount'],
    'platform_total_amount': ['Order Amount'],
    'item_platform_discount': ['SKU Platform Discount'],
    'item_seller_discount': ['SKU Seller Discount']
}

# 3. กำหนดการแปลงค่าสถานะ -> สถานะมาตรฐาน
STATUS_TRANSFORMATION_MAP = {
    'unpaid': 'Awaiting Shipment', # เปลี่ยนสถานะยังไม่จ่ายเป็นรอจัดส่ง
    'awaiting shipment': 'Awaiting Shipment',
    'to ship': 'Awaiting Shipment',
    'รอดำเนินการ': 'Awaiting Shipment',
    'shipped': 'Shipped',
    'in transit': 'Shipped',
    'completed': 'Completed',
    'delivered': 'Completed',
    'จัดส่งสำเร็จ': 'Completed',
    'cancelled': 'Cancelled',
    'ยกเลิก': 'Cancelled'
}

def _parse_dataframe(file_stream, filename):
    """อ่านไฟล์จาก stream และคืนค่าเป็น DataFrame"""
    if filename.lower().endswith('.xlsx'):
        return pd.read_excel(file_stream, engine='openpyxl')
    else:
        file_content = file_stream.read()
        encodings_to_try = ['utf-8', 'utf-8-sig', 'cp874', 'latin1']
        for enc in encodings_to_try:
            try:
                return pd.read_csv(StringIO(file_content.decode(enc)), thousands=',')
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
        raise ValueError("ไม่สามารถอ่านไฟล์ CSV ด้วย Encoding ที่รู้จักได้")

def transform_data(file_stream, filename, platform='tiktok'):
    """
    ฟังก์ชันหลักในการแปลงข้อมูลจาก File Stream และคืนค่าเป็น DataFrame ที่สะอาดแล้ว
    """
    try:
        df = _parse_dataframe(file_stream, filename)
    except Exception as e:
        raise ValueError(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")

    transformed_df = pd.DataFrame()
    column_map = TIKTOK_COLUMN_MAP # ในอนาคตอาจมี if platform == 'shopee' etc.

    for final_col, possible_names in column_map.items():
        found_col = next((col for col in df.columns if col.strip() in possible_names), None)
        if found_col:
            transformed_df[final_col] = df[found_col]
        else:
            # ทำให้ยืดหยุ่นขึ้นโดยไม่บังคับทุกคอลัมน์ แต่จะแจ้งเตือน
            print(f"คำเตือน: ไม่พบคอลัมน์สำหรับ '{final_col}', จะข้ามไป")
            transformed_df[final_col] = None

    if 'order_status' in transformed_df.columns:
        transformed_df['order_status'] = transformed_df['order_status'].astype(str).str.lower().apply(
            lambda x: STATUS_TRANSFORMATION_MAP.get(x.strip(), 'UNKNOWN')
        )
    
    if 'customer_phone' in transformed_df.columns:
        transformed_df['customer_phone'] = transformed_df['customer_phone'].astype(str).str.replace(r'\D', '', regex=True)

    # ทำให้แน่ใจว่าคอลัมน์ทั้งหมดมีอยู่
    for col in FINAL_COLUMNS:
        if col not in transformed_df.columns:
            transformed_df[col] = None

    return transformed_df[FINAL_COLUMNS]
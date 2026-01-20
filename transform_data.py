import pandas as pd
import sys
import os
from datetime import datetime

# --- ส่วนของการตั้งค่า (Configuration) ---

# 1. กำหนดชื่อคอลัมน์มาตรฐานที่เราต้องการ
FINAL_COLUMNS = [
    'order_id', 'tracking_no', 'order_status', 'customer_name',
    'customer_phone', 'customer_address', 'product_name', 'sku',
    'quantity', 'price', 'paid_time'
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
    'paid_time': ['Paid Time']
}

# 3. กำหนดการแปลงค่าสถานะ -> สถานะมาตรฐาน (ใช้ตัวพิมพ์ใหญ่ทั้งหมดเพื่อเป็นมาตรฐาน)
STATUS_TRANSFORMATION_MAP = {
    'unpaid': 'UNPAID',
    'awaiting shipment': 'AWAITING_SHIPMENT',
    'to ship': 'AWAITING_SHIPMENT',
    'รอดำเนินการ': 'AWAITING_SHIPMENT',
    'shipped': 'SHIPPED',
    'in transit': 'SHIPPED',
    'completed': 'COMPLETED',
    'delivered': 'COMPLETED',
    'จัดส่งสำเร็จ': 'COMPLETED',
    'cancelled': 'CANCELLED',
    'ยกเลิก': 'CANCELLED'
}

def transform_tiktok_data(input_path, output_path):
    """
    ฟังก์ชันหลักในการแปลงไฟล์ CSV จาก TikTok
    """
    try:
        # อ่านไฟล์ CSV
        df = pd.read_csv(input_path)
        print(f"อ่านไฟล์ '{os.path.basename(input_path)}' สำเร็จ, พบ {len(df)} แถว")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
        return

    transformed_df = pd.DataFrame()

    for final_col, possible_names in TIKTOK_COLUMN_MAP.items():
        found_col = next((col for col in df.columns if col.strip() in possible_names), None)
        if found_col:
            transformed_df[final_col] = df[found_col]
        else:
            print(f"คำเตือน: ไม่พบคอลัมน์สำหรับ '{final_col}', จะสร้างเป็นคอลัมน์ว่าง")
            transformed_df[final_col] = None

    if 'order_status' in transformed_df.columns:
        transformed_df['order_status'] = transformed_df['order_status'].astype(str).str.lower().apply(
            lambda x: STATUS_TRANSFORMATION_MAP.get(x.strip(), 'UNKNOWN')
        )

    if 'customer_phone' in transformed_df.columns:
        transformed_df['customer_phone'] = transformed_df['customer_phone'].astype(str).str.replace(r'\D', '', regex=True)
    
    # จัดเรียงและเลือกเฉพาะคอลัมน์ที่ต้องการ
    final_df = transformed_df.reindex(columns=FINAL_COLUMNS)

    try:
        final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"บันทึกไฟล์ที่แปลงแล้วไปที่ '{output_path}' สำเร็จ")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการบันทึกไฟล์: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("\nวิธีใช้งานที่ถูกต้อง:")
        print(f"python {os.path.basename(__file__)} <input_file_path> <output_file_path>\n")
        print("ตัวอย่าง:")
        print(f"python {os.path.basename(__file__)} \"C:\\Downloads\\คำสั่งซื้อ.csv\" \"C:\\Downloads\\import_this_file.csv\"")
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        if not os.path.exists(input_file):
            print(f"ข้อผิดพลาด: ไม่พบไฟล์ '{input_file}'")
        else:
            transform_tiktok_data(input_file, output_file)
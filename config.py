import os
from cryptography.fernet import Fernet

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secure-and-random-secret-key'
    DATABASE = 'database.db'
    UPLOAD_FOLDER = 'uploads'
    PRODUCT_IMAGE_FOLDER = 'static/product_images'
    ALLOWED_CSV_EXTENSIONS = {'csv'}
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

    # ✨ แก้ไข: เปลี่ยน path ให้ไปที่โฟลเดอร์ static/evidence
    EVIDENCE_UPLOAD_FOLDER = 'static/evidence'

    # --- ตั้งค่าสำหรับเชื่อมต่อกับ Llama API ---
    LLAMA_API_URL = os.environ.get('LLAMA_API_URL', 'YOUR_LLAMA_API_ENDPOINT_HERE')
    LLAMA_API_KEY = os.environ.get('LLAMA_API_KEY', 'YOUR_LLAMA_API_KEY_HERE')


# สร้างโฟลเดอร์ที่จำเป็นถ้ายังไม่มี
os.makedirs('uploads', exist_ok=True)
os.makedirs('static/product_images', exist_ok=True)

# ✨ แก้ไข: เปลี่ยน path ให้ตรงกับค่า Config ด้านบน
os.makedirs('static/evidence', exist_ok=True)
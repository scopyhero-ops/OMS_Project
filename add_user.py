import sqlite3
from werkzeug.security import generate_password_hash
import getpass
import os

# --- การตั้งค่า ---
# ✨✨✨ แก้ไขจุดนี้: เปลี่ยน path ให้ตรงกับไฟล์ฐานข้อมูลที่มีอยู่ ✨✨✨
DB_PATH = 'database.db'

def create_user():
    """
    ฟังก์ชันสำหรับสร้างผู้ใช้ใหม่ในฐานข้อมูล
    """
    print("--- สร้างผู้ใช้ใหม่สำหรับเข้าสู่ระบบ ---")

    # ตรวจสอบว่าไฟล์ฐานข้อมูลมีอยู่จริงหรือไม่
    if not os.path.exists(DB_PATH):
        print(f"!!! ข้อผิดพลาด: ไม่พบไฟล์ฐานข้อมูลที่ '{DB_PATH}'")
        print("กรุณาตรวจสอบว่าคุณรันสคริปต์นี้จากโฟลเดอร์หลักของโปรเจกต์")
        return

    try:
        # รับชื่อผู้ใช้และรหัสผ่านจาก User
        username = input("กรอกชื่อผู้ใช้ (Username) ที่ต้องการ: ")
        password = getpass.getpass("กรอกรหัสผ่าน (Password): ")
        confirm_password = getpass.getpass("ยืนยันรหัสผ่านอีกครั้ง (Confirm Password): ")

        # ตรวจสอบว่ารหัสผ่านตรงกันหรือไม่
        if password != confirm_password:
            print("\n[!] รหัสผ่านไม่ตรงกัน! ยกเลิกการทำงาน")
            return

        # ตรวจสอบว่าไม่ได้กรอกค่าว่าง
        if not username or not password:
            print("\n[!] ชื่อผู้ใช้และรหัสผ่านห้ามเป็นค่าว่าง! ยกเลิกการทำงาน")
            return

        # เข้ารหัสผ่านเพื่อความปลอดภัย
        hashed_password = generate_password_hash(password)

        # เชื่อมต่อฐานข้อมูลและเพิ่มผู้ใช้ใหม่
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # คำสั่ง SQL สำหรับเพิ่มข้อมูลลงในตาราง users
        # แก้ไข: เปลี่ยนชื่อคอลัมน์ password_hash ให้ตรงกับ schema ใน database.py
        # ตั้งค่า is_admin = 1 เพื่อให้เป็นผู้ดูแลระบบ
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, hashed_password)
        )

        conn.commit()
        print(f"\n[SUCCESS] สร้างผู้ใช้ '{username}' เรียบร้อยแล้ว!")

    except sqlite3.IntegrityError:
        # กรณีที่มีชื่อผู้ใช้นี้อยู่แล้ว
        print(f"\n[!] ข้อผิดพลาด: ชื่อผู้ใช้ '{username}' มีอยู่แล้วในระบบ")
    except Exception as e:
        print(f"\n[!] เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}")
    finally:
        # ปิดการเชื่อมต่อฐานข้อมูลเสมอ
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == '__main__':
    create_user()

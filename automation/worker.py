# Server_App/automation/worker.py

import sys
import os
import time
import sqlite3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# เพิ่ม Path ของโปรเจกต์หลักเพื่อให้สามารถ import database และอื่นๆ ได้
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Global variable for OTP - ใช้สำหรับแลกเปลี่ยน OTP ระหว่าง Web UI และ Worker
OTP_CACHE = {}

def log_automation_event(platform, status, message):
    """ฟังก์ชันสำหรับบันทึกการทำงานลงในตาราง automation_logs"""
    try:
        db_path = os.path.join(project_root, 'database.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO automation_logs (timestamp, platform, status, message) VALUES (?, ?, ?, ?)",
            (timestamp, platform, status, message)
        )
        conn.commit()
        conn.close()
        print(f"Logged: {platform} - {status} - {message}")
    except Exception as e:
        print(f"Error logging to database: {e}")

def get_tiktok_settings():
    """ดึงข้อมูลการตั้งค่าสำหรับ TikTok จากฐานข้อมูล"""
    settings = None
    try:
        db_path = os.path.join(project_root, 'database.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM automation_settings WHERE platform = 'tiktok'")
        row = cursor.fetchone()
        conn.close()
        if row:
            settings = dict(row)
    except Exception as e:
        print(f"Error getting tiktok settings from database: {e}")
    return settings

def run_tiktok_automation():
    """
    ฟังก์ชันหลักในการรันระบบ Automation สำหรับ TikTok
    """
    log_automation_event('tiktok', 'INFO', 'Starting TikTok automation process.')
    
    settings = get_tiktok_settings()
    if not (settings and settings['is_active']):
        log_automation_event('tiktok', 'INFO', 'TikTok automation is disabled in settings.')
        return

    username = settings.get('username')
    password = settings.get('password')
    if not (username and password):
        log_automation_event('tiktok', 'ERROR', 'TikTok username or password is not set in settings.')
        return

    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    
    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.maximize_window()
        
        driver.get("https://seller-th.tiktok.com/account/login")
        log_automation_event('tiktok', 'INFO', 'Opened TikTok Seller Center login page.')
        wait = WebDriverWait(driver, 20)
        
        # --- ขั้นตอนการล็อกอินที่ปรับปรุงใหม่ ---
        
        # 1. มองหาและคลิกลิงก์ "เข้าสู่ระบบด้วยรหัสผ่าน" ที่มุมบนขวา
        login_with_password_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "เข้าสู่ระบบด้วยรหัสผ่าน")))
        login_with_password_link.click()
        log_automation_event('tiktok', 'INFO', 'Clicked on "Login with password" link.')
        time.sleep(1) # รอเล็กน้อยเพื่อให้หน้า re-render

        # 2. กรอก Username
        username_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@placeholder='อีเมล / ชื่อผู้ใช้']")))
        username_input.send_keys(username)
        log_automation_event('tiktok', 'INFO', f'Entered username: {username}')

        # 3. กรอก Password
        password_input = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@placeholder='รหัสผ่าน']")))
        password_input.send_keys(password)
        log_automation_event('tiktok', 'INFO', 'Entered password.')

        # 4. กดปุ่ม Login
        login_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'เข้าสู่ระบบ')]")))
        login_button.click()
        log_automation_event('tiktok', 'INFO', 'Clicked login button, waiting for OTP page.')

        # 5. รอหน้า OTP และกรอก OTP
        wait.until(EC.url_contains("verification"))
        log_automation_event('tiktok', 'INFO', 'OTP page detected. Waiting for OTP from web UI...')
        
        otp_received = None
        for _ in range(120): # รอ OTP ไม่เกิน 2 นาที
            if OTP_CACHE.get('tiktok'):
                otp_received = OTP_CACHE.pop('tiktok')
                log_automation_event('tiktok', 'SUCCESS', 'OTP received from web UI.')
                break
            time.sleep(1)

        if not otp_received:
            raise Exception("OTP not received within 2 minutes timeout.")

        otp_inputs = driver.find_elements(By.XPATH, "//input[contains(@class, 'sp-input-code-input')]")
        if len(otp_inputs) == 6:
            for i, digit in enumerate(str(otp_received)):
                otp_inputs[i].send_keys(digit)
            log_automation_event('tiktok', 'INFO', 'Entered OTP.')
        else:
            raise Exception(f"Could not find 6 OTP input fields. Found {len(otp_inputs)} instead.")
        
        # 6. ตรวจสอบว่า Login สำเร็จ
        wait.until(EC.url_contains("homepage"))
        log_automation_event('tiktok', 'SUCCESS', 'Login successful! Reached homepage.')
        
        time.sleep(5)

    except Exception as e:
        log_automation_event('tiktok', 'ERROR', f'An error occurred: {e}')
    finally:
        if driver:
            driver.quit()
        log_automation_event('tiktok', 'INFO', 'TikTok automation process finished.')

if __name__ == '__main__':
    run_tiktok_automation()

import logging
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db
from .utils import login_required  # <-- import มาจาก utils.py

auth_bp = Blueprint('auth', __name__, url_prefix='/')
logging.basicConfig(level=logging.INFO)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        with get_db() as conn:
            user = conn.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            logging.info(f"User {username} logged in successfully.")
            return redirect(url_for('dashboard.view_dashboard')) # Redirect ไปหน้าแดชบอร์ด
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
            logging.warning(f"Failed login attempt for username: {username}")
            return render_template('login.html', error="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
            
    # หากมี user ใน session อยู่แล้ว ให้ redirect ไปหน้า dashboard เลย
    if 'user_id' in session:
        return redirect(url_for('dashboard.view_dashboard'))
        
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('คุณได้ออกจากระบบแล้ว', 'info')
    logging.info(f"User logged out.")
    return redirect(url_for('auth.login'))

@auth_bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        current_app.user = None
    else:
        with get_db() as conn:
            current_app.user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
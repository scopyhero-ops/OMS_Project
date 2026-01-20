# routes/utils.py

import functools
from flask import session, flash, redirect, url_for

def login_required(view):
    """
    Decorator สำหรับตรวจสอบว่าผู้ใช้ล็อกอินแล้วหรือยัง
    """
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            flash('กรุณาเข้าสู่ระบบก่อน', 'warning')
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped_view
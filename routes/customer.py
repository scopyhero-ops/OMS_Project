import csv
import io
import os
import sqlite3 # Import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from werkzeug.utils import secure_filename
from database import get_db
from routes.auth import login_required

customer_bp = Blueprint('customer', __name__, url_prefix='/')

# ฟังก์ชันสำหรับตรวจสอบนามสกุลไฟล์ CSV ที่อนุญาตสำหรับการอัปโหลด CSV
def allowed_csv_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_CSV_EXTENSIONS']

@customer_bp.route('/')
@login_required
def index():
    keyword = request.args.get('q', '')
    with get_db() as conn:
        c = conn.cursor()
        if keyword:
            c.execute('''
                SELECT * FROM customers
                WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR address LIKE ?
                ORDER BY created_at DESC
            ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
        else:
            c.execute('SELECT * FROM customers ORDER BY created_at DESC')
        customers = c.fetchall()
    return render_template('index.html', customers=customers, keyword=keyword)

@customer_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        date_of_birth = request.form['date_of_birth']
        created_at = datetime.now().isoformat()

        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO customers (first_name, last_name, email, phone, address, date_of_birth, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (first_name, last_name, email, phone, address, date_of_birth, created_at))
            conn.commit()
        flash('เพิ่มลูกค้าใหม่สำเร็จ!', 'success')
        return redirect(url_for('customer.index'))
    return render_template('add.html')

@customer_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_customer(id):
    with get_db() as conn:
        c = conn.cursor()
        if request.method == 'POST':
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            email = request.form['email']
            phone = request.form['phone']
            address = request.form['address']
            date_of_birth = request.form['date_of_birth']
            c.execute('''
                UPDATE customers
                SET first_name = ?, last_name = ?, email = ?, phone = ?, address = ?, date_of_birth = ?
                WHERE id = ?
            ''', (first_name, last_name, email, phone, address, date_of_birth, id))
            conn.commit()
            flash('แก้ไขข้อมูลลูกค้าสำเร็จ!', 'success')
            return redirect(url_for('customer.index'))

        c.execute('SELECT * FROM customers WHERE id = ?', (id,))
        customer = c.fetchone()
    if not customer:
        flash('ไม่พบข้อมูลลูกค้า!', 'danger')
        return redirect(url_for('customer.index'))
    return render_template('edit.html', customer=customer)

@customer_bp.route('/delete/<int:id>')
@login_required
def delete_customer(id):
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('DELETE FROM customers WHERE id = ?', (id,))
            conn.commit()
            flash('ลบลูกค้าสำเร็จ!', 'success')
        except sqlite3.IntegrityError:
            flash('ไม่สามารถลบลูกค้าได้เนื่องจากมีการอ้างอิงอยู่ในคำสั่งซื้อ!', 'danger')
    return redirect(url_for('customer.index'))

@customer_bp.route('/export')
@login_required
def export():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM customers ORDER BY created_at DESC')
        customers = c.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'ชื่อ', 'นามสกุล', 'อีเมล', 'เบอร์โทร', 'ที่อยู่', 'วันเกิด', 'วันที่สร้าง'])
    for customer in customers:
        writer.writerow(customer)

    output.seek(0)
    return send_file(
        io.BytesIO(output.read().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='customers.csv'
    )

@customer_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_customers():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_csv_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            with open(filepath, newline='', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                next(reader)  # Skip header row
                with get_db() as conn:
                    c = conn.cursor()
                    for row in reader:
                        if len(row) >= 6:
                            first_name = row[0] if len(row) > 0 else ''
                            last_name = row[1] if len(row) > 1 else ''
                            email = row[2] if len(row) > 2 else ''
                            phone = row[3] if len(row) > 3 else ''
                            address = row[4] if len(row) > 4 else ''
                            date_of_birth = row[5] if len(row) > 5 else ''
                            created_at = datetime.now().isoformat()

                            c.execute('''
                                INSERT INTO customers (first_name, last_name, email, phone, address, date_of_birth, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (first_name, last_name, email, phone, address, date_of_birth, created_at))
                        else:
                            flash(f"ข้ามแถวเนื่องจากข้อมูลไม่ครบถ้วน: {row}", 'warning')
                    conn.commit()
            flash('นำเข้าข้อมูลลูกค้าสำเร็จ!', 'success')
            return redirect(url_for('customer.index'))
        else:
            flash('กรุณาอัปโหลดไฟล์ .csv เท่านั้น!', 'danger')
            return render_template('import.html')
    return render_template('import.html')
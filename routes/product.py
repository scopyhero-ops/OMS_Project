import os
import uuid
import sqlite3
import math
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from database import get_db
from .utils import login_required
from extensions import csrf  # จำเป็นสำหรับ @csrf.exempt

# Import สำหรับสร้าง Barcode
import barcode
from barcode.writer import ImageWriter

product_bp = Blueprint('product', __name__, url_prefix='/products')

# ===================================================================
# 1. Helper Functions
# ===================================================================

def _allowed_image_file(filename):
    """ตรวจสอบว่านามสกุลไฟล์ของรูปภาพได้รับอนุญาตหรือไม่"""
    if not filename:
        return False
    return '.' in filename and \
           os.path.splitext(filename)[1].lower().lstrip('.') in current_app.config['ALLOWED_IMAGE_EXTENSIONS']

def _batch_update_product_field(field_name: str, value_type: type = float):
    """ฟังก์ชันกลางสำหรับอัปเดตข้อมูลสินค้าทีละหลายรายการ"""
    try:
        with get_db() as conn:
            with conn: 
                for key, value in request.form.items():
                    prefix = f"{field_name}_"
                    if key.startswith(prefix):
                        product_id = key.split(prefix)[1]
                        new_value = value_type(value)
                        conn.execute(f'UPDATE products SET {field_name} = ? WHERE id = ?', (new_value, product_id))
        flash(f'อัปเดตข้อมูล {field_name} สำเร็จ!', 'success')
    except (ValueError, TypeError):
        flash(f'ข้อมูล {field_name} ที่ป้อนเข้ามาไม่ถูกต้อง กรุณาใส่เป็นตัวเลขเท่านั้น', 'danger')
    except sqlite3.Error as e:
        flash(f'เกิดข้อผิดพลาดกับฐานข้อมูล: {e}', 'danger')
        traceback.print_exc()
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดที่ไม่คาดคิด: {e}', 'danger')
        traceback.print_exc()

# ===================================================================
# 2. Web Routes (หน้าเว็บปกติ)
# ===================================================================

@product_bp.route('/')
@login_required
def products_list():
    """แสดงรายการสินค้าทั้งหมด พร้อมระบบกรองและแบ่งหน้า"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    keyword = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    query_params = request.args.copy()
    query_params.pop('page', None)

    try:
        with get_db() as conn:
            count_base_query = "FROM products WHERE 1=1"
            where_clauses = []
            params = []

            if keyword:
                where_clauses.append("(name LIKE ? OR sku LIKE ?)")
                params.extend([f'%{keyword}%', f'%{keyword}%'])
            
            if status_filter == 'in_stock':
                where_clauses.append("stock > 0")
            elif status_filter == 'low_stock':
                where_clauses.append("stock > 0 AND stock <= 10")
            elif status_filter == 'out_of_stock':
                where_clauses.append("stock <= 0")

            if where_clauses:
                count_base_query += " AND " + " AND ".join(where_clauses)
            
            total_rows_query = "SELECT COUNT(id) " + count_base_query
            total_rows = conn.execute(total_rows_query, tuple(params)).fetchone()[0]
            total_pages = math.ceil(total_rows / per_page)
            
            data_query = "SELECT * " + count_base_query + " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            products = conn.execute(data_query, tuple(params)).fetchall()
        
        return render_template('products.html', 
                               products=products, 
                               keyword=keyword, 
                               status_filter=status_filter,
                               current_page=page, 
                               total_pages=total_pages,
                               query_params=query_params)
    except Exception as e:
        flash(f"เกิดข้อผิดพลาดในการโหลดหน้าสินค้า: {e}", "danger")
        traceback.print_exc()
        return render_template('products.html', products=[], total_pages=1, current_page=1, query_params={})

@product_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_product():
    """หน้าสำหรับเพิ่มสินค้าใหม่"""
    if request.method == 'POST':
        try:
            sku = request.form.get('sku', '').strip() or None
            
            image_filename = None
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file and file.filename and _allowed_image_file(file.filename):
                    ext = os.path.splitext(file.filename)[1]
                    unique_filename = str(uuid.uuid4()) + ext
                    filepath = os.path.join(current_app.config['PRODUCT_IMAGE_FOLDER'], unique_filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    image_filename = unique_filename
            
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO products (name, description, price, cost, stock, sku, category, color, size, image_filename, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.form['name'], request.form.get('description', ''), float(request.form['price']),
                        float(request.form.get('cost', 0.0)), int(request.form['stock']), sku,
                        request.form.get('category', '').strip(), request.form.get('color', '').strip(),
                        request.form.get('size', '').strip(), image_filename, datetime.now().isoformat()
                    )
                )
                conn.commit()
            flash('เพิ่มสินค้าใหม่สำเร็จ!', 'success')
            return redirect(url_for('product.products_list'))
            
        except sqlite3.IntegrityError:
            flash(f'SKU "{sku}" มีอยู่แล้วในระบบ กรุณาใช้ SKU อื่น', 'danger')
        except (ValueError, TypeError):
            flash('ข้อมูล ราคา, ต้นทุน หรือ สต็อก ไม่ถูกต้อง กรุณาใส่เป็นตัวเลข', 'danger')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการบันทึกข้อมูล: {e}', 'danger')
            traceback.print_exc()

    return render_template('add_product.html')

@product_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_product(id):
    """หน้าสำหรับแก้ไขข้อมูลสินค้า"""
    with get_db() as conn:
        product = conn.execute('SELECT * FROM products WHERE id = ?', (id,)).fetchone()
        if not product:
            flash('ไม่พบข้อมูลสินค้า!', 'danger')
            return redirect(url_for('product.products_list'))

    if request.method == 'POST':
        try:
            sku = request.form.get('sku', '').strip() or None
            
            image_filename = product['image_filename']
            if 'image_file' in request.files:
                file = request.files['image_file']
                if file and file.filename and _allowed_image_file(file.filename):
                    ext = os.path.splitext(file.filename)[1]
                    unique_filename = str(uuid.uuid4()) + ext
                    filepath = os.path.join(current_app.config['PRODUCT_IMAGE_FOLDER'], unique_filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    image_filename = unique_filename

            with get_db() as conn:
                conn.execute(
                    """
                    UPDATE products SET name = ?, description = ?, price = ?, cost = ?, stock = ?, sku = ?, 
                    category = ?, color = ?, size = ?, image_filename = ? WHERE id = ?
                    """,
                    (
                        request.form['name'], request.form.get('description', ''), float(request.form['price']),
                        float(request.form.get('cost', 0.0)), int(request.form['stock']), sku,
                        request.form.get('category', ''), request.form.get('color', ''),
                        request.form.get('size', ''), image_filename, id
                    )
                )
                conn.commit()
            flash('อัปเดตข้อมูลสินค้าสำเร็จ!', 'success')
            return redirect(url_for('product.products_list'))
        
        except sqlite3.IntegrityError:
            flash(f'SKU "{sku}" มีอยู่แล้วในระบบ กรุณาใช้ SKU อื่น', 'danger')
        except (ValueError, TypeError):
            flash('ข้อมูล ราคา, ต้นทุน หรือ สต็อก ไม่ถูกต้อง กรุณาใส่เป็นตัวเลข', 'danger')
        except Exception as e:
            flash(f'เกิดข้อผิดพลาดในการอัปเดตข้อมูล: {e}', 'danger')
            traceback.print_exc()
        
        product_from_form = dict(request.form)
        product_from_form['id'] = id
        product_from_form['image_filename'] = product['image_filename']
        return render_template('edit_product.html', product=product_from_form)

    return render_template('edit_product.html', product=product)

@product_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_product(id):
    """เส้นทางสำหรับลบสินค้า"""
    with get_db() as conn:
        try:
            items_in_orders = conn.execute('SELECT COUNT(id) FROM order_items WHERE product_id = ?', (id,)).fetchone()[0]
            if items_in_orders > 0:
                 flash('ไม่สามารถลบสินค้าได้เนื่องจากมีการอ้างอิงอยู่ในคำสั่งซื้อ!', 'danger')
                 return redirect(url_for('product.products_list'))
            
            conn.execute('DELETE FROM products WHERE id = ?', (id,))
            conn.commit()
            flash('ลบสินค้าสำเร็จ!', 'success')
        except sqlite3.Error as e:
            flash(f'เกิดข้อผิดพลาดกับฐานข้อมูล: {e}', 'danger')
    return redirect(url_for('product.products_list'))

@product_bp.route('/batch_update_stock', methods=['GET', 'POST'])
@login_required
def batch_update_stock():
    """หน้าสำหรับอัปเดตสต็อกสินค้าหลายรายการพร้อมกัน"""
    if request.method == 'POST':
        _batch_update_product_field('stock', int)
        return redirect(url_for('product.products_list'))
    with get_db() as conn:
        products = conn.execute('SELECT id, name, sku, stock FROM products ORDER BY name ASC').fetchall()
    return render_template('batch_update_stock.html', products=products)

@product_bp.route('/batch_update_cost', methods=['GET', 'POST'])
@login_required
def batch_update_cost():
    """หน้าสำหรับอัปเดตต้นทุนสินค้าหลายรายการพร้อมกัน"""
    if request.method == 'POST':
        _batch_update_product_field('cost', float)
        return redirect(url_for('product.products_list'))
    with get_db() as conn:
        products = conn.execute('SELECT id, name, sku, cost FROM products ORDER BY name ASC').fetchall()
    return render_template('batch_update_cost.html', products=products)

@product_bp.route('/stock_manager')
@login_required
def stock_manager():
    """หน้าเว็บสำหรับยิงบาร์โค้ด (Web Version)"""
    return render_template('stock_manager.html')


# ===================================================================
# 3. API Routes (สำหรับ Desktop App & Barcode Scanner)
# ===================================================================

@product_bp.route('/api/quick_adjust_stock', methods=['POST'])
@csrf.exempt # ยกเว้น CSRF เพื่อให้ Desktop App ยิงเข้ามาได้ง่าย
# @login_required # เปิดบรรทัดนี้ถ้าต้องการให้ App ต้อง login session ก่อน
def api_quick_adjust_stock():
    """API สำหรับปรับสต็อกทันทีเมื่อยิงบาร์โค้ด"""
    data = request.json
    sku = data.get('sku', '').strip()
    mode = data.get('mode')  # 'in' (เพิ่ม) หรือ 'out' (ลด)
    
    if not sku or not mode:
        return jsonify({'success': False, 'message': 'ข้อมูลไม่ครบถ้วน'}), 400

    try:
        with get_db() as conn:
            product = conn.execute('SELECT id, name, stock, image_filename, sku FROM products WHERE sku = ?', (sku,)).fetchone()
            
            if not product:
                return jsonify({'success': False, 'message': f'ไม่พบสินค้า SKU: {sku}'}), 404
            
            product_id = product['id']
            current_stock = product['stock']
            qty_change = 1

            if mode == 'in':
                new_stock = current_stock + qty_change
                action_text = "รับเข้า"
            elif mode == 'out':
                new_stock = current_stock - qty_change
                action_text = "เบิกออก"
            else:
                return jsonify({'success': False, 'message': 'Mode ไม่ถูกต้อง'}), 400

            conn.execute('UPDATE products SET stock = ? WHERE id = ?', (new_stock, product_id))
            conn.commit()
            
            return jsonify({
                'success': True,
                'message': f'{action_text}สำเร็จ: {product["name"]}',
                'product': {
                    'name': product['name'],
                    'sku': product['sku'],
                    'old_stock': current_stock,
                    'new_stock': new_stock,
                    'image': product['image_filename']
                }
            })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Server Error: {str(e)}'}), 500

@product_bp.route('/api/list', methods=['GET'])
@csrf.exempt
def api_product_list():
    """API สำหรับดึงรายการสินค้าทั้งหมด (รองรับการกรอง)"""
    keyword = request.args.get('q', '').strip()
    status_filter = request.args.get('status', 'all').strip()
    
    try:
        with get_db() as conn:
            base_query = "SELECT id, name, sku, stock, price, image_filename FROM products WHERE 1=1"
            params = []

            if keyword:
                base_query += " AND (name LIKE ? OR sku LIKE ?)"
                params.extend([f'%{keyword}%', f'%{keyword}%'])
            
            if status_filter == 'in_stock':
                base_query += " AND stock > 0"
            elif status_filter == 'low_stock':
                base_query += " AND stock > 0 AND stock <= 10"
            elif status_filter == 'out_of_stock':
                base_query += " AND stock <= 0"
            
            base_query += " ORDER BY id DESC"
            
            products = conn.execute(base_query, tuple(params)).fetchall()
            
            product_list = []
            for p in products:
                product_list.append({
                    'id': p['id'],
                    'name': p['name'],
                    'sku': p['sku'],
                    'stock': p['stock'],
                    'price': p['price'],
                    'image': p['image_filename']
                })
                
            return jsonify({'success': True, 'products': product_list})
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@product_bp.route('/api/generate_barcode', methods=['GET'])
@csrf.exempt
def api_generate_barcode():
    """API สำหรับสร้างรูปบาร์โค้ดจาก SKU"""
    sku = request.args.get('sku', '').strip()
    if not sku:
        return jsonify({'success': False, 'message': 'ไม่พบ SKU'}), 400

    try:
        barcode_dir = os.path.join(current_app.root_path, 'static', 'temp_barcodes')
        os.makedirs(barcode_dir, exist_ok=True)
        
        CODE = barcode.get_barcode_class('code128')
        writer = ImageWriter()
        writer.set_options({
            'module_height': 15.0, 
            'module_width': 0.2, 
            'font_size': 10, 
            'text_distance': 5.0, 
            'quiet_zone': 2.0,
            'write_text': True
        })
        
        my_barcode = CODE(sku, writer=writer)
        filename = f"barcode_{sku}"
        filepath = os.path.join(barcode_dir, filename)
        
        my_barcode.save(filepath) # .png will be added automatically
        
        full_filename = filename + ".png"
        url = url_for('static', filename=f'temp_barcodes/{full_filename}', _external=True)
        
        return jsonify({'success': True, 'barcode_url': url})

    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

@product_bp.route('/api/add', methods=['POST'])
@csrf.exempt
def api_add_product():
    """API สำหรับเพิ่มสินค้าใหม่ (สำหรับ Desktop App)"""
    try:
        data = request.json
        name = data.get('name')
        sku = data.get('sku')
        price = data.get('price', 0)
        stock = data.get('stock', 0)

        if not name or not sku:
             return jsonify({'success': False, 'message': 'กรุณาระบุชื่อสินค้าและ SKU'}), 400

        with get_db() as conn:
            exist = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
            if exist:
                return jsonify({'success': False, 'message': f'SKU {sku} มีอยู่ในระบบแล้ว'}), 409

            conn.execute(
                "INSERT INTO products (name, sku, price, stock, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, sku, float(price), int(stock), datetime.now().isoformat())
            )
            conn.commit()

        return jsonify({'success': True, 'message': 'เพิ่มสินค้าเรียบร้อยแล้ว'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
import os
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename
from datetime import datetime
from database import get_db

evidence_bp = Blueprint('evidence', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'avi'}

@evidence_bp.route('/orders/api/scan_to_initiate', methods=['POST'])
def scan_to_initiate():
    data = request.get_json()
    if not data or 'tracking_no' not in data:
        return jsonify({"error": "Missing tracking_no"}), 400
    tracking_no = data['tracking_no']

    # --- แก้ไข: เปลี่ยนมาใช้ with get_db() ---
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM orders WHERE tracking_no = ?", (tracking_no,))
            order_exists = cursor.fetchone()
            if order_exists:
                return jsonify({"message": "Order found. Ready to record."}), 200
            else:
                cursor.execute('''
                    INSERT INTO orders (customer_id, order_date, subtotal_before_discount, item_discount_total, total_amount, status, payment_status, tracking_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (1, datetime.now().isoformat(), 0, 0, 0, 'รอดำเนินการ', 'ยังไม่ชำระ', tracking_no))
                conn.commit()
                return jsonify({"message": "Placeholder order created. Ready to record."}), 201
    except Exception as e:
        # get_db context manager จะ handle rollback และ close เอง
        return jsonify({"error": "An error occurred with the database."}), 500

@evidence_bp.route('/orders/api/upload_pack_evidence', methods=['POST'])
def upload_pack_evidence():
    if 'order_id' not in request.form or 'file' not in request.files:
        return jsonify({"error": "Missing order_id or file"}), 400

    file = request.files['file']
    order_identifier = request.form['order_id'] # นี่คือ tracking_no

    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file"}), 400

    # --- แก้ไข: เปลี่ยนมาใช้ with get_db() ---
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM orders WHERE tracking_no = ?", (order_identifier,))
            order = cursor.fetchone()

            if not order:
                return jsonify({"error": f"Order with identifier '{order_identifier}' not found."}), 404

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            safe_order_id = secure_filename(order_identifier)
            new_filename = f"pack_evidence_{safe_order_id}_{timestamp}.mp4"
            upload_folder = current_app.config['EVIDENCE_UPLOAD_FOLDER']
            filepath = os.path.join(upload_folder, new_filename)
            file.save(filepath)

            new_status = 'กำลังจัดส่ง'
            cursor.execute("UPDATE orders SET pack_video_filename = ?, status = ? WHERE tracking_no = ?", (new_filename, new_status, order_identifier))
            conn.commit()
            return jsonify({"message": "Evidence uploaded and status updated.", "filename": new_filename, "new_status": new_status}), 200
    except Exception as e:
        # get_db context manager จะ handle rollback และ close เอง
        return jsonify({"error": "An error occurred with the database."}), 500


@evidence_bp.route('/evidence/video/<path:filename>')
def serve_video(filename):
    upload_folder = current_app.config['EVIDENCE_UPLOAD_FOLDER']
    return send_from_directory(upload_folder, filename)
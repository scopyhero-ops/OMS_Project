from flask import Blueprint, render_template, flash
from .utils import login_required
from database import get_db
import traceback
from datetime import date

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@dashboard_bp.route('/', methods=['GET'])
@login_required
def view_dashboard():
    # สร้างตัวแปรเริ่มต้น
    operational_data = {}
    chart_data = {}
    product_performance = []

    try:
        with get_db() as conn:
            c = conn.cursor()
            
            # --- 1. Operational Data (ข้อมูลสำหรับจัดการด่วน) ---
            today_str = date.today().isoformat()
            
            todays_sales = c.execute("SELECT SUM(total_amount) FROM orders WHERE DATE(paid_time) = ?", (today_str,)).fetchone()[0] or 0
            todays_orders_count = c.execute("SELECT COUNT(id) FROM orders WHERE DATE(order_date) = ?", (today_str,)).fetchone()[0] or 0
            pending_shipment_count = c.execute("SELECT COUNT(id) FROM orders WHERE status = 'Awaiting Shipment'").fetchone()[0] or 0
            
            orders_to_ship = c.execute("""
                SELECT o.id, c.first_name, o.order_date FROM orders o
                JOIN customers c ON o.customer_id = c.id
                WHERE o.status = 'Awaiting Shipment' ORDER BY o.order_date ASC LIMIT 5
            """).fetchall()
            
            low_stock_products = c.execute("""
                SELECT id, name, sku, stock FROM products
                WHERE stock < 10 AND stock > 0 ORDER BY stock ASC LIMIT 5
            """).fetchall()

            operational_data = {
                'todays_sales': todays_sales,
                'todays_orders_count': todays_orders_count,
                'pending_shipment_count': pending_shipment_count,
                'orders_to_ship': orders_to_ship,
                'low_stock_products': low_stock_products
            }

            # --- 2. BI Data (ข้อมูลวิเคราะห์ภาพรวม) ---
            sales_trend_rows = c.execute('''
                SELECT DATE(paid_time) as day, SUM(total_amount) as revenue
                FROM orders WHERE paid_time IS NOT NULL AND status != 'Cancelled'
                GROUP BY day ORDER BY day DESC LIMIT 30
            ''').fetchall()
            sales_trend_rows.reverse()
            
            sales_by_channel = c.execute('''
                SELECT sc.name, SUM(o.total_amount) as revenue
                FROM orders o JOIN sales_channels sc ON o.sales_channel_id = sc.id
                WHERE o.status != 'Cancelled' AND o.payment_status = 'ชำระแล้ว'
                GROUP BY sc.name ORDER BY revenue DESC
            ''').fetchall()

            chart_data = {
                'sales_trend': {
                    'labels': [row['day'] for row in sales_trend_rows],
                    'data': [row['revenue'] or 0 for row in sales_trend_rows]
                },
                'sales_by_channel': {
                    'labels': [row['name'] for row in sales_by_channel],
                    'data': [row['revenue'] or 0 for row in sales_by_channel]
                }
            }

            product_performance = c.execute('''
                SELECT p.name, p.sku, SUM(oi.quantity) as units_sold, 
                       SUM(oi.quantity * oi.unit_price) as total_revenue,
                       SUM(oi.quantity * p.cost) as total_cogs,
                       (SUM(oi.quantity * oi.unit_price) - SUM(oi.quantity * p.cost)) as gross_profit
                FROM products p 
                JOIN order_items oi ON p.id = oi.product_id 
                JOIN orders o ON oi.order_id = o.id
                WHERE o.status = 'Completed' OR o.status = 'Shipped'
                GROUP BY p.id 
                ORDER BY gross_profit DESC
            ''').fetchall()

    except Exception as e:
        traceback.print_exc()
        flash(f'เกิดข้อผิดพลาดในการดึงข้อมูลแดชบอร์ด: {e}', 'danger')
        # กำหนดค่าเริ่มต้นให้ครบทุก key ที่ template ต้องการ
        operational_data = {
            'todays_sales': 0,
            'todays_orders_count': 0,
            'pending_shipment_count': 0,
            'orders_to_ship': [],
            'low_stock_products': []
        }
        chart_data = {
            'sales_trend': {'labels': [], 'data': []},
            'sales_by_channel': {'labels': [], 'data': []}
        }
        product_performance = []

    return render_template('dashboard.html', 
                           operational_data=operational_data,
                           chart_data=chart_data, 
                           product_performance=product_performance)
from flask import Blueprint

# Import Blueprints from their respective files
from .auth import auth_bp
from .customer import customer_bp
from .product import product_bp
from .order import order_bp
from .settings import settings_bp
from .evidence import evidence_bp 
from .automation import automation_bp 
from .dashboard import dashboard_bp
from .debug import debug_bp
# 1. เพิ่มการ import finance_bp เข้ามา
from .finance import finance_bp 

def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(evidence_bp)
    app.register_blueprint(automation_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(debug_bp)
    # 2. เพิ่มการลงทะเบียน finance_bp
    app.register_blueprint(finance_bp)
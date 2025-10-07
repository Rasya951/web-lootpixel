from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from . import db

# ========================
# Produk Planner
# ========================
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    product_id = db.Column(db.Integer, unique=True, nullable=False)  # ID khusus, digunakan sebagai prefix file
    pdf_filename = db.Column(db.String(200), nullable=True)          # Final PDF planner
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# Kode Akses
# ========================
class AccessCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)     # Format: 1-ABCD12
    product_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='not used')            # 'not used' / 'used'
    user_email = db.Column(db.String(100), nullable=True)
    used_at = db.Column(db.DateTime, nullable=True)

# ========================
# Log Unduhan
# ========================
class DownloadLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_code = db.Column(db.String(50), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    user_email = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# Admin Login
# ========================
class AdminUser(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ========================
# Layout Template PDF (digunakan untuk builder)
# ========================
class LayoutTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    layout_type = db.Column(db.String(50), nullable=False)       # Contoh: 'weekly', 'daily'
    option_name = db.Column(db.String(100), nullable=False)      # Contoh: 'boxed', 'hourly'
    pdf_path = db.Column(db.String(255), nullable=False)         # Path ke PDF
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
# ========================
# Mapping Etsy Listing ke Product ID
# ========================
class EtsyMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    etsy_listing_id = db.Column(db.String(50), nullable=False, unique=True)
    product_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
# ========================
# Aset Produk (untuk manajemen aset yang lebih baik)
# ========================
class ProductAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False)
    asset_type = db.Column(db.String(50), nullable=False)  # 'ring', 'tab', 'layout', etc
    orientation = db.Column(db.String(20), nullable=False)  # 'portrait', 'landscape'
    name = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), nullable=True)
    order = db.Column(db.Integer, default=0)  # Untuk urutan tampilan
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# Koordinat dari file SVG builder
# ========================
class SVGElement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False)
    layout_type = db.Column(db.String(50), nullable=False)       # 'weekly' / 'daily'
    option_name = db.Column(db.String(100), nullable=False)      # 'boxed', 'hourly', dll
    name = db.Column(db.String(200), nullable=False)             # Nama anchor
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    width = db.Column(db.Float, nullable=True)                   # Lebar elemen
    height = db.Column(db.Float, nullable=True)                  # Tinggi elemen
    element_type = db.Column(db.String(20), default='text')      # 'text', 'rect', dll
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========================
# Data hyperlink dari PDF (diekstrak via fitz / PyMuPDF)
# ========================
class LayoutHyperlink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    layout_type = db.Column(db.String(50), nullable=False)       # 'weekly', 'daily', dll
    layout_name = db.Column(db.String(100), nullable=False)      # 'boxed', 'hourly', dll
    page = db.Column(db.Integer, nullable=False)
    x = db.Column(db.Float, nullable=False)
    y = db.Column(db.Float, nullable=False)
    width = db.Column(db.Float, nullable=False)
    height = db.Column(db.Float, nullable=False)
    destination = db.Column(db.String(200), nullable=False)      # Bisa angka atau label halaman
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

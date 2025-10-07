import os
import random
import string
import json
from functools import wraps
from flask import Blueprint, request, render_template, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import text  # Tambahan untuk raw SQL
from .models import Product, AccessCode, LayoutHyperlink, ProductAsset, EtsyMapping
from . import db
from .utils import save_svg_coordinates, extract_pdf_links

admin = Blueprint('admin', __name__, url_prefix='/admin')

# ================= Middleware =================
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash("Silakan login dulu 😅")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# ================= Dashboard =================
@admin.route('/')
@admin_required
def admin_root():
    return redirect(url_for('admin.dashboard'))

@admin.route('/dashboard')
@admin_required
def dashboard():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/dashboard.html', products=products)

# ================= Upload Produk =================
@admin.route('/upload', methods=['GET', 'POST'])
@admin_required
def upload_product():
    if request.method == 'POST':
        name = request.form['name']
        product_id = int(request.form['product_id'])
        description = request.form['description']
        kode_jumlah = int(request.form['kode_jumlah'])
        final_pdf = request.files.get('final_pdf')

        # Simpan PDF planner
        pdf_filename = None
        if final_pdf and final_pdf.filename:
            pdf_folder = 'static/pdfs'
            os.makedirs(pdf_folder, exist_ok=True)
            pdf_filename = f"{product_id}_planner.pdf"
            final_pdf.save(os.path.join(pdf_folder, pdf_filename))

        # Simpan ke DB
        product = Product(
            name=name,
            product_id=product_id,
            description=description,
            pdf_filename=pdf_filename
        )
        db.session.add(product)
        db.session.commit()

        # Helper Simpan File Biasa
        def save_files(file_list, orientation, folder_name, prefix, layout_type=None):
            folder_path = os.path.join('static/assets', str(product_id), orientation, folder_name)
            os.makedirs(folder_path, exist_ok=True)
            for file in file_list:
                if file.filename:
                    filename = secure_filename(file.filename)
                    full_name = f"{prefix}_{filename}"
                    file_path = os.path.join(folder_path, full_name)
                    file.save(file_path)

                    # Simpan koordinat kalau SVG layout
                    if folder_name == 'layouts' and filename.endswith('.svg'):
                        option_name = filename.replace('.svg', '').replace(f"{prefix}_", "")
                        save_svg_coordinates(
                            product_id=product_id,
                            layout_type=layout_type,
                            option_name=option_name,
                            svg_path=file_path
                        )

        # Simpan RING, TAB, LAYOUTS
        for orientation in ['portrait', 'landscape']:
            if orientation == 'landscape':
                save_files(request.files.getlist(f'{orientation}_ring'), orientation, 'rings', f"{product_id}_ring")
            save_files(request.files.getlist(f'{orientation}_tab'), orientation, 'tabs', f"{product_id}_tab")
            save_files(request.files.getlist(f'{orientation}_layout_weekly'), orientation, 'layouts', 'weekly', layout_type='weekly')
            save_files(request.files.getlist(f'{orientation}_layout_daily'), orientation, 'layouts', 'daily', layout_type='daily')

        # Simpan BULANAN ke folder + DB
        def save_monthly_assets(field_name, orientation, start_day):
            files = request.files.getlist(field_name)
            folder_path = os.path.join('static/assets', str(product_id), orientation, 'monthly', start_day)
            os.makedirs(folder_path, exist_ok=True)
            for f in files:
                if f and f.filename:
                    filename = secure_filename(f.filename)
                    f.save(os.path.join(folder_path, filename))
                    try:
                        month_number = int(filename.split('.')[0])  # misalnya 01.png → 1
                        db.session.execute(text("""
                            INSERT INTO monthly_layouts (product_id, orientation, start_day, month_number, filename)
                            VALUES (:product_id, :orientation, :start_day, :month_number, :filename)
                        """), {
                            "product_id": product_id,
                            "orientation": orientation,
                            "start_day": start_day,
                            "month_number": month_number,
                            "filename": filename
                        })
                    except ValueError:
                        flash(f"⚠️ Gagal simpan monthly: nama file tidak valid → {filename}")

        monthly_sets = [
            ('portrait_monthly_monday', 'portrait', 'monday'),
            ('portrait_monthly_sunday', 'portrait', 'sunday'),
            ('landscape_monthly_monday', 'landscape', 'monday'),
            ('landscape_monthly_sunday', 'landscape', 'sunday'),
        ]
        for field_name, ori, day in monthly_sets:
            save_monthly_assets(field_name, ori, day)

        # Generate kode akses
        for _ in range(kode_jumlah):
            code = f"{product_id}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            db.session.add(AccessCode(code=code, product_id=product_id))

        db.session.commit()
        flash("Produk dan semua aset berhasil di-upload ✅")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/upload_form.html')

# ================= Upload Layout Hyperlink =================
@admin.route('/upload_layout_hyperlink', methods=['GET', 'POST'])
@admin_required
def upload_layout_hyperlink():
    if request.method == 'POST':
        layout_type = request.form['layout_type']
        layout_name = request.form['layout_name']
        pdf_file = request.files.get('pdf_file')

        if not pdf_file or not pdf_file.filename.endswith('.pdf'):
            flash("File tidak valid (harus PDF)", 'error')
            return redirect(url_for('admin.upload_layout_hyperlink'))

        folder_path = os.path.join('static', 'layout_templates', layout_type)
        os.makedirs(folder_path, exist_ok=True)
        filename = secure_filename(pdf_file.filename)
        save_path = os.path.join(folder_path, filename)
        pdf_file.save(save_path)

        LayoutHyperlink.query.filter_by(layout_type=layout_type, layout_name=layout_name).delete()
        hyperlinks = extract_pdf_links(save_path)
        for link in hyperlinks:
            db.session.add(LayoutHyperlink(
                layout_type=layout_type,
                layout_name=layout_name,
                page=link['page'],
                x=link['x'],
                y=link['y'],
                width=link['width'],
                height=link['height'],
                destination=link['destination']
            ))
        db.session.commit()
        flash("Berhasil upload dan ekstrak hyperlink ✅")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/upload_layout_hyperlink.html')

# ================= Edit Produk =================
@admin.route('/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        db.session.commit()
        flash("Produk berhasil diperbarui ✏️")
        return redirect(url_for('admin.dashboard'))
    return render_template('admin/edit_product.html', product=product)

# ================= Hapus Produk =================
@admin.route('/delete_product/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    product = Product.query.filter_by(product_id=product_id).first_or_404()

    if product.pdf_filename:
        try:
            os.remove(os.path.join('static/pdfs', product.pdf_filename))
        except FileNotFoundError:
            pass

    asset_root = os.path.join('static/assets', str(product.product_id))
    if os.path.exists(asset_root):
        for root, dirs, files in os.walk(asset_root, topdown=False):
            for file in files:
                try:
                    os.remove(os.path.join(root, file))
                except FileNotFoundError:
                    pass
            for dir in dirs:
                try:
                    os.rmdir(os.path.join(root, dir))
                except OSError:
                    pass
        try:
            os.rmdir(asset_root)
        except OSError:
            pass

    AccessCode.query.filter_by(product_id=product.product_id).delete()
    db.session.delete(product)
    db.session.commit()

    flash("Produk dan seluruh aset berhasil dihapus ❌")
    return redirect(url_for('admin.dashboard'))

# ================= Reset Kode Akses =================
@admin.route('/reset_codes/<int:product_id>', methods=['POST'])
@admin_required
def reset_codes(product_id):
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    AccessCode.query.filter_by(product_id=product_id).delete()

    for _ in range(10):
        code = f"{product_id}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        db.session.add(AccessCode(code=code, product_id=product_id))

    db.session.commit()
    flash("Kode akses berhasil di-reset 🔁")
    return redirect(url_for('admin.dashboard'))

# ================= Lihat Kode Akses =================
@admin.route('/access_codes/<int:product_id>')
@admin_required
def access_codes(product_id):
    product = Product.query.filter_by(product_id=product_id).first_or_404()
    codes = AccessCode.query.filter_by(product_id=product_id).all()
    return render_template('admin/access_codes.html', product=product, codes=codes)

# ================= API Aset Produk =================
@admin.route('/api/assets', methods=['GET'])
@admin_required
def get_assets():
    """API untuk mendapatkan daftar aset produk"""
    product_id = request.args.get('product_id')
    asset_type = request.args.get('asset_type')
    orientation = request.args.get('orientation')
    
    query = ProductAsset.query
    
    if product_id:
        query = query.filter_by(product_id=int(product_id))
    if asset_type:
        query = query.filter_by(asset_type=asset_type)
    if orientation:
        query = query.filter_by(orientation=orientation)
    
    assets = query.order_by(ProductAsset.order).all()
    
    result = [{
        'id': asset.id,
        'product_id': asset.product_id,
        'asset_type': asset.asset_type,
        'orientation': asset.orientation,
        'name': asset.name,
        'display_name': asset.display_name,
        'file_path': asset.file_path,
        'order': asset.order
    } for asset in assets]
    
    return jsonify(result)

@admin.route('/api/assets', methods=['POST'])
@admin_required
def add_asset():
    """API untuk menambahkan aset produk baru"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    # Validasi data
    product_id = request.form.get('product_id')
    asset_type = request.form.get('asset_type')
    orientation = request.form.get('orientation')
    name = request.form.get('name')
    display_name = request.form.get('display_name')
    
    if not all([product_id, asset_type, orientation, name]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        product_id = int(product_id)
    except ValueError:
        return jsonify({'error': 'Invalid product ID'}), 400
    
    # Simpan file
    filename = secure_filename(file.filename)
    folder_path = os.path.join('static/assets', str(product_id), orientation, asset_type)
    os.makedirs(folder_path, exist_ok=True)
    file_path = os.path.join(folder_path, filename)
    file.save(file_path)
    
    # Simpan metadata ke database
    asset = ProductAsset(
        product_id=product_id,
        asset_type=asset_type,
        orientation=orientation,
        name=name,
        display_name=display_name or name,
        file_path=file_path,
        order=request.form.get('order', 0)
    )
    
    db.session.add(asset)
    db.session.commit()
    
    return jsonify({
        'id': asset.id,
        'product_id': asset.product_id,
        'asset_type': asset.asset_type,
        'orientation': asset.orientation,
        'name': asset.name,
        'display_name': asset.display_name,
        'file_path': asset.file_path,
        'order': asset.order
    }), 201

# ================= API Etsy Mapping =================
@admin.route('/api/etsy-mapping', methods=['GET'])
@admin_required
def get_etsy_mappings():
    """API untuk mendapatkan daftar mapping Etsy listing ke product ID"""
    mappings = EtsyMapping.query.all()
    
    result = [{
        'id': mapping.id,
        'etsy_listing_id': mapping.etsy_listing_id,
        'product_id': mapping.product_id
    } for mapping in mappings]
    
    return jsonify(result)

@admin.route('/api/etsy-mapping', methods=['POST'])
@admin_required
def add_etsy_mapping():
    """API untuk menambahkan mapping Etsy listing ke product ID"""
    data = request.json
    
    if not data or 'etsy_listing_id' not in data or 'product_id' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    etsy_listing_id = data['etsy_listing_id']
    product_id = data['product_id']
    
    # Cek apakah mapping sudah ada
    existing = EtsyMapping.query.filter_by(etsy_listing_id=etsy_listing_id).first()
    if existing:
        existing.product_id = product_id
        db.session.commit()
        return jsonify({
            'id': existing.id,
            'etsy_listing_id': existing.etsy_listing_id,
            'product_id': existing.product_id
        })
    
    # Buat mapping baru
    mapping = EtsyMapping(
        etsy_listing_id=etsy_listing_id,
        product_id=product_id
    )
    
    db.session.add(mapping)
    db.session.commit()
    
    return jsonify({
        'id': mapping.id,
        'etsy_listing_id': mapping.etsy_listing_id,
        'product_id': mapping.product_id
    }), 201

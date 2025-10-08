from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
from flask_login import current_user, login_required
from app.models import AccessCode, DownloadLog, Product, GeneratedPlanner, User
from app.utils import generate_planner_pdf, get_product_id_from_code, send_access_code_email, verify_etsy_signature
from app import db, mail
from datetime import datetime
import os
import fitz  # PyMuPDF
import random
import string
import hmac
import hashlib
import uuid

main = Blueprint('main', __name__)

def generate_preview(pdf_path, output_png_path):
    """Generate PNG preview dari halaman pertama PDF."""
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(150/72, 150/72))  # Render dengan DPI 150
    pix.save(output_png_path)
    doc.close()

def list_assets_clean(base_path):
    """List semua file gambar di folder tanpa ekstensi."""
    if os.path.exists(base_path):
        return sorted(set(
            os.path.splitext(f)[0]
            for f in os.listdir(base_path)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg'))
        ))
    return []

def list_layouts_clean(base_path, prefixes):
    """List layout (weekly/daily) dan hapus prefix tertentu."""
    if not os.path.exists(base_path):
        return []
    items = set()
    for f in os.listdir(base_path):
        if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg')):
            continue
        fname = os.path.splitext(f)[0]
        for pref in prefixes:
            if fname.lower().startswith(pref.lower()):
                val = fname[len(pref):] if fname.lower().startswith(pref.lower()) else fname
                val = val.lstrip('_-')  # hilangkan _ atau - di awal
                items.add(val)
                break
    return sorted(items)

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/api/etsy-webhook', methods=['POST'])
def etsy_webhook():
    # Verifikasi signature dari Etsy untuk keamanan
    etsy_signature = request.headers.get('X-Etsy-Signature')
    if not verify_etsy_signature(etsy_signature, request.data):
        return jsonify({'error': 'Invalid signature'}), 401
    
    data = request.json
    # Proses data pembelian dari Etsy
    if data.get('event_type') == 'listing.purchase':
        # Ekstrak informasi penting
        receipt_id = data.get('receipt_id')
        buyer_email = data.get('buyer_email')
        listing_id = data.get('listing_id')
        
        # Cari product_id yang sesuai dengan listing Etsy
        from app.models import EtsyMapping
        mapping = EtsyMapping.query.filter_by(etsy_listing_id=str(listing_id)).first()
        
        if not mapping:
            # Fallback ke mapping default jika tidak ditemukan
            product_id = map_etsy_listing_to_product_id(listing_id)
        else:
            product_id = mapping.product_id
        
        if not product_id:
            return jsonify({'error': 'Unknown product mapping'}), 400
        
        # Generate kode akses unik
        access_code = f"{product_id}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"
        
        # Simpan ke database
        new_code = AccessCode(
            code=access_code,
            product_id=product_id,
            user_email=buyer_email,
            status='not used'
        )
        db.session.add(new_code)
        db.session.commit()
        
        # Kirim email ke pembeli
        send_access_code_email(buyer_email, access_code)
        
        return jsonify({
            'success': True,
            'message': f'Access code generated and sent to {buyer_email}'
        }), 200
    
    return jsonify({'error': 'Unsupported event type'}), 400

# Fungsi helper untuk mapping Etsy listing ke product_id
def map_etsy_listing_to_product_id(listing_id):
    """Map listing ID Etsy ke product_id internal"""
    # Mapping sederhana, sebaiknya dipindahkan ke database
    mapping = {
        '123456789': 1,  # Etsy listing ID : product_id internal
        '987654321': 2,
        # Tambahkan mapping lainnya
    }
    return mapping.get(str(listing_id))

@main.route('/access', methods=['GET', 'POST'])
def access():
    # Jika user sudah login, redirect ke dashboard
    if current_user.is_authenticated:
        return redirect(url_for('user.dashboard'))
        
    if request.method == 'POST':
        access_code = request.form.get('access_code')
        
        # Validasi kode akses
        code = AccessCode.query.filter_by(code=access_code).first()
        
        if not code:
            flash('Kode akses tidak valid', 'danger')
            return redirect(url_for('main.access'))
            
        if code.status == 'used' or code.status == 'claimed':
            flash('Kode akses sudah digunakan', 'warning')
            return redirect(url_for('main.access'))
            
        # Simpan kode akses di session
        session['access_code'] = access_code
        session['product_id'] = code.product_id
        
        # Update status kode akses
        code.status = 'used'
        code.used_at = datetime.utcnow()
        db.session.commit()
        
        # Redirect ke halaman builder
        return redirect(url_for('main.builder', product_id=code.product_id))
        
    return render_template('access.html')

@main.route('/builder/<int:product_id>')
def builder(product_id):
    # Cek apakah user memiliki akses
    has_access = False
    
    # Jika user login, cek apakah memiliki akses ke produk
    if current_user.is_authenticated:
        product = Product.query.filter_by(product_id=product_id).first()
        if product in current_user.products:
            has_access = True
    # Jika tidak login, cek dari session
    elif session.get('access_code') and session.get('product_id') == product_id:
        has_access = True
        
    if not has_access:
        flash('Anda tidak memiliki akses ke produk ini', 'danger')
        return redirect(url_for('main.access'))
    
    # Ambil data produk
    product = Product.query.filter_by(product_id=product_id).first()
    
    if not product:
        flash('Produk tidak ditemukan', 'danger')
        return redirect(url_for('main.index'))

    # (BAGIAN YANG DIPERBAIKI)
    # Langsung gunakan builder statis berbasis file aset
    base_path = f"app/static/assets/{product_id}"
    
    rings = list_assets_clean(f"{base_path}/landscape/rings")
    tabs = list_assets_clean(f"{base_path}/portrait/tabs") or list_assets_clean(f"{base_path}/landscape/tabs")
    
    weekly_layouts = list_layouts_clean(f"{base_path}/portrait/weekly", ["weekly_"]) or \
                    list_layouts_clean(f"{base_path}/landscape/weekly", ["weekly_"])
                    
    daily_layouts = list_layouts_clean(f"{base_path}/portrait/daily", ["daily_"]) or \
                   list_layouts_clean(f"{base_path}/landscape/daily", ["daily_"])
    
    return render_template('builder.html', 
                          product_id=product_id,
                          rings=rings,
                          tabs=tabs,
                          weekly_layouts=weekly_layouts,
                          daily_layouts=daily_layouts)
@main.route('/build', methods=['POST'])
def build():
    data = request.json
    
    # Validasi data
    required_fields = ['orientation', 'tab', 'weekly_layout', 'start_day', 'product_id']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'Field {field} is required'}), 400
    
    # Buat nama file unik
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"{data['product_id']}-{unique_id}-{timestamp}.pdf"
    output_path = os.path.join('app/static/pdfs', filename)
    
    # Generate PDF
    try:
        generate_planner_pdf({
            'product_id': data['product_id'],
            'orientation': data['orientation'],
            'ring': data.get('ring', ''),
            'tab': data['tab'],
            'weekly_layout': data['weekly_layout'],
            'daily_layout': data.get('daily_layout', ''),
            'start_day': data['start_day']
        }, output_path)
        
        # Jika user login, simpan planner ke database
        if current_user.is_authenticated:
            new_planner = GeneratedPlanner(
                user_id=current_user.id,
                product_id=data['product_id'],
                orientation=data['orientation'],
                ring=data.get('ring', ''),
                tab=data['tab'],
                weekly_layout=data['weekly_layout'],
                daily_layout=data.get('daily_layout', ''),
                start_day=data['start_day'],
                pdf_filename=filename
            )
            db.session.add(new_planner)
            db.session.commit()
        
        # Simpan ke session untuk user yang tidak login
        else:
            session['generated_pdf'] = filename
        
        # Catat log unduhan
        user_email = current_user.email if current_user.is_authenticated else "guest"
        access_code = session.get('access_code')
        
        download_log = DownloadLog(
            access_code=access_code,
            product_id=data['product_id'],
            user_id=current_user.id if current_user.is_authenticated else None,
            user_email=user_email
        )
        db.session.add(download_log)
        db.session.commit()
        
        return jsonify({'filename': filename})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@main.route('/download/<filename>')
def download_file(filename):
    return send_from_directory('static/pdfs', filename, as_attachment=True)

@main.route('/preview')
def preview():
    if not session.get('access_granted'):
        flash("Silakan masukkan kode akses terlebih dahulu.")
        return redirect(url_for('main.access'))

    access_code = session.get('access_code')
    product_id = get_product_id_from_code(access_code)

    if not product_id:
        flash("Kode akses tidak valid.")
        return redirect(url_for('main.access'))

    orientation = session.get('orientation', 'portrait')
    ring = request.args.get('ring', '')
    tab = request.args.get('tab', '')
    weekly_layout = request.args.get('weekly_layout', '')
    daily_layout = request.args.get('daily_layout', '')
    start_day = request.args.get('start_day', '')
    
    # Generate filenames based on session data
    timestamp = int(datetime.now().timestamp())
    pdf_filename = f"planner_{timestamp}.pdf"
    png_filename = f"preview_{timestamp}.png"
    
    # Get assets for the product
    assets = list_assets_clean(product_id, orientation)
    layouts = list_layouts_clean(product_id, orientation)
    
    # Generate PDF
    pdf_path = os.path.join('static', 'pdfs', pdf_filename)
    os.makedirs(os.path.join('static', 'pdfs'), exist_ok=True)
    
    generate_planner_pdf({
        'product_id': product_id,
        'orientation': orientation,
        'ring': ring,
        'tab': tab,
        'weekly_layout': weekly_layout,
        'daily_layout': daily_layout,
        'start_day': start_day
    }, pdf_path)
    
    # Generate PNG preview
    preview_path = os.path.join('static', 'previews', png_filename)
    os.makedirs(os.path.join('static', 'previews'), exist_ok=True)
    generate_preview(pdf_path, preview_path)
    
    data = {
        'product_id': product_id,
        'orientation': orientation,
        'ring': ring,
        'tab': tab,
        'weekly_layout': weekly_layout,
        'daily_layout': daily_layout,
        'start_day': start_day,
        'pdf_filename': pdf_filename,
        'png_filename': png_filename
    }

    return render_template('preview.html', data=data)

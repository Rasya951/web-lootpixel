from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Product, AccessCode, SavedPlanner, user_products
from . import db
from datetime import datetime

user = Blueprint('user', __name__)

@user.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        access_code = request.form.get('access_code', '').strip()
        
        # Validasi input
        if not email or not username or not password:
            flash('Semua field harus diisi', 'danger')
            return redirect(url_for('user.register'))
            
        if password != confirm_password:
            flash('Password tidak cocok', 'danger')
            return redirect(url_for('user.register'))
            
        # Cek apakah email atau username sudah terdaftar
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar', 'danger')
            return redirect(url_for('user.register'))
            
        if User.query.filter_by(username=username).first():
            flash('Username sudah digunakan', 'danger')
            return redirect(url_for('user.register'))
        
        # Buat user baru
        new_user = User(email=email, username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Jika ada kode akses, tambahkan produk ke akun user
        if access_code:
            access = AccessCode.query.filter_by(code=access_code).first()
            if access and access.status != 'used':
                # Cari produk berdasarkan product_id
                product = Product.query.filter_by(product_id=access.product_id).first()
                if product:
                    # Tambahkan produk ke user
                    new_user.products.append(product)
                    
                    # Update status kode akses
                    access.status = 'used'
                    access.used_at = datetime.utcnow()
                    access.user_id = new_user.id
                    
                    db.session.commit()
                    flash(f'Produk {product.name} berhasil ditambahkan ke akun Anda', 'success')
        
        flash('Registrasi berhasil! Silakan login', 'success')
        return redirect(url_for('user.login'))
        
    return render_template('user/register.html')

@user.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_username = request.form.get('email_or_username')
        password = request.form.get('password')
        
        # Cari user berdasarkan email atau username
        user = User.query.filter((User.email == email_or_username) | 
                                (User.username == email_or_username)).first()
        
        if user and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash('Login berhasil!', 'success')
            return redirect(url_for('user.dashboard'))
        else:
            flash('Email/username atau password salah', 'danger')
            
    return render_template('user/login.html')

@user.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout berhasil', 'info')
    return redirect(url_for('main.index'))

@user.route('/dashboard')
@login_required
def dashboard():
    # Ambil semua produk yang dimiliki user
    user_products = current_user.products
    
    # Ambil semua planner yang disimpan user
    saved_planners = SavedPlanner.query.filter_by(user_id=current_user.id).all()
    
    return render_template('user/dashboard.html', 
                          products=user_products,
                          saved_planners=saved_planners)

@user.route('/add-product', methods=['POST'])
@login_required
def add_product():
    access_code = request.form.get('access_code', '').strip()
    
    if not access_code:
        flash('Kode akses tidak boleh kosong', 'danger')
        return redirect(url_for('user.dashboard'))
    
    # Cek kode akses
    access = AccessCode.query.filter_by(code=access_code).first()
    
    if not access:
        flash('Kode akses tidak valid', 'danger')
        return redirect(url_for('user.dashboard'))
        
    if access.status == 'used':
        flash('Kode akses sudah digunakan', 'danger')
        return redirect(url_for('user.dashboard'))
    
    # Cari produk berdasarkan product_id
    product = Product.query.filter_by(product_id=access.product_id).first()
    
    if not product:
        flash('Produk tidak ditemukan', 'danger')
        return redirect(url_for('user.dashboard'))
    
    # Cek apakah user sudah memiliki produk ini
    if product in current_user.products:
        flash('Anda sudah memiliki produk ini', 'warning')
        return redirect(url_for('user.dashboard'))
    
    # Tambahkan produk ke user
    current_user.products.append(product)
    
    # Update status kode akses
    access.status = 'used'
    access.used_at = datetime.utcnow()
    access.user_id = current_user.id
    
    db.session.commit()
    
    flash(f'Produk {product.name} berhasil ditambahkan', 'success')
    return redirect(url_for('user.dashboard'))

@user.route('/save-planner', methods=['POST'])
@login_required
def save_planner():
    data = request.get_json()
    
    # Validasi input
    required_fields = ['product_id', 'name', 'orientation', 'tab', 'weekly_layout', 'start_day']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({'error': f'Field {field} harus diisi'}), 400
    
    # Cek apakah user memiliki akses ke produk ini
    product = Product.query.filter_by(product_id=data['product_id']).first()
    if not product or product not in current_user.products:
        return jsonify({'error': 'Anda tidak memiliki akses ke produk ini'}), 403
    
    # Buat atau update saved planner
    planner_id = data.get('planner_id')
    if planner_id:
        # Update existing planner
        planner = SavedPlanner.query.filter_by(id=planner_id, user_id=current_user.id).first()
        if not planner:
            return jsonify({'error': 'Planner tidak ditemukan'}), 404
            
        planner.name = data['name']
        planner.orientation = data['orientation']
        planner.ring = data.get('ring', '')
        planner.tab = data['tab']
        planner.weekly_layout = data['weekly_layout']
        planner.daily_layout = data.get('daily_layout', '')
        planner.start_day = data['start_day']
        planner.updated_at = datetime.utcnow()
    else:
        # Create new planner
        planner = SavedPlanner(
            user_id=current_user.id,
            product_id=data['product_id'],
            name=data['name'],
            orientation=data['orientation'],
            ring=data.get('ring', ''),
            tab=data['tab'],
            weekly_layout=data['weekly_layout'],
            daily_layout=data.get('daily_layout', ''),
            start_day=data['start_day']
        )
        db.session.add(planner)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'planner_id': planner.id,
        'message': 'Planner berhasil disimpan'
    })

@user.route('/delete-planner/<int:planner_id>', methods=['POST'])
@login_required
def delete_planner(planner_id):
    planner = SavedPlanner.query.filter_by(id=planner_id, user_id=current_user.id).first()
    
    if not planner:
        flash('Planner tidak ditemukan', 'danger')
        return redirect(url_for('user.dashboard'))
    
    db.session.delete(planner)
    db.session.commit()
    
    flash('Planner berhasil dihapus', 'success')
    return redirect(url_for('user.dashboard'))

@user.route('/load-planner/<int:planner_id>')
@login_required
def load_planner(planner_id):
    planner = SavedPlanner.query.filter_by(id=planner_id, user_id=current_user.id).first()
    
    if not planner:
        return jsonify({'error': 'Planner tidak ditemukan'}), 404
    
    return jsonify({
        'product_id': planner.product_id,
        'name': planner.name,
        'orientation': planner.orientation,
        'ring': planner.ring,
        'tab': planner.tab,
        'weekly_layout': planner.weekly_layout,
        'daily_layout': planner.daily_layout,
        'start_day': planner.start_day
    })
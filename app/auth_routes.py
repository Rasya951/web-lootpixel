from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from .models import AdminUser
from . import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = AdminUser.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            session['admin_logged_in'] = True  # ✅ simpan login di session
            flash('Berhasil login!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Username atau password salah', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('admin/login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('admin_logged_in', None)  # ✅ hapus session login admin
    flash('Berhasil logout 👋', 'info')
    return redirect(url_for('auth.login'))

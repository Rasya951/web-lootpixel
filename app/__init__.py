from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_cors import CORS
from flask_login import LoginManager
from datetime import datetime

db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Konfigurasi dasar aplikasi
    app.config['SECRET_KEY'] = 'lootpixel-secret'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/lootpixel_db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Konfigurasi Mail
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'lootpixelofficial@gmail.com'
    app.config['MAIL_PASSWORD'] = '...'  # Ganti dengan password asli atau pakai env var
    app.config['MAIL_DEFAULT_SENDER'] = 'lootpixelofficial@gmail.com'

    # Inisialisasi ekstensi Flask
    db.init_app(app)
    mail.init_app(app)
    CORS(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # Load user untuk Flask-Login
    from .models import AdminUser
    @login_manager.user_loader
    def load_user(user_id):
        return AdminUser.query.get(int(user_id))

    # Register Blueprints
    from .routes import main
    from .admin_routes import admin
    from .auth_routes import auth
    app.register_blueprint(main)
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(auth)

    # Inject current_year ke semua template
    @app.context_processor
    def inject_current_year():
        return {'current_year': datetime.utcnow().year}

    return app

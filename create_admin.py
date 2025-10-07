from app import create_app, db
from app.models import AdminUser
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    username = 'Rasya951'
    password = 'muh.rasya.123a.h..'

    hashed = generate_password_hash(password, method='pbkdf2:sha256')
    print(f"[DEBUG] Password hash yang akan disimpan:\n{hashed}\n")

    existing = AdminUser.query.filter_by(username=username).first()

    if existing:
        existing.password_hash = hashed
        print(f"⚠️ Admin '{username}' sudah ada. Password-nya akan diperbarui.")
    else:
        new_admin = AdminUser(username=username, password_hash=hashed)
        db.session.add(new_admin)
        print(f"✅ Admin '{username}' berhasil dibuat.")

    db.session.commit()
    print("🔒 Password di-hash dan disimpan dengan aman.")

import sys
import os

# añadir el directorio raíz del proyecto al path para poder importar app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    username = os.environ.get('ADMIN_USERNAME')
    password = os.environ.get('ADMIN_PASSWORD')
    if not username or not password:
        raise SystemExit('Defina ADMIN_USERNAME y ADMIN_PASSWORD para crear el administrador')

    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(
            username=username,
            password=generate_password_hash(password),
            role='admin'
        )
        db.session.add(u)
        db.session.commit()
        print('administrador creado')
    else:
        if u.role != 'admin':
            u.role = 'admin'
            db.session.commit()
        print('administrador ya existe')

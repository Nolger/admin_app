# admin_app/scripts/create_admin_user.py
import os
import sys

from flask import Flask
from shared.config import Config
from shared.models import db, AdminUser # Importa AdminUser


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Crea una instancia mínima de la aplicación Flask para poder usar db
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

with app.app_context():
    username = input("Introduce el nombre de usuario para el administrador: ")
    password = input("Introduce la contraseña para el administrador: ")

    # Verifica si el usuario ya existe
    existing_user = AdminUser.query.filter_by(username=username).first()
    if existing_user:
        print(f"El usuario '{username}' ya existe. Intenta con otro nombre de usuario.")
    else:
        new_admin = AdminUser(username=username)
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        print(f"Usuario administrador '{username}' creado exitosamente.")
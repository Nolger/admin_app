# admin_app/admin_app.py

import os
import sys
from datetime import datetime
from flask import Flask, redirect, url_for, request, flash, render_template, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_socketio import SocketIO, emit, join_room

# Añadir ruta a módulos compartidos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.config import Config
from shared.models import db, Product, Order, OrderItem, AdminUser

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config)

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(AdminUser, int(user_id))

# --- Flask-Admin ---
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin_login', next=request.url))

admin = Admin(app, name='Admin Pollo Salsero', template_mode='bootstrap4', index_view=MyAdminIndexView())

class AuthenticatedModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('admin_login', next=request.url))

admin.add_view(AuthenticatedModelView(Product, db.session, name='Productos'))

class OrderAdminView(AuthenticatedModelView):
    column_list = ('id', 'customer_name', 'customer_address', 'customer_phone', 'total_amount', 'status', 'order_date')
    column_sortable_list = ('id', 'order_date', 'total_amount', 'status')
    column_filters = ('status', 'order_date')
    column_searchable_list = ('customer_name', 'customer_address', 'customer_phone')
    form_columns = ('customer_name', 'customer_address', 'customer_phone', 'total_amount', 'status', 'order_date', 'items')
    inline_models = [OrderItem]

admin.add_view(OrderAdminView(Order, db.session, name='Pedidos'))

class AdminUserView(AuthenticatedModelView):
    column_list = ('id', 'username')
    form_columns = ('username', 'password_hash')

    def on_model_change(self, form, model, is_created):
        if form.password_hash.data:
            model.set_password(form.password_hash.data)
        elif is_created:
            flash('La contraseña es requerida para nuevos usuarios.', 'error')
            raise ValueError('La contraseña es requerida para nuevos usuarios.')
        return super().on_model_change(form, model, is_created)

admin.add_view(AdminUserView(AdminUser, db.session, name='Usuarios Admin'))

# --- Rutas ---
@app.route('/')
def admin_root():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('admin_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = AdminUser.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Inicio de sesión exitoso.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin.index'))
        else:
            flash('Nombre de usuario o contraseña incorrectos.', 'danger')

    return render_template('admin_login.html')

@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    recent_orders = Order.query.order_by(Order.order_date.desc()).limit(10).all()
    return render_template('admin_dashboard.html', orders=recent_orders)

@app.route('/admin-api/new-order-notification', methods=['POST'])
def new_order_notification():
    data = request.get_json()
    order_id = data.get('order_id')
    if order_id:
        order = Order.query.get(order_id)
        if order:
            socketio.emit('new_order_alert', {
                'order_id': order.id,
                'customer_name': order.customer_name,
                'customer_phone': order.customer_phone,
                'total_amount': order.total_amount,
                'status': order.status,
                'order_date': order.order_date.isoformat()
            }, room='admin_dashboard')
            return jsonify({'message': 'Notificación procesada'}), 200
    return jsonify({'message': 'ID de pedido no proporcionado'}), 400

# --- Socket.IO ---
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room('admin_dashboard')
        emit('my_response', {'data': f'Conectado al dashboard admin. Sesión: {request.sid}'}, room=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info(f"Cliente SocketIO desconectado: {request.sid}")

@socketio.on('status_update_request')
@login_required
def handle_status_update(data):
    order_id = data.get('order_id')
    new_status = data.get('new_status')

    if order_id and new_status:
        order = db.session.get(Order, order_id)
        if order:
            order.status = new_status
            db.session.commit()
            socketio.emit('order_status_updated', {
                'order_id': order.id,
                'new_status': order.status,
                'updated_by': current_user.username
            }, room='admin_dashboard')

# --- Inicio del servidor ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)

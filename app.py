# admin_app/admin_app.py
import os
import sys
from datetime import datetime

# Añade el directorio padre (la raíz del proyecto 'chicken_restaurant_project') a sys.path
# Esto permite importar módulos desde 'shared' y otros subdirectorios como 'public_app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, redirect, url_for, request, flash, render_template, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_socketio import SocketIO, emit, join_room # Importar join_room si lo necesitas

# Importa desde el directorio compartido
from shared.config import Config
from shared.models import db, Product, Order, OrderItem, AdminUser # Importa AdminUser

# Se inicializa socketio fuera de create_app para que pueda ser accesible globalmente si es necesario,
# pero su inicialización completa se hace dentro de create_app con la instancia de 'app'.
# Esto es crucial para que `flask run` pueda detectar la aplicación y SocketIO.
socketio = SocketIO()

def create_app():
    # Inicializa la aplicación Flask
    app = Flask(__name__, static_folder='static', template_folder='templates')
    app.config.from_object(Config)

    # Inicializa SQLAlchemy con la app
    db.init_app(app)

    # Inicializa Flask-SocketIO con la app
    # Usamos async_mode='gevent' (o 'eventlet') para un mejor rendimiento en producción.
    # Si tienes problemas con gevent, puedes cambiar a async_mode='threaded' (menos eficiente).
    socketio.init_app(app, cors_allowed_origins="*", async_mode='gevent')

    # --- Configuración de Flask-Login ---
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'admin_login' # Nombre de la ruta de login para redirigir

    @login_manager.user_loader
    def load_user(user_id):
        """Callback para recargar el objeto de usuario de la ID de usuario almacenada en la sesión."""
        return db.session.get(AdminUser, int(user_id)) # Usa db.session.get para SQLAlchemy 2.0+

    # --- Configuración de Flask-Admin ---
    class MyAdminIndexView(AdminIndexView):
        """Vista de índice personalizada para Flask-Admin que requiere autenticación."""
        def is_accessible(self):
            return current_user.is_authenticated

        def inaccessible_callback(self, name, **kwargs):
            return redirect(url_for('admin_login', next=request.url))

    admin = Admin(app, name='Admin Pollo Salsero', template_mode='bootstrap4', index_view=MyAdminIndexView())

    class AuthenticatedModelView(ModelView):
        """Clase base para las vistas de modelos que requieren autenticación."""
        def is_accessible(self):
            return current_user.is_authenticated

        def inaccessible_callback(self, name, **kwargs):
            return redirect(url_for('admin_login', next=request.url))

    # Vista para Productos
    admin.add_view(AuthenticatedModelView(Product, db.session, name='Productos'))

    # Vista para Pedidos
    class OrderAdminView(AuthenticatedModelView):
        column_list = ('id', 'customer_name', 'customer_address', 'customer_phone', 'total_amount', 'status', 'order_date')
        column_sortable_list = ('id', 'order_date', 'total_amount', 'status')
        column_filters = ('status', 'order_date')
        column_searchable_list = ('customer_name', 'customer_address', 'customer_phone')
        form_columns = ('customer_name', 'customer_address', 'customer_phone', 'total_amount', 'status', 'order_date', 'items')
        inline_models = [OrderItem]

    admin.add_view(OrderAdminView(Order, db.session, name='Pedidos'))

    # Vista para Usuarios Administradores
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


    # --- Rutas de la Aplicación de Administración ---

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

    # --- API Endpoint para notificaciones de nuevos pedidos (llamado por public_app) ---
    @app.route('/admin-api/new-order-notification', methods=['POST'])
    def new_order_notification():
        data = request.get_json()
        order_id = data.get('order_id')
        if order_id:
            order = Order.query.get(order_id)
            if order:
                with app.app_context():
                    # Unir al cliente actual a la sala 'admin_dashboard' para emitir notificaciones
                    # Esto es importante si la notificación se envía desde un thread externo
                    # Pero en este caso, al ser una ruta Flask, ya está en el contexto de la app.
                    # Asegurarse de que el frontend se una a esta sala también.
                    socketio.emit('new_order_alert', {
                        'order_id': order.id,
                        'customer_name': order.customer_name,
                        'customer_phone': order.customer_phone,
                        'total_amount': order.total_amount,
                        'status': order.status,
                        'order_date': order.order_date.isoformat()
                    }, room='admin_dashboard')
                app.logger.info(f"Notificación de nuevo pedido {order_id} enviada via SocketIO.")
                return jsonify({'message': 'Notificación procesada'}), 200
        app.logger.warning("Intento de notificación de nuevo pedido sin ID de pedido.")
        return jsonify({'message': 'ID de pedido no proporcionado'}), 400

    # --- Eventos de Socket.IO (para la comunicación en tiempo real con el cliente del admin) ---
    @socketio.on('connect')
    def handle_connect():
        if current_user.is_authenticated:
            # Unir al usuario autenticado a la sala 'admin_dashboard'
            join_room('admin_dashboard')
            emit('my_response', {'data': f'Conectado al dashboard admin. Sesión: {request.sid}'}, room=request.sid)
            app.logger.info(f"Cliente SocketIO conectado: {request.sid} (Usuario: {current_user.username})")
        else:
            app.logger.warning(f"Cliente SocketIO no autenticado intentó conectarse: {request.sid}")
            # Considera emitir un mensaje de error o cerrar la conexión si es estrictamente necesario.
            # emit('unauthorized', {'message': 'No autorizado'}, room=request.sid)
            # disconnect() # Esto puede no funcionar directamente aquí o ser demasiado agresivo.
            # Para `flask run` con SocketIO, no necesitas devolver `socketio` en `create_app`
            pass


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
                app.logger.info(f"Estado de pedido {order_id} actualizado a {new_status} por {current_user.username}")
            else:
                app.logger.warning(f"Pedido {order_id} no encontrado para actualización de estado.")
        else:
            app.logger.warning("Datos incompletos para la solicitud de actualización de estado.")

    return app

# Para compatibilidad con 'flask run', asignamos el resultado de create_app a una variable 'app' o 'application'.
# Y usamos socketio.run(app) en el bloque __main__ si lo ejecutamos directamente.
# Sin embargo, la forma más limpia para `flask run` es usar un archivo `wsgi.py`.
# Mantendremos el if __name__ == '__main__': para ejecución directa, pero `flask run` ignorará esta parte.
if __name__ == '__main__':
    # Cuando se ejecuta directamente, creamos la app y luego usamos socketio.run
    app_instance = create_app()
    socketio.run(app_instance, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True) # Utiliza el puerto 5001 para la app de administración
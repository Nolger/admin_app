// admin_app/static/js/admin.js
document.addEventListener('DOMContentLoaded', () => {
    // Conéctate al servidor Socket.IO en el mismo host y puerto que la app de administración
    // Si la app admin está en localhost:5001, se conectará allí por defecto.
    const socket = io();

    const notificationArea = document.getElementById('notificationArea');
    const ordersList = document.getElementById('ordersList');

    // Manejar conexión de Socket.IO
    socket.on('connect', () => {
        console.log('Conectado al servidor de Socket.IO (Admin Dashboard)');
        // Puedes emitir algo al conectarte, por ejemplo, para unirte a una sala
        // socket.emit('join_room', { room: 'admin_dashboard' }); // Ya se hace en el backend si el usuario está autenticado.
    });

    socket.on('disconnect', () => {
        console.log('Desconectado del servidor de Socket.IO');
    });

    // Manejar notificaciones de nuevos pedidos
    socket.on('new_order_alert', (data) => {
        console.log('Nuevo pedido recibido (Socket.IO):', data);
        displayNewOrderNotification(data);
        addNewOrderToList(data);
    });

    // Manejar actualizaciones de estado de pedidos
    socket.on('order_status_updated', (data) => {
        console.log('Estado de pedido actualizado (Socket.IO):', data);
        updateOrderStatusInList(data.order_id, data.new_status);
        displayStatusUpdateNotification(data);
    });


    function displayNewOrderNotification(order) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-info alert-dismissible fade show alert-new-order';
        alertDiv.setAttribute('role', 'alert');
        alertDiv.innerHTML = `
            <strong>¡Nuevo Pedido Recibido!</strong> Pedido #${order.order_id} de ${order.customer_name} por $${order.total_amount.toFixed(2)}.
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">×</span>
            </button>
        `;
        notificationArea.appendChild(alertDiv);

        // Opcional: Remover la alerta después de un tiempo
        setTimeout(() => {
            $(alertDiv).alert('close');
        }, 8000); // 8 segundos
    }

    function displayStatusUpdateNotification(data) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-success alert-dismissible fade show alert-new-order'; // Reusa la animación
        alertDiv.setAttribute('role', 'alert');
        alertDiv.innerHTML = `
            <strong>¡Estado Actualizado!</strong> Pedido #${data.order_id} ahora es: <span class="status-badge status-${data.new_status}">${data.new_status.capitalize()}</span>.
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">×</span>
            </button>
        `;
        notificationArea.appendChild(alertDiv);
        setTimeout(() => {
            $(alertDiv).alert('close');
        }, 5000);
    }

    function addNewOrderToList(order) {
        // Convierte el timestamp ISO a un formato legible
        const orderDate = new Date(order.order_date).toLocaleString();

        const newOrderItem = document.createElement('div');
        newOrderItem.classList.add('order-item');
        newOrderItem.id = `order-${order.order_id}`; // Asegura que el ID exista
        newOrderItem.innerHTML = `
            <div>
                <strong>Pedido #${order.order_id}</strong><br>
                Cliente: ${order.customer_name} (${order.customer_phone || 'N/A'})<br>
                Total: $${order.total_amount.toFixed(2)}<br>
                Fecha: ${orderDate}
            </div>
            <div>
                <span class="status-badge status-${order.status}">${order.status.capitalize()}</span>
                <button class="btn btn-sm btn-info ml-2" onclick="window.location.href = '/admin/order/edit/?id=${order.order_id}'">Ver Detalles</button>
                <div class="btn-group ml-2">
                    <button type="button" class="btn btn-sm btn-secondary dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                        Cambiar Estado
                    </button>
                    <div class="dropdown-menu">
                        <a class="dropdown-item" href="#" onclick="updateOrderStatus(${order.order_id}, 'pending')">Pendiente</a>
                        <a class="dropdown-item" href="#" onclick="updateOrderStatus(${order.order_id}, 'confirmed')">Confirmado</a>
                        <a class="dropdown-item" href="#" onclick="updateOrderStatus(${order.order_id}, 'delivered')">Entregado</a>
                        <a class="dropdown-item" href="#" onclick="updateOrderStatus(${order.order_id}, 'cancelled')">Cancelado</a>
                    </div>
                </div>
            </div>
        `;
        // Añadir el nuevo pedido al principio de la lista
        if (ordersList.firstChild) {
            ordersList.insertBefore(newOrderItem, ordersList.firstChild);
        } else {
            ordersList.appendChild(newOrderItem);
        }
         // Asegúrate de que el mensaje de "no pedidos" se elimine si estaba presente
        const noOrdersP = ordersList.querySelector('p.text-center');
        if (noOrdersP) {
            noOrdersP.remove();
        }
    }

    function updateOrderStatusInList(orderId, newStatus) {
        const orderElement = document.getElementById(`order-${orderId}`);
        if (orderElement) {
            const statusSpan = orderElement.querySelector('.status-badge');
            if (statusSpan) {
                statusSpan.className = `status-badge status-${newStatus}`;
                statusSpan.textContent = newStatus.capitalize();
            }
        }
    }

    // Función global para ser llamada desde los botones del dashboard
    window.updateOrderStatus = (orderId, newStatus) => {
        socket.emit('status_update_request', { order_id: orderId, new_status: newStatus });
    };

    // Helper para capitalizar la primera letra
    String.prototype.capitalize = function() {
        return this.charAt(0).toUpperCase() + this.slice(1);
    }
});
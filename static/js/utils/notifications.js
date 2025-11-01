// notifications.js - Shared notification/toast utility

/**
 * Shows a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The notification type: 'info', 'success', 'error', 'warning'
 * @param {number} duration - How long to show the notification in ms (default: 4000)
 */
export function showNotification(message, type = 'info', duration = 4000) {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.className = `notification notification-${type}`;

    document.body.appendChild(notification);

    // Trigger animation after a brief delay to ensure CSS transition works
    requestAnimationFrame(() => {
        notification.classList.add('notification-show');
    });

    setTimeout(() => {
        notification.classList.remove('notification-show');
        notification.classList.add('notification-hide');
        setTimeout(() => notification.remove(), 300);
    }, duration);
}

// Inject notification styles if not already present
if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
        .notification {
            position: fixed;
            top: 100px;
            right: 30px;
            padding: 15px 25px;
            color: white;
            border-radius: 10px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            z-index: 10002;
            font-weight: 600;
            max-width: 400px;
            opacity: 0;
            transform: translateX(400px);
            transition: all 0.3s ease-out;
        }

        .notification-show {
            opacity: 1;
            transform: translateX(0);
        }

        .notification-hide {
            opacity: 0;
            transform: translateX(400px);
        }

        .notification-error {
            background: linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%);
        }

        .notification-success {
            background: linear-gradient(135deg, #51cf66 0%, #37b24d 100%);
        }

        .notification-warning {
            background: linear-gradient(135deg, #ff9966 0%, #ff6633 100%);
        }

        .notification-info {
            background: linear-gradient(135deg, #4a9eff 0%, #357abd 100%);
        }
    `;
    document.head.appendChild(style);
}

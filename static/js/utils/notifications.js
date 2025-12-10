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
            padding: 16px 28px;
            color: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(12px);
            border: 2px solid rgba(255, 255, 255, 0.1);
            z-index: 10002;
            font-weight: 600;
            font-size: 15px;
            max-width: 400px;
            opacity: 0;
            transform: translateX(420px);
            transition: all 0.4s cubic-bezier(0.68, -0.55, 0.265, 1.55);
        }

        .notification-show {
            opacity: 1;
            transform: translateX(0);
        }

        .notification-hide {
            opacity: 0;
            transform: translateX(420px);
            transition: all 0.3s ease-in;
        }

        .notification-error {
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.95) 0%, rgba(185, 28, 28, 0.95) 100%);
            border-color: rgba(248, 113, 113, 0.3);
        }

        .notification-success {
            background: linear-gradient(135deg, rgba(52, 211, 153, 0.95) 0%, rgba(16, 185, 129, 0.95) 100%);
            border-color: rgba(110, 231, 183, 0.3);
        }

        .notification-warning {
            background: linear-gradient(135deg, rgba(251, 146, 60, 0.95) 0%, rgba(249, 115, 22, 0.95) 100%);
            border-color: rgba(253, 186, 116, 0.3);
        }

        .notification-info {
            background: linear-gradient(135deg, rgba(96, 165, 250, 0.95) 0%, rgba(59, 130, 246, 0.95) 100%);
            border-color: rgba(147, 197, 253, 0.3);
        }
    `;
    document.head.appendChild(style);
}

// Convenience functions for common notification types
export function showSuccess(message, duration = 4000) {
    showNotification(message, 'success', duration);
}

export function showError(message, duration = 4000) {
    showNotification(message, 'error', duration);
}

export function showInfo(message, duration = 4000) {
    showNotification(message, 'info', duration);
}

export function showWarning(message, duration = 4000) {
    showNotification(message, 'warning', duration);
}

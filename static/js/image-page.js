// static/js/image-page.js

/**
 * Handles the deletion of the current image after user confirmation.
 * This relies on the modal logic defined in modal.js
 */
function confirmDelete() {
    const filepath = document.getElementById('imageFilepath')?.value;
    if (!filepath) {
        console.error('No filepath found');
        // Use the notification system from the tag editor if available, otherwise a simple alert.
        const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
        notifier.showNotification('Error: No filepath found to delete', 'error');
        return;
    }

    // The showConfirm function is globally available from modal.js
    showConfirm('Are you sure you want to permanently delete this image?', () => {
        fetch('/api/delete_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        })
        .then(res => {
            if (!res.ok) {
                 return res.json().then(err => { throw new Error(err.error || 'Server error') });
            }
            return res.json();
        })
        .then(data => {
            if (data.status === 'success') {
                const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
                notifier.showNotification('Image deleted!', 'success');
                // Redirect to home page after a short delay
                setTimeout(() => { window.location.href = '/'; }, 500);
            } else {
                throw new Error(data.error || 'Delete failed');
            }
        })
        .catch(err => {
            console.error('Delete error:', err);
            const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
            notifier.showNotification('Failed to delete: ' + err.message, 'error');
        });
    });
}


// --- Main Page Initialization ---
// This ensures all scripts are loaded before we try to attach event listeners.
document.addEventListener('DOMContentLoaded', () => {
    // Attach event listener for the delete button
    const deleteBtn = document.getElementById('deleteImageBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', confirmDelete);
    }

    // You can initialize other image-page-specific components here in the future
});
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


/**
 * Initialize collapsible sections for mobile-friendly UI
 * Handles the collapse/expand behavior of sidebar sections on mobile
 * Supports both standalone section headers and integrated panel headers
 */
function initCollapsibleSections() {
    const sectionHeaders = document.querySelectorAll('.mobile-toggle[data-section]');

    // Load saved states from localStorage
    const savedStates = JSON.parse(localStorage.getItem('imageSectionStates') || '{}');

    sectionHeaders.forEach(header => {
        const sectionId = header.dataset.section;
        const content = document.getElementById(sectionId);

        if (!content) return;

        // Check if this is a panel header (integrated) or section header (standalone)
        const isPanelHeader = header.classList.contains('panel-header');

        // Restore saved state or default to expanded on first visit
        const isCollapsed = savedStates[sectionId] !== undefined ? savedStates[sectionId] : false;

        if (isCollapsed) {
            header.classList.add('collapsed');
            if (!isPanelHeader) {
                // For standalone section headers, collapse the content wrapper
                content.classList.add('collapsed');
            }
        }

        // Add click handler
        header.addEventListener('click', (e) => {
            e.preventDefault();
            const isCurrentlyCollapsed = header.classList.contains('collapsed');

            // Toggle collapsed state on header
            header.classList.toggle('collapsed');

            // For standalone section headers, also toggle content wrapper
            if (!isPanelHeader) {
                content.classList.toggle('collapsed');
            }

            // Save state to localStorage
            savedStates[sectionId] = !isCurrentlyCollapsed;
            localStorage.setItem('imageSectionStates', JSON.stringify(savedStates));
        });
    });
}


// --- Main Page Initialization ---
// This ensures all scripts are loaded before we try to attach event listeners.
document.addEventListener('DOMContentLoaded', () => {
    // Initialize collapsible sections for mobile
    initCollapsibleSections();

    // Attach event listener for the delete button
    const deleteBtn = document.getElementById('deleteImageBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', confirmDelete);
    }

    // You can initialize other image-page-specific components here in the future
});
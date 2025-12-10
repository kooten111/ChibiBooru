// static/js/pool-detail.js
import { showSuccess, showError, showInfo } from './utils/notifications.js';

document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('poolModal');
    const closeBtn = modal ? modal.querySelector('.close') : null;
    const poolForm = document.getElementById('poolForm');

    // Close modal
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    // Close modal on outside click
    if (modal) {
        window.addEventListener('click', (event) => {
            if (event.target === modal) {
                closeModal();
            }
        });
    }

    // Pool form submission
    if (poolForm) {
        poolForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            await savePool();
        });
    }
});

function editPool(poolId, poolName, poolDescription) {
    const modal = document.getElementById('poolModal');
    const poolIdInput = document.getElementById('poolId');
    const poolNameInput = document.getElementById('poolName');
    const poolDescInput = document.getElementById('poolDescription');

    poolIdInput.value = poolId;
    poolNameInput.value = poolName;
    poolDescInput.value = poolDescription;

    modal.style.display = 'block';
    poolNameInput.focus();
}

function closeModal() {
    const modal = document.getElementById('poolModal');
    modal.style.display = 'none';
}

async function savePool() {
    const poolId = document.getElementById('poolId').value;
    const poolName = document.getElementById('poolName').value.trim();
    const poolDescription = document.getElementById('poolDescription').value.trim();

    if (!poolName) {
        showInfo('Pool name is required!');
        return;
    }

    const url = `/api/pools/${poolId}/update`;
    const data = { name: poolName, description: poolDescription };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
            showSuccess(result.message || 'Pool updated successfully!');
            window.location.reload();
        } else {
            showError(result.error || 'Failed to update pool.');
        }
    } catch (error) {
        console.error('Error updating pool:', error);
        showError('An error occurred while updating the pool.');
    }
}

async function removeFromPool(filepath, poolId) {
    if (!confirm('Remove this image from the pool?')) {
        return;
    }

    try {
        const response = await fetch(`/api/pools/${poolId}/remove_image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        const result = await response.json();

        if (response.ok) {
            // Remove the image element from the DOM
            const imageElement = document.querySelector(`[data-filepath="${filepath}"]`);
            if (imageElement) {
                imageElement.remove();
            }

            // Check if pool is now empty
            const gallery = document.querySelector('.pool-gallery');
            if (gallery && gallery.children.length === 0) {
                window.location.reload();
            }
        } else {
            showError(result.error || 'Failed to remove image from pool.');
        }
    } catch (error) {
        console.error('Error removing image from pool:', error);
        showError('An error occurred while removing the image.');
    }
}

// Expose functions to window for onclick handlers
window.editPool = editPool;
window.closeModal = closeModal;
window.removeFromPool = removeFromPool;

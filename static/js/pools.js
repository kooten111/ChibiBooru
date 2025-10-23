// static/js/pools.js

document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('poolSearchInput');
    const createPoolBtn = document.getElementById('createPoolBtn');
    const modal = document.getElementById('poolModal');
    const closeBtn = modal ? modal.querySelector('.close') : null;
    const poolForm = document.getElementById('poolForm');

    // Search functionality
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.trim();
            if (query.length > 0) {
                window.location.href = `${window.location.pathname}?query=${encodeURIComponent(query)}`;
            } else if (window.location.search) {
                window.location.href = window.location.pathname;
            }
        });
    }

    // Create pool button
    if (createPoolBtn) {
        createPoolBtn.addEventListener('click', () => {
            openCreatePoolModal();
        });
    }

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

function openCreatePoolModal() {
    const modal = document.getElementById('poolModal');
    const modalTitle = document.getElementById('modalTitle');
    const poolIdInput = document.getElementById('poolId');
    const poolNameInput = document.getElementById('poolName');
    const poolDescInput = document.getElementById('poolDescription');

    modalTitle.textContent = 'Create New Pool';
    poolIdInput.value = '';
    poolNameInput.value = '';
    poolDescInput.value = '';

    modal.style.display = 'block';
    poolNameInput.focus();
}

function editPool(poolId, poolName, poolDescription) {
    const modal = document.getElementById('poolModal');
    const modalTitle = document.getElementById('modalTitle');
    const poolIdInput = document.getElementById('poolId');
    const poolNameInput = document.getElementById('poolName');
    const poolDescInput = document.getElementById('poolDescription');

    modalTitle.textContent = 'Edit Pool';
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
        alert('Pool name is required!');
        return;
    }

    const isEdit = poolId !== '';
    const url = isEdit ? `/api/pools/${poolId}/update` : '/api/pools/create';
    const data = { name: poolName, description: poolDescription };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok) {
            alert(result.message || 'Pool saved successfully!');
            window.location.reload();
        } else {
            alert(result.error || 'Failed to save pool.');
        }
    } catch (error) {
        console.error('Error saving pool:', error);
        alert('An error occurred while saving the pool.');
    }
}

async function deletePool(poolId, poolName) {
    if (!confirm(`Are you sure you want to delete the pool "${poolName}"? This will remove the pool but not the images.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/pools/${poolId}/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (response.ok) {
            alert(result.message || 'Pool deleted successfully!');
            window.location.reload();
        } else {
            alert(result.error || 'Failed to delete pool.');
        }
    } catch (error) {
        console.error('Error deleting pool:', error);
        alert('An error occurred while deleting the pool.');
    }
}

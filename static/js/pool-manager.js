// static/js/pool-manager.js
import { showSuccess, showError, showInfo } from './utils/notifications.js';

const POOL_NAME_MAX_LENGTH = 200;
const POOL_DESCRIPTION_MAX_LENGTH = 1000;

document.addEventListener('DOMContentLoaded', () => {
    loadPoolsForImage();
});

async function loadPoolsForImage() {
    const filepath = document.getElementById('imageFilepath').value;
    const poolsList = document.getElementById('poolsList');
    const poolsContent = document.getElementById('pools-content');
    const poolCountBadge = document.getElementById('poolCountBadge');

    if (!filepath || !poolsList) {
        // Safe check for server-side hidden section
        return;
    }

    try {
        const response = await fetch(`/api/pools/for_image?filepath=${encodeURIComponent(filepath)}`);
        const data = await response.json();

        if (response.ok && Array.isArray(data.pools)) {
            if (poolsContent) {
                poolsContent.style.display = 'block';
            }

            if (poolCountBadge) {
                poolCountBadge.textContent = data.pools.length > 0 ? `(${data.pools.length})` : '(0)';
            }

            if (data.pools.length === 0) {
                showEmptyImagePools(poolsList);
                return;
            }

            // Clear and populate pool list
            poolsList.innerHTML = '';
            data.pools.forEach(pool => {
                const item = createPoolListItem(pool);
                poolsList.appendChild(item);
            });
        } else {
            // On error, keep the panel visible and show error
            if (poolsContent) {
                poolsContent.style.display = 'block';
            }
            if (poolCountBadge) {
                poolCountBadge.textContent = '';
            }
            showPoolError(poolsList);
        }
    } catch (error) {
        console.error('Error loading pools:', error);
        // On error, keep the panel visible and show error
        if (poolsContent) {
            poolsContent.style.display = 'block';
        }
        if (poolCountBadge) {
            poolCountBadge.textContent = '';
        }
        showPoolError(poolsList);
    }
}

function showEmptyImagePools(container) {
    container.innerHTML = '<div class="pool-empty-message">Not in any pools yet.</div>';
}

function createPoolListItem(pool) {
    const item = document.createElement('div');
    item.className = 'pool-list-item';

    const link = document.createElement('a');
    link.href = `/pool/${pool.id}`;
    link.textContent = pool.name;

    const button = document.createElement('button');
    button.textContent = 'Remove';
    button.onclick = () => removeImageFromPool(pool.id, pool.name);

    item.appendChild(link);
    item.appendChild(button);

    return item;
}

function showPoolError(container) {
    const template = document.getElementById('pool-error-template');
    const clone = template.content.cloneNode(true);
    container.innerHTML = '';
    container.appendChild(clone);
}

async function showAddToPoolModal() {
    // Create modal HTML if it doesn't exist
    let modal = document.getElementById('addToPoolModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'addToPoolModal';
        modal.className = 'modal';

        const template = document.getElementById('pool-modal-template');
        const clone = template.content.cloneNode(true);
        modal.appendChild(clone);

        document.body.appendChild(modal);

        initializeAddToPoolModal(modal);
    }

    // Show modal
    modal.classList.add('active');

    // Load all pools
    await loadAllPools();

    const searchInput = document.getElementById('poolSearchModal');
    if (searchInput) {
        searchInput.focus();
    }
}

function initializeAddToPoolModal(modal) {
    if (modal.dataset.initialized === 'true') {
        return;
    }

    const searchInput = modal.querySelector('#poolSearchModal');
    if (searchInput) {
        searchInput.addEventListener('input', filterPoolList);
    }

    const createForm = modal.querySelector('#createPoolForm');
    if (createForm) {
        createForm.addEventListener('submit', async (event) => {
            event.preventDefault();

            const nameInput = modal.querySelector('#createPoolName');
            const descriptionInput = modal.querySelector('#createPoolDescription');
            const name = nameInput ? nameInput.value.trim() : '';
            const description = descriptionInput ? descriptionInput.value.trim() : '';

            if (!name) {
                showInfo('Pool name is required.');
                if (nameInput) {
                    nameInput.focus();
                }
                return;
            }

            if (name.length > POOL_NAME_MAX_LENGTH) {
                showInfo(`Pool name must be ${POOL_NAME_MAX_LENGTH} characters or less.`);
                return;
            }

            if (description.length > POOL_DESCRIPTION_MAX_LENGTH) {
                showInfo(`Description must be ${POOL_DESCRIPTION_MAX_LENGTH} characters or less.`);
                return;
            }

            await createPoolAndAddCurrentImage(name, description);
        });
    }

    modal.dataset.initialized = 'true';
}

async function loadAllPools() {
    const poolsList = document.getElementById('poolSelectorList');
    const filepath = document.getElementById('imageFilepath').value;

    if (!poolsList || !filepath) {
        return;
    }

    try {
        // Get pools this image is in
        const poolsResponse = await fetch('/api/pools/for_image?filepath=' + encodeURIComponent(filepath));
        const poolsData = await poolsResponse.json();
        const imagePools = new Set((poolsData.pools || []).map(p => p.id));

        // Get all available pools
        const allPoolsResponse = await fetch('/api/pools/all');
        const allPoolsData = await allPoolsResponse.json();

        if (!allPoolsData.pools || allPoolsData.pools.length === 0) {
            const template = document.getElementById('pool-empty-template');
            const clone = template.content.cloneNode(true);
            poolsList.innerHTML = '';
            poolsList.appendChild(clone);
            return;
        }

        const poolsWithStatus = allPoolsData.pools.map(pool => ({
            id: pool.id,
            name: pool.name,
            description: pool.description,
            image_count: pool.image_count || 0,
            inPool: imagePools.has(pool.id)
        }));

        renderPoolList(poolsWithStatus);
    } catch (error) {
        console.error('Error loading pools:', error);
        showPoolError(poolsList);
    }
}

function renderPoolList(pools) {
    const poolsList = document.getElementById('poolSelectorList');
    poolsList.innerHTML = '';

    pools.forEach(pool => {
        const item = createPoolSelectorItem(pool);
        poolsList.appendChild(item);
    });
}

function createPoolSelectorItem(pool) {
    const item = document.createElement('div');
    item.className = `pool-selector-item ${pool.inPool ? 'in-pool' : ''}`;
    item.dataset.poolId = pool.id;
    item.dataset.poolName = pool.name.toLowerCase();

    const contentDiv = document.createElement('div');
    contentDiv.style.flex = '1';

    const nameDiv = document.createElement('div');
    nameDiv.className = 'pool-selector-name';
    nameDiv.textContent = pool.name;
    contentDiv.appendChild(nameDiv);

    if (pool.description) {
        const descDiv = document.createElement('div');
        descDiv.className = 'pool-selector-desc';
        descDiv.textContent = pool.description;
        contentDiv.appendChild(descDiv);
    }

    const badge = document.createElement('span');
    badge.className = 'pool-selector-badge';
    badge.textContent = pool.inPool ? '✓ In Pool' : '+ Add';

    item.appendChild(contentDiv);
    item.appendChild(badge);

    item.onclick = () => togglePoolMembership(pool.id, pool.name, pool.inPool);

    return item;
}

function filterPoolList() {
    const searchInput = document.getElementById('poolSearchModal');
    if (!searchInput) {
        return;
    }

    const query = searchInput.value.toLowerCase().trim();
    const items = document.querySelectorAll('.pool-selector-item');

    items.forEach(item => {
        const poolName = item.dataset.poolName;
        if (poolName.includes(query)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

function setCreatePoolFormLoading(loading) {
    const nameInput = document.getElementById('createPoolName');
    const descriptionInput = document.getElementById('createPoolDescription');
    const submitBtn = document.getElementById('createPoolSubmit');

    if (nameInput) {
        nameInput.disabled = loading;
    }
    if (descriptionInput) {
        descriptionInput.disabled = loading;
    }
    if (submitBtn) {
        submitBtn.disabled = loading;
        submitBtn.textContent = loading ? 'Creating...' : 'Create + Add';
    }
}

function resetCreatePoolForm() {
    const createForm = document.getElementById('createPoolForm');
    if (createForm) {
        createForm.reset();
    }
}

async function createPoolAndAddCurrentImage(name, description) {
    const filepathInput = document.getElementById('imageFilepath');
    const filepath = filepathInput ? filepathInput.value : '';

    if (!filepath) {
        showError('Image path is missing.');
        return;
    }

    setCreatePoolFormLoading(true);

    try {
        const createResponse = await fetch('/api/pools/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, description: description })
        });

        const createResult = await createResponse.json();
        if (!createResponse.ok) {
            showError(createResult.error || 'Failed to create pool.');
            return;
        }

        const poolId = createResult.pool_id;
        if (!poolId) {
            showError('Pool was created but no pool id was returned.');
            return;
        }

        const addResponse = await fetch(`/api/pools/${poolId}/add_image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        const addResult = await addResponse.json();
        if (!addResponse.ok) {
            showError(addResult.error || 'Pool created, but failed to add image.');
            return;
        }

        await loadAllPools();
        await loadPoolsForImage();
        resetCreatePoolForm();
        showSuccess(`Pool "${name}" created and image added.`);
    } catch (error) {
        console.error('Error creating pool from modal:', error);
        showError('An error occurred while creating the pool.');
    } finally {
        setCreatePoolFormLoading(false);
    }
}

async function togglePoolMembership(poolId, _poolName, currentlyInPool) {
    const filepath = document.getElementById('imageFilepath').value;
    const endpoint = currentlyInPool ? 'remove_image' : 'add_image';

    try {
        const response = await fetch(`/api/pools/${poolId}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        const result = await response.json();

        if (response.ok) {
            // Reload the pools list in the modal
            await loadAllPools();
            // Reload the pools list in the sidebar
            await loadPoolsForImage();
        } else {
            showError(result.error || 'Failed to update pool membership.');
        }
    } catch (error) {
        console.error('Error toggling pool membership:', error);
        showError('An error occurred.');
    }
}

async function removeImageFromPool(poolId, poolName) {
    if (!confirm(`Remove this image from "${poolName}"?`)) {
        return;
    }

    const filepath = document.getElementById('imageFilepath').value;

    try {
        const response = await fetch(`/api/pools/${poolId}/remove_image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        const result = await response.json();

        if (response.ok) {
            await loadPoolsForImage();
        } else {
            showError(result.error || 'Failed to remove from pool.');
        }
    } catch (error) {
        console.error('Error removing from pool:', error);
        showError('An error occurred.');
    }
}

function closeAddToPoolModal() {
    const modal = document.getElementById('addToPoolModal');
    if (modal) {
        modal.classList.remove('active');
    }

    const searchInput = document.getElementById('poolSearchModal');
    if (searchInput) {
        searchInput.value = '';
        filterPoolList();
    }

    resetCreatePoolForm();
    setCreatePoolFormLoading(false);
}

// Expose functions globally for use by other scripts
window.showAddToPoolModal = showAddToPoolModal;
window.closeAddToPoolModal = closeAddToPoolModal;
window.loadPoolsForImage = loadPoolsForImage;

// Close modal on outside click
window.addEventListener('click', (event) => {
    const modal = document.getElementById('addToPoolModal');
    if (modal && modal.classList.contains('active') && event.target === modal) {
        closeAddToPoolModal();
    }
});

document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') {
        return;
    }

    const modal = document.getElementById('addToPoolModal');
    if (modal && modal.classList.contains('active')) {
        closeAddToPoolModal();
    }
});

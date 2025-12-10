// static/js/pool-manager.js
import { showSuccess, showError, showInfo } from './utils/notifications.js';

document.addEventListener('DOMContentLoaded', () => {
    loadPoolsForImage();
});

async function loadPoolsForImage() {
    const filepath = document.getElementById('imageFilepath').value;
    const poolsList = document.getElementById('poolsList');
    const poolsPanel = document.querySelector('.pool-management.panel');
    const poolsContent = document.getElementById('pools-content');

    if (!filepath || !poolsList) return;

    try {
        const response = await fetch(`/api/pools/for_image?filepath=${encodeURIComponent(filepath)}`);
        const data = await response.json();

        if (response.ok && data.pools) {
            if (data.pools.length === 0) {
                // Hide the entire pools section when not in any pools
                if (poolsContent) {
                    poolsContent.style.display = 'none';
                }
                if (poolsPanel) {
                    poolsPanel.style.display = 'none';
                }
            } else {
                // Show the section and panel, then populate with pools
                if (poolsContent) {
                    poolsContent.style.display = 'contents';
                }
                if (poolsPanel) {
                    poolsPanel.style.display = 'block';
                }

                // Clear and populate pool list
                poolsList.innerHTML = '';
                data.pools.forEach(pool => {
                    const item = createPoolListItem(pool);
                    poolsList.appendChild(item);
                });
            }
        } else {
            // On error, show the panel with error message
            if (poolsContent) {
                poolsContent.style.display = 'contents';
            }
            if (poolsPanel) {
                poolsPanel.style.display = 'block';
            }
            showPoolError(poolsList);
        }
    } catch (error) {
        console.error('Error loading pools:', error);
        // On error, show the panel with error message
        if (poolsContent) {
            poolsContent.style.display = 'contents';
        }
        if (poolsPanel) {
            poolsPanel.style.display = 'block';
        }
        showPoolError(poolsList);
    }
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
    }

    // Show modal
    modal.style.display = 'block';

    // Load all pools
    await loadAllPools();

    // Setup search
    const searchInput = document.getElementById('poolSearchModal');
    if (searchInput) {
        searchInput.addEventListener('input', filterPoolList);
    }
}

async function loadAllPools() {
    const poolsList = document.getElementById('poolSelectorList');
    const filepath = document.getElementById('imageFilepath').value;

    try {
        // Get pools this image is in
        const poolsResponse = await fetch('/api/pools/for_image?filepath=' + encodeURIComponent(filepath));
        const poolsData = await poolsResponse.json();
        const imagePools = new Set(poolsData.pools.map(p => p.id));

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
        modal.style.display = 'none';
    }
}

// Close modal on outside click
window.addEventListener('click', (event) => {
    const modal = document.getElementById('addToPoolModal');
    if (modal && event.target === modal) {
        closeAddToPoolModal();
    }
});

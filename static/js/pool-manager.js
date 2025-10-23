// static/js/pool-manager.js

document.addEventListener('DOMContentLoaded', () => {
    loadPoolsForImage();

    const addToPoolBtn = document.getElementById('addToPoolBtn');
    if (addToPoolBtn) {
        addToPoolBtn.addEventListener('click', showAddToPoolModal);
    }
});

async function loadPoolsForImage() {
    const filepath = document.getElementById('imageFilepath').value;
    const poolsList = document.getElementById('poolsList');

    if (!filepath || !poolsList) return;

    try {
        const response = await fetch(`/api/pools/for_image?filepath=${encodeURIComponent(filepath)}`);
        const data = await response.json();

        if (response.ok && data.pools) {
            if (data.pools.length === 0) {
                poolsList.innerHTML = '<div style="color: #888; padding: 10px; text-align: center;">Not in any pools</div>';
            } else {
                poolsList.innerHTML = data.pools.map(pool => `
                    <div class="pool-list-item">
                        <a href="/pool/${pool.id}">${pool.name}</a>
                        <button onclick="removeImageFromPool(${pool.id}, '${pool.name}')">Remove</button>
                    </div>
                `).join('');
            }
        } else {
            poolsList.innerHTML = '<div style="color: #ff6b6b; padding: 10px;">Failed to load pools</div>';
        }
    } catch (error) {
        console.error('Error loading pools:', error);
        poolsList.innerHTML = '<div style="color: #ff6b6b; padding: 10px;">Error loading pools</div>';
    }
}

async function showAddToPoolModal() {
    // Create modal HTML if it doesn't exist
    let modal = document.getElementById('addToPoolModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'addToPoolModal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <span class="close" onclick="closeAddToPoolModal()">&times;</span>
                <h3>Add to Pool</h3>
                <div class="form-group">
                    <input type="text" id="poolSearchModal" placeholder="Search pools..." style="width: 100%; padding: 10px; margin-bottom: 15px;">
                </div>
                <div id="poolSelectorList" class="pool-selector-list">
                    <div class="loading-spinner">Loading pools...</div>
                </div>
                <div class="form-actions" style="margin-top: 20px;">
                    <button class="btn-secondary" onclick="closeAddToPoolModal()">Close</button>
                </div>
            </div>
        `;
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
        // Get all pools
        const poolsResponse = await fetch('/api/pools/for_image?filepath=' + encodeURIComponent(filepath));
        const poolsData = await poolsResponse.json();
        const imagePools = new Set(poolsData.pools.map(p => p.id));

        // Get all available pools from the pools page
        const response = await fetch('/pools');
        const html = await response.text();
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, 'text/html');
        const poolItems = doc.querySelectorAll('.pool-item');

        if (poolItems.length === 0) {
            poolsList.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No pools available. Create a pool first!</div>';
            return;
        }

        const allPoolsData = Array.from(poolItems).map(item => ({
            id: item.dataset.poolId,
            name: item.querySelector('.pool-name').textContent,
            inPool: imagePools.has(parseInt(item.dataset.poolId))
        }));

        renderPoolList(allPoolsData);
    } catch (error) {
        console.error('Error loading pools:', error);
        poolsList.innerHTML = '<div style="color: #ff6b6b; padding: 20px; text-align: center;">Error loading pools</div>';
    }
}

function renderPoolList(pools) {
    const poolsList = document.getElementById('poolSelectorList');
    poolsList.innerHTML = pools.map(pool => `
        <div class="pool-selector-item ${pool.inPool ? 'in-pool' : ''}"
             data-pool-id="${pool.id}"
             data-pool-name="${pool.name.toLowerCase()}"
             onclick="togglePoolMembership(${pool.id}, '${pool.name}', ${pool.inPool})">
            <span class="pool-selector-name">${pool.name}</span>
            <span class="pool-selector-badge">${pool.inPool ? 'In Pool' : 'Add'}</span>
        </div>
    `).join('');
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

async function togglePoolMembership(poolId, poolName, currentlyInPool) {
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
            alert(result.error || 'Failed to update pool membership.');
        }
    } catch (error) {
        console.error('Error toggling pool membership:', error);
        alert('An error occurred.');
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
            alert(result.error || 'Failed to remove from pool.');
        }
    } catch (error) {
        console.error('Error removing from pool:', error);
        alert('An error occurred.');
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

/**
 * Upscaler Module for ChibiBooru
 * Handles AI image upscaling with RealESRGAN and comparison UI
 */

(function () {
    'use strict';

    // State
    let currentFilepath = null;
    let hasUpscaled = false;
    let isUpscaling = false;
    let showingUpscaled = false;
    let upscalerEnabled = false;
    let upscalerReady = false;

    // DOM Elements
    let upscaleBtn = null;
    let imageContainer = null;
    let hoverMenu = null;

    /**
     * Initialize the upscaler module
     */
    async function init() {
        // Get current filepath
        const filepathInput = document.getElementById('imageFilepath');
        if (!filepathInput) return;

        currentFilepath = filepathInput.value;

        // Find or create upscale button
        const actionsBar = document.querySelector('.actions-bar.pill');
        if (!actionsBar) return;

        // Check existing button or create new one
        upscaleBtn = document.getElementById('upscaleBtn');
        if (!upscaleBtn) {
            // Create button after the download button
            const downloadBtn = actionsBar.querySelector('a[download]');
            if (downloadBtn) {
                upscaleBtn = document.createElement('button');
                upscaleBtn.id = 'upscaleBtn';
                upscaleBtn.className = 'action-btn';
                upscaleBtn.title = 'Upscale Image (AI 4x)';
                upscaleBtn.innerHTML = '<span class="upscale-icon">✨</span>';
                downloadBtn.insertAdjacentElement('afterend', upscaleBtn);
            }
        }

        if (!upscaleBtn) return;

        imageContainer = document.getElementById('imageViewContainer');

        // Check upscaler status
        await checkUpscalerStatus();

        // Update button state
        updateButtonState();

        // Create hover menu
        createHoverMenu();

        // Attach event listeners
        upscaleBtn.addEventListener('click', handleUpscaleClick);
    }

    /**
     * Check upscaler feature status
     */
    async function checkUpscalerStatus() {
        try {
            const response = await fetch('/api/upscale/status');
            if (!response.ok) {
                upscalerEnabled = false;
                return;
            }

            const data = await response.json();
            upscalerEnabled = data.enabled;
            upscalerReady = data.ready;

            // Check if upscaled version exists
            if (upscalerEnabled && currentFilepath) {
                const checkResponse = await fetch(`/api/upscale/check?filepath=${encodeURIComponent(currentFilepath)}`);
                if (checkResponse.ok) {
                    const checkData = await checkResponse.json();
                    hasUpscaled = checkData.has_upscaled;
                }
            }
        } catch (error) {
            console.warn('Upscaler status check failed:', error);
            upscalerEnabled = false;
        }
    }

    /**
     * Update the upscale button state
     */
    function updateButtonState() {
        if (!upscaleBtn) return;

        // Remove all state classes
        upscaleBtn.classList.remove('upscale-ready', 'upscale-done', 'upscale-loading', 'disabled');

        // Get or create the icon span (separate from hover menu)
        let iconSpan = upscaleBtn.querySelector('.upscale-icon');
        if (!iconSpan) {
            iconSpan = document.createElement('span');
            iconSpan.className = 'upscale-icon';
            upscaleBtn.insertBefore(iconSpan, upscaleBtn.firstChild);
        }

        if (!upscalerEnabled) {
            upscaleBtn.classList.add('disabled');
            upscaleBtn.title = 'Upscaler disabled (enable in config)';
            iconSpan.innerHTML = '✨';
            return;
        }

        if (isUpscaling) {
            upscaleBtn.classList.add('upscale-loading');
            upscaleBtn.title = 'Upscaling...';
            iconSpan.innerHTML = '<span class="spinner">⏳</span>';
            return;
        }

        if (hasUpscaled) {
            upscaleBtn.classList.add('upscale-done');
            upscaleBtn.title = 'Upscale options (hover for menu)';
            iconSpan.innerHTML = '✨';
            return;
        }

        upscaleBtn.classList.add('upscale-ready');
        upscaleBtn.title = 'Upscale Image (AI 4x)';
        iconSpan.innerHTML = '✨';
    }

    /**
     * Create hover menu for upscale options
     */
    function createHoverMenu() {
        if (hoverMenu) hoverMenu.remove();

        hoverMenu = document.createElement('div');
        hoverMenu.className = 'upscale-hover-menu';
        hoverMenu.innerHTML = `
            <div class="upscale-menu-item view-original" data-view="original">
                <span class="menu-icon">📷</span>
                <span class="menu-label">Original</span>
            </div>
            <div class="upscale-menu-item view-upscaled" data-view="upscaled">
                <span class="menu-icon">✨</span>
                <span class="menu-label">Upscaled (4x)</span>
            </div>
            <div class="upscale-menu-divider"></div>
            <div class="upscale-menu-item delete-upscaled danger">
                <span class="menu-icon">🗑️</span>
                <span class="menu-label">Remove Upscaled</span>
            </div>
        `;

        // Position relative to button
        upscaleBtn.style.position = 'relative';
        upscaleBtn.appendChild(hoverMenu);

        // Event listeners for menu items
        hoverMenu.querySelector('.view-original').addEventListener('click', (e) => {
            e.stopPropagation();
            showOriginalImage();
            updateMenuState();
        });

        hoverMenu.querySelector('.view-upscaled').addEventListener('click', (e) => {
            e.stopPropagation();
            showUpscaledFromCache();
            updateMenuState();
        });

        hoverMenu.querySelector('.delete-upscaled').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteUpscaled();
        });

        updateMenuState();
    }

    /**
     * Update menu item active states
     */
    function updateMenuState() {
        if (!hoverMenu) return;

        const originalItem = hoverMenu.querySelector('.view-original');
        const upscaledItem = hoverMenu.querySelector('.view-upscaled');
        const deleteItem = hoverMenu.querySelector('.delete-upscaled');

        originalItem.classList.toggle('active', !showingUpscaled);
        upscaledItem.classList.toggle('active', showingUpscaled);

        // Show/hide menu items based on state
        if (hasUpscaled) {
            hoverMenu.classList.add('has-upscaled');
        } else {
            hoverMenu.classList.remove('has-upscaled');
        }
    }

    /**
     * Handle upscale button click
     */
    async function handleUpscaleClick(e) {
        // If menu is showing, don't trigger upscale
        if (hoverMenu && hoverMenu.matches(':hover')) return;

        if (!upscalerEnabled) {
            showToast('Upscaler is disabled. Enable UPSCALER_ENABLED in .env', 'warning');
            return;
        }

        if (isUpscaling) return;

        // If already upscaled, toggle view
        if (hasUpscaled) {
            toggleView();
            updateMenuState();
            return;
        }

        // Check if dependencies are ready
        if (!upscalerReady) {
            const confirmed = await showDependencyModal();
            if (!confirmed) return;
        }

        // Start upscaling
        await upscaleImage();
    }

    /**
     * Upscale the current image
     */
    async function upscaleImage() {
        if (!currentFilepath) return;

        isUpscaling = true;
        updateButtonState();

        try {
            const response = await fetch('/api/upscale', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: currentFilepath })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Upscaling failed');
            }

            hasUpscaled = true;
            showingUpscaled = true;

            // Show the upscaled image
            showUpscaledImage(data.upscaled_url);

            showToast(`Upscaled in ${data.processing_time?.toFixed(1) || '?'}s`, 'success');

            // Update menu
            createHoverMenu();

        } catch (error) {
            console.error('Upscaling error:', error);
            showToast(error.message || 'Upscaling failed', 'error');
        } finally {
            isUpscaling = false;
            updateButtonState();
        }
    }

    /**
     * Show the upscaled image
     */
    function showUpscaledImage(upscaledUrl) {
        if (!imageContainer) return;

        const img = imageContainer.querySelector('img');
        if (!img) return;

        // Store original src if not already stored
        if (!img.dataset.originalSrc) {
            img.dataset.originalSrc = img.src;
        }

        // Store upscaled URL
        img.dataset.upscaledSrc = upscaledUrl;

        img.src = upscaledUrl;
        showingUpscaled = true;
        updateButtonState();
    }

    /**
     * Show upscaled image from cache
     */
    function showUpscaledFromCache() {
        if (!imageContainer) return;

        const img = imageContainer.querySelector('img');
        if (!img || !img.dataset.upscaledSrc) {
            // Need to fetch URL
            fetch(`/api/upscale/check?filepath=${encodeURIComponent(currentFilepath)}`)
                .then(r => r.json())
                .then(data => {
                    if (data.upscaled_url) {
                        showUpscaledImage(data.upscaled_url);
                    }
                });
            return;
        }

        img.src = img.dataset.upscaledSrc;
        showingUpscaled = true;
        updateButtonState();
    }

    /**
     * Show the original image
     */
    function showOriginalImage() {
        if (!imageContainer) return;

        const img = imageContainer.querySelector('img');
        if (!img || !img.dataset.originalSrc) return;

        img.src = img.dataset.originalSrc;
        showingUpscaled = false;
        updateButtonState();
    }

    /**
     * Toggle between original and upscaled view
     */
    function toggleView() {
        if (showingUpscaled) {
            showOriginalImage();
        } else {
            showUpscaledFromCache();
        }
    }

    /**
     * Delete the upscaled version
     */
    async function deleteUpscaled() {
        if (!hasUpscaled) return;

        try {
            const response = await fetch('/api/upscale', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: currentFilepath })
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || 'Delete failed');
            }

            // Show original image
            showOriginalImage();

            // Clear cached upscaled URL
            const img = imageContainer?.querySelector('img');
            if (img) delete img.dataset.upscaledSrc;

            hasUpscaled = false;
            showingUpscaled = false;
            updateButtonState();
            createHoverMenu(); // Refresh menu

            showToast('Upscaled version removed', 'success');

        } catch (error) {
            console.error('Delete upscaled error:', error);
            showToast(error.message || 'Failed to remove upscaled version', 'error');
        }
    }

    /**
     * Show dependency installation modal
     */
    async function showDependencyModal() {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'upscale-dep-modal';
            modal.innerHTML = `
                <div class="upscale-dep-modal-content">
                    <h3>🔧 Upscaler Setup Required</h3>
                    <p>The AI upscaler needs to install PyTorch for your GPU.</p>
                    <p class="warning">This may take a few minutes.</p>
                    <div class="modal-actions">
                        <button class="btn-cancel">Cancel</button>
                        <button class="btn-install">Install Dependencies</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            modal.querySelector('.btn-cancel').addEventListener('click', () => {
                modal.remove();
                resolve(false);
            });

            modal.querySelector('.btn-install').addEventListener('click', async () => {
                const installBtn = modal.querySelector('.btn-install');
                installBtn.disabled = true;
                installBtn.textContent = 'Installing...';

                try {
                    const response = await fetch('/api/upscale/install', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({})
                    });

                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.error || 'Installation failed');
                    }

                    upscalerReady = true;
                    showToast('Dependencies installed successfully!', 'success');
                    modal.remove();
                    resolve(true);

                } catch (error) {
                    console.error('Installation error:', error);
                    showToast(error.message || 'Installation failed', 'error');
                    installBtn.disabled = false;
                    installBtn.textContent = 'Retry Install';
                }
            });
        });
    }

    /**
     * Show a toast notification
     */
    function showToast(message, type = 'info') {
        if (window.showToast) {
            window.showToast(message, type);
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'error' ? '#f44336' : type === 'success' ? '#4caf50' : '#2196f3'};
            color: white;
            border-radius: 8px;
            z-index: 10000;
            animation: fadeIn 0.3s ease;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'fadeOut 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    /**
     * Re-initialize for client-side navigation
     */
    function reinit() {
        hasUpscaled = false;
        isUpscaling = false;
        showingUpscaled = false;

        if (hoverMenu) hoverMenu.remove();
        hoverMenu = null;

        init();
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Listen for client-side navigation events
    window.addEventListener('imagePageNavigated', reinit);

    // Export for external access
    window.Upscaler = {
        init,
        reinit,
        toggleView,
        deleteUpscaled
    };

})();

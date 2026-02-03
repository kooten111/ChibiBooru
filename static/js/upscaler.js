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
    let upscaleProgress = 0;
    let showingUpscaled = false;
    let isComparing = false;
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

        // Key listeners for comparison
        document.addEventListener('keydown', handleKeyDown);
        document.addEventListener('keyup', handleKeyUp);
    }

    /**
     * Handle key down event
     */
    function handleKeyDown(e) {
        // 'c' key for compare
        if (e.key.toLowerCase() === 'c' && !e.repeat) {
            // Ignore if typing in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            startComparison();
        }
    }

    /**
     * Handle key up event
     */
    function handleKeyUp(e) {
        if (e.key.toLowerCase() === 'c') {
            stopComparison();
        }
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
            upscaleBtn.style.background = '';
            return;
        }

        if (isUpscaling) {
            upscaleBtn.classList.add('upscale-loading');
            upscaleBtn.title = `Upscaling... ${Math.round(upscaleProgress)}%`;
            iconSpan.innerHTML = `<span class="progress-text" style="font-size: 0.8em; font-weight: bold;">${Math.round(upscaleProgress)}%</span>`;

            // Visual progress bar using background gradient
            const p = upscaleProgress;
            upscaleBtn.style.background = `linear-gradient(to right, rgba(var(--primary-rgb), 0.3) ${p}%, transparent ${p}%)`;
            return;
        }

        // Reset background
        upscaleBtn.style.background = '';

        if (hasUpscaled) {
            upscaleBtn.classList.add('upscale-done');
            upscaleBtn.title = 'Upscale options (hover for menu) | Hold "C" to compare';
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
        upscaleProgress = 0;
        updateButtonState();

        // Start progress polling
        const progressInterval = setInterval(async () => {
            try {
                const res = await fetch(`/api/upscale/progress?filepath=${encodeURIComponent(currentFilepath)}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.status === 'processing' || data.percentage > 0) {
                        upscaleProgress = data.percentage;
                        updateButtonState();
                    }
                }
            } catch (ignore) { }
        }, 1000);

        try {
            const response = await fetch('/api/upscale', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: currentFilepath })
            });

            const data = await response.json();

            if (!response.ok) {
                // Provide more helpful error messages
                let errorMessage = data.error || 'Upscaling failed';

                // Check for common error patterns
                if (errorMessage.includes('ML Worker is not available') ||
                    errorMessage.includes('Connection failed')) {
                    errorMessage = 'ML Worker is not available. Please check if the ML Worker process is running and try again.';
                } else if (errorMessage.includes('ML Worker error')) {
                    errorMessage = `ML Worker error: ${errorMessage}`;
                } else if (errorMessage.includes('disabled')) {
                    errorMessage = 'Upscaler is disabled. Enable UPSCALER_ENABLED in config to use this feature.';
                }

                throw new Error(errorMessage);
            }

            hasUpscaled = true;
            showingUpscaled = true;
            upscaleProgress = 100;

            // Show the upscaled image
            showUpscaledImage(data.upscaled_url);

            showToast(`Upscaled in ${data.processing_time?.toFixed(1) || '?'}s`, 'success');

            // Update menu
            createHoverMenu();

        } catch (error) {
            console.error('Upscaling error:', error);

            // Show user-friendly error message
            let userMessage = error.message || 'Upscaling failed';

            // Handle network errors
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                userMessage = 'Network error: Could not connect to server. Please check your connection and try again.';
            }

            showToast(userMessage, 'error');
        } finally {
            clearInterval(progressInterval);
            isUpscaling = false;
            upscaleProgress = 0;
            updateButtonState();
        }
    }

    /**
     * Show the upscaled image using a stacked approach for seamless switching
     */
    function showUpscaledImage(upscaledUrl) {
        if (!imageContainer) return;

        // Get or create stack
        let stack = imageContainer.querySelector('.image-stack');
        let originalImg = imageContainer.querySelector('img:not(.upscaled)');

        // Safety check - if we have a stack but no original inside, something is wrong, reset
        if (stack && !stack.querySelector('img:not(.upscaled)')) {
            // Unwrap or reset logic would go here, but for now assuming clean state or valid stack
        }

        if (!stack && originalImg) {
            // Create stack wrapper
            stack = document.createElement('div');
            stack.className = 'image-stack';

            // Layout: Absolute overlay to prevent flow impact
            // Stack container - just a positioning context
            stack.style.position = 'absolute';
            stack.style.top = '0';
            stack.style.left = '0';
            stack.style.right = '0';
            stack.style.bottom = '0';
            stack.style.boxSizing = 'border-box';
            stack.style.padding = '24px';

            // Match the padding of the parent container to keep visual consistency
            // Using a safe approximation for var(--spacing-lg)

            // Remove display: flex/grid entirely
            // Insert stack and move original image into it
            originalImg.parentNode.insertBefore(stack, originalImg);
            stack.appendChild(originalImg);

            // Original Image Constraints
            // Original image - absolutely positioned and centered
            originalImg.style.position = 'absolute';
            originalImg.style.top = '50%';
            originalImg.style.left = '50%';
            originalImg.style.transform = 'translate(-50%, -50%)';
            originalImg.style.maxWidth = '100%';
            originalImg.style.maxHeight = '100%';
            originalImg.style.width = 'auto';
            originalImg.style.height = 'auto';
            originalImg.style.objectFit = 'contain';
            originalImg.style.zIndex = '1';
        }

        if (!stack) return; // Should not happen if originalImg exists

        // Get or create upscaled image
        let upscaledImg = stack.querySelector('img.upscaled');
        if (!upscaledImg) {
            upscaledImg = document.createElement('img');
            upscaledImg.className = 'upscaled';
            upscaledImg.alt = 'Upscaled Image';

            // Upscaled Image Constraints
            // Upscaled image - identical positioning, just higher z-index
            upscaledImg.style.position = 'absolute';
            upscaledImg.style.top = '50%';
            upscaledImg.style.left = '50%';
            upscaledImg.style.transform = 'translate(-50%, -50%)';
            upscaledImg.style.maxWidth = '100%';
            upscaledImg.style.maxHeight = '100%';
            upscaledImg.style.width = 'auto';
            upscaledImg.style.height = 'auto';
            upscaledImg.style.objectFit = 'contain';
            upscaledImg.style.zIndex = '2';

            stack.appendChild(upscaledImg);
        }

        // Store original src on original image if not set (for consistency)
        if (originalImg && !originalImg.dataset.originalSrc) {
            originalImg.dataset.originalSrc = originalImg.src;
        }

        // Update upscaled source with cache buster
        const cacheBuster = upscaledUrl.includes('?') ? '&t=' : '?t=';
        upscaledImg.src = upscaledUrl + cacheBuster + Date.now();

        // Show upscaled
        upscaledImg.style.visibility = 'visible';

        showingUpscaled = true;
        updateButtonState();
    }

    /**
     * Show upscaled image from cache
     */
    function showUpscaledFromCache() {
        if (!imageContainer) return;

        // Check if we already have the stack
        const stack = imageContainer.querySelector('.image-stack');
        const upscaledImg = stack?.querySelector('img.upscaled');

        if (upscaledImg && upscaledImg.src) {
            upscaledImg.style.visibility = 'visible';
            showingUpscaled = true;
            updateButtonState();
            return;
        }

        // If not in DOM, check logic or fetch
        // Fallback to fetch check logic
        const img = imageContainer.querySelector('img:not(.upscaled)');

        // Show loading state on button
        if (upscaleBtn) {
            const iconSpan = upscaleBtn.querySelector('.upscale-icon');
            if (iconSpan) iconSpan.innerHTML = '<span class="spinner">⏳</span>';
        }

        fetch(`/api/upscale/check?filepath=${encodeURIComponent(currentFilepath)}`)
            .then(r => r.json())
            .then(data => {
                if (data.upscaled_url) {
                    showUpscaledImage(data.upscaled_url);
                } else {
                    updateButtonState();
                }
            })
            .catch(() => updateButtonState());
    }

    /**
     * Show the original image
     */
    function showOriginalImage() {
        if (!imageContainer) return;

        const stack = imageContainer.querySelector('.image-stack');
        const upscaledImg = stack?.querySelector('img.upscaled');

        if (upscaledImg) {
            upscaledImg.style.visibility = 'hidden';
        }

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

            // Remove upscaled element
            const stack = imageContainer?.querySelector('.image-stack');
            const upscaledImg = stack?.querySelector('img.upscaled');
            if (upscaledImg) {
                upscaledImg.remove();
            }

            // Optionally unwrap original if we want to clean up completely
            // But leaving stack is fine for now

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
     * Start comparing (hide upscaled temporarily)
     */
    function startComparison() {
        if (!hasUpscaled || !showingUpscaled) return; // Only compare if we are looking at upscaled

        isComparing = true;

        // Hide upscaled layer
        const stack = imageContainer?.querySelector('.image-stack');
        const upscaledImg = stack?.querySelector('img.upscaled');
        if (upscaledImg) {
            upscaledImg.style.visibility = 'hidden';
        }
    }

    /**
     * Stop comparing (show upscaled again)
     */
    function stopComparison() {
        if (!isComparing) return;

        isComparing = false;

        // Show upscaled layer
        const stack = imageContainer?.querySelector('.image-stack');
        const upscaledImg = stack?.querySelector('img.upscaled');
        if (upscaledImg) {
            upscaledImg.style.visibility = 'visible';
        }
    }

    /**
     * Re-initialize for client-side navigation
     */
    function reinit() {
        hasUpscaled = false;
        isUpscaling = false;
        showingUpscaled = false;
        isComparing = false; // Reset comparison state

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

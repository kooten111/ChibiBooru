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
    let originalMetadata = null;
    let upscaledMetadata = null;
    let preloadedOriginalSrc = null;

    // DOM Elements
    let upscaleBtn = null;
    let imageContainer = null;
    let hoverMenu = null;

    /**
     * Helper to format bytes
     */
    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 bytes';
        const k = 1024;
        const sizes = ['bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    /**
     * Update image metadata (resolution, filesize, download link)
     */
    function updateMetadata(isUpscaled, data = null) {
        const resEl = document.getElementById('metadata-resolution');
        const sizeEl = document.getElementById('metadata-filesize');
        const dlBtn = document.getElementById('download-btn');

        // Initialize original metadata on first run
        if (!originalMetadata) {
            let resText = '';
            if (resEl) {
                resText = resEl.dataset.originalResolution || resEl.textContent.trim();
                // If taking from text content and it has arrow, strip it
                if (!resEl.dataset.originalResolution && resText.includes('➜')) {
                    resText = resText.split('➜')[0].trim();
                }
            }

            originalMetadata = {
                resolution: resText,
                filesize: sizeEl ? sizeEl.textContent : '',
                downloadHref: dlBtn ? dlBtn.href : ''
            };
        }

        // If the original resolution was empty, try to update it from the element content again
        if (originalMetadata.resolution === '') {
            if (resEl) {
                // Check data attribute first (most reliable)
                if (resEl.dataset.originalResolution) {
                    originalMetadata.resolution = resEl.dataset.originalResolution;
                } else if (resEl.textContent.trim() !== '') {
                    // Fallback to text content (might be "A x B -> C x D", need to be careful)
                    const text = resEl.textContent.trim();
                    if (text.includes('➜')) {
                        // Extract original from "Original ➜ Upscaled"
                        // But text content might be just numbers, so split by ➜
                        originalMetadata.resolution = text.split('➜')[0].trim();
                    } else {
                        originalMetadata.resolution = text;
                    }
                }
            }
        }

        if (isUpscaled) {
            // ... (existing logic)
            // Ensure originalMetadata is initialized before updating
            if (!originalMetadata) {
                let resText = '';
                if (resEl) {
                    resText = resEl.dataset.originalResolution || resEl.textContent.trim();
                    if (!resEl.dataset.originalResolution && resText.includes('➜')) {
                        resText = resText.split('➜')[0].trim();
                    }
                }
                originalMetadata = {
                    resolution: resText,
                    filesize: sizeEl ? sizeEl.textContent : '',
                    downloadHref: dlBtn ? dlBtn.href : ''
                };
            }

            // Update cache if data provided
            if (data) {
                upscaledMetadata = data;
            } else if (upscaledMetadata) {
                data = upscaledMetadata;
            }

            if (data) {
                if (resEl && data.upscaled_size) {
                    // Show "Original -> Upscaled"
                    const originalRes = originalMetadata.resolution !== '...' ? originalMetadata.resolution : 'Original';
                    resEl.innerHTML = `<span style="opacity: 0.7">${originalRes}</span> ➜ <strong>${data.upscaled_size[0]}×${data.upscaled_size[1]}</strong>`;
                }
                if (sizeEl && data.upscaled_filesize) {
                    sizeEl.textContent = formatBytes(data.upscaled_filesize);
                }
                if (dlBtn && data.upscaled_url) {
                    dlBtn.href = data.upscaled_url;
                }
            }
        } else {
            // Restore original
            if (resEl) {
                // Prefer data attribute if available, as it is the ground truth
                if (resEl.dataset.originalResolution) {
                    resEl.textContent = resEl.dataset.originalResolution;
                } else {
                    resEl.textContent = originalMetadata.resolution;
                }
            }
            if (sizeEl) sizeEl.textContent = originalMetadata.filesize;
            if (dlBtn) dlBtn.href = originalMetadata.downloadHref;
        }
    }

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

        // Initialize originalMetadata first (for any metadata operations)
        // This ensures we capture the original resolution before any updates
        updateMetadata(false);

        // Check if page was loaded with a pre-rendered upscaled image
        // The template marks upscaled images with data-original-src attribute
        // Create stack eagerly to prevent layout shift on first C press
        if (imageContainer) {
            const img = imageContainer.querySelector('img[data-original-src]');
            if (img) {
                hasUpscaled = true;
                showingUpscaled = true;

                // Create stack immediately to avoid layout shift
                ensureStack();

                preloadOriginalForComparison();

                // Fetch upscaled resolution data and cache it
                fetch(`/api/upscale/check?filepath=${encodeURIComponent(currentFilepath)}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.upscaled_size) {
                            upscaledMetadata = data;
                            // Update metadata to show both resolutions in one box
                            updateMetadata(true, data);
                        }
                    })
                    .catch(() => { /* silently ignore */ });
            }
        }

        // Check upscaler status (async); stack should already be ready if upscaled exists
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
     * Lazily create the image stack for comparison.
     * Called on first C-key press or menu toggle, NOT on page load,
     * so the upscaled <img> keeps its native CSS (width:auto/height:auto)
     * and renders at full quality during normal viewing and zoom.
     */
    function ensureStack() {
        if (!imageContainer) return null;
        let stack = imageContainer.querySelector('.image-stack');
        if (stack) return stack;

        const upscaledImg = imageContainer.querySelector('img[data-original-src]');
        if (!upscaledImg) return null;

        setupStackForExistingUpscaledImage(upscaledImg);
        return imageContainer.querySelector('.image-stack');
    }

    function preloadOriginalForComparison() {
        if (!imageContainer) return;
        const upscaledImg = imageContainer.querySelector('img[data-original-src]');
        if (!upscaledImg) return;

        const originalSrc = upscaledImg.dataset.originalSrc;
        if (!originalSrc || preloadedOriginalSrc === originalSrc) return;

        preloadedOriginalSrc = originalSrc;
        const preloadImg = new Image();
        preloadImg.src = originalSrc;
    }

    /**
     * Set up image stack for a pre-rendered upscaled image
     * This is needed when the page loads with an upscaled image already rendered in the template
     * We need to create the stack structure for comparison (C key) to work
     */
    function setupStackForExistingUpscaledImage(upscaledImg) {
        if (!imageContainer || !upscaledImg) return;

        // Get the original image URL from the data attribute
        const originalSrc = upscaledImg.dataset.originalSrc;
        if (!originalSrc) return;

        // Check if the upscaled image is already loaded
        const isAlreadyLoaded = upscaledImg.complete && upscaledImg.naturalWidth > 0;

        // Create stack wrapper - fills container so both images use same frame (same size when comparing)
        const stack = document.createElement('div');
        stack.className = 'image-stack';
        stack.style.position = 'relative';
        stack.style.maxWidth = '100%';
        stack.style.maxHeight = '100%';

        // Insert stack and move upscaled image into it
        upscaledImg.parentNode.insertBefore(stack, upscaledImg);

        // Image keeps its transform (transforms target the image directly now).
        // Stack only needs transform-origin set for when comparison mode transfers transform to it.
        stack.style.transformOrigin = '0 0';

        // Enforce overlay positioning (handled by CSS Grid in .image-stack)
        upscaledImg.style.position = '';
        upscaledImg.style.top = '';
        upscaledImg.style.left = '';
        upscaledImg.style.width = '';
        upscaledImg.style.height = '';

        // Mark as upscaled and set proper z-index
        upscaledImg.classList.add('upscaled');
        upscaledImg.style.zIndex = '2';
        upscaledImg.style.visibility = 'visible';
        upscaledImg.style.display = 'block';
        upscaledImg.style.opacity = '1';
        upscaledImg.style.pointerEvents = 'auto';

        stack.appendChild(upscaledImg);

        // Notify image-viewer to recalculate transform for new DOM structure
        if (window.imageViewerAPI?.refreshTransformTarget) {
            window.imageViewerAPI.refreshTransformTarget();
        }
        if (window.imageViewerAPI?.recalculateTransformForNewTarget) {
            window.imageViewerAPI.recalculateTransformForNewTarget();
        }

        // Create original image element (hidden by default when showing upscaled)
        const originalImg = document.createElement('img');
        originalImg.src = originalSrc;
        originalImg.alt = 'Original Image';
        originalImg.className = 'original';
        originalImg.dataset.originalSrc = originalSrc;

        // Style for proper stacking
        originalImg.style.zIndex = '1';
        originalImg.style.position = '';
        originalImg.style.top = '';
        originalImg.style.left = '';
        originalImg.style.width = '';
        originalImg.style.height = '';
        originalImg.style.visibility = 'hidden';
        originalImg.style.display = 'none';
        originalImg.style.opacity = '0';
        originalImg.style.pointerEvents = 'none';

        // Insert original as the first child (behind upscaled in z-order)
        stack.insertBefore(originalImg, upscaledImg);

        // Preload the original image to prevent stutter during comparison
        // This ensures smooth switching between original and upscaled
        const preloadImg = new Image();
        preloadImg.src = originalSrc;
        // No need to append to DOM, just let browser cache it

        // If the upscaled image was already loaded when we set up the stack,
        // manually add the has-image class since the onload event already fired
        if (isAlreadyLoaded && imageContainer) {
            imageContainer.classList.add('has-image');
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
            upscaleProgress = 100;

            // Show the upscaled image with metadata update
            showUpscaledImage(data.upscaled_url, data);

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
    /**
     * Show the upscaled image using a stacked approach for seamless switching
     */
    function showUpscaledImage(upscaledUrl, data = null) {
        if (!imageContainer) return;

        // Get or create stack
        let stack = imageContainer.querySelector('.image-stack');
        let originalImg = imageContainer.querySelector('img:not(.upscaled)');

        // Safety check - if we have a stack but no original inside, something is wrong, reset
        if (stack && !stack.querySelector('img:not(.upscaled)')) {
            // Unwrap or reset logic would go here, but for now assuming clean state or valid stack
        }

        if (!stack && originalImg) {
            // Create stack - fills container so original and upscaled share same frame
            stack = document.createElement('div');
            stack.className = 'image-stack';
            stack.style.position = 'relative';
            stack.style.maxWidth = '100%';
            stack.style.maxHeight = '100%';

            originalImg.parentNode.insertBefore(stack, originalImg);

            // Transfer zoom/pan state if exists
            if (originalImg.style.transform) {
                stack.style.transform = originalImg.style.transform;
                stack.style.cursor = originalImg.style.cursor;
                stack.style.transformOrigin = originalImg.style.transformOrigin;

                originalImg.style.transform = '';
                originalImg.style.cursor = '';
                originalImg.style.transformOrigin = '';
            }

            stack.appendChild(originalImg);
            originalImg.style.zIndex = '1';

            // Clean up old inline styles if any
            originalImg.style.position = '';
            originalImg.style.top = '';
            originalImg.style.left = '';
            originalImg.style.width = '';
            originalImg.style.height = '';
        }

        if (!stack) return; // Should not happen if originalImg exists

        // Get or create upscaled image
        // Get or create upscaled image
        let upscaledImg = stack.querySelector('img.upscaled');
        if (!upscaledImg) {
            upscaledImg = document.createElement('img');
            upscaledImg.className = 'upscaled';
            upscaledImg.alt = 'Upscaled Image';
            upscaledImg.style.zIndex = '2';

            // Clean up inline styles - handled by CSS Grid
            upscaledImg.style.position = '';
            upscaledImg.style.top = '';
            upscaledImg.style.left = '';
            upscaledImg.style.width = '';
            upscaledImg.style.height = '';

            stack.appendChild(upscaledImg);
        }

        // Store original src on original image if not set (for consistency)
        if (originalImg && !originalImg.dataset.originalSrc) {
            originalImg.dataset.originalSrc = originalImg.src;
        }

        // Prepare onload handler to swap visibility cleanly
        upscaledImg.onload = () => {
            // Remove skeleton loading animation
            if (imageContainer) {
                imageContainer.classList.add('has-image');
            }

            // Only hide original if we are still showing upscaled
            if (showingUpscaled && originalImg) {
                originalImg.style.visibility = 'hidden';
                originalImg.style.display = 'none';
                // Keep stack for comparison - don't unwrap it
            }
        };

        // Add error handler to remove skeleton on load failure
        upscaledImg.onerror = () => {
            if (imageContainer) {
                imageContainer.classList.add('has-image', 'load-error');
            }
            console.error('Failed to load upscaled image:', upscaledUrl);
        };

        upscaledImg.src = upscaledUrl;

        // Show upscaled immediately (will load over original)
        upscaledImg.style.visibility = 'visible';
        upscaledImg.style.display = 'block';

        // Fallback polling in case onload doesn't fire (e.g., hard refresh)
        // Check every 100ms if image has actual dimensions
        let loadCheckAttempts = 0;
        const loadCheckInterval = setInterval(() => {
            loadCheckAttempts++;

            // Check if image is actually loaded
            if (upscaledImg.complete && upscaledImg.naturalWidth > 0) {
                // Image loaded! Manually trigger onload logic
                clearInterval(loadCheckInterval);
                if (imageContainer) {
                    imageContainer.classList.add('has-image');
                }
            } else if (loadCheckAttempts >= 100) {
                // Timeout after 10 seconds - stop polling but don't give up on display
                clearInterval(loadCheckInterval);
            }
        }, 100);

        // Update metadata (shows both resolutions in one box with arrow format)
        updateMetadata(true, data);

        showingUpscaled = true;
        updateButtonState();
    }

    /**
     * Show upscaled image from cache
     */
    function showUpscaledFromCache() {
        if (!imageContainer) return;

        // Ensure the stack exists for toggling
        const stack = ensureStack();
        const upscaledImg = stack?.querySelector('img.upscaled');

        if (upscaledImg && upscaledImg.src) {
            upscaledImg.style.visibility = 'visible';
            upscaledImg.style.display = 'block';

            // Hide original immediately since this is from cache/existing DOM
            const originalImg = stack.querySelector('img:not(.upscaled)');
            if (originalImg) {
                originalImg.style.visibility = 'hidden';
                originalImg.style.display = 'none';
            }

            showingUpscaled = true;

            // Ensure skeleton is removed since we're showing a cached image
            if (imageContainer) {
                imageContainer.classList.add('has-image');
            }

            // Update metadata to show both resolutions if cached
            updateMetadata(true, upscaledMetadata);
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
                    showUpscaledImage(data.upscaled_url, data);
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

        const stack = ensureStack();
        const upscaledImg = stack?.querySelector('img.upscaled');
        const originalImg = stack?.querySelector('img:not(.upscaled)');

        if (upscaledImg) {
            upscaledImg.style.visibility = 'hidden';
            upscaledImg.style.display = 'none';
        }
        if (originalImg) {
            originalImg.style.visibility = 'visible';
            originalImg.style.display = 'block';
        }

        showingUpscaled = false;
        updateMetadata(false);
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

            // Remove upscaled element from DOM
            const stack = imageContainer?.querySelector('.image-stack');
            const upscaledImg = stack?.querySelector('img.upscaled');
            if (upscaledImg) {
                upscaledImg.remove();
            }

            // Clear cached metadata so resolution metadata reverts to original
            upscaledMetadata = null;

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

        // Ensure stack exists for comparison
        const stack = ensureStack();
        if (!stack) return;

        const upscaledImg = stack.querySelector('img.upscaled');
        const originalImg = stack.querySelector('img:not(.upscaled)');

        // Calculate image's centering offset within the stack (before layout changes)
        const imgOffsetX = (stack.clientWidth - (upscaledImg?.clientWidth || 0)) / 2;
        const imgOffsetY = (stack.clientHeight - (upscaledImg?.clientHeight || 0)) / 2;

        // Transfer transform from image to stack, adjusting for centering offset
        if (upscaledImg && upscaledImg.style.transform) {
            const scaleMatch = upscaledImg.style.transform.match(/scale\(([^)]+)\)/);
            const translateMatch = upscaledImg.style.transform.match(/translate\(([^,]+)px,\s*([^)]+)px\)/);

            const s = scaleMatch ? parseFloat(scaleMatch[1]) : 1;
            const tx = translateMatch ? parseFloat(translateMatch[1]) : 0;
            const ty = translateMatch ? parseFloat(translateMatch[2]) : 0;

            // Convert from image-origin coords to stack-origin coords
            const stackTX = tx + imgOffsetX * (1 - s);
            const stackTY = ty + imgOffsetY * (1 - s);

            stack.style.transform = `translate(${stackTX}px, ${stackTY}px) scale(${s})`;
            stack.style.transformOrigin = '0 0';
            upscaledImg.style.transform = '';
            upscaledImg.style.transformOrigin = '';
        }

        // Add comparing class (changes images to position:absolute overlay)
        stack.classList.add('comparing');

        // Tell image-viewer to retarget to the stack
        if (window.imageViewerAPI?.refreshTransformTarget) {
            window.imageViewerAPI.refreshTransformTarget();
        }
        if (window.imageViewerAPI?.recalculateTransformForNewTarget) {
            window.imageViewerAPI.recalculateTransformForNewTarget();
        }

        // Hide upscaled, show original - use multiple properties to ensure visibility
        if (upscaledImg) {
            upscaledImg.style.visibility = 'hidden';
            upscaledImg.style.display = 'none';
            upscaledImg.style.opacity = '0';
            upscaledImg.style.pointerEvents = 'none';
            upscaledImg.style.zIndex = '1';
        }

        if (originalImg) {
            originalImg.style.visibility = 'visible';
            originalImg.style.display = 'block';
            originalImg.style.opacity = '1';
            originalImg.style.pointerEvents = 'auto';
            originalImg.style.zIndex = '2';
        }

        updateMetadata(false);
    }

    /**
     * Stop comparing (show upscaled again)
     */
    function stopComparison() {
        if (!isComparing) return;

        isComparing = false;

        // Make sure stack exists
        const stack = imageContainer?.querySelector('.image-stack');
        if (!stack) return;

        const upscaledImg = stack.querySelector('img.upscaled');
        const originalImg = stack.querySelector('img:not(.upscaled)');

        // Show upscaled again
        if (upscaledImg) {
            upscaledImg.style.visibility = 'visible';
            upscaledImg.style.display = 'block';
            upscaledImg.style.opacity = '1';
            upscaledImg.style.pointerEvents = 'auto';
        }

        if (originalImg) {
            originalImg.style.visibility = 'hidden';
            originalImg.style.display = 'none';
            originalImg.style.opacity = '0';
            originalImg.style.pointerEvents = 'none';
        }

        // Remove comparing class (image returns to flex-sized layout)
        stack.classList.remove('comparing');

        // Calculate image's centering offset (after layout change back to flex)
        const imgOffsetX = (stack.clientWidth - (upscaledImg?.clientWidth || 0)) / 2;
        const imgOffsetY = (stack.clientHeight - (upscaledImg?.clientHeight || 0)) / 2;

        // Transfer transform from stack back to image, adjusting for centering offset
        if (stack.style.transform && upscaledImg) {
            const scaleMatch = stack.style.transform.match(/scale\(([^)]+)\)/);
            const translateMatch = stack.style.transform.match(/translate\(([^,]+)px,\s*([^)]+)px\)/);

            const s = scaleMatch ? parseFloat(scaleMatch[1]) : 1;
            const stx = translateMatch ? parseFloat(translateMatch[1]) : 0;
            const sty = translateMatch ? parseFloat(translateMatch[2]) : 0;

            // Convert from stack-origin coords back to image-origin coords
            const imgTX = stx - imgOffsetX * (1 - s);
            const imgTY = sty - imgOffsetY * (1 - s);

            upscaledImg.style.transform = `translate(${imgTX}px, ${imgTY}px) scale(${s})`;
            upscaledImg.style.transformOrigin = '0 0';
            stack.style.transform = '';
            stack.style.transformOrigin = '';
        }

        // Tell image-viewer to retarget to the image
        if (window.imageViewerAPI?.refreshTransformTarget) {
            window.imageViewerAPI.refreshTransformTarget();
        }
        if (window.imageViewerAPI?.recalculateTransformForNewTarget) {
            window.imageViewerAPI.recalculateTransformForNewTarget();
        }

        // Restore metadata to upscaled
        updateMetadata(true);
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

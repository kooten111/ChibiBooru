// Image Viewer Enhancements - UI Overhaul
// Features: Collapsible sidebars, focus mode, keyboard navigation, zoom/pan

let imageViewerCleanup = null;

function initImageViewer() {
    // Clean up previous event listeners if they exist
    if (imageViewerCleanup) {
        imageViewerCleanup();
        imageViewerCleanup = null;
    }

    const imageView = document.querySelector('.image-view');
    const body = document.body;
    const isVisibleImage = (img) => {
        if (!img) return false;
        const style = window.getComputedStyle(img);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    };

    const getPreferredImgElement = (root) => {
        // First check for unwrapped upscaled image
        const upscaledActive = root?.querySelector('img.upscaled-active');
        if (upscaledActive && isVisibleImage(upscaledActive)) return upscaledActive;

        // Then check for upscaled image in stack
        const upscaled = root?.querySelector('.image-stack img.upscaled');
        if (upscaled && isVisibleImage(upscaled)) return upscaled;

        // Then check for any visible image in stack ensuring we don't pick hidden ones
        const stackImgs = root?.querySelectorAll('.image-stack img');
        if (stackImgs) {
            for (const img of stackImgs) {
                if (img.classList.contains('upscaled')) continue; // Already checked
                if (isVisibleImage(img)) return img;
            }
        }

        return root?.querySelector('img');
    };

    // Target the stack wrapper if it exists, otherwise the active upscaled image, or fallback to any image
    let transformTarget = imageView?.querySelector('.image-stack') ||
        imageView?.querySelector('img.upscaled-active') ||
        imageView?.querySelector('img');

    // We also need access to the image for dimensions/cursor, prefer the upscaled if present
    let imgElement = getPreferredImgElement(imageView);

    if (!body.classList.contains('image-page')) return;

    // Cache refs to avoid expensive DOM queries during interactions
    let cachedStack = imageView?.querySelector('.image-stack');
    let cachedUpscaledActive = imageView?.querySelector('img.upscaled-active');
    let cachedImg = imageView?.querySelector('img');

    function refreshTransformTarget() {
        cachedStack = imageView?.querySelector('.image-stack');
        cachedUpscaledActive = imageView?.querySelector('img.upscaled-active');
        cachedImg = imageView?.querySelector('img');
        transformTarget = cachedStack || cachedUpscaledActive || cachedImg;
        imgElement = getPreferredImgElement(imageView);
    }

    /**
     * Recalculate transform state for new target after DOM structure changes
     * This preserves the visual viewport when switching from img to .image-stack wrapper
     */
    function recalculateTransformForNewTarget() {
        if (!transformTarget) return;

        // Parse current transform from the target
        const currentTransform = transformTarget.style.transform;
        if (!currentTransform || currentTransform === 'none' || !currentTransform.includes('scale')) {
            return;
        }

        // Extract current transform values
        const scaleMatch = currentTransform.match(/scale\(([^)]+)\)/);
        const translateMatch = currentTransform.match(/translate\(([^,]+)px,\s*([^)]+)px\)/);

        if (!scaleMatch) return;

        const currentScale = parseFloat(scaleMatch[1]);
        const currentTranslateX = translateMatch ? parseFloat(translateMatch[1]) : 0;
        const currentTranslateY = translateMatch ? parseFloat(translateMatch[2]) : 0;

        // Update internal state to match DOM
        scale = currentScale;
        translateX = currentTranslateX;
        translateY = currentTranslateY;

        // Ensure transform-origin is set for consistency
        if (!transformTarget.style.transformOrigin) {
            transformTarget.style.transformOrigin = '0 0';
        }
    }

    // Elements
    const sidebarLeft = document.getElementById('sidebarLeft');
    const sidebarRight = document.getElementById('sidebarRight');
    const toggleLeft = document.getElementById('toggleLeft');
    const toggleRight = document.getElementById('toggleRight');
    const toggleFocus = document.getElementById('toggleFocus');
    const focusBtn = document.getElementById('focusBtn');
    const focusExit = document.getElementById('focusExit');
    const focusHint = document.getElementById('focusHint');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const zoomBtn = document.getElementById('zoomBtn');
    const floatingFavBtn = document.getElementById('floatingFavBtn');

    const floatingDeleteBtn = document.getElementById('floatingDeleteBtn');

    // Zoom/pan state
    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let startX = 0;
    let startY = 0;
    let dragStartClientX = 0;
    let dragStartClientY = 0;
    let didDrag = false;
    let suppressClick = false;
    const DRAG_CLICK_THRESHOLD = 5;
    const MIN_SCALE = 1;
    const MAX_SCALE = 8;
    let transformRaf = null;
    let lastMoveTime = 0;
    const MOVE_THROTTLE = 8; // ~120fps, allows browser to batch repaints
    let cursorUpdateScheduled = false;

    function toggleZoom() {
        // Refresh target only when toggling to catch upscaler changes
        refreshTransformTarget();

        if (scale === 1) {
            // Enter focus mode if not active
            if (!body.classList.contains('focus-mode')) {
                enterFocusMode();
            }
            scale = 2;
        } else {
            scale = 1;
            translateX = 0;
            translateY = 0;
        }
        updateTransform();
        updateCursor();
    }


    // ============================================================================
    // SIDEBAR TOGGLE
    // ============================================================================

    function toggleSidebar(side) {
        if (side === 'left') {
            body.classList.toggle('left-collapsed');
            sidebarLeft?.classList.toggle('collapsed');
            toggleLeft?.classList.toggle('active');
            localStorage.setItem('sidebar-left', !body.classList.contains('left-collapsed'));
        } else {
            body.classList.toggle('right-collapsed');
            sidebarRight?.classList.toggle('collapsed');
            toggleRight?.classList.toggle('active');
            localStorage.setItem('sidebar-right', !body.classList.contains('right-collapsed'));
        }
    }

    // Restore sidebar preferences
    if (localStorage.getItem('sidebar-left') === 'false') {
        body.classList.add('left-collapsed');
        sidebarLeft?.classList.add('collapsed');
        toggleLeft?.classList.remove('active');
    }
    if (localStorage.getItem('sidebar-right') === 'false') {
        body.classList.add('right-collapsed');
        sidebarRight?.classList.add('collapsed');
        toggleRight?.classList.remove('active');
    }

    // ============================================================================
    // FOCUS MODE
    // ============================================================================

    function enterFocusMode() {
        body.classList.add('focus-mode');
        toggleFocus?.classList.add('active');

        // Minimal GPU hint - avoid expensive contain property during transform
        if (transformTarget) {
            transformTarget.style.backfaceVisibility = 'hidden';
            transformTarget.style.WebkitBackfaceVisibility = 'hidden';
            // Skip perspective and contain - they cause expensive composition
        }

        // Reset focus hint animation
        if (focusHint) {
            focusHint.style.animation = 'none';
            requestAnimationFrame(() => {
                void focusHint.offsetHeight; // Trigger reflow in next frame
                focusHint.style.animation = '';
            });
        }
    }

    function exitFocusMode() {
        body.classList.remove('focus-mode');
        toggleFocus?.classList.remove('active');
        resetZoom();
        updateCursor();

        // Clear GPU hints
        if (transformTarget) {
            transformTarget.style.backfaceVisibility = 'visible';
            transformTarget.style.WebkitBackfaceVisibility = 'visible';
        }
    }

    // ============================================================================
    // NAVIGATION
    // ============================================================================

    function navigate(direction) {
        // Get related images from sidebar
        const relatedLinks = document.querySelectorAll('.related-thumb');
        if (relatedLinks.length > 0) {
            const targetIndex = direction === 'next' ? 0 : relatedLinks.length - 1;
            relatedLinks[targetIndex].click();
        }
    }

    // ============================================================================
    // ZOOM/PAN (preserved from original)
    // ============================================================================

    function updateTransform() {
        if (transformTarget) {
            transformTarget.style.transformOrigin = '0 0';
            transformTarget.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
        }
    }

    function scheduleTransformUpdate() {
        if (transformRaf) return;
        transformRaf = requestAnimationFrame(() => {
            transformRaf = null;
            updateTransform();
            // Update cursor in same frame to avoid separate repaint
            if (cursorUpdateScheduled) {
                cursorUpdateScheduled = false;
                updateCursor();
            }
        });
    }

    function scheduleCursorUpdate() {
        cursorUpdateScheduled = true;
        // Cursor will be updated in next scheduleTransformUpdate's RAF
        if (!transformRaf) {
            scheduleTransformUpdate();
        }
    }

    function resetZoom() {
        scale = 1;
        translateX = 0;
        translateY = 0;
        updateTransform();
    }

    function updateCursor() {
        if (!transformTarget) return;
        if (scale > 1) {
            transformTarget.style.cursor = isDragging ? 'grabbing' : 'grab';
            transformTarget.style.willChange = 'transform';
        } else {
            transformTarget.style.cursor = 'zoom-in';
            transformTarget.style.willChange = '';
        }
    }

    // ============================================================================
    // EVENT HANDLERS
    // ============================================================================

    // Image click - toggle focus mode
    const imgClickHandler = function (event) {
        if (scale === 1) {
            event.stopPropagation();
            if (body.classList.contains('focus-mode')) {
                exitFocusMode();
            } else {
                enterFocusMode();
            }
        }
    };

    // Mouse wheel to zoom (only in focus mode)
    const wheelHandler = function (event) {
        if (!body.classList.contains('focus-mode') || !transformTarget) return;
        
        const delta = -Math.sign(event.deltaY);
        const zoomIntensity = 0.1;
        const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * (1 + delta * zoomIntensity)));

        if (newScale !== scale) {
            event.preventDefault();
            // For transform-origin: 0 0, zoom toward cursor position
            const rect = transformTarget.getBoundingClientRect();
            const pointX = event.clientX;
            const pointY = event.clientY;
            
            // rect already includes current transform, so just adjust based on scale change
            const scaleRatio = newScale / scale;
            translateX = translateX + (pointX - rect.left) * (1 - scaleRatio);
            translateY = translateY + (pointY - rect.top) * (1 - scaleRatio);

            scale = newScale;
            scheduleTransformUpdate();
            scheduleCursorUpdate();
        }
    };

    // Mouse drag to pan when zoomed in
    const mouseDownHandler = function (event) {
        if (scale > 1 && transformTarget) {
            event.preventDefault();
            isDragging = true;
            startX = event.clientX - translateX;
            startY = event.clientY - translateY;
            dragStartClientX = event.clientX;
            dragStartClientY = event.clientY;
            didDrag = false;
            suppressClick = false;
            // Hint browser to pre-composite during drag
            if (transformTarget) {
                transformTarget.style.willChange = 'transform';
            }
            // Disable pointer events on body to prevent hover effects during drag
            transformTarget.style.pointerEvents = 'none';
            scheduleCursorUpdate();
        }
    };

    const mouseMoveHandler = function (event) {
        if (isDragging) {
            // Throttle pan updates to reduce repaint frequency
            const now = performance.now();
            if (now - lastMoveTime < MOVE_THROTTLE) return;
            lastMoveTime = now;

            if (!didDrag) {
                const deltaX = Math.abs(event.clientX - dragStartClientX);
                const deltaY = Math.abs(event.clientY - dragStartClientY);
                if (deltaX > DRAG_CLICK_THRESHOLD || deltaY > DRAG_CLICK_THRESHOLD) {
                    didDrag = true;
                }
            }

            translateX = event.clientX - startX;
            translateY = event.clientY - startY;
            scheduleTransformUpdate();
        }
    };

    const mouseUpHandler = function () {
        if (isDragging) {
            isDragging = false;
            if (didDrag) {
                suppressClick = true;
                didDrag = false;
            }
            if (transformTarget) {
                transformTarget.style.pointerEvents = '';
                transformTarget.style.willChange = 'auto'; // Release pre-composite hint
            }
            scheduleCursorUpdate();
        }
    };

    // Prevent context menu when dragging
    const contextMenuHandler = function (event) {
        if (scale > 1) {
            event.preventDefault();
        }
    };

    // Keyboard shortcuts
    const keydownHandler = function (event) {
        // Ignore if typing in input
        if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') return;

        switch (event.key) {
            case 'f':
            case 'F':
                event.preventDefault();
                if (body.classList.contains('focus-mode')) {
                    exitFocusMode();
                } else {
                    enterFocusMode();
                }
                break;
            case 'Escape':
                if (body.classList.contains('focus-mode')) {
                    exitFocusMode();
                }
                break;
            case 'ArrowLeft':
                navigate('prev');
                break;
            case 'ArrowRight':
                navigate('next');
                break;
            case 'h':
            case 'H':
                toggleSidebar('left');
                break;
            case 'l':
            case 'L':
                toggleSidebar('right');
                break;
            case 'z':
            case 'Z':
                toggleZoom();
                break;

        }
    };

    // Click outside image to exit focus mode
    const imageViewClickHandler = function (event) {
        // Allow exit if clicking on container OR the stack wrapper (which covers container)
        // But NOT if clicking on the actual image inside
        if ((event.target === imageView || event.target.classList.contains('image-stack')) &&
            body.classList.contains('focus-mode')) {
            exitFocusMode();
        }
    };

    // ============================================================================
    // BIND EVENTS
    // ============================================================================

    // Sidebar toggles
    toggleLeft?.addEventListener('click', () => toggleSidebar('left'));
    toggleRight?.addEventListener('click', () => toggleSidebar('right'));

    // Focus mode controls
    toggleFocus?.addEventListener('click', enterFocusMode);
    toggleFocus?.addEventListener('click', enterFocusMode);
    focusBtn?.addEventListener('click', enterFocusMode);
    focusExit?.addEventListener('click', exitFocusMode);
    zoomBtn?.addEventListener('click', toggleZoom);


    // Navigation
    prevBtn?.addEventListener('click', () => navigate('prev'));
    nextBtn?.addEventListener('click', () => navigate('next'));

    // Connect floating buttons to existing functionality
    floatingFavBtn?.addEventListener('click', () => {
        document.getElementById('favouriteBtn')?.click();
    });
    floatingDeleteBtn?.addEventListener('click', () => {
        document.getElementById('deleteImageBtn')?.click();
    });

    // Connect Edit Tags and Add to Pool buttons
    const floatingEditTagsBtn = document.getElementById('floatingEditTagsBtn');
    const floatingAddPoolBtn = document.getElementById('floatingAddPoolBtn');

    floatingEditTagsBtn?.addEventListener('click', () => {
        if (typeof toggleTagEditor === 'function') {
            toggleTagEditor();
        }
    });

    floatingAddPoolBtn?.addEventListener('click', () => {
        if (typeof showAddToPoolModal === 'function') {
            showAddToPoolModal();
        }
    });

    // Sync floating favourite button state with main button
    const mainFavBtn = document.getElementById('favouriteBtn');
    if (mainFavBtn && floatingFavBtn) {
        const observer = new MutationObserver(() => {
            const isFav = mainFavBtn.classList.contains('is-favourite');
            floatingFavBtn.textContent = isFav ? '❤️' : '🤍';
            floatingFavBtn.classList.toggle('active', isFav);
        });
        observer.observe(mainFavBtn, { attributes: true, attributeFilter: ['class'] });

        // Initial state
        const isFav = mainFavBtn.classList.contains('is-favourite');
        floatingFavBtn.textContent = isFav ? '❤️' : '🤍';
        floatingFavBtn.classList.toggle('active', isFav);
    }

    // Image zoom/pan events
    // Attach to container to catch events on any image inside

    // Named handlers for delegation
    const onDelegatedClick = (e) => {
        if (suppressClick) {
            suppressClick = false;
            return;
        }
        if (e.target.tagName === 'IMG') {
            imgClickHandler(e);
        } else {
            imageViewClickHandler(e);
        }
    };

    const onDelegatedMouseDown = (e) => {
        if (e.target.tagName === 'IMG') {
            mouseDownHandler(e);
        }
    };

    const onDelegatedContextMenu = (e) => {
        if (e.target.tagName === 'IMG') {
            contextMenuHandler(e);
        }
    };

    if (imageView) {
        imageView.addEventListener('wheel', wheelHandler, { passive: false });
        imageView.addEventListener('click', onDelegatedClick);
        imageView.addEventListener('mousedown', onDelegatedMouseDown);
        imageView.addEventListener('contextmenu', onDelegatedContextMenu);
    }

    document.addEventListener('mousemove', mouseMoveHandler);
    document.addEventListener('mouseup', mouseUpHandler);
    document.addEventListener('keydown', keydownHandler);

    // Initial cursor
    updateCursor();

    // ============================================================================
    // CLEANUP
    // ============================================================================

    imageViewerCleanup = function () {
        toggleLeft?.removeEventListener('click', () => toggleSidebar('left'));
        toggleRight?.removeEventListener('click', () => toggleSidebar('right'));
        toggleFocus?.removeEventListener('click', enterFocusMode);
        focusBtn?.removeEventListener('click', enterFocusMode);
        focusExit?.removeEventListener('click', exitFocusMode);
        prevBtn?.removeEventListener('click', () => navigate('prev'));
        nextBtn?.removeEventListener('click', () => navigate('next'));

        if (imageView) {
            imageView.removeEventListener('wheel', wheelHandler);
            imageView.removeEventListener('click', onDelegatedClick);
            imageView.removeEventListener('mousedown', onDelegatedMouseDown);
            imageView.removeEventListener('contextmenu', onDelegatedContextMenu);
        }

        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
        document.removeEventListener('keydown', keydownHandler);

        if (transformRaf) {
            cancelAnimationFrame(transformRaf);
            transformRaf = null;
        }
    };

    // ============================================================================
    // RESOLUTION DISPLAY
    // ============================================================================

    function updateImageResolution() {
        // Find the resolution display element
        const resEl = document.getElementById('metadata-resolution');
        if (!resEl) return;

        // Get the current image element (prefer original or upscaled)
        const img = getPreferredImgElement(imageView);
        if (!img) return;

        // If image is loaded, update resolution
        if (img.complete && img.naturalWidth > 0) {
            // Check if we already have a resolution set and if it matches
            // If it's a value, only update if it's different and we are looking at the original

            // If upscaled, upscaler.js handles the logic, so we only touch if not upscaled

            if (!img.classList.contains('upscaled') && !img.classList.contains('upscaled-active')) {
                // Only update if the element is empty or we really need to.
                // But better to just let it be if server rendered it.
                // However, if server didn't render it (no metadata), we still want this.
                if (!resEl.textContent.trim()) {
                    resEl.textContent = `${img.naturalWidth}×${img.naturalHeight}`;
                    const resBox = document.getElementById('resolution-stat-box');
                    if (resBox) resBox.style.display = '';
                }
            }
        } else {
            // Wait for load
            img.onload = () => updateImageResolution();
        }
    }

    // Initial check
    updateImageResolution();

    // Also listen for image load events on the container capture phase to catch any lazy loaded images
    imageView.addEventListener('load', (e) => {
        if (e.target.tagName === 'IMG') {
            updateImageResolution();
        }
    }, true);

    // Expose API for external modules to handle DOM changes
    window.imageViewerAPI = {
        recalculateTransformForNewTarget,
        refreshTransformTarget
    };
};

document.addEventListener('DOMContentLoaded', initImageViewer);

// Make initImageViewer globally accessible for re-initialization
window.initImageViewer = initImageViewer;
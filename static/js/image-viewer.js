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
    const MIN_SCALE = 1;
    const MAX_SCALE = 8;

    function toggleZoom() {
        // Always refresh target before zooming to catch upscaled image
        transformTarget = imageView?.querySelector('.image-stack') ||
            imageView?.querySelector('img.upscaled-active') ||
            imageView?.querySelector('img');
        imgElement = getPreferredImgElement(imageView);

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

        // Reset focus hint animation
        if (focusHint) {
            focusHint.style.animation = 'none';
            focusHint.offsetHeight; // Trigger reflow
            focusHint.style.animation = null;
        }
    }

    function exitFocusMode() {
        body.classList.remove('focus-mode');
        toggleFocus?.classList.remove('active');
        resetZoom();
        updateCursor();
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
            transformTarget.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
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
        } else {
            transformTarget.style.cursor = 'zoom-in';
        }
    }

    // ============================================================================
    // EVENT HANDLERS
    // ============================================================================

    // Image click - toggle focus mode
    const imgClickHandler = function (event) {
        // Refresh targets
        transformTarget = imageView?.querySelector('.image-stack') ||
            imageView?.querySelector('img.upscaled-active') ||
            imageView?.querySelector('img');
        imgElement = getPreferredImgElement(imageView);

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
        // Refresh target reference in case it changed (e.g. upscaler init)
        transformTarget = imageView?.querySelector('.image-stack') ||
            imageView?.querySelector('img.upscaled-active') ||
            imageView?.querySelector('img');
        imgElement = getPreferredImgElement(imageView);

        if (!body.classList.contains('focus-mode') || !transformTarget) return;

        event.preventDefault();

        const delta = -Math.sign(event.deltaY);
        const zoomIntensity = 0.1;
        const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * (1 + delta * zoomIntensity)));

        if (newScale !== scale) {
            // Use imgElement for rect calculation to pivot around the image center
            let rect = (imgElement || transformTarget).getBoundingClientRect();
            if (!rect.width || !rect.height) {
                rect = transformTarget.getBoundingClientRect();
            }
            const pointX = event.clientX;
            const pointY = event.clientY;
            const imgCenterX = rect.left + rect.width / 2;
            const imgCenterY = rect.top + rect.height / 2;
            const scaleChange = newScale / scale;

            translateX = pointX - imgCenterX - (pointX - imgCenterX - translateX) * scaleChange;
            translateY = pointY - imgCenterY - (pointY - imgCenterY - translateY) * scaleChange;

            scale = newScale;
            updateTransform();
            updateCursor();
        }
    };

    // Mouse drag to pan when zoomed in
    const mouseDownHandler = function (event) {
        if (scale > 1 && transformTarget) {
            event.preventDefault();
            isDragging = true;
            startX = event.clientX - translateX;
            startY = event.clientY - translateY;
            updateCursor();
        }
    };

    const mouseMoveHandler = function (event) {
        if (isDragging) {
            translateX = event.clientX - startX;
            translateY = event.clientY - startY;
            updateTransform();
        }
    };

    const mouseUpHandler = function () {
        if (isDragging) {
            isDragging = false;
            updateCursor();
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
    };
};

document.addEventListener('DOMContentLoaded', initImageViewer);

// Make initImageViewer globally accessible for re-initialization
window.initImageViewer = initImageViewer;
// Store active event listeners for cleanup
let imageViewerCleanup = null;

function initImageViewer() {
    // Clean up previous event listeners if they exist
    if (imageViewerCleanup) {
        imageViewerCleanup();
        imageViewerCleanup = null;
    }

    const imageView = document.querySelector('.image-view');
    const body = document.body;
    const img = imageView?.querySelector('img');

    if (!imageView || !body.classList.contains('image-page') || !img) return;

    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let startX = 0;
    let startY = 0;

    const MIN_SCALE = 1;
    const MAX_SCALE = 8;

    function updateTransform() {
        img.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
    }

    function resetZoom() {
        scale = 1;
        translateX = 0;
        translateY = 0;
        updateTransform();
    }

    function updateCursor() {
        if (scale > 1) {
            img.style.cursor = isDragging ? 'grabbing' : 'grab';
        } else {
            img.style.cursor = 'zoom-in';
        }
    }

    // Single click to toggle fullscreen
    const imgClickHandler = function(event) {
        if (scale === 1) {
            event.stopPropagation();
            body.classList.toggle('ui-hidden');
            // Reset position when exiting fullscreen
            if (!body.classList.contains('ui-hidden')) {
                resetZoom();
            }
        }
    };
    img.addEventListener('click', imgClickHandler);

    // Mouse wheel to zoom (only in fullscreen mode)
    const wheelHandler = function(event) {
        if (!body.classList.contains('ui-hidden')) return;

        event.preventDefault();

        const delta = -Math.sign(event.deltaY);
        const zoomIntensity = 0.1;
        const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * (1 + delta * zoomIntensity)));

        if (newScale !== scale) {
            const rect = img.getBoundingClientRect();

            // Calculate point on image where mouse is (in screen coordinates)
            const pointX = event.clientX;
            const pointY = event.clientY;

            // Calculate the center of the image in screen coordinates
            const imgCenterX = rect.left + rect.width / 2;
            const imgCenterY = rect.top + rect.height / 2;

            const scaleChange = newScale / scale;

            // New translation to keep point under cursor
            translateX = pointX - imgCenterX - (pointX - imgCenterX - translateX) * scaleChange;
            translateY = pointY - imgCenterY - (pointY - imgCenterY - translateY) * scaleChange;

            scale = newScale;
            updateTransform();
            updateCursor();
        }
    };
    imageView.addEventListener('wheel', wheelHandler, { passive: false });

    // Mouse drag to pan when zoomed in
    const mouseDownHandler = function(event) {
        if (scale > 1) {
            event.preventDefault();
            isDragging = true;
            startX = event.clientX - translateX;
            startY = event.clientY - translateY;
            updateCursor();
        }
    };
    img.addEventListener('mousedown', mouseDownHandler);

    const mouseMoveHandler = function(event) {
        if (isDragging) {
            translateX = event.clientX - startX;
            translateY = event.clientY - startY;
            updateTransform();
        }
    };
    document.addEventListener('mousemove', mouseMoveHandler);

    const mouseUpHandler = function() {
        if (isDragging) {
            isDragging = false;
            updateCursor();
        }
    };
    document.addEventListener('mouseup', mouseUpHandler);

    // Prevent context menu when dragging
    const contextMenuHandler = function(event) {
        if (scale > 1) {
            event.preventDefault();
        }
    };
    img.addEventListener('contextmenu', contextMenuHandler);

    // ESC key to exit fullscreen and reset zoom
    const keydownHandler = function(event) {
        if (event.key === 'Escape' && body.classList.contains('ui-hidden')) {
            body.classList.remove('ui-hidden');
            resetZoom();
            updateCursor();
        }
    };
    document.addEventListener('keydown', keydownHandler);

    // Click outside image to exit fullscreen and reset zoom
    const imageViewClickHandler = function(event) {
        // Check if click was on imageView (background) and not on the img itself
        if (event.target === imageView && body.classList.contains('ui-hidden')) {
            body.classList.remove('ui-hidden');
            resetZoom();
            updateCursor();
        }
    };
    imageView.addEventListener('click', imageViewClickHandler);

    // Initial cursor
    updateCursor();

    // Return cleanup function
    imageViewerCleanup = function() {
        img.removeEventListener('click', imgClickHandler);
        imageView.removeEventListener('wheel', wheelHandler);
        img.removeEventListener('mousedown', mouseDownHandler);
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
        img.removeEventListener('contextmenu', contextMenuHandler);
        document.removeEventListener('keydown', keydownHandler);
        imageView.removeEventListener('click', imageViewClickHandler);
    };
}

document.addEventListener('DOMContentLoaded', initImageViewer);

// Make initImageViewer globally accessible for re-initialization
window.initImageViewer = initImageViewer;
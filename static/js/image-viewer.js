document.addEventListener('DOMContentLoaded', function() {
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
    img.addEventListener('click', function(event) {
        if (scale === 1) {
            event.stopPropagation();
            body.classList.toggle('ui-hidden');
            // Reset position when exiting fullscreen
            if (!body.classList.contains('ui-hidden')) {
                resetZoom();
            }
        }
    });

    // Mouse wheel to zoom (only in fullscreen mode)
    imageView.addEventListener('wheel', function(event) {
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
    }, { passive: false });

    // Mouse drag to pan when zoomed in
    img.addEventListener('mousedown', function(event) {
        if (scale > 1) {
            event.preventDefault();
            isDragging = true;
            startX = event.clientX - translateX;
            startY = event.clientY - translateY;
            updateCursor();
        }
    });

    document.addEventListener('mousemove', function(event) {
        if (isDragging) {
            translateX = event.clientX - startX;
            translateY = event.clientY - startY;
            updateTransform();
        }
    });

    document.addEventListener('mouseup', function() {
        if (isDragging) {
            isDragging = false;
            updateCursor();
        }
    });

    // Prevent context menu when dragging
    img.addEventListener('contextmenu', function(event) {
        if (scale > 1) {
            event.preventDefault();
        }
    });

    // ESC key to exit fullscreen and reset zoom
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape' && body.classList.contains('ui-hidden')) {
            body.classList.remove('ui-hidden');
            resetZoom();
            updateCursor();
        }
    });

    // Click outside image to exit fullscreen and reset zoom
    imageView.addEventListener('click', function(event) {
        // Check if click was on imageView (background) and not on the img itself
        if (event.target === imageView && body.classList.contains('ui-hidden')) {
            body.classList.remove('ui-hidden');
            resetZoom();
            updateCursor();
        }
    });

    // Initial cursor
    updateCursor();
});
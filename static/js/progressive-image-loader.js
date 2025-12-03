// Progressive Image Loader
// Loads thumbnails first, then swaps to full-resolution images seamlessly
// Similar to LOD (Level of Detail) textures in games

class ProgressiveImageLoader {
    constructor() {
        this.loadQueue = [];
        this.isProcessing = false;
        this.observer = null;
        this.loadedImages = new Set();
    }

    /**
     * Initialize progressive loading for an image container
     * @param {HTMLElement} container - The container with image/video
     * @param {string} fullSizePath - Path to full resolution image
     * @param {string} thumbnailPath - Path to thumbnail (optional, will be derived)
     */
    loadProgressively(container, fullSizePath, thumbnailPath = null) {
        // Skip if already loaded
        if (this.loadedImages.has(fullSizePath)) {
            return;
        }

        // Derive thumbnail path if not provided
        if (!thumbnailPath) {
            thumbnailPath = this.getThumbnailPath(fullSizePath);
        }

        // Don't use progressive loading if thumbnail and full image are the same
        if (thumbnailPath === fullSizePath) {
            return;
        }

        const mediaElement = container.querySelector('img, video');
        if (!mediaElement) {
            console.warn('No image or video element found in container');
            return;
        }

        // Skip videos for now (they're handled separately)
        if (mediaElement.tagName === 'VIDEO') {
            return;
        }

        // Check if we're already using the thumbnail
        const currentSrc = mediaElement.getAttribute('src');
        const isThumbnail = currentSrc.includes('/thumbnails/') ||
                           currentSrc === `/static/${thumbnailPath}`;

        if (isThumbnail) {
            // Already showing thumbnail, load full image in background
            this.queueFullImageLoad(mediaElement, fullSizePath, thumbnailPath);
        } else {
            // Currently showing full image (or no image), swap to thumbnail then load full
            // This handles slow connections where the full image is still loading
            this.swapToThumbnailThenFull(mediaElement, fullSizePath, thumbnailPath);
        }
    }

    /**
     * Get thumbnail path from full image path
     */
    getThumbnailPath(fullPath) {
        // Remove /static/ prefix if present
        let path = fullPath.replace(/^\/static\//, '');

        // Check if it's already a thumbnail path
        if (path.startsWith('thumbnails/')) {
            return path;
        }

        // Convert images/path/file.ext to thumbnails/path/file.webp
        if (path.startsWith('images/')) {
            const pathWithoutImages = path.replace(/^images\//, '');
            const pathWithoutExt = pathWithoutImages.replace(/\.[^/.]+$/, '');
            return `thumbnails/${pathWithoutExt}.webp`;
        }

        return path; // Fallback to original if we can't determine thumbnail
    }

    /**
     * Swap image to thumbnail first, then load full resolution
     */
    swapToThumbnailThenFull(imgElement, fullPath, thumbPath) {
        // Remove skeleton state if present
        const thumbnail = imgElement.closest('.thumbnail');
        if (thumbnail) {
            thumbnail.classList.remove('skeleton');
            thumbnail.classList.add('has-image');
        }

        // Add loading class
        imgElement.classList.add('progressive-loading');

        // Set thumbnail immediately for instant visual feedback
        imgElement.src = `/static/${thumbPath}`;
        imgElement.dataset.fullSrc = fullPath;

        // Queue the full image load
        this.queueFullImageLoad(imgElement, fullPath, thumbPath);
    }

    /**
     * Queue full image loading
     */
    queueFullImageLoad(imgElement, fullPath, thumbPath) {
        this.loadQueue.push({
            imgElement,
            fullPath,
            thumbPath
        });

        if (!this.isProcessing) {
            this.processQueue();
        }
    }

    /**
     * Process the load queue
     */
    async processQueue() {
        if (this.loadQueue.length === 0) {
            this.isProcessing = false;
            return;
        }

        this.isProcessing = true;
        const item = this.loadQueue.shift();

        try {
            await this.loadFullImage(item.imgElement, item.fullPath, item.thumbPath);
        } catch (error) {
            console.warn(`Failed to load full image ${item.fullPath}:`, error);
        }

        // Continue processing queue
        setTimeout(() => this.processQueue(), 100); // Small delay between loads
    }

    /**
     * Load full resolution image
     */
    loadFullImage(imgElement, fullPath, thumbPath) {
        return new Promise((resolve, reject) => {
            // Create a new image to preload
            const fullImg = new Image();

            fullImg.onload = () => {
                // Mark as loaded
                this.loadedImages.add(fullPath);

                // Smooth transition to full image
                imgElement.classList.add('progressive-transitioning');

                // Use a small timeout to ensure the transition is visible
                setTimeout(() => {
                    imgElement.src = `/static/${fullPath}`;
                    imgElement.dataset.loaded = 'true';

                    // Remove loading class after transition
                    setTimeout(() => {
                        imgElement.classList.remove('progressive-loading', 'progressive-transitioning');
                    }, 300); // Match CSS transition duration
                }, 50);

                resolve();
            };

            fullImg.onerror = () => {
                console.warn(`Failed to load full image: ${fullPath}, keeping thumbnail`);
                imgElement.classList.remove('progressive-loading');
                reject(new Error(`Failed to load ${fullPath}`));
            };

            // Start loading the full image
            fullImg.src = `/static/${fullPath}`;
        });
    }

    /**
     * Initialize intersection observer for lazy loading
     * Only loads images when they're near the viewport
     */
    initLazyLoading(rootMargin = '200px') {
        if ('IntersectionObserver' in window) {
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const container = entry.target;
                        const fullPath = container.dataset.fullImage;
                        const thumbPath = container.dataset.thumbnail;

                        if (fullPath) {
                            this.loadProgressively(container, fullPath, thumbPath);
                            this.observer.unobserve(container); // Stop observing once loaded
                        }
                    }
                });
            }, {
                rootMargin: rootMargin // Start loading before element is visible
            });
        }
    }

    /**
     * Observe an element for lazy loading
     */
    observe(container) {
        if (this.observer) {
            this.observer.observe(container);
        } else {
            // Fallback if IntersectionObserver not supported
            const fullPath = container.dataset.fullImage;
            const thumbPath = container.dataset.thumbnail;
            if (fullPath) {
                this.loadProgressively(container, fullPath, thumbPath);
            }
        }
    }

    /**
     * Stop observing all elements
     */
    disconnect() {
        if (this.observer) {
            this.observer.disconnect();
        }
    }
}

// Create global instance
window.progressiveLoader = new ProgressiveImageLoader();

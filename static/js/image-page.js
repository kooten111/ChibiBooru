// static/js/image-page.js

/**
 * Handles the deletion of the current image after user confirmation.
 * This relies on the modal logic defined in modal.js
 */
function confirmDelete() {
    const filepath = document.getElementById('imageFilepath')?.value;
    if (!filepath) {
        console.error('No filepath found');
        // Use the notification system from the tag editor if available, otherwise a simple alert.
        const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
        notifier.showNotification('Error: No filepath found to delete', 'error');
        return;
    }

    // The showConfirm function is globally available from modal.js
    showConfirm('Are you sure you want to permanently delete this image?', () => {
        fetch('/api/delete_image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        })
        .then(res => {
            if (!res.ok) {
                 return res.json().then(err => { throw new Error(err.error || 'Server error') });
            }
            return res.json();
        })
        .then(data => {
            if (data.status === 'success') {
                const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
                notifier.showNotification('Image deleted!', 'success');
                // Redirect to home page after a short delay
                setTimeout(() => { window.location.href = '/'; }, 500);
            } else {
                throw new Error(data.error || 'Delete failed');
            }
        })
        .catch(err => {
            console.error('Delete error:', err);
            const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
            notifier.showNotification('Failed to delete: ' + err.message, 'error');
        });
    });
}


/**
 * Shows options dialog for retry tagging
 */
function confirmRetryTagging() {
    const overlay = document.createElement('div');
    overlay.className = 'custom-confirm-overlay';
    overlay.innerHTML = `
        <div class="custom-confirm-modal" style="max-width: 500px;">
            <h3 style="margin: 0 0 15px 0; color: #87ceeb;">🔄 Retry Tagging Options</h3>
            <p style="margin: 0 0 20px 0; color: #d0d0d0; line-height: 1.5;">
                Choose how to retry tagging for this image:
            </p>
            <div style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px;">
                <button class="retry-option-btn" data-option="online-only" style="padding: 15px; background: rgba(74, 158, 255, 0.2); border: 2px solid rgba(74, 158, 255, 0.4); border-radius: 8px; color: #87ceeb; cursor: pointer; text-align: left; transition: all 0.2s;">
                    <div style="font-weight: 600; margin-bottom: 5px;">🌐 Online Sources Only</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Try Danbooru, e621, and SauceNao. Keep current tags if nothing found.</div>
                </button>
                <button class="retry-option-btn" data-option="with-fallback" style="padding: 15px; background: rgba(251, 146, 60, 0.2); border: 2px solid rgba(251, 146, 60, 0.4); border-radius: 8px; color: #ff9966; cursor: pointer; text-align: left; transition: all 0.2s;">
                    <div style="font-weight: 600; margin-bottom: 5px;">🤖 With Local AI Fallback</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Try online sources first, then use local AI tagger if nothing found.</div>
                </button>
            </div>
            <div class="button-group">
                <button class="btn-cancel">Cancel</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnCancel = modal.querySelector('.btn-cancel');
    const optionBtns = modal.querySelectorAll('.retry-option-btn');

    // Add hover effects
    optionBtns.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
        });
        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'none';
        });
        btn.addEventListener('click', function() {
            const option = this.dataset.option;
            overlay.remove();
            retryTagging(option === 'online-only');
        });
    });

    btnCancel.onclick = () => overlay.remove();
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };
}

/**
 * Handles retrying the tagging process for images that were tagged with local_tagger.
 * @param {boolean} skipLocalFallback - If true, only try online sources and keep current tags if nothing found
 */
function retryTagging(skipLocalFallback = false) {
    const filepath = document.getElementById('imageFilepath')?.value;
    if (!filepath) {
        console.error('No filepath found');
        const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
        notifier.showNotification('Error: No filepath found', 'error');
        return;
    }

    // Show loading notification
    const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
    notifier.showNotification('Retrying tagging...', 'info');

    fetch('/api/retry_tagging', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            filepath: filepath,
            skip_local_fallback: skipLocalFallback
        })
    })
    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.error || 'Server error') });
        }
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
            const message = `Successfully retagged! Source: ${data.new_source} (${data.tag_count} tags)`;
            notifier.showNotification(message, 'success');

            // Reload the page to show updated tags
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else if (data.status === 'no_online_results') {
            const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
            notifier.showNotification('No online sources found. Current tags kept.', 'info');
        } else if (data.status === 'no_results') {
            throw new Error('No metadata found from any source. The image may not exist in any booru database.');
        } else {
            throw new Error(data.error || 'Retry failed');
        }
    })
    .catch(err => {
        console.error('Retry tagging error:', err);
        const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
        notifier.showNotification('Failed to retry tagging: ' + err.message, 'error');
    });
}


/**
 * Initialize collapsible sections for desktop and mobile
 * Handles the collapse/expand behavior of sidebar sections
 * Supports both standalone section headers and integrated panel headers
 * Pools and Information sections are collapsed by default
 */
function initCollapsibleSections() {
    const sectionHeaders = document.querySelectorAll('.mobile-toggle[data-section]');

    // Load saved states from localStorage
    const savedStates = JSON.parse(localStorage.getItem('imageSectionStates') || '{}');

    // Sections that should be collapsed by default
    const defaultCollapsed = ['pools-panel-content', 'metadata-panel-content'];

    sectionHeaders.forEach(header => {
        const sectionId = header.dataset.section;
        const content = document.getElementById(sectionId);

        if (!content) return;

        // Check if this is a panel header (integrated) or section header (standalone)
        const isPanelHeader = header.classList.contains('panel-header');

        // Restore saved state, or use default collapsed state for specific sections
        let isCollapsed;
        if (savedStates[sectionId] !== undefined) {
            isCollapsed = savedStates[sectionId];
        } else {
            // Default to collapsed for pools and metadata, expanded for others
            isCollapsed = defaultCollapsed.includes(sectionId);
        }

        if (isCollapsed) {
            header.classList.add('collapsed');
            if (!isPanelHeader) {
                // For standalone section headers, collapse the content wrapper
                content.classList.add('collapsed');
            }
        }

        // Add click handler
        header.addEventListener('click', (e) => {
            e.preventDefault();
            const isCurrentlyCollapsed = header.classList.contains('collapsed');

            // Toggle collapsed state on header
            header.classList.toggle('collapsed');

            // For standalone section headers, also toggle content wrapper
            if (!isPanelHeader) {
                content.classList.toggle('collapsed');
            }

            // Save state to localStorage
            savedStates[sectionId] = !isCurrentlyCollapsed;
            localStorage.setItem('imageSectionStates', JSON.stringify(savedStates));
        });
    });
}


/**
 * Initialize swipe gestures for mobile navigation between related images
 * With preloading and smooth crossfade transitions
 */
function initSwipeNavigation() {
    // Get all related image links
    const relatedLinks = Array.from(document.querySelectorAll('.related-thumb'));
    if (relatedLinks.length === 0) return; // No related images

    // Touch event state
    let touchStartX = 0;
    let touchStartY = 0;
    let touchEndX = 0;
    let touchEndY = 0;
    let isSwiping = false;
    let isTransitioning = false;

    // Minimum swipe distance (in pixels)
    const minSwipeDistance = 50;
    // Maximum vertical movement allowed for horizontal swipe
    const maxVerticalMovement = 100;

    // Get the main content area for swipe detection
    const imageContainer = document.querySelector('.image-view') || document.querySelector('.main-content');
    if (!imageContainer) return;

    // Preload next and previous images
    const preloadedImages = new Map();

    function preloadImage(url) {
        if (preloadedImages.has(url)) return preloadedImages.get(url);

        return fetch(url)
            .then(response => response.text())
            .then(html => {
                // Parse the HTML to extract the image src
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const imgElement = doc.querySelector('.image-view img, .image-view video');
                const videoElement = doc.querySelector('.image-view video source');

                if (imgElement) {
                    const imgSrc = videoElement ? videoElement.src : imgElement.src;
                    // Preload the actual image
                    const img = new Image();
                    img.src = imgSrc;
                    preloadedImages.set(url, { html, imgSrc, isVideo: !!videoElement });
                    return { html, imgSrc, isVideo: !!videoElement };
                }
                return null;
            })
            .catch(err => {
                console.error('Failed to preload:', url, err);
                return null;
            });
    }

    // Preload first and last related images
    if (relatedLinks.length > 0) {
        preloadImage(relatedLinks[0].href);
        if (relatedLinks.length > 1) {
            preloadImage(relatedLinks[relatedLinks.length - 1].href);
        }
    }

    // Add click handlers to all related image links for crossfade navigation
    relatedLinks.forEach((link, index) => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            if (isTransitioning) return;

            const targetUrl = link.href;

            // Start preloading if not already preloaded
            if (!preloadedImages.has(targetUrl)) {
                preloadImage(targetUrl).then(() => {
                    navigateWithCrossfade(targetUrl);
                });
            } else {
                navigateWithCrossfade(targetUrl);
            }
        });

        // Preload on hover for desktop
        link.addEventListener('mouseenter', () => {
            if (!preloadedImages.has(link.href)) {
                preloadImage(link.href);
            }
        });
    });

    // Touch start handler
    imageContainer.addEventListener('touchstart', (e) => {
        // Only start tracking if touching the image area directly (not buttons or links)
        if (e.target.closest('.actions-bar') || e.target.closest('button') || e.target.closest('a')) {
            return;
        }

        if (isTransitioning) return;

        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
        isSwiping = false;
    }, { passive: true });

    // Touch move handler
    imageContainer.addEventListener('touchmove', (e) => {
        if (touchStartX === 0 || isTransitioning) return;

        const currentX = e.changedTouches[0].screenX;
        const currentY = e.changedTouches[0].screenY;
        const diffX = Math.abs(currentX - touchStartX);
        const diffY = Math.abs(currentY - touchStartY);

        // If horizontal movement is greater than vertical, we're swiping
        if (diffX > diffY && diffX > 10) {
            isSwiping = true;
        }
    }, { passive: true });

    // Touch end handler
    imageContainer.addEventListener('touchend', (e) => {
        if (touchStartX === 0 || isTransitioning) return;

        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;

        handleSwipe();

        // Reset
        touchStartX = 0;
        touchStartY = 0;
        touchEndX = 0;
        touchEndY = 0;
        isSwiping = false;
    }, { passive: true });

    function handleSwipe() {
        const horizontalDistance = touchEndX - touchStartX;
        const verticalDistance = Math.abs(touchEndY - touchStartY);

        // Check if it's a valid horizontal swipe
        if (Math.abs(horizontalDistance) < minSwipeDistance) return;
        if (verticalDistance > maxVerticalMovement) return;
        if (!isSwiping) return;

        let targetUrl = null;

        // Swipe left = next image (first related image)
        if (horizontalDistance < 0 && relatedLinks.length > 0) {
            targetUrl = relatedLinks[0].href;
        }
        // Swipe right = previous image (last related image)
        else if (horizontalDistance > 0 && relatedLinks.length > 0) {
            targetUrl = relatedLinks[relatedLinks.length - 1].href;
        }

        if (targetUrl) {
            navigateWithCrossfade(targetUrl);
        }
    }

    function navigateWithCrossfade(targetUrl) {
        if (isTransitioning) return;
        isTransitioning = true;

        // Check if we have preloaded data
        const preloadedData = preloadedImages.get(targetUrl);

        if (preloadedData) {
            performCrossfade(targetUrl, preloadedData);
        } else {
            // Fallback: show loading and navigate normally
            showLoadingOverlay();
            window.location.href = targetUrl;
        }
    }

    function performCrossfade(targetUrl, preloadedData) {
        // Find the current image container
        const currentImageView = document.querySelector('.image-view');
        const currentImage = currentImageView?.querySelector('img, video');

        if (!currentImageView || !currentImage) {
            // Fallback if we can't find the image
            showLoadingOverlay();
            window.location.href = targetUrl;
            return;
        }

        // Fetch the full page HTML to replace content
        fetch(targetUrl)
            .then(response => response.text())
            .then(html => {
                // Parse the new page
                const parser = new DOMParser();
                const newDoc = parser.parseFromString(html, 'text/html');

                // Make the image container position relative if it isn't already
                const originalPosition = currentImageView.style.position;
                if (!originalPosition || originalPosition === 'static') {
                    currentImageView.style.position = 'relative';
                }

                // Lock the container's current height to prevent jumping
                const currentHeight = currentImageView.offsetHeight;
                currentImageView.style.height = currentHeight + 'px';
                currentImageView.style.transition = 'height 0.3s ease-in-out';

                // Add fade-out to current image
                currentImage.style.transition = 'opacity 0.3s ease-in-out';
                currentImage.style.opacity = '0';

                // Create overlay for new image
                const overlay = document.createElement('div');
                overlay.style.cssText = `
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 100;
                    opacity: 0;
                    transition: opacity 0.3s ease-in-out;
                `;

                // Create new image element
                let newMediaElement;
                if (preloadedData.isVideo) {
                    newMediaElement = document.createElement('video');
                    newMediaElement.controls = true;
                    newMediaElement.loop = true;
                    const source = document.createElement('source');
                    source.src = preloadedData.imgSrc;
                    source.type = 'video/mp4';
                    newMediaElement.appendChild(source);
                } else {
                    newMediaElement = document.createElement('img');
                    newMediaElement.src = preloadedData.imgSrc;
                    newMediaElement.alt = 'Image';
                }

                // Style new image to match container
                newMediaElement.style.cssText = `
                    max-width: 100%;
                    max-height: 100%;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    display: block;
                `;

                overlay.appendChild(newMediaElement);
                currentImageView.appendChild(overlay);

                // Wait for new image to load to get its dimensions
                const onMediaReady = () => {
                    // Calculate new height based on loaded image
                    const newHeight = newMediaElement.offsetHeight;
                    if (newHeight > 0) {
                        currentImageView.style.height = newHeight + 'px';
                    }

                    // Trigger crossfade
                    requestAnimationFrame(() => {
                        overlay.style.opacity = '1';
                    });

                    // After fade, replace page content without reload
                    setTimeout(() => {
                        replacePageContent(newDoc, targetUrl);
                    }, 300);
                };

                // Handle image vs video loading
                if (preloadedData.isVideo) {
                    newMediaElement.addEventListener('loadedmetadata', onMediaReady, { once: true });
                    // Fallback if already loaded
                    if (newMediaElement.readyState >= 1) {
                        onMediaReady();
                    }
                } else {
                    if (newMediaElement.complete) {
                        onMediaReady();
                    } else {
                        newMediaElement.addEventListener('load', onMediaReady, { once: true });
                    }
                }
            })
            .catch(err => {
                console.error('Failed to load page:', err);
                // Fallback to regular navigation
                window.location.href = targetUrl;
            });
    }

    function replacePageContent(newDoc, newUrl) {
        // Update the URL without reloading
        window.history.pushState({}, '', newUrl);

        // Update page title
        document.title = newDoc.title;

        // Load saved states from localStorage before replacing content
        const savedStates = JSON.parse(localStorage.getItem('imageSectionStates') || '{}');
        const defaultCollapsed = ['pools-panel-content', 'metadata-panel-content'];

        // Replace main content areas
        const container = document.querySelector('.container');
        const newContainer = newDoc.querySelector('.container');
        if (container && newContainer) {
            container.innerHTML = newContainer.innerHTML;

            // Immediately apply collapsed states to prevent visual jumping
            const sectionHeaders = document.querySelectorAll('.mobile-toggle[data-section]');
            sectionHeaders.forEach(header => {
                const sectionId = header.dataset.section;
                const isPanelHeader = header.classList.contains('panel-header');

                let isCollapsed;
                if (savedStates[sectionId] !== undefined) {
                    isCollapsed = savedStates[sectionId];
                } else {
                    isCollapsed = defaultCollapsed.includes(sectionId);
                }

                if (isCollapsed) {
                    header.classList.add('collapsed');
                    if (!isPanelHeader) {
                        const content = document.getElementById(sectionId);
                        if (content) content.classList.add('collapsed');
                    }
                }
            });
        }

        // Re-initialize the navigation after content is replaced
        setTimeout(() => {
            initSwipeNavigation();
            initCollapsibleSections();

            // Re-attach delete button handler
            const deleteBtn = document.getElementById('deleteImageBtn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', confirmDelete);
            }

            // Re-initialize image viewer (fullscreen/zoom functionality)
            if (typeof window.initImageViewer === 'function') {
                window.initImageViewer();
            }

            // Reload pools for the new image
            if (typeof loadPoolsForImage === 'function') {
                loadPoolsForImage();
            }
        }, 50);

        isTransitioning = false;
    }

    function showLoadingOverlay() {
        const overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: var(--bg-primary, #0a0a0f);
            z-index: 10000;
            opacity: 0;
            transition: opacity 0.2s ease-in-out;
            display: flex;
            align-items: center;
            justify-content: center;
        `;
        overlay.innerHTML = '<div style="color: #87ceeb; font-size: 1.2em;">Loading...</div>';
        document.body.appendChild(overlay);
        requestAnimationFrame(() => {
            overlay.style.opacity = '1';
        });
    }
}


// --- Main Page Initialization ---
// This ensures all scripts are loaded before we try to attach event listeners.
document.addEventListener('DOMContentLoaded', () => {
    // Initialize collapsible sections for mobile
    initCollapsibleSections();

    // Initialize swipe navigation for mobile
    initSwipeNavigation();

    // Attach event listener for the delete button
    const deleteBtn = document.getElementById('deleteImageBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', confirmDelete);
    }

    // Handle browser back/forward buttons
    window.addEventListener('popstate', () => {
        // When the user clicks back/forward, reload the page to show correct content
        window.location.reload();
    });

    // You can initialize other image-page-specific components here in the future
});
// static/js/image-page.js
import { showNotification } from './utils/notifications.js';

function findNextImageUrl() {
    const carouselImages = document.querySelectorAll('.carousel-track a[href^="/view/"]');
    if (carouselImages.length > 0) {
        return carouselImages[0].href;
    }

    const referrer = document.referrer;
    if (referrer && referrer.includes(window.location.origin)) {
        return referrer;
    }

    return null;
}

function confirmDelete() {
    const filepath = document.getElementById('imageFilepath')?.value;
    if (!filepath) {
        console.error('No filepath found');
        showNotification('Error: No filepath found to delete', 'error');
        return;
    }

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
                showNotification('Image deleted!', 'success');
                const nextUrl = findNextImageUrl();
                setTimeout(() => {
                    window.location.href = nextUrl || '/';
                }, 500);
            } else {
                throw new Error(data.error || 'Delete failed');
            }
        })
        .catch(err => {
            console.error(err);
            showNotification('Failed to delete: ' + err.message, 'error');
        });
    });
}


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
            overlay.remove();
            retryTagging(this.dataset.option === 'online-only');
        });
    });

    btnCancel.onclick = () => overlay.remove();
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };
}

function retryTagging(skipLocalFallback = false) {
    const filepath = document.getElementById('imageFilepath')?.value;
    if (!filepath) {
        console.error('No filepath found');
        const notifier = window.tagEditor || { showNotification: (msg, type) => alert(`${type}: ${msg}`) };
        notifier.showNotification('Error: No filepath found', 'error');
        return;
    }

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
            notifier.showNotification(`Successfully retagged! Source: ${data.new_source} (${data.tag_count} tags)`, 'success');
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


function initCollapsibleSections() {
    const sectionHeaders = document.querySelectorAll('.mobile-toggle[data-section]');
    const savedStates = JSON.parse(localStorage.getItem('imageSectionStates') || '{}');
    const defaultCollapsed = ['pools-panel-content', 'metadata-panel-content'];

    sectionHeaders.forEach(header => {
        const sectionId = header.dataset.section;
        const content = document.getElementById(sectionId);
        if (!content) return;

        const isPanelHeader = header.classList.contains('panel-header');
        const isCollapsed = savedStates[sectionId] !== undefined ? savedStates[sectionId] : defaultCollapsed.includes(sectionId);

        if (isCollapsed) {
            header.classList.add('collapsed');
            if (!isPanelHeader) {
                content.classList.add('collapsed');
            }
        }

        header.addEventListener('click', (e) => {
            e.preventDefault();
            const isCurrentlyCollapsed = header.classList.contains('collapsed');
            header.classList.toggle('collapsed');

            if (!isPanelHeader) {
                content.classList.toggle('collapsed');
            }

            savedStates[sectionId] = !isCurrentlyCollapsed;
            localStorage.setItem('imageSectionStates', JSON.stringify(savedStates));
        });
    });
}


function initSwipeNavigation() {
    const relatedLinks = Array.from(document.querySelectorAll('.related-thumb'));
    if (relatedLinks.length === 0) return;

    let touchStartX = 0;
    let touchStartY = 0;
    let touchEndX = 0;
    let touchEndY = 0;
    let isSwiping = false;
    let isTransitioning = false;

    const minSwipeDistance = 50;
    const maxVerticalMovement = 100;

    const imageContainer = document.querySelector('.image-view') || document.querySelector('.main-content');
    if (!imageContainer) return;

    const preloadedImages = new Map();

    function preloadImage(url) {
        if (preloadedImages.has(url)) return preloadedImages.get(url);

        return fetch(url)
            .then(response => response.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const imgElement = doc.querySelector('.image-view img, .image-view video');
                const videoElement = doc.querySelector('.image-view video source');

                if (imgElement) {
                    const imgSrc = videoElement ? videoElement.src : imgElement.src;
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

    if (relatedLinks.length > 0) {
        preloadImage(relatedLinks[0].href);
        if (relatedLinks.length > 1) {
            preloadImage(relatedLinks[relatedLinks.length - 1].href);
        }
    }

    relatedLinks.forEach((link) => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            if (isTransitioning) return;

            const targetUrl = link.href;
            if (!preloadedImages.has(targetUrl)) {
                preloadImage(targetUrl).then(() => {
                    navigateWithCrossfade(targetUrl);
                });
            } else {
                navigateWithCrossfade(targetUrl);
            }
        });

        link.addEventListener('mouseenter', () => {
            if (!preloadedImages.has(link.href)) {
                preloadImage(link.href);
            }
        });
    });

    imageContainer.addEventListener('touchstart', (e) => {
        if (e.target.closest('.actions-bar') || e.target.closest('button') || e.target.closest('a')) {
            return;
        }
        if (isTransitioning) return;

        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
        isSwiping = false;
    }, { passive: true });

    imageContainer.addEventListener('touchmove', (e) => {
        if (touchStartX === 0 || isTransitioning) return;

        const currentX = e.changedTouches[0].screenX;
        const currentY = e.changedTouches[0].screenY;
        const diffX = Math.abs(currentX - touchStartX);
        const diffY = Math.abs(currentY - touchStartY);

        if (diffX > diffY && diffX > 10) {
            isSwiping = true;
        }
    }, { passive: true });

    imageContainer.addEventListener('touchend', (e) => {
        if (touchStartX === 0 || isTransitioning) return;

        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;

        handleSwipe();

        touchStartX = 0;
        touchStartY = 0;
        touchEndX = 0;
        touchEndY = 0;
        isSwiping = false;
    }, { passive: true });

    function handleSwipe() {
        const horizontalDistance = touchEndX - touchStartX;
        const verticalDistance = Math.abs(touchEndY - touchStartY);

        if (Math.abs(horizontalDistance) < minSwipeDistance) return;
        if (verticalDistance > maxVerticalMovement) return;
        if (!isSwiping) return;

        let targetUrl = null;
        if (horizontalDistance < 0 && relatedLinks.length > 0) {
            targetUrl = relatedLinks[0].href;
        } else if (horizontalDistance > 0 && relatedLinks.length > 0) {
            targetUrl = relatedLinks[relatedLinks.length - 1].href;
        }

        if (targetUrl) {
            navigateWithCrossfade(targetUrl);
        }
    }

    function navigateWithCrossfade(targetUrl) {
        if (isTransitioning) return;
        isTransitioning = true;

        const preloadedData = preloadedImages.get(targetUrl);
        if (preloadedData) {
            performCrossfade(targetUrl, preloadedData);
        } else {
            showLoadingOverlay();
            window.location.href = targetUrl;
        }
    }

    function performCrossfade(targetUrl, preloadedData) {
        const currentImageView = document.querySelector('.image-view');
        const currentImage = currentImageView?.querySelector('img, video');

        if (!currentImageView || !currentImage) {
            showLoadingOverlay();
            window.location.href = targetUrl;
            return;
        }

        fetch(targetUrl)
            .then(response => response.text())
            .then(html => {
                const parser = new DOMParser();
                const newDoc = parser.parseFromString(html, 'text/html');

                const originalPosition = currentImageView.style.position;
                if (!originalPosition || originalPosition === 'static') {
                    currentImageView.style.position = 'relative';
                }

                const containerWidth = currentImageView.clientWidth;
                const containerHeight = currentImageView.clientHeight;

                currentImage.style.transition = 'opacity 0.3s ease-in-out';
                currentImage.style.opacity = '0';

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
                    padding: var(--spacing-lg);
                `;

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

                newMediaElement.style.cssText = `
                    max-width: 100%;
                    max-height: 100%;
                    width: auto;
                    height: auto;
                    object-fit: contain;
                    display: block;
                    border-radius: var(--radius-xl);
                    box-shadow: var(--shadow-2xl);
                    border: var(--border-width) solid var(--border-color);
                    opacity: 0;
                `;

                overlay.appendChild(newMediaElement);
                currentImageView.appendChild(overlay);

                const onMediaReady = () => {
                    const naturalWidth = preloadedData.isVideo ? newMediaElement.videoWidth : newMediaElement.naturalWidth;
                    const naturalHeight = preloadedData.isVideo ? newMediaElement.videoHeight : newMediaElement.naturalHeight;

                    if (naturalWidth && naturalHeight) {
                        const scaleX = containerWidth / naturalWidth;
                        const scaleY = containerHeight / naturalHeight;
                        const scale = Math.min(scaleX, scaleY, 1);

                        const displayWidth = Math.floor(naturalWidth * scale);
                        const displayHeight = Math.floor(naturalHeight * scale);

                        newMediaElement.style.width = displayWidth + 'px';
                        newMediaElement.style.height = displayHeight + 'px';
                    }

                    newMediaElement.style.opacity = '1';

                    requestAnimationFrame(() => {
                        overlay.style.opacity = '1';
                    });

                    setTimeout(() => {
                        replacePageContent(newDoc, targetUrl);
                    }, 300);
                };

                if (preloadedData.isVideo) {
                    newMediaElement.addEventListener('loadedmetadata', onMediaReady, { once: true });
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
                window.location.href = targetUrl;
            });
    }

    function replacePageContent(newDoc, newUrl) {
        window.history.pushState({}, '', newUrl);
        document.title = newDoc.title;

        const savedStates = JSON.parse(localStorage.getItem('imageSectionStates') || '{}');
        const defaultCollapsed = ['pools-panel-content', 'metadata-panel-content'];

        const container = document.querySelector('.container');
        const newContainer = newDoc.querySelector('.container');
        if (container && newContainer) {
            container.innerHTML = newContainer.innerHTML;

            const sectionHeaders = document.querySelectorAll('.mobile-toggle[data-section]');
            sectionHeaders.forEach(header => {
                const sectionId = header.dataset.section;
                const isPanelHeader = header.classList.contains('panel-header');
                const isCollapsed = savedStates[sectionId] !== undefined ? savedStates[sectionId] : defaultCollapsed.includes(sectionId);

                if (isCollapsed) {
                    header.classList.add('collapsed');
                    if (!isPanelHeader) {
                        const content = document.getElementById(sectionId);
                        if (content) content.classList.add('collapsed');
                    }
                }
            });
        }

        setTimeout(() => {
            initSwipeNavigation();
            initCollapsibleSections();

            const deleteBtn = document.getElementById('deleteImageBtn');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', confirmDelete);
            }

            if (typeof window.initImageViewer === 'function') {
                window.initImageViewer();
            }

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


document.addEventListener('DOMContentLoaded', () => {
    initCollapsibleSections();
    initSwipeNavigation();

    const deleteBtn = document.getElementById('deleteImageBtn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', confirmDelete);
    }

    window.addEventListener('popstate', () => {
        window.location.reload();
    });
});
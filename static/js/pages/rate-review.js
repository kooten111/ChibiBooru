// static/js/pages/rate-review.js - Modern Rating Review Page
import { showNotification } from '../utils/notifications.js';
import { normalizeImagePath, getImageUrl } from '../utils/path-utils.js';

// Configuration constants
const RATING_KEYS = {
    '1': 'rating:general',
    '2': 'rating:sensitive',
    '3': 'rating:questionable',
    '4': 'rating:explicit'
};

const RATING_COLORS = {
    'rating:general': 'var(--rating-general)',
    'rating:sensitive': 'var(--rating-sensitive)',
    'rating:questionable': 'var(--rating-questionable)',
    'rating:explicit': 'var(--rating-explicit)'
};

// State
let currentImage = null;
let currentFilter = 'unrated';
let isLoading = false;
let imageHistory = []; // Stack for previous images
let imagePool = []; // Pool of images to cycle through
let currentPoolIndex = 0; // Current index in the pool
let seenImageIds = new Set(); // Track all image IDs we've seen to avoid duplicates
let lastSeenImageId = 0; // Track the highest ID we've seen to fetch next batch
const POOL_SIZE = 100; // Number of images to fetch at once
const REFETCH_THRESHOLD = 80; // Refetch when we reach this index (80th image, 0-indexed)

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Check initial filter from URL or default
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('filter')) {
        currentFilter = urlParams.get('filter');
        const radio = document.querySelector(`input[name="filter"][value="${currentFilter}"]`);
        if (radio) radio.checked = true;
    }

    // Initial load
    loadNextImage();

    // Setup keyboard shortcuts
    setupKeyboard();

    // Setup tags toggle
    document.getElementById('tagsToggleIcon').addEventListener('click', toggleTags);
});

// Setup keyboard shortcuts
function setupKeyboard() {
    document.addEventListener('keydown', (e) => {
        // Ignore if input focused
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // Rating shortcuts (1-4)
        if (RATING_KEYS[e.key]) {
            setRating(RATING_KEYS[e.key], parseInt(e.key));
            return;
        }

        switch (e.key.toLowerCase()) {
            case 'arrowright':
            case 'n':
                nextImage();
                break;
            case 'arrowleft':
            case 'p':
                previousImage();
                break;
            case 's':
                skipImage();
                break;
            case 't':
                toggleTags();
                break;
        }
    });
}

// Change filter
window.changeFilter = function () {
    const radios = document.getElementsByName('filter');
    for (const radio of radios) {
        if (radio.checked) {
            currentFilter = radio.value;
            break;
        }
    }
    // Reset state when filter changes
    imageHistory = [];
    imagePool = [];
    currentPoolIndex = 0;
    seenImageIds = new Set();
    lastSeenImageId = 0;
    currentImage = null;
    // Clear current display
    const display = document.getElementById('imageDisplay');
    display.innerHTML = '';
    // Load next image with new filter
    loadNextImage();
};

// Fetch a batch of images for the pool, starting after the last seen image ID
async function fetchImagePool() {
    try {
        let url = `/api/rate/images?filter=${currentFilter}&limit=${POOL_SIZE}`;
        if (lastSeenImageId > 0) {
            url += `&after_id=${lastSeenImageId}`;
        }
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.error || !data.images || data.images.length === 0) {
            return [];
        }
        
        // Filter out images we've already seen (safety check)
        const newImages = data.images.filter(img => !seenImageIds.has(img.id));
        
        // If we got new images, update lastSeenImageId to the highest ID in the batch
        if (newImages.length > 0) {
            const maxId = Math.max(...newImages.map(img => img.id));
            if (maxId > lastSeenImageId) {
                lastSeenImageId = maxId;
            }
        }
        
        return newImages;
    } catch (error) {
        console.error('Error fetching image pool:', error);
        return [];
    }
}

// Load next image from pool
window.loadNextImage = async function () {
    if (isLoading) return;
    isLoading = true;

    const display = document.getElementById('imageDisplay');
    const loadingState = document.getElementById('loadingState');

    // Show loading state if taking too long
    const loadingTimeout = setTimeout(() => {
        display.innerHTML = '';
        display.appendChild(loadingState);
        loadingState.style.display = 'block';
        updateProgress('Loading...', 0);
    }, 200);

    try {
        // If pool is empty or we're at the threshold, fetch more
        if (imagePool.length === 0 || currentPoolIndex >= REFETCH_THRESHOLD) {
            const newImages = await fetchImagePool();
            if (newImages.length > 0) {
                // If we're at threshold, append to existing pool, otherwise replace
                if (currentPoolIndex >= REFETCH_THRESHOLD && imagePool.length > 0) {
                    // Add new images to pool (they're already filtered by fetchImagePool)
                    imagePool = imagePool.concat(newImages);
                } else {
                    imagePool = newImages;
                    currentPoolIndex = 0;
                }
            }
        }

        // If still no images, show empty state
        if (imagePool.length === 0) {
            clearTimeout(loadingTimeout);
            showEmptyState('No more images found matching the current filter.');
            return;
        }

        // Get next image from pool
        if (currentPoolIndex >= imagePool.length) {
            // Pool exhausted, fetch more
            const newImages = await fetchImagePool();
            if (newImages.length > 0) {
                imagePool = imagePool.concat(newImages);
            }
        }

        if (currentPoolIndex >= imagePool.length) {
            clearTimeout(loadingTimeout);
            showEmptyState('No more images found matching the current filter.');
            return;
        }

        const data = imagePool[currentPoolIndex];
        currentPoolIndex++;

        clearTimeout(loadingTimeout);

        if (data.error) {
            showEmptyState(data.error);
        } else {
            // Mark this image as seen and update last seen ID
            seenImageIds.add(data.id);
            if (data.id > lastSeenImageId) {
                lastSeenImageId = data.id;
            }
            currentImage = data;
            renderImage(data);
            // Preload next one
            preloadNext();
        }
    } catch (error) {
        clearTimeout(loadingTimeout);
        console.error('Error loading image:', error);
        showNotification('Error loading image', 'error');
        showEmptyState('Error loading images. Please try again.');
    } finally {
        isLoading = false;
        updateProgress('Ready', 100);
    }
};

// Preload next image from pool (if available)
async function preloadNext() {
    try {
        // Check if we have a next image in the pool
        if (currentPoolIndex < imagePool.length) {
            const nextData = imagePool[currentPoolIndex];
            // Preload actual image asset
            const img = new Image();
            const normalizedPath = normalizeImagePath(nextData.filepath);
            img.src = getImageUrl(normalizedPath);
        } else if (currentPoolIndex >= REFETCH_THRESHOLD) {
            // Prefetch next batch in background
            fetchImagePool().then(newImages => {
                if (newImages.length > 0) {
                    const seenIds = new Set();
                    imagePool.forEach(img => seenIds.add(img.id));
                    if (currentImage?.id) seenIds.add(currentImage.id);
                    imageHistory.forEach(img => seenIds.add(img.id));
                    
                    const filtered = newImages.filter(img => !seenIds.has(img.id));
                    if (filtered.length > 0) {
                        imagePool = imagePool.concat(filtered);
                    }
                }
            });
        }
    } catch (e) {
        // Ignore preload errors
    }
}

// Render image to DOM
function renderImage(data) {
    const container = document.getElementById('imageDisplay');
    const isVideo = data.filepath.match(/\.(mp4|webm|mov)$/i);

    // Normalize filepath to remove 'images/' prefix if present, then use getImageUrl
    const normalizedPath = normalizeImagePath(data.filepath);
    const imageUrl = getImageUrl(normalizedPath);

    let content = '';
    if (isVideo) {
        content = `
            <video src="${imageUrl}" controls autoplay loop muted>
            </video>
        `;
    } else {
        content = `
            <img src="${imageUrl}" alt="Image to rate">
        `;
    }

    container.innerHTML = content;

    // Update AI suggestion
    const aiBadge = document.getElementById('aiSuggestion');
    const aiText = document.getElementById('aiSuggestionText');
    const confidenceBar = document.getElementById('confidenceBar');
    const confidenceFill = document.getElementById('confidenceFill');
    const confidenceValue = document.getElementById('confidenceValue');

    if (data.ai_rating) {
        const ratingName = data.ai_rating.replace('rating:', '');
        const confidence = (data.ai_confidence * 100).toFixed(1);

        aiText.textContent = `AI suggests: ${ratingName.charAt(0).toUpperCase() + ratingName.slice(1)}`;
        aiBadge.className = `ai-suggestion-badge ${ratingName}`; // Helper class for color
        aiBadge.style.display = 'flex';

        // Update confidence bar
        confidenceValue.textContent = `${confidence}%`;
        confidenceFill.style.width = `${confidence}%`;

        // Color code confidence
        if (data.ai_confidence > 0.8) confidenceFill.style.background = 'var(--success)';
        else if (data.ai_confidence > 0.5) confidenceFill.style.background = 'var(--warning)';
        else confidenceFill.style.background = 'var(--rating-explicit)'; // Low confidence red

        confidenceBar.style.display = 'block';
    } else {
        aiBadge.style.display = 'none';
        confidenceBar.style.display = 'none';
    }

    // Render tags (initially hidden if collapsed)
    renderTags(data.tags);
    updateTagCount(Object.values(data.tags).reduce((a, b) => a + b.length, 0));
}

// Render tags
function renderTags(tags) {
    const container = document.getElementById('imageTags');
    const sortedCategories = ['character', 'copyright', 'artist', 'general', 'meta'];

    let html = '';

    sortedCategories.forEach(cat => {
        if (tags[cat] && tags[cat].length > 0) {
            html += `
                <div class="tag-category">
                    <h4 class="category-name ${cat}">${cat.charAt(0).toUpperCase() + cat.slice(1)}</h4>
                    <div class="tag-list">
                        ${tags[cat].map(tag => `
                            <span class="tag ${cat}" onclick="window.open('/tags?query=${tag}', '_blank')">
                                ${tag}
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }
    });

    container.innerHTML = html;
}

// Set rating
window.setRating = async function (rating, keyIndex) {
    if (!currentImage || isLoading) return;

    // Visual feedback on button
    const btn = document.querySelector(`.rating-btn:nth-child(${keyIndex})`);
    btn.classList.add('active');
    setTimeout(() => btn.classList.remove('active'), 200);

    // Save current image for history
    const previous = currentImage;

    try {
        // Wait for rating to be saved before loading next image
        const response = await fetch('/api/rate/rate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_id: currentImage.id,
                rating: rating
            })
        });
        
        const data = await response.json();
        
        if (data.status !== 'success') {
            showNotification('Failed to save rating', 'error');
            return; // Don't proceed if rating failed
        }

        // Show success notification
        showNotification(`Rated as ${rating.replace('rating:', '')}`, 'success');

        // Add to history
        imageHistory.push(previous);

        // Move to next image from pool
        await loadNextImage();

    } catch (error) {
        console.error('Rating error:', error);
        showNotification('Network error', 'error');
    }
};

// Skip image
window.skipImage = async function () {
    if (!currentImage) {
        // No current image, just load next
        await loadNextImage();
        return;
    }
    
    // Save current image for history
    const previous = currentImage;
    
    // Add to history
    imageHistory.push(previous);
    showNotification('Skipped image', 'info');
    
    // Load next image from pool
    await loadNextImage();
};

// Previous image
window.previousImage = function () {
    if (imageHistory.length === 0) {
        showNotification('No previous image', 'warning');
        return;
    }

    const prev = imageHistory.pop();
    currentImage = prev;
    renderImage(prev);
    
    // Decrement pool index when going back
    if (currentPoolIndex > 0) {
        currentPoolIndex--;
    }
};

// Next image
window.nextImage = async function () {
    if (!currentImage) {
        // No current image, just load next
        await loadNextImage();
        return;
    }
    
    // Save current image for history
    const previous = currentImage;
    
    // Add to history
    imageHistory.push(previous);
    
    // Load next image from pool
    await loadNextImage();
};

// Toggle tags visibility
window.toggleTags = function () {
    const tagsDiv = document.getElementById('imageTags');
    const icon = document.getElementById('tagsToggleIcon');

    if (tagsDiv.style.display === 'none') {
        tagsDiv.style.display = 'block';
        icon.style.transform = 'rotate(180deg)';
    } else {
        tagsDiv.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
};

// Update tag count
function updateTagCount(count) {
    document.getElementById('tagCount').textContent = `(${count} tags)`;
}

// Show empty state
function showEmptyState(message) {
    const container = document.getElementById('imageDisplay');
    container.innerHTML = `
        <div style="text-align: center; padding: 4rem; color: var(--text-muted);">
            <div style="font-size: 4rem; margin-bottom: 1rem;">🎉</div>
            <h3>${message || 'All done!'}</h3>
            <p>No more images found matching the current filter.</p>
            <div style="margin-top: 2rem;">
                <button class="btn btn-primary" onclick="window.location.reload()">Refresh Page</button>
            </div>
        </div>
    `;

    // Hide specialized UI elements
    document.getElementById('aiSuggestion').style.display = 'none';
    document.getElementById('confidenceBar').style.display = 'none';
}

// Update progress bar (progress elements removed, function kept for compatibility)
function updateProgress(text, percent) {
    // Progress elements removed - no longer displayed
    const progressText = document.getElementById('progressText');
    const progressBar = document.getElementById('progressBar');
    if (progressText) progressText.textContent = text;
    if (progressBar) progressBar.style.width = `${percent}%`;
}

// Shuffle images (client side effective reload with shuffle)
window.shuffleImages = async function () {
    showNotification('Shuffling queue...', 'info');
    // Reset pool and reload
    imagePool = [];
    currentPoolIndex = 0;
    imageHistory = [];
    seenImageIds = new Set();
    lastSeenImageId = 0;
    loadNextImage();
};

// static/js/pages/rate-review.js - Rating Review Page
import { showNotification } from '../utils/notifications.js';

let currentImages = [];
let currentIndex = 0;
let currentFilter = 'unrated';

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Don't trigger if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
        case '1':
            setRating('rating:general');
            break;
        case '2':
            setRating('rating:sensitive');
            break;
        case '3':
            setRating('rating:questionable');
            break;
        case '4':
            setRating('rating:explicit');
            break;
        case 'n':
        case 'N':
        case 'ArrowRight':
            nextImage();
            break;
        case 'p':
        case 'P':
        case 'ArrowLeft':
            previousImage();
            break;
        case 's':
        case 'S':
            skipImage();
            break;
    }
});

// Filter change handlers
document.querySelectorAll('input[name="filter"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        currentFilter = e.target.value;
        currentIndex = 0;
        loadImages();
    });
});

async function loadImages() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) {
        loadingState.style.display = 'block';
    }
    document.getElementById('imageDisplay').innerHTML = '<div class="loading-state">Loading images...</div>';

    try {
        const response = await fetch('/api/rate/images?filter=' + currentFilter);
        const data = await response.json();

        currentImages = data.images || [];
        currentIndex = 0;

        if (currentImages.length === 0) {
            document.getElementById('imageDisplay').innerHTML =
                '<div class="no-images-state">No images to rate! 🎉</div>';
            document.getElementById('rateProgress').textContent = 'All done!';
        } else {
            displayCurrentImage();
        }
    } catch (error) {
        console.error('Error loading images:', error);
        document.getElementById('imageDisplay').innerHTML =
            '<div class="no-images-state">Error loading images: ' + error.message + '</div>';
        document.getElementById('rateProgress').textContent = 'Error';
    }
}

function displayCurrentImage() {
    if (currentImages.length === 0) {
        document.getElementById('imageDisplay').innerHTML =
            '<div class="no-images-state">No images to rate! 🎉</div>';
        return;
    }

    const image = currentImages[currentIndex];
    const progress = `Image ${currentIndex + 1} / ${currentImages.length}`;
    document.getElementById('rateProgress').textContent = progress;

    const filepath = image.filepath || image.path; // Support both old and new API
    const isVideo = filepath.endsWith('.mp4') || filepath.endsWith('.webm');
    const videoType = filepath.endsWith('.webm') ? 'video/webm' : 'video/mp4';
    const mediaTag = isVideo
        ? `<video controls autoplay loop preload="metadata"><source src="/static/images/${filepath}" type="${videoType}"></video>`
        : `<img src="/static/images/${filepath}" alt="Image to rate">`;

    let aiSuggestion = '';
    if (image.ai_rating && image.ai_confidence) {
        const ratingName = image.ai_rating.split(':')[1];
        const confidence = Math.round(image.ai_confidence * 100);
        aiSuggestion = `
            <div class="ai-suggestion">
                <strong>AI Suggestion:</strong> ${ratingName} (${confidence}% confidence)
            </div>
        `;
    }

    const tags = (image.tags || []).map(tag => `<span class="tag">${tag}</span>`).join('');

    document.getElementById('imageDisplay').innerHTML = `
        ${mediaTag}
        <div class="image-info">
            ${aiSuggestion}
            <div class="image-tags">
                ${tags}
            </div>
            <div class="rating-buttons">
                <button class="rating-btn rating-btn-general" onclick="setRating('rating:general')">
                    General<br><small>(1)</small>
                </button>
                <button class="rating-btn rating-btn-sensitive" onclick="setRating('rating:sensitive')">
                    Sensitive<br><small>(2)</small>
                </button>
                <button class="rating-btn rating-btn-questionable" onclick="setRating('rating:questionable')">
                    Questionable<br><small>(3)</small>
                </button>
                <button class="rating-btn rating-btn-explicit" onclick="setRating('rating:explicit')">
                    Explicit<br><small>(4)</small>
                </button>
            </div>
            <div class="navigation-buttons">
                <button class="nav-btn" onclick="previousImage()" ${currentIndex === 0 ? 'disabled' : ''}>
                    ← Previous (P)
                </button>
                <button class="nav-btn" onclick="skipImage()">
                    Skip (S)
                </button>
                <button class="nav-btn nav-btn-primary" onclick="nextImage()" ${currentIndex >= currentImages.length - 1 ? 'disabled' : ''}>
                    Next (N / →)
                </button>
            </div>
        </div>
    `;
}

async function setRating(rating) {
    const image = currentImages[currentIndex];

    try {
        const response = await fetch('/api/rate/set', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                image_id: image.id,
                rating: rating
            })
        });

        const result = await response.json();

        if (result.success) {
            // Move to next image
            nextImage();
        } else {
            showNotification('Error setting rating: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error setting rating:', error);
        showNotification('Error setting rating: ' + error.message, 'error');
    }
}

function nextImage() {
    if (currentIndex < currentImages.length - 1) {
        currentIndex++;
        displayCurrentImage();
    } else {
        // Reload images to get new ones
        loadImages();
    }
}

function previousImage() {
    if (currentIndex > 0) {
        currentIndex--;
        displayCurrentImage();
    }
}

function skipImage() {
    nextImage();
}

// Expose functions to window for onclick handlers
window.setRating = setRating;
window.nextImage = nextImage;
window.previousImage = previousImage;
window.skipImage = skipImage;

// Load images on page load
loadImages();

// static/js/pages/rate-review-v2.js - Modern Rating Review Page
import { showNotification } from '../utils/notifications.js';

// Configuration constants
const VIDEO_EXTENSIONS = ['.mp4', '.webm', '.mov', '.avi'];

let images = [];
let currentIndex = 0;
let currentFilter = 'unrated';
let tagsExpanded = false;

// Load images based on filter
async function loadImages() {
    try {
        updateFooterStatus('Loading images...');
        
        const response = await fetch(`/api/rate/images?filter=${currentFilter}&limit=200`);
        const data = await response.json();
        
        if (!data.images || data.images.length === 0) {
            document.getElementById('imageDisplay').innerHTML = `
                <div style="padding: 4rem; text-align: center; color: var(--text-muted);">
                    <div style="font-size: 3em; margin-bottom: 1rem;">📭</div>
                    <div style="font-size: 1.2em;">No images found</div>
                    <div style="margin-top: 1rem; font-size: 0.9em;">
                        Try changing the filter or add more images
                    </div>
                </div>
            `;
            updateProgress(0, 0);
            updateFooterStatus('No images to rate');
            return;
        }
        
        images = data.images;
        currentIndex = 0;
        
        showCurrentImage();
        updateProgress(currentIndex + 1, images.length);
        updateFooterStatus(`Loaded ${images.length} images`);
        
    } catch (error) {
        console.error('Error loading images:', error);
        showNotification('Error loading images: ' + error.message, 'error');
        updateFooterStatus('Error loading images');
    }
}

// Show current image
function showCurrentImage() {
    if (!images || images.length === 0) {
        return;
    }
    
    const image = images[currentIndex];
    const container = document.getElementById('imageDisplay');
    
    // Determine if it's a video
    const isVideo = image.filepath && VIDEO_EXTENSIONS.some(ext => image.filepath.toLowerCase().endsWith(ext));
    
    // Create media element
    let mediaHTML;
    if (isVideo) {
        mediaHTML = `
            <video controls autoplay loop style="max-width: 100%; max-height: 70vh; border-radius: 0.75rem; box-shadow: var(--shadow-xl);">
                <source src="/${image.filepath}" type="video/${image.filepath.split('.').pop()}">
                Your browser does not support the video tag.
            </video>
        `;
    } else {
        mediaHTML = `
            <img src="/${image.filepath}" alt="Image ${image.id}" 
                 style="max-width: 100%; max-height: 70vh; border-radius: 0.75rem; box-shadow: var(--shadow-xl);">
        `;
    }
    
    container.innerHTML = mediaHTML;
    
    // Show AI suggestion if available
    const aiSuggestion = document.getElementById('aiSuggestion');
    const confidenceBar = document.getElementById('confidenceBar');
    
    if (image.ai_rating && image.rating_source === 'ai_inference') {
        const ratingLabel = image.ai_rating.replace('rating:', '');
        document.getElementById('aiSuggestionText').textContent = `AI suggests: ${ratingLabel}`;
        aiSuggestion.style.display = 'flex';
        
        // Show confidence
        const confidence = image.ai_confidence || 0.7;
        document.getElementById('confidenceValue').textContent = Math.round(confidence * 100) + '%';
        document.getElementById('confidenceFill').style.width = (confidence * 100) + '%';
        confidenceBar.style.display = 'block';
    } else {
        aiSuggestion.style.display = 'none';
        confidenceBar.style.display = 'none';
    }
    
    // Update tags
    updateImageTags(image);
    
    // Update progress
    updateProgress(currentIndex + 1, images.length);
}

// Update image tags display
function updateImageTags(image) {
    const tagsContainer = document.getElementById('imageTags');
    const tagCountEl = document.getElementById('tagCount');
    
    if (!image.tags || image.tags.length === 0) {
        tagCountEl.textContent = '(0 tags)';
        tagsContainer.innerHTML = '<div style="color: var(--text-muted);">No tags</div>';
        return;
    }
    
    tagCountEl.textContent = `(${image.tags.length} tags)`;
    
    tagsContainer.innerHTML = `
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
            ${image.tags.map(tag => `
                <span style="
                    background: var(--modern-panel-light);
                    border: 1px solid var(--cyan-border);
                    border-radius: 0.5rem;
                    padding: 0.25rem 0.75rem;
                    font-size: 0.85em;
                    color: var(--text-primary);
                ">
                    ${tag}
                </span>
            `).join('')}
        </div>
    `;
}

// Update progress indicator
function updateProgress(current, total) {
    const progressText = document.getElementById('progressText');
    const progressBar = document.getElementById('progressBar');
    
    if (total === 0) {
        progressText.textContent = 'No images';
        progressBar.style.width = '0%';
        return;
    }
    
    progressText.textContent = `Image ${current} / ${total}`;
    const percentage = (current / total) * 100;
    progressBar.style.width = percentage + '%';
}

// Update footer status
function updateFooterStatus(message) {
    const footerStatus = document.getElementById('footerStatus');
    footerStatus.textContent = message;
}

// Set rating for current image
window.setRating = async function(rating, keyNumber) {
    if (!images || images.length === 0) {
        return;
    }
    
    const image = images[currentIndex];
    
    try {
        updateFooterStatus(`Setting rating to ${rating.replace('rating:', '')}...`);
        
        const response = await fetch('/api/rate/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_id: image.id,
                rating: rating
            })
        });
        
        const data = await response.json();
        
        // Visual feedback
        showNotification(`Rated as ${rating.replace('rating:', '')}`, 'success');
        
        // Move to next image
        setTimeout(() => {
            nextImage();
        }, 300);
        
        updateFooterStatus('Ready');
        
    } catch (error) {
        console.error('Error setting rating:', error);
        showNotification('Error setting rating: ' + error.message, 'error');
        updateFooterStatus('Error setting rating');
    }
};

// Navigate to previous image
window.previousImage = function() {
    if (images.length === 0) return;
    
    currentIndex = (currentIndex - 1 + images.length) % images.length;
    showCurrentImage();
    updateFooterStatus('Previous image');
};

// Navigate to next image
window.nextImage = function() {
    if (images.length === 0) return;
    
    currentIndex = (currentIndex + 1) % images.length;
    showCurrentImage();
    updateFooterStatus('Next image');
};

// Skip current image
window.skipImage = function() {
    nextImage();
    updateFooterStatus('Skipped');
};

// Change filter
window.changeFilter = function() {
    const filterUnrated = document.getElementById('filterUnrated');
    const filterAI = document.getElementById('filterAI');
    const filterAll = document.getElementById('filterAll');
    
    if (filterUnrated.checked) {
        currentFilter = 'unrated';
    } else if (filterAI.checked) {
        currentFilter = 'ai_predicted';
    } else if (filterAll.checked) {
        currentFilter = 'all';
    }
    
    loadImages();
};

// Shuffle images
window.shuffleImages = function() {
    if (images.length === 0) return;
    
    // Fisher-Yates shuffle
    for (let i = images.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [images[i], images[j]] = [images[j], images[i]];
    }
    
    currentIndex = 0;
    showCurrentImage();
    showNotification('Images shuffled', 'info');
    updateFooterStatus('Shuffled');
};

// Toggle tags visibility
window.toggleTags = function() {
    const tagsContainer = document.getElementById('imageTags');
    const toggleIcon = document.getElementById('tagsToggleIcon');
    
    tagsExpanded = !tagsExpanded;
    
    if (tagsExpanded) {
        tagsContainer.style.display = 'block';
        toggleIcon.style.transform = 'rotate(180deg)';
    } else {
        tagsContainer.style.display = 'none';
        toggleIcon.style.transform = 'rotate(0deg)';
    }
};

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Don't trigger if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }
    
    switch(e.key) {
        case '1':
            e.preventDefault();
            setRating('rating:general', 1);
            break;
        case '2':
            e.preventDefault();
            setRating('rating:sensitive', 2);
            break;
        case '3':
            e.preventDefault();
            setRating('rating:questionable', 3);
            break;
        case '4':
            e.preventDefault();
            setRating('rating:explicit', 4);
            break;
        case 'ArrowLeft':
        case 'p':
        case 'P':
            e.preventDefault();
            previousImage();
            break;
        case 'ArrowRight':
        case 'n':
        case 'N':
            e.preventDefault();
            nextImage();
            break;
        case 's':
        case 'S':
            e.preventDefault();
            skipImage();
            break;
        case 't':
        case 'T':
            e.preventDefault();
            toggleTags();
            break;
    }
});

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadImages();
});

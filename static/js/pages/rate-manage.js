// static/js/pages/rate-manage.js - Rating Management Page
import { showNotification } from '../utils/notifications.js';

let currentStats = null;

function showLoading(message) {
    document.getElementById('loadingMessage').textContent = message;
    document.getElementById('loadingOverlay').classList.add('active');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.remove('active');
}

function showLog(message) {
    document.getElementById('actionLog').style.display = 'block';
    document.getElementById('actionLogContent').textContent += message + '\n';
}

function clearLog() {
    document.getElementById('actionLog').style.display = 'none';
    document.getElementById('actionLogContent').textContent = '';
}

// URL encode a filepath, preserving forward slashes
function urlEncodePath(filepath) {
    if (!filepath) return filepath;
    return filepath.split('/').map(part => encodeURIComponent(part)).join('/');
}

async function loadStats() {
    try {
        const response = await fetch('/api/rate/stats');
        currentStats = await response.json();

        // Update model status
        document.getElementById('trainedStatus').textContent =
            currentStats.model_trained ? '✅ Trained' : '❌ Not Trained';

        const metadata = currentStats.metadata || {};
        document.getElementById('lastTrained').textContent =
            metadata.last_trained ? new Date(metadata.last_trained).toLocaleString() : 'Never';
        document.getElementById('trainingSamples').textContent =
            metadata.training_sample_count || '0';
        document.getElementById('uniqueTags').textContent =
            metadata.unique_tags_used || '0';
        document.getElementById('tagPairs').textContent =
            metadata.unique_pairs_used || '0';
        document.getElementById('unratedCount').textContent =
            currentStats.unrated_images || '0';

        // Update distribution
        updateDistribution(currentStats.rating_distribution);

        // Update config
        updateConfig(currentStats.config);

    } catch (error) {
        console.error('Error loading stats:', error);
        showNotification('Error loading statistics: ' + error.message, 'error');
    }
}

function updateDistribution(distribution) {
    const grid = document.getElementById('distributionGrid');
    const ratings = [
        {key: 'rating:general', label: 'General', color: '#4ade80'},
        {key: 'rating:sensitive', label: 'Sensitive', color: '#60a5fa'},
        {key: 'rating:questionable', label: 'Questionable', color: '#fb923c'},
        {key: 'rating:explicit', label: 'Explicit', color: '#f87171'}
    ];

    const maxCount = Math.max(...ratings.map(r => distribution[r.key]?.total || 0));

    grid.innerHTML = ratings.map(rating => {
        const data = distribution[rating.key] || {total: 0, ai: 0, user: 0, original: 0};
        const percentage = maxCount > 0 ? (data.total / maxCount) * 100 : 0;

        return `
            <div class="distribution-row">
                <div class="rating-label">${rating.label}</div>
                <div class="rating-bar">
                    <div class="rating-bar-fill" style="width: ${percentage}%; background: ${rating.color};"></div>
                    <div class="rating-bar-text">${data.total} images</div>
                </div>
                <div class="rating-count">
                    ${data.user} user<br>
                    ${data.ai} AI<br>
                    ${data.original} original
                </div>
            </div>
        `;
    }).join('');
}

function updateConfig(config) {
    const grid = document.getElementById('configGrid');

    const configItems = [
        {key: 'threshold_general', label: 'General Threshold', min: 0, max: 1, step: 0.05},
        {key: 'threshold_sensitive', label: 'Sensitive Threshold', min: 0, max: 1, step: 0.05},
        {key: 'threshold_questionable', label: 'Questionable Threshold', min: 0, max: 1, step: 0.05},
        {key: 'threshold_explicit', label: 'Explicit Threshold', min: 0, max: 1, step: 0.05},
        {key: 'min_confidence', label: 'Min Confidence', min: 0, max: 1, step: 0.05},
        {key: 'pair_weight_multiplier', label: 'Pair Weight Multiplier', min: 0.5, max: 3, step: 0.1},
        {key: 'min_training_samples', label: 'Min Training Samples', min: 10, max: 200, step: 10},
        {key: 'min_pair_cooccurrence', label: 'Min Pair Co-occurrence', min: 2, max: 20, step: 1},
        {key: 'min_tag_frequency', label: 'Min Tag Frequency', min: 5, max: 50, step: 5},
        {key: 'max_pair_count', label: 'Max Tag Pairs', min: 5000, max: 200000, step: 5000},
    ];

    grid.innerHTML = configItems.map(item => {
        const value = config[item.key] || 0;
        return `
            <div class="config-item">
                <label for="config_${item.key}">${item.label}</label>
                <input type="number" id="config_${item.key}" value="${value}"
                       min="${item.min}" max="${item.max}" step="${item.step}">
            </div>
        `;
    }).join('');
}

async function trainModel() {
    showConfirm('Train the model on all manually-rated images?', async () => {
        clearLog();
        showLoading('Training model...');

        try {
            const response = await fetch('/api/rate/train', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog('✅ Training complete!');
                showLog(JSON.stringify(result.stats, null, 2));
                showNotification('Model trained successfully!', 'success');
                loadStats();
            } else {
                showLog('❌ Training failed: ' + result.error);
                showNotification('Training failed: ' + result.error, 'error');
            }
        } catch (error) {
            hideLoading();
            showLog('❌ Error: ' + error.message);
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

async function inferRatings() {
    showConfirm('Run inference on all unrated images?', async () => {
        clearLog();
        showLoading('Running inference...');

        try {
            const response = await fetch('/api/rate/infer', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog('✅ Inference complete!');
                showLog(JSON.stringify(result.stats, null, 2));
                showNotification(`Inference complete! Rated ${result.stats.rated} images.`, 'success');
                loadStats();
            } else {
                showLog('❌ Inference failed: ' + result.error);
                showNotification('Inference failed: ' + result.error, 'error');
            }
        } catch (error) {
            hideLoading();
            showLog('❌ Error: ' + error.message);
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

async function clearAI() {
    showConfirm('Clear all AI-inferred ratings? This cannot be undone.', async () => {
        clearLog();
        showLoading('Clearing AI ratings...');

        try {
            const response = await fetch('/api/rate/clear_ai', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog(`✅ Cleared ${result.deleted_count} AI ratings`);
                showNotification(`Cleared ${result.deleted_count} AI ratings`, 'success');
                loadStats();
            } else {
                showLog('❌ Failed: ' + result.error);
                showNotification('Failed: ' + result.error, 'error');
            }
        } catch (error) {
            hideLoading();
            showLog('❌ Error: ' + error.message);
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

async function retrainAll() {
    showConfirm('Clear AI ratings, retrain model, and re-infer everything? This will take a while.', async () => {
        clearLog();
        showLoading('Retraining and reapplying...');

        try {
            const response = await fetch('/api/rate/retrain_all', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog('✅ Retrain complete!');
                showLog('Cleared: ' + result.cleared);
                showLog('Training: ' + JSON.stringify(result.training_stats, null, 2));
                showLog('Inference: ' + JSON.stringify(result.inference_stats, null, 2));
                showNotification('Retrain and reapply complete!', 'success');
                loadStats();
            } else {
                showLog('❌ Failed: ' + result.error);
                showNotification('Failed: ' + result.error, 'error');
            }
        } catch (error) {
            hideLoading();
            showLog('❌ Error: ' + error.message);
            showNotification('Error: ' + error.message, 'error');
        }
    });
}

async function saveConfig() {
    const configData = {};

    const inputs = document.querySelectorAll('[id^="config_"]');
    inputs.forEach(input => {
        const key = input.id.replace('config_', '');
        configData[key] = parseFloat(input.value);
    });

    showLoading('Saving configuration...');

    try {
        const response = await fetch('/api/rate/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(configData)
        });

        const result = await response.json();

        hideLoading();

        if (result.success) {
            showNotification('Configuration saved!', 'success');
        } else {
            showNotification('Failed to save configuration: ' + result.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showNotification('Error saving configuration: ' + error.message, 'error');
    }
}

async function loadImages() {
    const filter = document.getElementById('imageFilter').value;
    const limit = document.getElementById('imageLimit').value;
    const container = document.getElementById('imagesContainer');

    showLoading('Loading images...');

    try {
        const response = await fetch(`/api/rate/images?filter=${filter}&limit=${limit}`);
        const data = await response.json();

        hideLoading();

        // Update count
        document.getElementById('imageCount').textContent = `${data.images.length} images loaded`;

        if (!data.images || data.images.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #888;">No images found</div>';
            document.getElementById('imageCount').textContent = '0 images loaded';
            return;
        }

        container.innerHTML = data.images.map(img => {
            const rating = img.rating || 'unrated';
            const ratingClass = rating.replace('rating:', '');
            const ratingColor = {
                'general': '#4ade80',
                'sensitive': '#60a5fa',
                'questionable': '#fb923c',
                'explicit': '#f87171',
                'unrated': '#888'
            }[ratingClass] || '#888';

            const ratingLabel = rating === 'unrated' ? 'Unrated' : rating.replace('rating:', '').toUpperCase();
            const sourceLabel = img.rating_source === 'ai_inference' ? '🤖 AI' :
                               img.rating_source === 'user' ? '👤 User' :
                               img.rating_source === 'original' ? '📦 Original' : '';

            // URL encode paths for special characters
            const encodedFilepath = urlEncodePath(img.filepath);
            const encodedThumb = urlEncodePath(img.thumb);
            const thumbPrefix = img.thumb.startsWith('thumbnails/') || img.thumb.startsWith('images/') ? '' : 'images/';

            return `
                <div class="image-card" style="border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--bg-panel);">
                    <a href="/view/${encodedFilepath}" target="_blank" style="display: block;">
                        <img src="/static/${thumbPrefix}${encodedThumb}"
                             alt="Image ${img.id}"
                             style="width: 100%; height: 200px; object-fit: cover; display: block;"
                             onerror="this.src='/static/images/${encodedFilepath}'">
                    </a>
                    <div style="padding: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                            <span style="font-weight: bold; color: ${ratingColor};">${ratingLabel}</span>
                            <span style="font-size: 0.85em; color: #888;">${sourceLabel}</span>
                        </div>
                        <div style="font-size: 0.85em; color: #888; margin-bottom: 8px;">
                            ID: ${img.id} • ${img.tag_count} tags
                        </div>
                        <div style="display: flex; gap: 5px;">
                            <button onclick="viewImage('${img.filepath}')" class="action-btn action-btn-primary" style="flex: 1; padding: 5px; font-size: 0.85em;">
                                View
                            </button>
                            ${img.rating_source === 'ai_inference' ? `
                            <button onclick="correctRating('${img.filepath}')" class="action-btn action-btn-warning" style="flex: 1; padding: 5px; font-size: 0.85em;">
                                Correct
                            </button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        hideLoading();
        container.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #f87171;">Error loading images: ${error.message}</div>`;
        console.error('Error loading images:', error);
    }
}

function viewImage(filepath) {
    window.open(`/view/${filepath}`, '_blank');
}

function correctRating(filepath) {
    showConfirm(`Open image in a new tab to correct the rating?`, () => {
        window.open(`/view/${filepath}`, '_blank');
    });
}

function scrollToReview() {
    document.getElementById('imagesContainer').parentElement.scrollIntoView({ behavior: 'smooth' });
    // Load images if not already loaded
    if (document.getElementById('imagesContainer').children.length === 0) {
        loadImages();
    }
}

// Expose functions to window for onclick handlers
window.trainModel = trainModel;
window.inferRatings = inferRatings;
window.clearAI = clearAI;
window.retrainAll = retrainAll;
window.saveConfig = saveConfig;
window.loadImages = loadImages;
window.viewImage = viewImage;
window.correctRating = correctRating;
window.scrollToReview = scrollToReview;

// Load stats and images on page load
loadStats();
loadImages();

// Auto-refresh stats every 30 seconds
setInterval(loadStats, 30000);

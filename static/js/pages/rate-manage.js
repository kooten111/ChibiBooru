// static/js/pages/rate-manage.js - Modern Rating Management Page
import { showNotification } from '../utils/notifications.js';

let currentStats = null;
let currentConfig = null;

// Show/hide processing overlay
function showProcessing(message, progress = '') {
    const overlay = document.getElementById('processingOverlay');
    const messageEl = document.getElementById('processingMessage');
    const progressEl = document.getElementById('processingProgress');

    messageEl.textContent = message;
    progressEl.textContent = progress;
    overlay.classList.add('active');
}

function hideProcessing() {
    const overlay = document.getElementById('processingOverlay');
    overlay.classList.remove('active');
}

// Update footer status
function updateFooterStatus(message) {
    const footerStatus = document.getElementById('footerStatus');
    footerStatus.textContent = message;
}

// Load stats from API
async function loadStats() {
    try {
        updateFooterStatus('Loading statistics...');
        const response = await fetch('/api/rate/stats');
        const data = await response.json();
        currentStats = data;

        // Update status badges
        updateStatusBadges(data);

        // Update sidebar stats
        updateSidebarStats(data);

        // Update rating distribution
        updateRatingDistribution(data.rating_distribution || {});

        // Update configuration
        currentConfig = data.config || {};
        updateConfigPanel(currentConfig);

        // Update dashboard
        updateDashboard(data);

        updateFooterStatus('Ready');
    } catch (error) {
        console.error('Error loading stats:', error);
        showNotification('Error loading statistics: ' + error.message, 'error');
        updateFooterStatus('Error loading stats');
    }
}

// Update status badges in header
function updateStatusBadges(stats) {
    const container = document.getElementById('statusBadges');
    const badges = [];

    if (stats.model_trained) {
        badges.push('<span class="badge success">✓ Model Trained</span>');
    } else {
        badges.push('<span class="badge warning">❌ Not Trained</span>');
    }

    const unrated = stats.unrated_images || 0;
    if (unrated > 0) {
        badges.push(`<span class="badge">${unrated} unrated images</span>`);
    }

    const pending = stats.pending_corrections || 0;
    if (pending > 0) {
        badges.push(`<span class="badge warning">${pending} pending corrections</span>`);
    }

    container.innerHTML = badges.join('');
}

// Update sidebar stats
function updateSidebarStats(stats) {
    const metadata = stats.metadata || {};

    document.getElementById('trainingSamples').textContent =
        metadata.training_sample_count || '0';
    document.getElementById('uniqueTags').textContent =
        metadata.unique_tags_used || '0';
    document.getElementById('tagPairs').textContent =
        metadata.unique_pairs_used || '0';
    document.getElementById('unratedCount').textContent =
        stats.unrated_images || '0';
}

// Update rating distribution bars
function updateRatingDistribution(distribution) {
    const container = document.getElementById('ratingDistribution');

    const ratings = [
        { key: 'rating:general', label: 'General', class: 'general' },
        { key: 'rating:sensitive', label: 'Sensitive', class: 'sensitive' },
        { key: 'rating:questionable', label: 'Questionable', class: 'questionable' },
        { key: 'rating:explicit', label: 'Explicit', class: 'explicit' }
    ];

    const maxCount = Math.max(...ratings.map(r => {
        const data = distribution[r.key] || { total: 0 };
        return data.total;
    }), 1);

    const html = ratings.map(rating => {
        const data = distribution[rating.key] || { total: 0, ai: 0, user: 0, original: 0 };
        const percentage = (data.total / maxCount) * 100;

        return `
            <div class="rating-bar ${rating.class}">
                <div class="label">
                    <span>${rating.label}</span>
                    <span>${data.total}</span>
                </div>
                <div class="bar">
                    <div class="fill" style="width: ${percentage}%;"></div>
                </div>
                <div style="font-size: 0.75em; color: var(--text-muted); margin-top: 0.25rem;">
                    ${data.user} user · ${data.ai} AI · ${data.original} original
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// Update configuration panel
function updateConfigPanel(config) {
    console.log('Updating config panel with:', config);

    // Inference thresholds
    const inferenceFields = [
        'threshold_general',
        'threshold_sensitive',
        'threshold_questionable',
        'threshold_explicit'
    ];

    inferenceFields.forEach(field => {
        const value = config[field] || 0.5;
        const input = document.getElementById(field);
        const display = document.getElementById(field + '_value');

        if (input) input.value = value;
        if (display) display.textContent = parseFloat(value).toFixed(2);
    });

    // Training parameters with defaults
    const trainingDefaults = {
        'max_pair_count': 10000,
        'min_tag_frequency': 10,
        'min_pair_cooccurrence': 5
    };

    Object.keys(trainingDefaults).forEach(field => {
        const value = config[field] !== undefined ? config[field] : trainingDefaults[field];
        const input = document.getElementById(field);
        if (input) {
            input.value = parseInt(value);
            console.log(`Set ${field} = ${value}`);
        }
    });
}

// Update dashboard tab
function updateDashboard(stats) {
    const metadata = stats.metadata || {};

    // Model status
    const modelStatusEl = document.getElementById('modelStatus');
    if (stats.model_trained) {
        modelStatusEl.textContent = '✅ Trained';
        modelStatusEl.style.color = 'var(--rating-general)';
    } else {
        modelStatusEl.textContent = '❌ Not Trained';
        modelStatusEl.style.color = 'var(--rating-explicit)';
    }

    // Last trained
    const lastTrainedEl = document.getElementById('lastTrained');
    if (metadata.last_trained) {
        const date = new Date(metadata.last_trained);
        lastTrainedEl.textContent = `Last trained: ${date.toLocaleString()}`;
    } else {
        lastTrainedEl.textContent = 'Never trained';
    }

    // Pending corrections
    document.getElementById('pendingCorrections').textContent =
        stats.pending_corrections || '0';

    // Model health
    const healthEl = document.getElementById('modelHealth');
    const healthDescEl = document.getElementById('modelHealthDesc');
    const pending = stats.pending_corrections || 0;

    if (!stats.model_trained) {
        healthEl.textContent = '⚠️ Needs Training';
        healthEl.style.color = 'var(--warning)';
        healthDescEl.textContent = 'Model not trained yet';
    } else if (pending >= 50) {
        healthEl.textContent = '⚠️ Stale';
        healthEl.style.color = 'var(--warning)';
        healthDescEl.textContent = 'Many corrections pending, consider retraining';
    } else if (stats.unrated_images > 100) {
        healthEl.textContent = '✅ Good';
        healthEl.style.color = 'var(--rating-sensitive)';
        healthDescEl.textContent = `${stats.unrated_images} images ready for inference`;
    } else {
        healthEl.textContent = '✅ Excellent';
        healthEl.style.color = 'var(--rating-general)';
        healthDescEl.textContent = 'Model is up to date';
    }
}

// Switch tabs
window.switchTab = function (tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.tab-pane').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById('tab-' + tabName).classList.add('active');

    // Load data for specific tabs
    if (tabName === 'review') {
        loadReviewImages();
    } else if (tabName === 'insights') {
        loadInsights();
    }
};

// Helper to setup progress bar
function setupProgressBar(overlay, messageEl, progressEl) {
    let progressBar = overlay.querySelector('.progress-bar');
    if (!progressBar) {
        const container = document.createElement('div');
        container.className = 'progress-container';
        container.innerHTML = '<div class="progress-bar" style="width: 0%"></div>';
        // Insert after message
        messageEl.parentNode.insertBefore(container, progressEl);
        progressBar = container.querySelector('.progress-bar');
    }
    return progressBar;
}

// Helper to ensure overlay has a close button
function ensureOverlayCloseButton(overlay) {
    let closeBtn = overlay.querySelector('.close-overlay-btn');
    if (!closeBtn) {
        const panel = overlay.querySelector('.panel');
        closeBtn = document.createElement('button');
        closeBtn.className = 'btn btn-secondary close-overlay-btn';
        closeBtn.textContent = 'Close';
        closeBtn.style.marginTop = '1rem';
        closeBtn.style.display = 'none';
        closeBtn.onclick = hideProcessing;
        panel.appendChild(closeBtn);
    }
    return closeBtn;
}

// Helper to poll job status
async function startJobPolling(jobId, progressBar, progressEl, onComplete) {
    const overlay = document.getElementById('processingOverlay');
    const closeBtn = ensureOverlayCloseButton(overlay);

    // Reset close button
    closeBtn.style.display = 'none';

    const poll = async () => {
        try {
            const response = await fetch(`/api/rate/job/${jobId}`);
            const job = await response.json();

            if (!job.found) {
                console.error('Job not found:', jobId);
                progressEl.textContent = 'Job lost or expired.';
                closeBtn.style.display = 'inline-block';
                return;
            }

            if (job.status === 'running' || job.status === 'pending') {
                const percent = job.progress || 0;
                progressBar.style.width = percent + '%';
                if (job.message) {
                    progressEl.textContent = job.message;
                }

                // Continue polling
                setTimeout(poll, 500);
            } else if (job.status === 'completed') {
                progressBar.style.width = '100%';
                progressEl.textContent = 'Complete!';

                // Allow UI to update
                await new Promise(r => setTimeout(r, 500));

                if (onComplete) {
                    onComplete(job.result);
                }
            } else if (job.status === 'failed') {
                progressBar.style.backgroundColor = 'var(--rating-explicit)';
                progressEl.textContent = 'Failed: ' + (job.error || 'Unknown error');
                console.error('Job failed:', job);

                // Show close button so user isn't stuck
                closeBtn.style.display = 'inline-block';
            }
        } catch (error) {
            console.error('Polling error:', error);
            // Retry anyway
            setTimeout(poll, 1000);
        }
    };

    poll();
}

// Train model
window.trainModel = function () {
    showConfirm('Train the rating inference model? This may take a few minutes.', async () => {

        const overlay = document.getElementById('processingOverlay');
        const messageEl = document.getElementById('processingMessage');
        const progressEl = document.getElementById('processingProgress');
        const progressBar = setupProgressBar(overlay, messageEl, progressEl);

        try {
            messageEl.textContent = 'Starting training...';
            progressEl.textContent = 'Initializing...';
            overlay.classList.add('active');
            updateFooterStatus('Starting training...');

            const response = await fetch('/api/rate/train', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });

            const data = await response.json();

            if (data.job_id) {
                // Async mode - Poll for progress
                messageEl.textContent = 'Training model...';
                startJobPolling(data.job_id, progressBar, progressEl, async (result) => {
                    hideProcessing();
                    progressBar.style.width = '0%';

                    const stats = result || {};
                    const source = 'ml_worker'; // We know it's async so it's ML worker

                    showNotification(
                        `Model trained successfully! ` +
                        `Samples: ${stats.training_samples}, ` +
                        `Tags: ${stats.unique_tags}, ` +
                        `Pairs: ${stats.unique_pairs}`,
                        'success'
                    );

                    await loadStats();
                    updateFooterStatus('Training complete');
                });
            } else {
                // Sync mode (fallback) or direct stats return
                progressBar.style.width = '100%';
                progressEl.textContent = 'Complete!';
                await new Promise(r => setTimeout(r, 500));

                hideProcessing();
                progressBar.style.width = '0%';

                if (data.stats) {
                    const stats = data.stats;
                    const source = data.source || 'unknown';

                    showNotification(
                        `Model trained successfully via ${source}! ` +
                        `Samples: ${stats.training_samples}, ` +
                        `Tags: ${stats.unique_tags}, ` +
                        `Pairs: ${stats.unique_pairs}`,
                        'success'
                    );

                    await loadStats();
                } else {
                    showNotification('Training completed', 'success');
                    await loadStats();
                }
                updateFooterStatus('Training complete');
            }
        } catch (error) {
            hideProcessing();
            console.error('Training error:', error);
            showNotification('Training failed: ' + error.message, 'error');
            updateFooterStatus('Training failed');
            if (progressBar) progressBar.style.width = '0%';
        }
    });
};

// Infer all ratings
window.inferAll = function () {
    showConfirm('Run inference on all unrated images? This may take a while.', async () => {

        const overlay = document.getElementById('processingOverlay');
        const messageEl = document.getElementById('processingMessage');
        const progressEl = document.getElementById('processingProgress');
        const progressBar = setupProgressBar(overlay, messageEl, progressEl);

        try {
            messageEl.textContent = 'Starting inference...';
            progressEl.textContent = 'Initializing...';
            overlay.classList.add('active');
            updateFooterStatus('Starting inference...');

            const response = await fetch('/api/rate/infer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });

            const data = await response.json();

            if (data.job_id) {
                // Async mode - Poll for progress
                messageEl.textContent = 'Running inference...';
                startJobPolling(data.job_id, progressBar, progressEl, async (result) => {
                    hideProcessing();
                    progressBar.style.width = '0%';

                    const stats = result || {};
                    const source = 'ml_worker';

                    showNotification(
                        `Inference complete! ` +
                        `Processed: ${stats.processed}, ` +
                        `Rated: ${stats.rated}, ` +
                        `Skipped: ${stats.skipped_low_confidence}`,
                        'success'
                    );

                    await loadStats();
                    updateFooterStatus('Inference complete');
                });
            } else {
                // Sync mode (fallback)
                progressBar.style.width = '100%';
                progressEl.textContent = 'Complete!';
                await new Promise(r => setTimeout(r, 500));

                hideProcessing();
                progressBar.style.width = '0%';

                if (data.stats) {
                    const stats = data.stats;
                    const source = data.source || 'unknown';

                    showNotification(
                        `Inference complete via ${source}! ` +
                        `Processed: ${stats.processed}, ` +
                        `Rated: ${stats.rated}, ` +
                        `Skipped: ${stats.skipped_low_confidence}`,
                        'success'
                    );

                    await loadStats();
                } else {
                    showNotification('Inference completed', 'success');
                    await loadStats();
                }

                updateFooterStatus('Inference complete');
            }
        } catch (error) {
            hideProcessing();
            console.error('Inference error:', error);
            showNotification('Inference failed: ' + error.message, 'error');
            updateFooterStatus('Inference failed');
            if (progressBar) progressBar.style.width = '0%';
        }
    });
};

// Clear AI ratings
window.clearAI = function () {
    showConfirm('Remove all AI-inferred ratings? This cannot be undone.', async () => {

        try {
            showProcessing('Clearing AI ratings...');
            updateFooterStatus('Clearing AI ratings...');

            const response = await fetch('/api/rate/clear_ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            const data = await response.json();
            hideProcessing();

            showNotification(`Cleared ${data.deleted_count} AI-inferred ratings`, 'success');

            // Reload stats
            await loadStats();
            updateFooterStatus('AI ratings cleared');
        } catch (error) {
            hideProcessing();
            console.error('Clear error:', error);
            showNotification('Failed to clear AI ratings: ' + error.message, 'error');
            updateFooterStatus('Clear failed');
        }
    });
};

// Load review images
window.loadReviewImages = async function () {
    const filter = document.getElementById('reviewFilter').value;
    const container = document.getElementById('reviewImageGrid');

    try {
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-muted);">Loading images...</div>';

        const response = await fetch(`/api/rate/images?filter=${filter}&limit=50`);
        const data = await response.json();

        if (!data.images || data.images.length === 0) {
            container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--text-muted);">No images found</div>';
            return;
        }

        container.innerHTML = data.images.map(img => {
            const ratingClass = img.rating ? img.rating.replace('rating:', '') : '';
            const ratingLabel = img.rating ? img.rating.replace('rating:', '') : 'unrated';
            const source = img.rating_source || '';

            return `
                <div class="image-card" onclick="window.location.href='/view/${img.filepath}'">
                    <img src="/${img.thumb}" alt="Image ${img.id}" loading="lazy">
                    ${img.rating ? `<div class="badge ${ratingClass}" style="position: absolute; top: 0.5rem; right: 0.5rem;">${ratingLabel}</div>` : ''}
                    <div class="info">
                        <div style="font-size: 0.85em; color: var(--text-muted);">
                            Image #${img.id}
                        </div>
                        <div style="font-size: 0.75em; color: var(--text-muted); margin-top: 0.25rem;">
                            ${source === 'ai_inference' ? '🤖 AI' : source === 'user' ? '👤 User' : '📦 Original'}
                            · ${img.tag_count} tags
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading images:', error);
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: var(--rating-explicit);">Error loading images</div>';
    }
};

// Load insights
window.loadInsights = async function () {
    const rating = document.getElementById('insightRating').value;

    try {
        const response = await fetch(`/api/rate/top_tags?rating=${rating}&limit=50`);
        const data = await response.json();

        // Update top tags
        const tagsContainer = document.getElementById('topTags');
        if (data.tags && data.tags.length > 0) {
            tagsContainer.innerHTML = data.tags.map((tag, idx) => `
                <div style="padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 0.5rem; margin-bottom: 0.5rem; border-left: 3px solid var(--primary-blue);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600;">#${idx + 1} ${tag.name}</span>
                        <span style="color: var(--primary-blue); font-weight: bold;">${tag.weight.toFixed(3)}</span>
                    </div>
                    <div style="font-size: 0.75em; color: var(--text-muted); margin-top: 0.25rem;">
                        ${tag.samples} samples
                    </div>
                </div>
            `).join('');
        } else {
            tagsContainer.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">No tag data available</div>';
        }

        // Update top pairs
        const pairsContainer = document.getElementById('topPairs');
        if (data.pairs && data.pairs.length > 0) {
            pairsContainer.innerHTML = data.pairs.map((pair, idx) => `
                <div style="padding: 0.75rem; background: rgba(255,255,255,0.03); border-radius: 0.5rem; margin-bottom: 0.5rem; border-left: 3px solid var(--rating-sensitive);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-weight: 600;">#${idx + 1}</span>
                        <span style="color: var(--primary-blue); font-weight: bold;">${pair.weight.toFixed(3)}</span>
                    </div>
                    <div style="font-size: 0.85em; margin-top: 0.25rem;">
                        ${pair.tag1} + ${pair.tag2}
                    </div>
                    <div style="font-size: 0.75em; color: var(--text-muted); margin-top: 0.25rem;">
                        ${pair.count} co-occurrences
                    </div>
                </div>
            `).join('');
        } else {
            pairsContainer.innerHTML = '<div style="color: var(--text-muted); padding: 1rem;">No pair data available</div>';
        }

    } catch (error) {
        console.error('Error loading insights:', error);
        showNotification('Error loading insights: ' + error.message, 'error');
    }
};

// Update config value display
window.updateConfigValue = function (key, value) {
    const display = document.getElementById(key + '_value');
    if (display) {
        display.textContent = parseFloat(value).toFixed(2);
    }
};

// Save configuration
window.saveConfig = async function () {
    try {
        const config = {};

        // Inference thresholds
        ['threshold_general', 'threshold_sensitive', 'threshold_questionable', 'threshold_explicit'].forEach(key => {
            const input = document.getElementById(key);
            if (input) {
                config[key] = parseFloat(input.value);
            }
        });

        // Training parameters
        // Need to parse these as integers
        ['max_pair_count', 'min_tag_frequency', 'min_pair_cooccurrence'].forEach(key => {
            const input = document.getElementById(key);
            if (input) {
                config[key] = parseInt(input.value);
            }
        });

        showProcessing('Saving configuration...');

        const response = await fetch('/api/rate/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const data = await response.json();
        hideProcessing();

        showNotification('Configuration saved successfully', 'success');

    } catch (error) {
        hideProcessing();
        console.error('Save config error:', error);
        showNotification('Failed to save configuration: ' + error.message, 'error');
    }
};

// Toggle settings panel
window.toggleSettings = function () {
    const layout = document.getElementById('rateLayout');
    layout.classList.toggle('details-hidden');
};



// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
});

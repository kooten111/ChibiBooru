// static/js/pages/character-manage.js - Character Management Page
import { showNotification } from '../utils/notifications.js';

let currentStats = null;
let allCharacters = [];

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
        const response = await fetch('/api/character/stats');
        currentStats = await response.json();

        // Update model status
        document.getElementById('trainedStatus').textContent =
            currentStats.model_trained ? '✅ Trained' : '❌ Not Trained';

        const metadata = currentStats.metadata || {};
        document.getElementById('lastTrained').textContent =
            metadata.last_trained ? new Date(metadata.last_trained).toLocaleString() : 'Never';
        document.getElementById('trainingSamples').textContent =
            metadata.training_sample_count || '0';
        document.getElementById('uniqueCharacters').textContent =
            metadata.unique_characters || '0';
        document.getElementById('uniqueTags').textContent =
            metadata.unique_tags_used || '0';
        document.getElementById('untaggedCount').textContent =
            currentStats.untagged_images || '0';

        // Load all characters
        await loadAllCharacters();

        // Update config
        updateConfig(currentStats.config);

    } catch (error) {
        console.error('Error loading stats:', error);
        showNotification('Error loading statistics: ' + error.message, 'error');
    }
}

async function loadAllCharacters() {
    try {
        const response = await fetch('/api/character/characters');
        const data = await response.json();
        allCharacters = data.characters || [];
        
        updateCharacterGrid(allCharacters);
    } catch (error) {
        console.error('Error loading characters:', error);
        showNotification('Error loading characters: ' + error.message, 'error');
    }
}

function updateCharacterGrid(characters) {
    const grid = document.getElementById('characterGrid');
    
    if (!characters || characters.length === 0) {
        grid.innerHTML = '<p style="color: #888; padding: 20px; text-align: center;">No characters found. Train the model first.</p>';
        return;
    }

    // Sort by total count descending
    characters.sort((a, b) => b.total - a.total);

    const maxCount = Math.max(...characters.map(c => c.total || 0));

    grid.innerHTML = characters.map(character => {
        const total = character.total || 0;
        const ai = character.ai || 0;
        const user = character.user || 0;
        const original = character.original || 0;
        const samples = character.sample_count || 0;
        const percentage = maxCount > 0 ? (total / maxCount) * 100 : 0;

        // Pick a color based on hash of character name
        const hash = character.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
        const colors = ['#4ade80', '#60a5fa', '#fb923c', '#f87171', '#a78bfa', '#fbbf24'];
        const color = colors[hash % colors.length];

        return `
            <div class="distribution-row" data-character="${character.name}">
                <div class="rating-label" style="overflow: hidden; text-overflow: ellipsis;" title="${character.name}">
                    ${character.name.replace(/_/g, ' ')}
                </div>
                <div class="rating-bar">
                    <div class="rating-bar-fill" style="width: ${percentage}%; background: ${color};"></div>
                    <div class="rating-bar-text">${total} images (${samples} train)</div>
                </div>
                <div class="rating-count" style="font-size: 0.85em;">
                    ${user} user<br>
                    ${ai} AI<br>
                    ${original} booru
                </div>
            </div>
        `;
    }).join('');
}

function updateConfig(config) {
    const grid = document.getElementById('configGrid');

    const configItems = [
        { key: 'min_character_samples', label: 'Min Character Samples', min: 5, max: 100, step: 5 },
        { key: 'min_confidence', label: 'Min Confidence', min: 0, max: 1, step: 0.05 },
        { key: 'max_predictions', label: 'Max Predictions per Image', min: 1, max: 10, step: 1 },
        { key: 'pair_weight_multiplier', label: 'Pair Weight Multiplier', min: 0.5, max: 3, step: 0.1 },
        { key: 'min_pair_cooccurrence', label: 'Min Pair Co-occurrence', min: 2, max: 20, step: 1 },
        { key: 'min_tag_frequency', label: 'Min Tag Frequency', min: 5, max: 50, step: 5 },
        { key: 'max_pair_count', label: 'Max Tag Pairs', min: 5000, max: 200000, step: 5000 },
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
    showConfirm('Train the model on all booru-tagged images?', async () => {
        clearLog();
        showLoading('Training model...');

        try {
            const response = await fetch('/api/character/train', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
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

async function inferCharacters() {
    showConfirm('Run character inference on all untagged images?', async () => {
        clearLog();
        showLoading('Running inference...');

        try {
            const response = await fetch('/api/character/infer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog('✅ Inference complete!');
                showLog(JSON.stringify(result.stats, null, 2));
                showNotification('Inference completed successfully!', 'success');
                loadStats();
                loadImages();
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
    showConfirm('Clear all AI-inferred character tags?', async () => {
        clearLog();
        showLoading('Clearing AI characters...');

        try {
            const response = await fetch('/api/character/clear_ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog(`✅ Cleared ${result.deleted_count} AI-inferred character tags`);
                showNotification(`Cleared ${result.deleted_count} tags`, 'success');
                loadStats();
                loadImages();
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
    showConfirm('Clear all AI characters, retrain model, and re-infer all images? This will take a while.', async () => {
        clearLog();
        showLoading('Retraining and reapplying...');

        try {
            const response = await fetch('/api/character/retrain_all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const result = await response.json();

            hideLoading();

            if (result.success) {
                showLog('✅ Retrain and reapply complete!');
                showLog(JSON.stringify(result, null, 2));
                showNotification('Retrain and reapply completed!', 'success');
                loadStats();
                loadImages();
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
    const config = {};
    document.querySelectorAll('#configGrid input').forEach(input => {
        const key = input.id.replace('config_', '');
        config[key] = parseFloat(input.value);
    });

    try {
        const response = await fetch('/api/character/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const result = await response.json();

        if (result.success) {
            showNotification('Configuration saved!', 'success');
        } else {
            showNotification('Failed to save config: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('Error: ' + error.message, 'error');
    }
}

async function loadImages() {
    const filter = document.getElementById('imageFilter').value;
    const limit = document.getElementById('imageLimit').value;

    try {
        const response = await fetch(`/api/character/images?filter=${filter}&limit=${limit}`);
        const data = await response.json();

        const container = document.getElementById('imagesContainer');
        const images = data.images || [];

        document.getElementById('imageCount').textContent = `${images.length} images loaded`;

        if (images.length === 0) {
            container.innerHTML = '<p style="color: #888; padding: 20px; text-align: center; grid-column: 1/-1;">No images found</p>';
            return;
        }

        container.innerHTML = images.map(image => {
            const characterTags = image.characters || [];
            const aiCharacters = image.ai_characters || [];
            
            let characterBadges = '';
            if (characterTags.length > 0) {
                characterBadges = characterTags.map(ct => {
                    const isAI = ct.source === 'ai_inference';
                    const badge = isAI ? '🤖' : '👤';
                    return `<span style="background: ${isAI ? '#fb923c' : '#4ade80'}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.75em; margin: 2px; display: inline-block;" title="${ct.source}">
                        ${badge} ${ct.name.replace(/_/g, ' ')}
                    </span>`;
                }).join('');
            }

            return `
                <div class="image-card" style="border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; background: var(--bg-panel);">
                    <img src="/${urlEncodePath(image.thumb)}" alt="Image ${image.id}" 
                         style="width: 100%; height: 200px; object-fit: cover; cursor: pointer;"
                         onclick="showPredictions(${image.id})"
                         onerror="this.src='/static/placeholder.png'">
                    <div style="padding: 10px;">
                        <div style="margin-bottom: 8px; min-height: 40px;">
                            ${characterBadges || '<span style="color: #888; font-size: 0.85em;">No characters</span>'}
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.85em; color: #888;">
                            <span>${image.tag_count} tags</span>
                            <button onclick="showPredictions(${image.id})" class="action-btn action-btn-primary" style="padding: 4px 8px; font-size: 0.8em;">
                                🔮 Predict
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading images:', error);
        showNotification('Error loading images: ' + error.message, 'error');
    }
}

async function showPredictions(imageId) {
    try {
        const response = await fetch(`/api/character/predict/${imageId}`);
        const data = await response.json();

        const modal = document.getElementById('predictionModal');
        const modalBody = document.getElementById('predictionModalBody');

        const predictions = data.predictions || [];
        const tags = data.tags || [];

        let content = `
            <div style="margin-bottom: 20px;">
                <h3>Image #${imageId}</h3>
                <p style="color: #888; font-size: 0.9em;">Based on ${tags.length} tags</p>
            </div>
        `;

        if (predictions.length === 0) {
            content += '<p style="color: #888;">No character predictions (confidence too low or model not trained)</p>';
        } else {
            content += '<div style="display: flex; flex-direction: column; gap: 20px;">';
            
            predictions.forEach(pred => {
                const confidencePercent = (pred.confidence * 100).toFixed(1);
                const confidenceColor = pred.confidence > 0.7 ? '#4ade80' : pred.confidence > 0.5 ? '#fbbf24' : '#fb923c';
                
                content += `
                    <div style="border: 1px solid var(--border-color); border-radius: 8px; padding: 15px; background: var(--bg-secondary);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h4 style="margin: 0;">${pred.character.replace(/_/g, ' ')}</h4>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="color: ${confidenceColor}; font-weight: bold;">${confidencePercent}%</span>
                                <button onclick="applyCharacter(${imageId}, '${pred.character}')" class="action-btn action-btn-success" style="padding: 4px 12px;">
                                    ✓ Apply
                                </button>
                            </div>
                        </div>
                        <div style="margin-top: 10px;">
                            <strong style="font-size: 0.9em;">Contributing tags:</strong>
                            <div style="margin-top: 5px; display: flex; flex-wrap: wrap; gap: 5px;">
                                ${pred.contributing_tags.map(ct => {
                                    const weightColor = ct.weight > 0 ? '#4ade80' : '#f87171';
                                    return `<span style="background: var(--bg-panel); padding: 3px 8px; border-radius: 4px; font-size: 0.85em; border-left: 3px solid ${weightColor};">
                                        ${ct.tag} <span style="color: ${weightColor};">(${ct.weight > 0 ? '+' : ''}${ct.weight})</span>
                                    </span>`;
                                }).join('')}
                            </div>
                        </div>
                    </div>
                `;
            });
            
            content += '</div>';
        }

        // Show all tags at the bottom
        content += `
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-color);">
                <strong style="font-size: 0.9em;">All tags:</strong>
                <div style="margin-top: 10px; display: flex; flex-wrap: wrap; gap: 5px;">
                    ${tags.map(tag => `<span style="background: var(--bg-panel); padding: 3px 8px; border-radius: 4px; font-size: 0.85em;">${tag}</span>`).join('')}
                </div>
            </div>
        `;

        modalBody.innerHTML = content;
        modal.style.display = 'flex';

    } catch (error) {
        console.error('Error loading predictions:', error);
        showNotification('Error loading predictions: ' + error.message, 'error');
    }
}

async function applyCharacter(imageId, character) {
    try {
        const response = await fetch(`/api/character/apply/${imageId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ characters: [character] })
        });
        const result = await response.json();

        if (result.success) {
            showNotification(`Applied character: ${character.replace(/_/g, ' ')}`, 'success');
            closePredictionModal();
            loadImages();
            loadStats();
        } else {
            showNotification('Failed to apply character: ' + result.error, 'error');
        }
    } catch (error) {
        showNotification('Error: ' + error.message, 'error');
    }
}

function closePredictionModal() {
    document.getElementById('predictionModal').style.display = 'none';
}

function scrollToExplorer() {
    document.querySelector('#imagesContainer').scrollIntoView({ behavior: 'smooth' });
}

function showConfirm(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Character search
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('characterSearch');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const filtered = allCharacters.filter(c => 
                c.name.toLowerCase().includes(searchTerm)
            );
            updateCharacterGrid(filtered);
        });
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadImages();
});

// Make functions global
window.trainModel = trainModel;
window.inferCharacters = inferCharacters;
window.clearAI = clearAI;
window.retrainAll = retrainAll;
window.saveConfig = saveConfig;
window.loadImages = loadImages;
window.showPredictions = showPredictions;
window.applyCharacter = applyCharacter;
window.closePredictionModal = closePredictionModal;
window.scrollToExplorer = scrollToExplorer;

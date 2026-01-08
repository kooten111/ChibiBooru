// static/js/pages/character-manage.js - Character Management Page (Three-Panel Layout)
import { showNotification } from '../utils/notifications.js';

let currentStats = null;
let allCharacters = [];
let selectedCharacter = null;
let currentSortBy = 'total';
let currentSortDirection = 'desc';
let currentSourceFilter = 'all';

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

        // Update model badge
        const modelBadge = document.getElementById('modelBadge');
        if (currentStats.model_trained) {
            modelBadge.textContent = '✅ Trained';
            modelBadge.className = 'character-model-badge trained';
        } else {
            modelBadge.textContent = '❌ Not Trained';
            modelBadge.className = 'character-model-badge untrained';
        }

        const metadata = currentStats.metadata || {};
        
        // Update header stats
        document.getElementById('untaggedCount').textContent = currentStats.untagged_images || '0';
        document.getElementById('untaggedMiniCount').textContent = currentStats.untagged_images || '0';
        
        // Update insights panel
        const lastTrained = metadata.last_trained ? new Date(metadata.last_trained).toLocaleString() : 'Never';
        document.getElementById('lastTrained').textContent = lastTrained;
        document.getElementById('trainingSamples').textContent = metadata.training_sample_count || '0';
        document.getElementById('uniqueCharacters').textContent = metadata.unique_characters || '0';
        document.getElementById('uniqueTags').textContent = metadata.unique_tags_used || '0';
        
        // Update footer
        document.getElementById('footerLastTrained').textContent = lastTrained;
        document.getElementById('footerTagsCount').textContent = metadata.unique_tags_used || '0';

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
        
        updateCharacterCount();
        renderCharacterList();
        renderDistributionChart();
    } catch (error) {
        console.error('Error loading characters:', error);
        showNotification('Error loading characters: ' + error.message, 'error');
    }
}

function updateCharacterCount() {
    document.getElementById('characterCount').textContent = allCharacters.length;
}

function getFilteredAndSortedCharacters() {
    let filtered = [...allCharacters];
    
    // Apply source filter
    if (currentSourceFilter !== 'all') {
        filtered = filtered.filter(char => {
            if (currentSourceFilter === 'user') return (char.user || 0) > 0;
            if (currentSourceFilter === 'ai') return (char.ai || 0) > 0;
            if (currentSourceFilter === 'booru') return (char.original || 0) > 0;
            return true;
        });
    }
    
    // Apply search filter
    const searchInput = document.getElementById('characterSearch');
    if (searchInput && searchInput.value) {
        const searchTerm = searchInput.value.toLowerCase();
        filtered = filtered.filter(c => c.name.toLowerCase().includes(searchTerm));
    }
    
    // Sort characters
    filtered.sort((a, b) => {
        let aVal, bVal;
        if (currentSortBy === 'name') {
            aVal = a.name;
            bVal = b.name;
            const result = aVal.localeCompare(bVal);
            return currentSortDirection === 'asc' ? result : -result;
        } else {
            aVal = a[currentSortBy] || 0;
            bVal = b[currentSortBy] || 0;
            return currentSortDirection === 'desc' ? bVal - aVal : aVal - bVal;
        }
    });
    
    return filtered;
}

function renderCharacterList() {
    const listContainer = document.getElementById('characterList');
    const filtered = getFilteredAndSortedCharacters();
    
    // Update mini stats
    document.getElementById('shownCount').textContent = filtered.length;
    const totalSamples = filtered.reduce((sum, char) => sum + (char.sample_count || 0), 0);
    document.getElementById('totalSamples').textContent = totalSamples;
    
    if (filtered.length === 0) {
        listContainer.innerHTML = `
            <div class="character-empty-state">
                <div class="character-empty-state-icon">🔍</div>
                <div class="character-empty-state-text">No characters found</div>
                <div class="character-empty-state-subtext">Try adjusting your filters</div>
            </div>
        `;
        return;
    }
    
    const maxCount = Math.max(...filtered.map(c => c.total || 0), 1);
    
    listContainer.innerHTML = filtered.map(character => {
        const total = character.total || 0;
        const ai = character.ai || 0;
        const user = character.user || 0;
        const original = character.original || 0;
        const samples = character.sample_count || 0;
        const percentage = (total / maxCount) * 100;
        
        const isSelected = selectedCharacter && selectedCharacter.name === character.name;
        
        return `
            <div class="character-list-item ${isSelected ? 'selected' : ''}" data-character="${character.name}" onclick="selectCharacter('${character.name}')">
                <div class="character-list-item-name">${character.name.replace(/_/g, ' ')}</div>
                <div class="character-list-item-counts">
                    <div class="character-list-item-count">
                        <span>🎯</span>
                        <span>${total}</span>
                    </div>
                    <div class="character-list-item-count">
                        <span>📚</span>
                        <span>${samples}</span>
                    </div>
                </div>
                <div class="character-list-item-counts">
                    <div class="character-list-item-count" title="User">
                        <span>👥</span>
                        <span>${user}</span>
                    </div>
                    <div class="character-list-item-count" title="AI">
                        <span>🤖</span>
                        <span>${ai}</span>
                    </div>
                    <div class="character-list-item-count" title="Booru">
                        <span>📚</span>
                        <span>${original}</span>
                    </div>
                </div>
                <div class="character-list-item-progress">
                    <div class="character-list-item-progress-bar" style="width: ${percentage}%"></div>
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
            <div class="character-config-item">
                <label for="config_${item.key}">${item.label}</label>
                <input type="number" id="config_${item.key}" value="${value}"
                       min="${item.min}" max="${item.max}" step="${item.step}">
            </div>
        `;
    }).join('');
}

// Character Selection
function selectCharacter(characterName) {
    selectedCharacter = allCharacters.find(c => c.name === characterName);
    if (!selectedCharacter) return;
    
    // Update selected state in list
    document.querySelectorAll('.character-list-item').forEach(item => {
        if (item.dataset.character === characterName) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
    
    // Update details panel
    updateCharacterDetails();
    
    // Load character images
    loadCharacterImages(characterName);
    
    // Load character weights
    loadCharacterWeights(characterName);
}

function updateCharacterDetails() {
    const infoContainer = document.getElementById('characterInfo');
    
    if (!selectedCharacter) {
        infoContainer.innerHTML = `
            <div class="character-empty-state">
                <div class="character-empty-state-icon">ℹ️</div>
                <div class="character-empty-state-text">No selection</div>
            </div>
        `;
        return;
    }
    
    const total = selectedCharacter.total || 0;
    const ai = selectedCharacter.ai || 0;
    const user = selectedCharacter.user || 0;
    const original = selectedCharacter.original || 0;
    const samples = selectedCharacter.sample_count || 0;
    
    infoContainer.innerHTML = `
        <div class="character-detail-item">
            <span class="character-detail-label">Name</span>
            <span class="character-detail-value">${selectedCharacter.name.replace(/_/g, ' ')}</span>
        </div>
        <div class="character-detail-item">
            <span class="character-detail-label">Total Images</span>
            <span class="character-detail-value">${total}</span>
        </div>
        <div class="character-detail-item">
            <span class="character-detail-label">Training Samples</span>
            <span class="character-detail-value">${samples}</span>
        </div>
        
        <h3 style="margin-top: var(--spacing-lg); margin-bottom: var(--spacing-sm); font-size: var(--font-size-sm);">Source Breakdown</h3>
        <div class="character-source-breakdown">
            <div class="character-source-breakdown-item">
                <span>👥 User Tagged</span>
                <span>${user}</span>
            </div>
            <div class="character-source-breakdown-item">
                <span>🤖 AI Inferred</span>
                <span>${ai}</span>
            </div>
            <div class="character-source-breakdown-item">
                <span>📚 Booru Original</span>
                <span>${original}</span>
            </div>
        </div>
    `;
}

async function loadCharacterImages(characterName) {
    const grid = document.getElementById('characterImagesGrid');
    
    try {
        grid.innerHTML = '<div class="character-loading">Loading images...</div>';
        
        // Fetch images with characters, limit to reduce initial load
        const response = await fetch(`/api/character/images?filter=all&limit=200`);
        const data = await response.json();
        const allImages = data.images || [];
        
        // Filter images that have this character
        const images = allImages.filter(image => {
            const chars = image.characters || [];
            return chars.some(ct => ct.name === characterName);
        });
        
        if (images.length === 0) {
            grid.innerHTML = `
                <div class="character-empty-state">
                    <div class="character-empty-state-icon">📸</div>
                    <div class="character-empty-state-text">No images found</div>
                    <div class="character-empty-state-subtext">This character has no associated images in the first 200 results</div>
                </div>
            `;
            return;
        }
        
        // Limit to first 50 images for performance
        grid.innerHTML = images.slice(0, 50).map(image => {
            const characterTag = (image.characters || []).find(ct => ct.name === characterName);
            const source = characterTag ? characterTag.source : 'unknown';
            
            let sourceBadge = '';
            if (source === 'user') sourceBadge = '<span class="character-source-badge user">👥 User</span>';
            else if (source === 'ai_inference') sourceBadge = '<span class="character-source-badge ai">🤖 AI</span>';
            else if (source.includes('booru') || source === 'original') sourceBadge = '<span class="character-source-badge booru">📚 Booru</span>';
            
            return `
                <div class="character-image-card" onclick="window.location.href='/image/${image.id}'">
                    <img src="/${urlEncodePath(image.thumb)}" alt="Image ${image.id}"
                         onerror="this.src='/static/placeholder.png'">
                    <div class="character-image-card-footer">
                        ${sourceBadge}
                        <span>#${image.id}</span>
                    </div>
                </div>
            `;
        }).join('');
        
        // Show count if there are more images
        if (images.length > 50) {
            grid.innerHTML += `
                <div style="grid-column: 1/-1; text-align: center; padding: var(--spacing-md); color: var(--text-muted); font-size: var(--font-size-sm);">
                    Showing first 50 of ${images.length} images
                </div>
            `;
        }
        
    } catch (error) {
        console.error('Error loading character images:', error);
        grid.innerHTML = `
            <div class="character-empty-state">
                <div class="character-empty-state-icon">⚠️</div>
                <div class="character-empty-state-text">Error loading images</div>
            </div>
        `;
    }
}

async function loadCharacterWeights(characterName) {
    const weightsContainer = document.getElementById('tagWeights');
    
    try {
        weightsContainer.innerHTML = '<div class="character-loading">Loading weights...</div>';
        
        const response = await fetch(`/api/character/top_tags?character=${encodeURIComponent(characterName)}&limit=30`);
        const data = await response.json();
        const tags = data.tags || [];
        
        if (tags.length === 0) {
            weightsContainer.innerHTML = `
                <div class="character-empty-state">
                    <div class="character-empty-state-icon">⚖️</div>
                    <div class="character-empty-state-text">No weights found</div>
                    <div class="character-empty-state-subtext">Train the model first</div>
                </div>
            `;
            return;
        }
        
        const maxAbsWeight = Math.max(...tags.map(t => Math.abs(t.weight)));
        
        weightsContainer.innerHTML = `
            <div class="character-weight-list">
                ${tags.map(tag => {
                    const isPositive = tag.weight > 0;
                    const percentage = (Math.abs(tag.weight) / maxAbsWeight) * 100;
                    
                    return `
                        <div class="character-weight-item">
                            <div class="character-weight-header">
                                <span class="character-weight-tag">${tag.tag}</span>
                                <span class="character-weight-value ${isPositive ? 'positive' : 'negative'}">
                                    ${isPositive ? '+' : ''}${tag.weight.toFixed(3)}
                                </span>
                            </div>
                            <div class="character-weight-bar-container">
                                <div class="character-weight-bar ${isPositive ? 'positive' : 'negative'}" 
                                     style="width: ${percentage}%"></div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        
    } catch (error) {
        console.error('Error loading character weights:', error);
        weightsContainer.innerHTML = `
            <div class="character-empty-state">
                <div class="character-empty-state-icon">⚠️</div>
                <div class="character-empty-state-text">Error loading weights</div>
            </div>
        `;
    }
}

function renderDistributionChart() {
    const chartContainer = document.getElementById('distributionChart');
    
    if (allCharacters.length === 0) {
        chartContainer.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 20px;">No data available</p>';
        return;
    }
    
    // Sort and take top 15
    const topCharacters = [...allCharacters]
        .sort((a, b) => (b.total || 0) - (a.total || 0))
        .slice(0, 15);
    
    const maxCount = Math.max(...topCharacters.map(c => c.total || 0), 1);
    
    chartContainer.innerHTML = `
        <div class="distribution-grid" style="max-height: none;">
            ${topCharacters.map(character => {
                const total = character.total || 0;
                const samples = character.sample_count || 0;
                const percentage = (total / maxCount) * 100;
                
                // Pick a color based on hash of character name
                const hash = character.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
                const colors = ['#4ade80', '#60a5fa', '#fb923c', '#f87171', '#a78bfa', '#fbbf24'];
                const color = colors[hash % colors.length];
                
                return `
                    <div class="distribution-row" style="cursor: pointer;" onclick="selectCharacter('${character.name}')">
                        <div class="rating-label" style="overflow: hidden; text-overflow: ellipsis;" title="${character.name}">
                            ${character.name.replace(/_/g, ' ')}
                        </div>
                        <div class="rating-bar">
                            <div class="rating-bar-fill" style="width: ${percentage}%; background: ${color};"></div>
                            <div class="rating-bar-text">${total} images (${samples} train)</div>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;
}

async function trainModel() {
    if (!confirm('Train the model on all booru-tagged images?')) return;
    
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
}

async function inferCharacters() {
    if (!confirm('Run character inference on all untagged images?')) return;
    
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
        } else {
            showLog('❌ Inference failed: ' + result.error);
            showNotification('Inference failed: ' + result.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showLog('❌ Error: ' + error.message);
        showNotification('Error: ' + error.message, 'error');
    }
}

async function clearAI() {
    if (!confirm('Clear all AI-inferred character tags?')) return;
    
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
        } else {
            showLog('❌ Failed: ' + result.error);
            showNotification('Failed: ' + result.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showLog('❌ Error: ' + error.message);
        showNotification('Error: ' + error.message, 'error');
    }
}

async function retrainAll() {
    if (!confirm('Clear all AI characters, retrain model, and re-infer all images? This will take a while.')) return;
    
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
        } else {
            showLog('❌ Failed: ' + result.error);
            showNotification('Failed: ' + result.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showLog('❌ Error: ' + error.message);
        showNotification('Error: ' + error.message, 'error');
    }
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

// Prediction Preview
async function predictImageById() {
    const imageId = document.getElementById('predictionImageId').value;
    if (!imageId) {
        showNotification('Please enter an image ID', 'error');
        return;
    }
    
    const resultsContainer = document.getElementById('predictionResults');
    
    try {
        resultsContainer.innerHTML = '<div class="character-loading">Loading predictions...</div>';
        
        const response = await fetch(`/api/character/predict/${imageId}`);
        const data = await response.json();
        
        const predictions = data.predictions || [];
        const tags = data.tags || [];
        
        if (predictions.length === 0) {
            resultsContainer.innerHTML = `
                <div class="character-empty-state">
                    <div class="character-empty-state-icon">🔮</div>
                    <div class="character-empty-state-text">No predictions</div>
                    <div class="character-empty-state-subtext">Confidence too low or model not trained</div>
                </div>
            `;
            return;
        }
        
        resultsContainer.innerHTML = predictions.map(pred => {
            const confidencePercent = (pred.confidence * 100).toFixed(1);
            let confidenceClass = 'low';
            if (pred.confidence > 0.7) confidenceClass = 'high';
            else if (pred.confidence > 0.5) confidenceClass = 'medium';
            
            return `
                <div class="character-prediction-item">
                    <div class="character-prediction-item-header">
                        <div class="character-prediction-item-name">${pred.character.replace(/_/g, ' ')}</div>
                        <div class="character-prediction-item-confidence ${confidenceClass}">${confidencePercent}%</div>
                    </div>
                    <div class="character-prediction-tags">
                        ${pred.contributing_tags.map(ct => {
                            const isPositive = ct.weight > 0;
                            return `
                                <span class="character-prediction-tag ${isPositive ? 'positive' : 'negative'}">
                                    ${ct.tag} <span style="opacity: 0.7;">(${ct.weight > 0 ? '+' : ''}${ct.weight})</span>
                                </span>
                            `;
                        }).join('')}
                    </div>
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error predicting:', error);
        resultsContainer.innerHTML = `
            <div class="character-empty-state">
                <div class="character-empty-state-icon">⚠️</div>
                <div class="character-empty-state-text">Error loading predictions</div>
            </div>
        `;
        showNotification('Error: ' + error.message, 'error');
    }
}

// Tab Switching
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.character-tab-btn').forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab panes
    document.querySelectorAll('.character-tab-pane').forEach(pane => {
        if (pane.id === tabName + 'Pane') {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });
}

function switchRightTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.character-right-tab-btn').forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Update tab panes
    document.querySelectorAll('.character-right-pane').forEach(pane => {
        if (pane.id === tabName + 'Pane') {
            pane.classList.add('active');
        } else {
            pane.classList.remove('active');
        }
    });
}

// Event Listeners and Initialization
document.addEventListener('DOMContentLoaded', () => {
    // Initialize page
    loadStats();
    
    // Tab switching
    document.querySelectorAll('.character-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    
    document.querySelectorAll('.character-right-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchRightTab(btn.dataset.tab));
    });
    
    // Character search
    const searchInput = document.getElementById('characterSearch');
    if (searchInput) {
        searchInput.addEventListener('input', renderCharacterList);
    }
    
    // Source filter
    const sourceFilter = document.getElementById('sourceFilter');
    if (sourceFilter) {
        sourceFilter.addEventListener('change', (e) => {
            currentSourceFilter = e.target.value;
            renderCharacterList();
        });
    }
    
    // Sort by
    const sortBy = document.getElementById('sortBy');
    if (sortBy) {
        sortBy.addEventListener('change', (e) => {
            currentSortBy = e.target.value;
            renderCharacterList();
        });
    }
    
    // Sort direction toggle
    const sortDirection = document.getElementById('sortDirection');
    if (sortDirection) {
        sortDirection.addEventListener('click', () => {
            currentSortDirection = currentSortDirection === 'desc' ? 'asc' : 'desc';
            sortDirection.textContent = currentSortDirection === 'desc' ? '↓' : '↑';
            renderCharacterList();
        });
    }
});

// Make functions global
window.trainModel = trainModel;
window.inferCharacters = inferCharacters;
window.clearAI = clearAI;
window.retrainAll = retrainAll;
window.saveConfig = saveConfig;
window.selectCharacter = selectCharacter;
window.predictImageById = predictImageById;
window.switchTab = switchTab;
window.switchRightTab = switchRightTab;

// static/js/saucenao-fetch.js
import { showNotification } from './utils/notifications.js';

var SYSTEM_SECRET = localStorage.getItem('system_secret');
var saucenaoResults = [];
var selectedResult = null;

function formatFileSize(bytes) {
    if (bytes >= 1048576) {
        return (bytes / 1048576).toFixed(2) + ' MB';
    } else if (bytes >= 1024) {
        return (bytes / 1024).toFixed(2) + ' KB';
    }
    return bytes + ' bytes';
}

// Expose functions to global scope for onclick handlers
window.showSauceNaoFetcher = showSauceNaoFetcher;
window.closeSauceNaoModal = closeSauceNaoModal;
window.selectSauceNaoResult = selectSauceNaoResult;
window.selectMetadataSource = selectMetadataSource;
window.applySauceNaoMetadata = applySauceNaoMetadata;
window.displaySauceNaoResults = displaySauceNaoResults;

function showSauceNaoFetcher() {
    if (!SYSTEM_SECRET) {
        const secret = prompt('Enter system secret to use SauceNao fetch:');
        if (!secret) return;
        SYSTEM_SECRET = secret;
        localStorage.setItem('system_secret', secret);
    }
    
    const modal = document.createElement('div');
    modal.id = 'saucenaoModal';

    modal.innerHTML = `
        <div class="saucenao-modal-content">
            <div class="saucenao-modal-header">
                <h2>🔍 SauceNao Fetch</h2>
                <button onclick="closeSauceNaoModal()" class="saucenao-close-btn">&times; Close</button>
            </div>

            <div id="saucenaoContent">
                <div class="saucenao-loading">
                    <div class="saucenao-loading-icon">🔍</div>
                    <div class="saucenao-loading-text">Searching SauceNao...</div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Start search
    searchSauceNao();
}

function closeSauceNaoModal() {
    const modal = document.getElementById('saucenaoModal');
    if (modal) modal.remove();
}

async function searchSauceNao() {
    const filepath = document.getElementById('imageFilepath').value;
    
    try {
        const response = await fetch('/api/saucenao/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filepath: filepath,
                secret: SYSTEM_SECRET
            })
        });
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response:', text);
            throw new Error('Server returned non-JSON response. Check console for details.');
        }
        
        const data = await response.json();
        
        if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            showNotification('Invalid system secret', 'error');
            closeSauceNaoModal();
            return;
        }
        
        if (!data.found || !data.results || data.results.length === 0) {
            document.getElementById('saucenaoContent').innerHTML = `
                <div class="saucenao-no-results">
                    <div class="saucenao-no-results-icon">😔</div>
                    <div class="saucenao-no-results-text">No results found on SauceNao</div>
                    <div class="saucenao-no-results-hint">
                        Try searching manually on booru sites
                    </div>
                </div>
            `;
            return;
        }
        
        saucenaoResults = data.results;
        displaySauceNaoResults(data.results);
        
    } catch (error) {
        document.getElementById('saucenaoContent').innerHTML = `
            <div class="saucenao-error">
                <div class="saucenao-error-icon">⚠️</div>
                <div class="saucenao-error-text">Error: ${error.message}</div>
            </div>
        `;
    }
}

function displaySauceNaoResults(results) {
    const html = `
        <div class="saucenao-success-banner">
            <div class="saucenao-success-title">
                ✓ Found ${results.length} potential match${results.length !== 1 ? 'es' : ''}
            </div>
            <div class="saucenao-success-subtitle">
                Click on a result to view details and apply metadata
            </div>
        </div>

        <div class="saucenao-results-grid">
            ${results.map((result, idx) => `
                <div class="saucenao-result" onclick="selectSauceNaoResult(${idx})">
                    <div class="saucenao-result-content">
                        ${result.thumbnail ? `
                            <img src="${result.thumbnail}" class="saucenao-result-thumbnail">
                        ` : ''}
                        <div class="saucenao-result-info">
                            <div class="saucenao-result-similarity">
                                ${(result.similarity).toFixed(1)}% Match
                            </div>
                            <div class="saucenao-result-sources">
                                ${result.sources.map(source => `
                                    <span class="saucenao-source-badge">
                                        ${source.type}
                                    </span>
                                `).join('')}
                            </div>
                        </div>
                        <div class="saucenao-result-arrow">→</div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    document.getElementById('saucenaoContent').innerHTML = html;
}

async function selectSauceNaoResult(idx) {
    const result = saucenaoResults[idx];
    selectedResult = result;
    
    // Show loading
    document.getElementById('saucenaoContent').innerHTML = `
        <div class="saucenao-loading">
            <div class="saucenao-loading-icon">⚙️</div>
            <div class="saucenao-loading-text">Loading metadata...</div>
        </div>
    `;
    
    try {
        // Fetch metadata from all sources in parallel
        const metadataPromises = result.sources.map(source => 
            fetch('/api/saucenao/fetch_metadata', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    source: source.type,
                    post_id: source.post_id,
                    secret: SYSTEM_SECRET
                })
            }).then(async r => {
                const contentType = r.headers.get('content-type');
                if (!contentType || !contentType.includes('application/json')) {
                    const text = await r.text();
                    console.error('Non-JSON response from fetch_metadata:', text);
                    throw new Error('Server returned non-JSON response');
                }
                const data = await r.json();
                console.log(`Metadata result from ${source.type}:`, data);
                return {...data, source: source.type};
            }).catch(err => {
                console.error(`Failed to fetch ${source.type}:`, err);
                return {status: 'error', error: err.message, source: source.type};
            })
        );
        
        const metadataResults = await Promise.all(metadataPromises);
        console.log('All metadata results:', metadataResults);
        displayMetadataOptions(metadataResults);
        
    } catch (error) {
        document.getElementById('saucenaoContent').innerHTML = `
            <div class="saucenao-error">
                <div class="saucenao-error-icon">⚠️</div>
                <div class="saucenao-error-text">Error: ${error.message}</div>
            </div>
        `;
    }
}

function displayMetadataOptions(metadataResults) {
    const validResults = metadataResults.filter(r => r.status === 'success');
    const failedResults = metadataResults.filter(r => r.status !== 'success');
    
    if (validResults.length === 0) {
        // Show which sources failed and why
        const failedSources = metadataResults.map(r =>
            `<div class="saucenao-failed-source">
                <strong>${r.source}</strong>: ${r.error || 'Unknown error'}
            </div>`
        ).join('');
        
        document.getElementById('saucenaoContent').innerHTML = `
            <div class="saucenao-error">
                <div class="saucenao-error-icon">⚠️</div>
                <div class="saucenao-error-text">
                    Failed to fetch metadata from all sources
                </div>
                <div style="color: #b0b0b0; margin-bottom: 15px;">Details:</div>
                ${failedSources}
                <div style="margin-top: 20px; text-align: center;">
                    <button onclick="displaySauceNaoResults(saucenaoResults)" class="saucenao-back-btn">← Back to Results</button>
                </div>
            </div>
        `;
        return;
    }
    
    // Show warning if some sources failed
    const warningSection = failedResults.length > 0 ? `
        <div class="saucenao-warning">
            <div class="saucenao-warning-title">⚠️ Some sources unavailable</div>
            <div class="saucenao-warning-text">
                ${failedResults.map(r => r.source).join(', ')} could not be fetched
            </div>
        </div>
    ` : '';
    
    // Use first valid result as default
    const primaryResult = validResults[0];
    
    const html = `
        <div class="saucenao-back-btn-container">
            <button onclick="displaySauceNaoResults(saucenaoResults)" class="saucenao-back-btn">← Back to Results</button>
        </div>

        <div class="saucenao-metadata-grid">
            <div class="saucenao-panel">
                <h3>Select Source</h3>
                <div class="saucenao-source-grid">
                    ${validResults.map((result, idx) => {
                        const sourceInfo = selectedResult.sources.find(s => s.type === result.source);
                        return `
                        <div class="saucenao-source-container">
                            <button onclick="selectMetadataSource(${idx})" id="sourceBtn${idx}" class="saucenao-source-btn ${idx === 0 ? 'active' : ''}">
                                ${result.preview_url ? `
                                    <img src="${result.preview_url}" class="saucenao-source-preview" onerror="this.style.display='none'">
                                ` : ''}
                                <div class="saucenao-source-text">
                                    <div class="saucenao-source-name">${result.source}</div>
                                    ${result.width && result.height ? `
                                        <div class="saucenao-source-resolution">${result.width}×${result.height}</div>
                                    ` : ''}
                                    ${result.file_size ? `
                                        <div class="saucenao-source-filesize">
                                            ${formatFileSize(result.file_size)}
                                        </div>
                                    ` : ''}
                                </div>
                            </button>
                            ${sourceInfo && sourceInfo.url ? `
                                <a href="${sourceInfo.url}" target="_blank" rel="noopener" class="saucenao-source-link">
                                    <span>🔗</span>
                                    <span>View on ${result.source}</span>
                                </a>
                            ` : ''}
                        </div>
                    `}).join('')}
                </div>
            </div>

            <div id="metadataPreview">
                ${renderMetadataPreview(primaryResult, 0)}
            </div>

            <div class="saucenao-panel">
                <h3>Apply Options</h3>

                <label class="saucenao-checkbox-label">
                    <input type="checkbox" id="downloadImage" class="saucenao-checkbox">
                    <div>
                        <div class="saucenao-checkbox-text-title">Download Higher Quality Image</div>
                        <div class="saucenao-checkbox-text-subtitle">
                            Replace current image file with booru source
                        </div>
                    </div>
                </label>

                <div class="saucenao-button-group">
                    <button onclick="applySauceNaoMetadata()" class="saucenao-apply-btn">
                        ✓ Apply Metadata
                    </button>
                    <button onclick="closeSauceNaoModal()" class="saucenao-cancel-btn">Cancel</button>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('saucenaoContent').innerHTML = html;
    
    // Store metadata results for later use
    window.currentMetadataResults = validResults;
    window.selectedMetadataIdx = 0;
}

function renderMetadataPreview(result, idx) {
    const tags = result.tags || {};

    return `
        <div class="saucenao-panel">
            <h3>Metadata Preview</h3>

            ${result.preview_url ? `
                <div class="saucenao-preview-image-container">
                    <img src="${result.preview_url}" class="saucenao-preview-image" onerror="this.style.display='none';">
                </div>
            ` : ''}

            ${result.image_url ? `
                <div class="saucenao-image-link-container">
                    <a href="${result.image_url}" target="_blank" class="saucenao-image-link">
                        🔗 View Full Image
                    </a>
                </div>
            ` : ''}

            ${renderTagCategory('Character', tags.character)}
            ${renderTagCategory('Copyright', tags.copyright)}
            ${renderTagCategory('Artist', tags.artist)}
            ${renderTagCategory('Meta', tags.meta)}
            ${renderTagCategory('General', tags.general, true)}
        </div>
    `;
}

function renderTagCategory(name, tagsString, expandable = false) {
    if (!tagsString || tagsString.trim() === '') return '';

    const tags = tagsString.split(' ').filter(t => t);
    const displayTags = expandable && tags.length > 20 ? tags.slice(0, 20) : tags;
    const hasMore = expandable && tags.length > 20;

    return `
        <div class="saucenao-tag-category">
            <div class="saucenao-tag-category-title">${name} (${tags.length})</div>
            <div class="saucenao-tag-list">
                ${displayTags.map(tag => `
                    <span class="saucenao-tag">${tag}</span>
                `).join('')}
                ${hasMore ? `<span class="saucenao-tag-more">+${tags.length - 20} more</span>` : ''}
            </div>
        </div>
    `;
}

function selectMetadataSource(idx) {
    window.selectedMetadataIdx = idx;

    // Update button styles
    const results = window.currentMetadataResults;
    results.forEach((_, i) => {
        const btn = document.getElementById(`sourceBtn${i}`);
        if (btn) {
            if (i === idx) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }
    });

    // Update preview
    document.getElementById('metadataPreview').innerHTML = renderMetadataPreview(results[idx], idx);
}

async function applySauceNaoMetadata() {
    const selectedIdx = window.selectedMetadataIdx || 0;
    const selectedMetadata = window.currentMetadataResults[selectedIdx];
    const downloadImage = document.getElementById('downloadImage').checked;
    const filepath = document.getElementById('imageFilepath').value;
    
    // Get the source info
    const sourceInfo = selectedResult.sources.find(s => s.type === selectedMetadata.source);
    
    // Show loading overlay
    const overlay = document.createElement('div');
    overlay.className = 'saucenao-loading-overlay';
    overlay.innerHTML = `
        <div class="saucenao-loading-overlay-content">
            <div class="saucenao-loading-overlay-icon">⚙️</div>
            <div id="applyStatus">Applying metadata...</div>
            ${downloadImage ? '<div class="saucenao-loading-overlay-download" id="downloadStatus">Preparing download...</div>' : ''}
        </div>
    `;
    document.body.appendChild(overlay);
    
    // Client-side timeout (90 seconds)
    const timeoutId = setTimeout(() => {
        overlay.remove();
        showNotification('Operation timed out - check Flask console for details', 'error');
    }, 90000);
    
    try {
        if (downloadImage) {
            const statusEl = document.getElementById('downloadStatus');
            if (statusEl) statusEl.textContent = 'Downloading image...';
        }
        
        const response = await fetch('/api/saucenao/apply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filepath: filepath,
                source: selectedMetadata.source,
                post_id: sourceInfo.post_id,
                tags: selectedMetadata.tags,
                download_image: downloadImage,
                image_url: selectedMetadata.image_url,
                secret: SYSTEM_SECRET
            })
        });
        
        clearTimeout(timeoutId);
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response from apply:', text);
            throw new Error('Server returned non-JSON response. Check console for details.');
        }
        
        const data = await response.json();
        
        if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            overlay.remove();
            showNotification('Invalid system secret', 'error');
            closeSauceNaoModal();
            return;
        }
        
        if (data.status === 'success') {
            document.getElementById('applyStatus').textContent = 'Success!';
            if (downloadImage && document.getElementById('downloadStatus')) {
                document.getElementById('downloadStatus').textContent = '✓ Image downloaded';
            }
            
            setTimeout(() => {
                // Redirect to new URL if filepath changed, otherwise reload
                if (data.redirect_url) {
                    window.location.href = data.redirect_url;
                } else {
                    window.location.reload();
                }
            }, 1000);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
        
    } catch (error) {
        clearTimeout(timeoutId);
        overlay.remove();
        console.error('Apply error:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}


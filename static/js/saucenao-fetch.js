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

// Helper function to create elements
function createElement(tag, className, content) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (content) el.textContent = content;
    return el;
}

function showSauceNaoFetcher() {
    if (!SYSTEM_SECRET) {
        const secret = prompt('Enter system secret to use SauceNao fetch:');
        if (!secret) return;
        SYSTEM_SECRET = secret;
        localStorage.setItem('system_secret', secret);
    }

    const modal = document.createElement('div');
    modal.id = 'saucenaoModal';

    const content = createElement('div', 'saucenao-modal-content');

    const header = createElement('div', 'saucenao-modal-header');
    const h2 = createElement('h2', null, '🔍 SauceNao Fetch');
    const closeBtn = createElement('button', 'saucenao-close-btn', '× Close');
    closeBtn.onclick = closeSauceNaoModal;
    header.appendChild(h2);
    header.appendChild(closeBtn);

    const contentDiv = createElement('div');
    contentDiv.id = 'saucenaoContent';

    const loading = createElement('div', 'saucenao-loading');
    const loadingIcon = createElement('div', 'saucenao-loading-icon', '🔍');
    const loadingText = createElement('div', 'saucenao-loading-text', 'Searching SauceNao...');
    loading.appendChild(loadingIcon);
    loading.appendChild(loadingText);
    contentDiv.appendChild(loading);

    content.appendChild(header);
    content.appendChild(contentDiv);
    modal.appendChild(content);

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
            showNoResults();
            return;
        }

        saucenaoResults = data.results;
        displaySauceNaoResults(data.results);

    } catch (error) {
        showError(error.message);
    }
}

function showNoResults() {
    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    const noResults = createElement('div', 'saucenao-no-results');
    const icon = createElement('div', 'saucenao-no-results-icon', '😔');
    const text = createElement('div', 'saucenao-no-results-text', 'No results found on SauceNao');
    const hint = createElement('div', 'saucenao-no-results-hint', 'Try searching manually on booru sites');

    noResults.appendChild(icon);
    noResults.appendChild(text);
    noResults.appendChild(hint);
    content.appendChild(noResults);
}

function showError(message) {
    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    const errorDiv = createElement('div', 'saucenao-error');
    const icon = createElement('div', 'saucenao-error-icon', '⚠️');
    const text = createElement('div', 'saucenao-error-text', `Error: ${message}`);

    errorDiv.appendChild(icon);
    errorDiv.appendChild(text);
    content.appendChild(errorDiv);
}

function displaySauceNaoResults(results) {
    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    // Success banner
    const banner = createElement('div', 'saucenao-success-banner');
    const title = createElement('div', 'saucenao-success-title');
    title.textContent = `✓ Found ${results.length} potential match${results.length !== 1 ? 'es' : ''}`;
    const subtitle = createElement('div', 'saucenao-success-subtitle', 'Click on a result to view details and apply metadata');
    banner.appendChild(title);
    banner.appendChild(subtitle);

    // Results grid
    const grid = createElement('div', 'saucenao-results-grid');
    results.forEach((result, idx) => {
        const resultCard = createResultCard(result, idx);
        grid.appendChild(resultCard);
    });

    content.appendChild(banner);
    content.appendChild(grid);
}

function createResultCard(result, idx) {
    const card = createElement('div', 'saucenao-result');
    card.onclick = () => selectSauceNaoResult(idx);

    const cardContent = createElement('div', 'saucenao-result-content');

    if (result.thumbnail) {
        const img = document.createElement('img');
        img.src = result.thumbnail;
        img.className = 'saucenao-result-thumbnail';
        cardContent.appendChild(img);
    }

    const info = createElement('div', 'saucenao-result-info');
    const similarity = createElement('div', 'saucenao-result-similarity');
    similarity.textContent = `${result.similarity.toFixed(1)}% Match`;

    const sources = createElement('div', 'saucenao-result-sources');
    result.sources.forEach(source => {
        const badge = createElement('span', 'saucenao-source-badge', source.type);
        sources.appendChild(badge);
    });

    info.appendChild(similarity);
    info.appendChild(sources);
    cardContent.appendChild(info);

    const arrow = createElement('div', 'saucenao-result-arrow', '→');
    cardContent.appendChild(arrow);

    card.appendChild(cardContent);
    return card;
}

async function selectSauceNaoResult(idx) {
    const result = saucenaoResults[idx];
    selectedResult = result;

    // Show loading
    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    const loading = createElement('div', 'saucenao-loading');
    const icon = createElement('div', 'saucenao-loading-icon', '⚙️');
    const text = createElement('div', 'saucenao-loading-text', 'Loading metadata...');
    loading.appendChild(icon);
    loading.appendChild(text);
    content.appendChild(loading);

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
        showError(error.message);
    }
}

function displayMetadataOptions(metadataResults) {
    const validResults = metadataResults.filter(r => r.status === 'success');
    const failedResults = metadataResults.filter(r => r.status !== 'success');

    if (validResults.length === 0) {
        showAllSourcesFailed(metadataResults);
        return;
    }

    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    // Back button
    const backBtnContainer = createElement('div', 'saucenao-back-btn-container');
    const backBtn = createElement('button', 'saucenao-back-btn', '← Back to Results');
    backBtn.onclick = () => displaySauceNaoResults(saucenaoResults);
    backBtnContainer.appendChild(backBtn);
    content.appendChild(backBtnContainer);

    // Warning if some sources failed
    if (failedResults.length > 0) {
        const warning = createElement('div', 'saucenao-warning');
        const title = createElement('div', 'saucenao-warning-title', '⚠️ Some sources unavailable');
        const text = createElement('div', 'saucenao-warning-text');
        text.textContent = `${failedResults.map(r => r.source).join(', ')} could not be fetched`;
        warning.appendChild(title);
        warning.appendChild(text);
        content.appendChild(warning);
    }

    // Metadata grid
    const grid = createElement('div', 'saucenao-metadata-grid');

    // Source selection panel
    const sourcePanel = createSourceSelectionPanel(validResults);
    grid.appendChild(sourcePanel);

    // Metadata preview
    const previewDiv = createElement('div');
    previewDiv.id = 'metadataPreview';
    previewDiv.appendChild(createMetadataPreview(validResults[0], 0));
    grid.appendChild(previewDiv);

    // Apply options panel
    const applyPanel = createApplyOptionsPanel();
    grid.appendChild(applyPanel);

    content.appendChild(grid);

    // Store metadata results for later use
    window.currentMetadataResults = validResults;
    window.selectedMetadataIdx = 0;
}

function showAllSourcesFailed(metadataResults) {
    const content = document.getElementById('saucenaoContent');
    content.innerHTML = '';

    const errorDiv = createElement('div', 'saucenao-error');
    const icon = createElement('div', 'saucenao-error-icon', '⚠️');
    const text = createElement('div', 'saucenao-error-text', 'Failed to fetch metadata from all sources');

    const detailsLabel = createElement('div');
    detailsLabel.style.color = '#b0b0b0';
    detailsLabel.style.marginBottom = '15px';
    detailsLabel.textContent = 'Details:';

    errorDiv.appendChild(icon);
    errorDiv.appendChild(text);
    errorDiv.appendChild(detailsLabel);

    metadataResults.forEach(r => {
        const failedSource = createElement('div', 'saucenao-failed-source');
        const strong = createElement('strong', null, r.source);
        failedSource.appendChild(strong);
        failedSource.appendChild(document.createTextNode(`: ${r.error || 'Unknown error'}`));
        errorDiv.appendChild(failedSource);
    });

    const btnContainer = createElement('div');
    btnContainer.style.marginTop = '20px';
    btnContainer.style.textAlign = 'center';
    const backBtn = createElement('button', 'saucenao-back-btn', '← Back to Results');
    backBtn.onclick = () => displaySauceNaoResults(saucenaoResults);
    btnContainer.appendChild(backBtn);
    errorDiv.appendChild(btnContainer);

    content.appendChild(errorDiv);
}

function createSourceSelectionPanel(validResults) {
    const panel = createElement('div', 'saucenao-panel');
    const h3 = createElement('h3', null, 'Select Source');
    panel.appendChild(h3);

    const grid = createElement('div', 'saucenao-source-grid');

    validResults.forEach((result, idx) => {
        const sourceInfo = selectedResult.sources.find(s => s.type === result.source);
        const container = createElement('div', 'saucenao-source-container');

        const btn = createElement('button', `saucenao-source-btn ${idx === 0 ? 'active' : ''}`);
        btn.id = `sourceBtn${idx}`;
        btn.onclick = () => selectMetadataSource(idx);

        if (result.preview_url) {
            const img = document.createElement('img');
            img.src = result.preview_url;
            img.className = 'saucenao-source-preview';
            img.onerror = () => img.style.display = 'none';
            btn.appendChild(img);
        }

        const textDiv = createElement('div', 'saucenao-source-text');
        const name = createElement('div', 'saucenao-source-name', result.source);
        textDiv.appendChild(name);

        if (result.width && result.height) {
            const res = createElement('div', 'saucenao-source-resolution', `${result.width}×${result.height}`);
            textDiv.appendChild(res);
        }

        if (result.file_size) {
            const size = createElement('div', 'saucenao-source-filesize', formatFileSize(result.file_size));
            textDiv.appendChild(size);
        }

        btn.appendChild(textDiv);
        container.appendChild(btn);

        if (sourceInfo && sourceInfo.url) {
            const link = document.createElement('a');
            link.href = sourceInfo.url;
            link.target = '_blank';
            link.rel = 'noopener';
            link.className = 'saucenao-source-link';

            const linkIcon = createElement('span', null, '🔗');
            const linkText = createElement('span', null, `View on ${result.source}`);
            link.appendChild(linkIcon);
            link.appendChild(linkText);
            container.appendChild(link);
        }

        grid.appendChild(container);
    });

    panel.appendChild(grid);
    return panel;
}

function createMetadataPreview(result, _idx) {
    const panel = createElement('div', 'saucenao-panel');
    const h3 = createElement('h3', null, 'Metadata Preview');
    panel.appendChild(h3);

    if (result.preview_url) {
        const imgContainer = createElement('div', 'saucenao-preview-image-container');
        const img = document.createElement('img');
        img.src = result.preview_url;
        img.className = 'saucenao-preview-image';
        img.onerror = () => img.style.display = 'none';
        imgContainer.appendChild(img);
        panel.appendChild(imgContainer);
    }

    if (result.image_url) {
        const linkContainer = createElement('div', 'saucenao-image-link-container');
        const link = document.createElement('a');
        link.href = result.image_url;
        link.target = '_blank';
        link.className = 'saucenao-image-link';
        link.textContent = '🔗 View Full Image';
        linkContainer.appendChild(link);
        panel.appendChild(linkContainer);
    }

    const tags = result.tags || {};

    if (tags.character) panel.appendChild(createTagCategory('Character', tags.character));
    if (tags.copyright) panel.appendChild(createTagCategory('Copyright', tags.copyright));
    if (tags.artist) panel.appendChild(createTagCategory('Artist', tags.artist));
    if (tags.meta) panel.appendChild(createTagCategory('Meta', tags.meta));
    if (tags.general) panel.appendChild(createTagCategory('General', tags.general, true));

    return panel;
}

function createTagCategory(name, tagsString, expandable = false) {
    if (!tagsString || tagsString.trim() === '') return createElement('div');

    const tags = tagsString.split(' ').filter(t => t);
    const displayTags = expandable && tags.length > 20 ? tags.slice(0, 20) : tags;
    const hasMore = expandable && tags.length > 20;

    const category = createElement('div', 'saucenao-tag-category');
    const title = createElement('div', 'saucenao-tag-category-title', `${name} (${tags.length})`);
    category.appendChild(title);

    const tagList = createElement('div', 'saucenao-tag-list');
    displayTags.forEach(tag => {
        const tagSpan = createElement('span', 'saucenao-tag', tag);
        tagList.appendChild(tagSpan);
    });

    if (hasMore) {
        const more = createElement('span', 'saucenao-tag-more', `+${tags.length - 20} more`);
        tagList.appendChild(more);
    }

    category.appendChild(tagList);
    return category;
}

function createApplyOptionsPanel() {
    const panel = createElement('div', 'saucenao-panel');
    const h3 = createElement('h3', null, 'Apply Options');
    panel.appendChild(h3);

    const label = createElement('label', 'saucenao-checkbox-label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'downloadImage';
    checkbox.className = 'saucenao-checkbox';
    label.appendChild(checkbox);

    const textDiv = createElement('div');
    const titleDiv = createElement('div', 'saucenao-checkbox-text-title', 'Download Higher Quality Image');
    const subtitleDiv = createElement('div', 'saucenao-checkbox-text-subtitle', 'Replace current image file with booru source');
    textDiv.appendChild(titleDiv);
    textDiv.appendChild(subtitleDiv);
    label.appendChild(textDiv);
    panel.appendChild(label);

    const btnGroup = createElement('div', 'saucenao-button-group');
    const applyBtn = createElement('button', 'saucenao-apply-btn', '✓ Apply Metadata');
    applyBtn.onclick = applySauceNaoMetadata;
    const cancelBtn = createElement('button', 'saucenao-cancel-btn', 'Cancel');
    cancelBtn.onclick = closeSauceNaoModal;
    btnGroup.appendChild(applyBtn);
    btnGroup.appendChild(cancelBtn);
    panel.appendChild(btnGroup);

    return panel;
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
    const previewDiv = document.getElementById('metadataPreview');
    previewDiv.innerHTML = '';
    previewDiv.appendChild(createMetadataPreview(results[idx], idx));
}

async function applySauceNaoMetadata() {
    const selectedIdx = window.selectedMetadataIdx || 0;
    const selectedMetadata = window.currentMetadataResults[selectedIdx];
    const downloadImage = document.getElementById('downloadImage').checked;
    const filepath = document.getElementById('imageFilepath').value;

    // Get the source info
    const sourceInfo = selectedResult.sources.find(s => s.type === selectedMetadata.source);

    // Show loading overlay
    const overlay = createElement('div', 'saucenao-loading-overlay');
    const overlayContent = createElement('div', 'saucenao-loading-overlay-content');
    const overlayIcon = createElement('div', 'saucenao-loading-overlay-icon', '⚙️');
    const statusDiv = createElement('div');
    statusDiv.id = 'applyStatus';
    statusDiv.textContent = 'Applying metadata...';
    overlayContent.appendChild(overlayIcon);
    overlayContent.appendChild(statusDiv);

    if (downloadImage) {
        const downloadStatus = createElement('div', 'saucenao-loading-overlay-download', 'Preparing download...');
        downloadStatus.id = 'downloadStatus';
        overlayContent.appendChild(downloadStatus);
    }

    overlay.appendChild(overlayContent);
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

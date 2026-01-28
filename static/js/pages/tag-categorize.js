// static/js/pages/tag-categorize.js - Tag Categorization Page
import { showNotification } from '../utils/notifications.js';

let currentTags = [];
let currentIndex = 0;
let availableCategories = [];
let extendedCategories = []; // Full category data with shortcuts

async function loadTags() {
    const loadingState = document.getElementById('loadingState');
    if (loadingState) loadingState.style.display = 'block';

    const tagDisplay = document.getElementById('tagDisplay');
    if (tagDisplay) tagDisplay.innerHTML = '<div class="loading-state">Loading tags...</div>';

    try {
        // Load tags first for immediate page display
        const tagsResponse = await fetch('/api/tag_categorize/tags?limit=100');
        const data = await tagsResponse.json();

        currentTags = data.tags || [];
        availableCategories = data.categories || [];
        extendedCategories = data.extended_categories || [];
        currentIndex = 0;

        // Display tags immediately
        if (currentTags.length === 0) {
            tagDisplay.innerHTML = '<div class="no-tags-state">No uncategorized tags in this batch.</div>';
        } else {
            displayCurrentTag();
        }

        // Load stats in the background (non-blocking, without "meaningful" counts for speed)
        fetch('/api/tag_categorize/stats')
            .then(res => res.json())
            .then(data => {
                updateStatsDisplay(data);

                // Update the empty state message if stats show everything is categorized
                if (currentTags.length === 0 && data.uncategorized === 0) {
                    tagDisplay.innerHTML = '<div class="no-tags-state">All tags are categorized! 🎉</div>';
                }
            })
            .catch(error => {
                console.error('Error loading stats:', error);
            });

    } catch (error) {
        console.error('Error loading tags:', error);
        const tagDisplay = document.getElementById('tagDisplay');
        if (tagDisplay) {
            tagDisplay.innerHTML = '<div class="no-tags-state">Error loading tags: ' + error.message + '</div>';
        }
    }
}

function updateStatsDisplay(data) {
    try {
        // Use meaningful counts if available (tags actually used in images)
        // Otherwise fall back to basic counts for faster loading
        const hasMeaningful = data.meaningful_categorized !== undefined &&
                             data.meaningful_categorized > 0 ||
                             data.meaningful_uncategorized > 0;

        const categorized = hasMeaningful ? data.meaningful_categorized : data.categorized;
        const uncategorized = hasMeaningful ? data.meaningful_uncategorized : data.uncategorized;
        const total = (categorized || 0) + (uncategorized || 0);

        const statTotal = document.getElementById('statTotal');
        const statCategorized = document.getElementById('statCategorized');
        const statUncategorized = document.getElementById('statUncategorized');

        if (statTotal) statTotal.textContent = total;
        if (statCategorized) statCategorized.textContent = categorized || 0;
        if (statUncategorized) statUncategorized.textContent = uncategorized || 0;
    } catch (error) {
        console.error('Error updating stats display:', error);
    }
}

async function loadStats() {
    try {
        const response = await fetch('/api/tag_categorize/stats');
        const data = await response.json();
        updateStatsDisplay(data);
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function updateQueueList() {
    const queueList = document.getElementById('queueList');
    if (currentTags.length === 0) {
        queueList.innerHTML = '<div class="queue-empty">No more tags</div>';
        return;
    }

    // Show 25 tags: keep 3 previous tags visible + current + 21 upcoming
    const startIndex = Math.max(0, currentIndex - 3);
    const endIndex = Math.min(currentTags.length, startIndex + 25);
    const visibleTags = currentTags.slice(startIndex, endIndex);

    queueList.innerHTML = visibleTags.map((tag, idx) => {
        const actualIndex = startIndex + idx;
        const isActive = actualIndex === currentIndex;
        return `<div class="queue-item ${isActive ? 'queue-item-active' : ''}"
                     onclick="jumpToTag(${actualIndex})"
                     title="${tag.name} (${tag.usage_count} uses)">
            <div class="queue-item-number">${actualIndex + 1}</div>
            <div class="queue-item-name">${tag.name}</div>
            <div class="queue-item-count">${tag.usage_count}</div>
        </div>`;
    }).join('');

    // Auto-scroll to active item
    setTimeout(() => {
        const activeItem = queueList.querySelector('.queue-item-active');
        if (activeItem) {
            activeItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, 50);
}

function jumpToTag(index) {
    if (index >= 0 && index < currentTags.length) {
        currentIndex = index;
        displayCurrentTag();
    }
}

function displayCurrentTag() {
    // Check actual uncategorized count from stats
    const uncategorizedCount = parseInt(document.getElementById('statUncategorized').textContent) || 0;

    if (currentTags.length === 0 && uncategorizedCount === 0) {
        document.getElementById('tagDisplay').innerHTML =
            '<div class="no-tags-state">All tags are categorized! 🎉</div>';
        document.getElementById('queueList').innerHTML = '<div class="queue-empty">No more tags</div>';
        return;
    }

    if (currentTags.length === 0) {
        document.getElementById('tagDisplay').innerHTML =
            '<div class="no-tags-state">No tags in current batch. Try refreshing the page.</div>';
        document.getElementById('queueList').innerHTML = '<div class="queue-empty">No more tags</div>';
        return;
    }

    const tag = currentTags[currentIndex];
    const progress = `Tag ${currentIndex + 1} / ${currentTags.length}`;
    document.getElementById('categorizeProgress').textContent = progress;

    // Update queue list
    updateQueueList();

    const sampleImages = tag.sample_images || [];
    const imageGallery = sampleImages.length > 0
        ? `<div class="sample-images">
            ${sampleImages.map(filepath => {
            const isVideo = filepath.endsWith('.mp4') || filepath.endsWith('.webm');
            const videoType = filepath.endsWith('.webm') ? 'video/webm' : 'video/mp4';
            return isVideo
                ? `<video controls loop preload="metadata"><source src="/static/images/${filepath}" type="${videoType}"></video>`
                : `<img src="/static/images/${filepath}" alt="Sample image">`;
        }).join('')}
          </div>`
        : '<div class="no-samples">No sample images available</div>';

    document.getElementById('tagDisplay').innerHTML = `
        <div class="tag-info">
            <div class="tag-name">${tag.name}</div>
            <div class="tag-usage">Used in ${tag.usage_count} image${tag.usage_count !== 1 ? 's' : ''}</div>
            ${imageGallery}

            <div class="category-buttons">
                ${extendedCategories.map(catData => {
        const [catKey, catName, shortcut, description] = catData;
        const cssClass = catKey.replace(/_/g, '-').toLowerCase();
        return `<button class="category-btn category-btn-${cssClass}"
                            onclick="setCategory('${catKey}')"
                            title="${description}">
                        ${catName}<br><small>(${shortcut})</small>
                    </button>`;
    }).join('')}
            </div>

            <div class="navigation-buttons">
                <button class="nav-btn" onclick="previousTag()" ${currentIndex === 0 ? 'disabled' : ''}>
                    ← Previous (P)
                </button>
                <button class="nav-btn" onclick="showSuggestion()">
                    Suggest (?)
                </button>
                <button class="nav-btn" onclick="skipTag()">
                    Skip (K)
                </button>
                <button class="nav-btn nav-btn-primary" onclick="nextTag()" ${currentIndex >= currentTags.length - 1 ? 'disabled' : ''}>
                    Next (N / →)
                </button>
            </div>
        </div>
    `;
}

async function showSuggestion() {
    const tag = currentTags[currentIndex];

    try {
        const response = await fetch(`/api/tag_categorize/tag_details?tag_name=${encodeURIComponent(tag.name)}`);
        const data = await response.json();

        if (data.suggested_category) {
            showNotification(`Suggested: ${data.suggested_category}`, 'info');

            // Auto-select the suggested category
            if (confirm(`Categorize "${tag.name}" as "${data.suggested_category}"?`)) {
                await setCategory(data.suggested_category);
            }
        } else {
            showNotification('No suggestion available', 'info');
        }
    } catch (error) {
        console.error('Error getting suggestion:', error);
        showNotification('Error getting suggestion: ' + error.message, 'error');
    }
}

async function setCategory(category) {
    const tag = currentTags[currentIndex];

    try {
        const response = await fetch('/api/tag_categorize/set', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tag_name: tag.name,
                category: category
            })
        });

        const result = await response.json();

        if (result.success) {
            showNotification(`"${tag.name}" → ${category}`, 'success');
            // Remove the tag from the list
            currentTags.splice(currentIndex, 1);

            // Update stats
            await loadStats();

            // Display next tag (or stay at same index since we removed one)
            if (currentIndex >= currentTags.length) {
                currentIndex = currentTags.length - 1;
            }
            displayCurrentTag();
        } else {
            showNotification('Error: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error setting category:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

function nextTag() {
    if (currentIndex < currentTags.length - 1) {
        currentIndex++;
        displayCurrentTag();
    } else {
        showNotification('No more tags', 'info');
    }
}

function previousTag() {
    if (currentIndex > 0) {
        currentIndex--;
        displayCurrentTag();
    }
}

function skipTag() {
    nextTag();
}

async function loadTagForEdit() {
    const tagName = document.getElementById('editTagInput').value.trim();
    if (!tagName) {
        showNotification('Please enter a tag name', 'error');
        return;
    }

    const editDisplay = document.getElementById('editTagDisplay');
    editDisplay.innerHTML = '<div class="loading-state">Loading tag...</div>';

    try {
        const response = await fetch(`/api/tag_categorize/tag_details?tag_name=${encodeURIComponent(tagName)}`);
        const data = await response.json();

        if (!data || data.error) {
            editDisplay.innerHTML = `<div class="no-tags-state">Tag "${tagName}" not found</div>`;
            return;
        }

        const tag = data;
        editDisplay.innerHTML = `
            <div class="edit-tag-info">
                <div class="edit-tag-name">${tag.name}</div>
                <div class="edit-tag-meta">
                    <span>Current Category: <strong>${tag.category || 'Uncategorized'}</strong></span>
                    <span>Usage Count: ${tag.usage_count || 0}</span>
                </div>
                <div class="category-buttons">
                    ${extendedCategories.map(catData => {
            const [catKey, catName, shortcut, description] = catData;
            const cssClass = catKey.replace(/_/g, '-').toLowerCase();
            return `<button class="category-btn category-btn-${cssClass}"
                                onclick="updateTagCategory('${tag.name}', '${catKey}')"
                                title="${description}">
                            ${catName}
                        </button>`;
        }).join('')}
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error loading tag:', error);
        editDisplay.innerHTML = `<div class="no-tags-state">Error loading tag: ${error.message}</div>`;
    }
}

async function updateTagCategory(tagName, category) {
    try {
        const response = await fetch('/api/tag_categorize/set', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tag_name: tagName,
                category: category
            })
        });

        const result = await response.json();

        if (result.success) {
            showNotification(`"${tagName}" updated to ${category}`, 'success');
            document.getElementById('editTagInput').value = '';
            document.getElementById('editTagDisplay').innerHTML = '';
            await loadStats();
        } else {
            showNotification('Error: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error updating category:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

// Allow Enter key to load tag
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('editTagInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            loadTagForEdit();
        }
    });
});

// Export modal functions
function exportCategorizations() {
    document.getElementById('exportModal').style.display = 'flex';
}

function closeExportModal() {
    document.getElementById('exportModal').style.display = 'none';
}

async function confirmExport() {
    const exportType = document.querySelector('input[name="exportType"]:checked').value;
    const categorizedOnly = exportType === 'categorized';

    closeExportModal();

    try {
        const url = `/api/tag_categorize/export?categorized_only=${categorizedOnly}`;

        showNotification('Exporting tag categorizations...', 'info');

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Export failed: ${response.statusText}`);
        }

        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `tag_categorizations_${new Date().toISOString()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        showNotification('Export completed successfully!', 'success');
    } catch (error) {
        console.error('Error exporting:', error);
        showNotification('Error exporting: ' + error.message, 'error');
    }
}

// Import modal functions
let importFileData = null;

function closeImportModal() {
    document.getElementById('importModal').style.display = 'none';
    importFileData = null;
}

async function confirmImport() {
    const mode = document.querySelector('input[name="importMode"]:checked').value;

    if (!importFileData) {
        showNotification('No import data available', 'error');
        return;
    }

    // Store data in local variable before closing modal
    const dataToImport = importFileData;
    closeImportModal();

    try {
        showNotification('Importing tag categorizations...', 'info');

        const response = await fetch(`/api/tag_categorize/import?mode=${mode}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(dataToImport)
        });

        const result = await response.json();

        if (result.success) {
            showNotification(`Import completed! Updated: ${result.updated}, Skipped: ${result.skipped}`, 'success');

            // Reload tags and stats
            await loadStats();
            await loadTags();
        } else {
            showNotification('Error importing: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error importing:', error);
        showNotification('Error importing: ' + error.message, 'error');
    } finally {
        importFileData = null;
    }
}

// Handle import file selection
async function handleImportFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    try {
        const text = await file.text();
        const data = JSON.parse(text);

        // Store the data and show the modal
        importFileData = data;
        document.getElementById('importModal').style.display = 'flex';
    } catch (error) {
        console.error('Error reading file:', error);
        showNotification('Error reading file: ' + error.message, 'error');
    } finally {
        // Reset file input
        event.target.value = '';
    }
}

// Sync base categories from extended categories
async function syncBaseCategories() {
    if (!confirm('This will update the base category (character/artist/copyright/species/general/meta) for all tags based on their extended categories. Continue?')) {
        return;
    }

    try {
        showNotification('Syncing base categories...', 'info');

        const response = await fetch('/api/tag_categorize/sync_base_categories', {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            const cleanedMsg = result.cleaned > 0 ? `, Cleaned: ${result.cleaned}` : '';
            showNotification(`Sync completed! Checked: ${result.total_checked}, Updated: ${result.updated}, Unchanged: ${result.unchanged}${cleanedMsg}`, 'success');
            await loadStats();
        } else {
            showNotification('Error syncing: ' + result.error, 'error');
        }
    } catch (error) {
        console.error('Error syncing:', error);
        showNotification('Error syncing: ' + error.message, 'error');
    }
}

// Load tags on page load
loadTags();

// Expose functions to window for onclick handlers
window.jumpToTag = jumpToTag;
window.setCategory = setCategory;
window.nextTag = nextTag;
window.previousTag = previousTag;
window.skipTag = skipTag;
window.showSuggestion = showSuggestion;
window.loadTagForEdit = loadTagForEdit;
window.updateTagCategory = updateTagCategory;
window.exportCategorizations = exportCategorizations;
window.closeExportModal = closeExportModal;
window.confirmExport = confirmExport;
window.closeImportModal = closeImportModal;
window.confirmImport = confirmImport;
window.handleImportFile = handleImportFile;
window.syncBaseCategories = syncBaseCategories;

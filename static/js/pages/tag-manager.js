// Tag Manager Main Module
import { showNotification } from '../utils/notifications.js';

// State Management
const state = {
    currentMode: 'tags',
    workingSet: {
        images: [],
        source: 'manual',
        createdAt: Date.now()
    },
    tags: {
        data: [],
        total: 0,
        offset: 0,
        limit: 50,
        filters: {
            search: '',
            status: 'all',
            baseCategories: [],
            extendedCategory: '',
            sort: 'count_desc'
        },
        selected: new Set()
    },
    images: {
        data: [],
        offset: 0,
        limit: 50,
        searchQuery: '',
        selected: new Set()
    },
    currentTag: null
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadWorkingSetFromStorage();
    initializeEventListeners();
    initializeKeyboardShortcuts();
    switchMode('tags');
});

// Load Working Set from localStorage
function loadWorkingSetFromStorage() {
    const stored = localStorage.getItem('tagManagerWorkingSet');
    if (stored) {
        try {
            const parsed = JSON.parse(stored);
            state.workingSet = parsed;
            updateWorkingSetDisplay();
        } catch (e) {
            console.error('Failed to load working set:', e);
        }
    }
}

// Save Working Set to localStorage
function saveWorkingSetToStorage() {
    try {
        localStorage.setItem('tagManagerWorkingSet', JSON.stringify(state.workingSet));
    } catch (e) {
        console.error('Failed to save working set:', e);
    }
}

// Update Working Set Display
function updateWorkingSetDisplay() {
    const countEl = document.getElementById('workingSetCount');
    const thumbnailsEl = document.getElementById('workingSetThumbnails');
    const summaryEl = document.getElementById('workingSetSummary');

    const count = state.workingSet.images.length;
    countEl.textContent = `${count} image${count !== 1 ? 's' : ''}`;

    // Update thumbnails
    thumbnailsEl.innerHTML = '';
    const displayCount = Math.min(count, 10);
    for (let i = 0; i < displayCount; i++) {
        const filepath = state.workingSet.images[i];
        const img = document.createElement('img');
        img.src = `/images/${filepath}`;
        img.className = 'ws-thumbnail';
        img.title = filepath;
        thumbnailsEl.appendChild(img);
    }

    if (count > displayCount) {
        const more = document.createElement('div');
        more.textContent = `+${count - displayCount} more`;
        more.style.cssText = 'color: var(--text-muted); font-size: 0.85rem; align-self: center;';
        thumbnailsEl.appendChild(more);
    }

    // Update summary in bulk editor
    if (summaryEl) {
        summaryEl.querySelector('.ws-count').textContent = `${count} image${count !== 1 ? 's' : ''}`;
    }

    // Load common tags if in images mode and working set is not empty
    if (state.currentMode === 'images' && count > 0) {
        loadCommonTags();
    }
}

// Initialize Event Listeners
function initializeEventListeners() {
    // Mode tabs
    document.querySelectorAll('.mode-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            switchMode(tab.dataset.mode);
        });
    });

    // Header actions
    document.getElementById('helpBtn').addEventListener('click', () => {
        document.getElementById('helpModal').style.display = 'flex';
    });

    // Working Set actions
    document.getElementById('addTagsBtn').addEventListener('click', () => {
        if (state.workingSet.images.length === 0) {
            showNotification('No images in working set', 'warning');
            return;
        }
        switchMode('images');
    });

    document.getElementById('removeTagsBtn').addEventListener('click', () => {
        if (state.workingSet.images.length === 0) {
            showNotification('No images in working set', 'warning');
            return;
        }
        switchMode('images');
    });

    document.getElementById('clearWorkingSetBtn').addEventListener('click', clearWorkingSet);

    // Tag mode filters
    document.getElementById('tagSearchInput').addEventListener('input', debounce(() => {
        state.tags.filters.search = document.getElementById('tagSearchInput').value;
        state.tags.offset = 0;
        loadTags();
    }, 300));

    document.querySelectorAll('input[name="tagStatus"]').forEach(radio => {
        radio.addEventListener('change', () => {
            state.tags.filters.status = radio.value;
            state.tags.offset = 0;
            loadTags();
        });
    });

    document.querySelectorAll('input[name="baseCategory"]').forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            state.tags.filters.baseCategories = Array.from(
                document.querySelectorAll('input[name="baseCategory"]:checked')
            ).map(cb => cb.value);
            state.tags.offset = 0;
            loadTags();
        });
    });

    document.getElementById('tagSortSelect').addEventListener('change', (e) => {
        state.tags.filters.sort = e.target.value;
        state.tags.offset = 0;
        loadTags();
    });

    // Tag pagination
    document.getElementById('tagPrevBtn').addEventListener('click', () => {
        if (state.tags.offset > 0) {
            state.tags.offset -= state.tags.limit;
            loadTags();
        }
    });

    document.getElementById('tagNextBtn').addEventListener('click', () => {
        if (state.tags.offset + state.tags.limit < state.tags.total) {
            state.tags.offset += state.tags.limit;
            loadTags();
        }
    });

    document.getElementById('tagPerPageSelect').addEventListener('change', (e) => {
        state.tags.limit = parseInt(e.target.value);
        state.tags.offset = 0;
        loadTags();
    });

    // Select all tags
    document.getElementById('selectAllTags').addEventListener('change', (e) => {
        if (e.target.checked) {
            state.tags.data.forEach(tag => state.tags.selected.add(tag.name));
        } else {
            state.tags.selected.clear();
        }
        updateTagTable();
    });

    // Image mode
    document.getElementById('imageSearchBtn').addEventListener('click', searchImages);
    document.getElementById('imageSearchInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            searchImages();
        }
    });

    document.getElementById('selectAllImages').addEventListener('click', () => {
        state.images.data.forEach(img => state.images.selected.add(img.filepath));
        updateImageGrid();
    });

    document.getElementById('addSelectedToWorkingSet').addEventListener('click', addSelectedToWorkingSet);

    // Bulk editor
    document.getElementById('addTagInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const tag = e.target.value.trim();
            if (tag) {
                addTagToQueue('add', tag);
                e.target.value = '';
            }
        }
    });

    document.getElementById('applyAddTagsBtn').addEventListener('click', applyBulkAddTags);
    document.getElementById('applyRemoveTagsBtn').addEventListener('click', applyBulkRemoveTags);

    // Bulk operations
    document.getElementById('bulkCategorizeBtn').addEventListener('click', bulkCategorize);
    document.getElementById('bulkMergeBtn').addEventListener('click', showMergeModal);
    document.getElementById('bulkDeleteBtn').addEventListener('click', showDeleteModal);
    document.getElementById('bulkCancelBtn').addEventListener('click', () => {
        state.tags.selected.clear();
        updateTagTable();
    });

    // Modal confirmations
    document.getElementById('confirmRenameBtn').addEventListener('click', confirmRename);
    document.getElementById('confirmMergeBtn').addEventListener('click', confirmMerge);
    document.getElementById('confirmDeleteBtn').addEventListener('click', confirmDelete);
}

// Initialize Keyboard Shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ignore if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            if (e.key === 'Escape') {
                e.target.blur();
            }
            return;
        }

        // Global shortcuts
        if (e.key === '1') {
            switchMode('tags');
        } else if (e.key === '2') {
            switchMode('images');
        } else if (e.key === '3') {
            switchMode('stats');
        } else if (e.key === '/' && !e.shiftKey) {
            e.preventDefault();
            if (state.currentMode === 'tags') {
                document.getElementById('tagSearchInput').focus();
            } else if (state.currentMode === 'images') {
                document.getElementById('imageSearchInput').focus();
            }
        } else if (e.key === '?') {
            document.getElementById('helpModal').style.display = 'flex';
        } else if (e.key === 'Escape') {
            // Close modals
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
            // Clear selections
            state.tags.selected.clear();
            state.images.selected.clear();
            updateTagTable();
            updateImageGrid();
        }

        // Tag mode shortcuts
        if (state.currentMode === 'tags') {
            if (e.key === 'd' && state.tags.selected.size > 0) {
                showDeleteModal();
            } else if (e.key === 'm' && state.tags.selected.size > 1) {
                showMergeModal();
            } else if (e.key === 'c' && state.tags.selected.size > 0) {
                document.getElementById('bulkBaseCategorySelect').focus();
            }
        }

        // Image mode shortcuts
        if (state.currentMode === 'images') {
            if (e.key === 't') {
                document.getElementById('addTagInput').focus();
            } else if (e.key === 'A' && e.shiftKey) {
                e.preventDefault();
                document.getElementById('selectAllImages').click();
            }
        }
    });
}

// Switch Mode
function switchMode(mode) {
    state.currentMode = mode;

    // Update tabs
    document.querySelectorAll('.mode-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });

    // Update content panels
    document.querySelectorAll('.mode-content').forEach(panel => {
        const panelMode = panel.dataset.mode;
        panel.style.display = panelMode === mode ? 'block' : 'none';
    });

    // Load mode-specific data
    if (mode === 'tags') {
        loadTags();
    } else if (mode === 'images') {
        // Don't auto-search, wait for user input
    } else if (mode === 'stats') {
        loadStats();
    }
}

// Load Tags
async function loadTags() {
    const loadingState = document.getElementById('tagLoadingState');
    const tagTable = document.getElementById('tagTable');
    const pagination = document.getElementById('tagPagination');
    const resultCount = document.getElementById('tagResultCount');

    loadingState.style.display = 'block';
    tagTable.style.display = 'none';

    try {
        const params = new URLSearchParams({
            offset: state.tags.offset,
            limit: state.tags.limit,
            sort: state.tags.filters.sort
        });

        if (state.tags.filters.search) {
            params.append('search', state.tags.filters.search);
        }
        if (state.tags.filters.status !== 'all') {
            params.append('status', state.tags.filters.status);
        }
        if (state.tags.filters.baseCategories.length === 1) {
            params.append('base_category', state.tags.filters.baseCategories[0]);
        }

        const response = await fetch(`/api/tags/browse?${params}`);
        const data = await response.json();

        state.tags.data = data.tags;
        state.tags.total = data.total;

        loadingState.style.display = 'none';
        tagTable.style.display = 'table';
        pagination.style.display = 'flex';

        resultCount.textContent = `${data.total} tag${data.total !== 1 ? 's' : ''}`;

        updateTagTable();
        updatePagination();
    } catch (error) {
        console.error('Failed to load tags:', error);
        showNotification('Failed to load tags', 'error');
        loadingState.textContent = 'Error loading tags';
    }
}

// Update Tag Table
function updateTagTable() {
    const tbody = document.getElementById('tagTableBody');
    tbody.innerHTML = '';

    state.tags.data.forEach(tag => {
        const tr = document.createElement('tr');
        tr.classList.toggle('selected', state.tags.selected.has(tag.name));

        tr.innerHTML = `
            <td><input type="checkbox" ${state.tags.selected.has(tag.name) ? 'checked' : ''} data-tag="${tag.name}"></td>
            <td class="tag-name">${tag.name}</td>
            <td><span class="tag-category ${tag.base_category}">${tag.base_category || 'none'}</span></td>
            <td>${tag.extended_category || '—'}</td>
            <td>${tag.count}</td>
            <td class="tag-actions">
                <button class="tag-action-btn" data-action="view" data-tag="${tag.name}">View</button>
            </td>
        `;

        // Checkbox toggle - use event delegation to avoid recursive calls
        tr.querySelector('input[type="checkbox"]').addEventListener('change', (e) => {
            e.stopPropagation(); // Prevent row click from triggering
            if (e.target.checked) {
                state.tags.selected.add(tag.name);
            } else {
                state.tags.selected.delete(tag.name);
            }
            tr.classList.toggle('selected', e.target.checked);
            updateBulkOperationsBar(); // Update only the bulk bar, not the whole table
        });

        // View button
        tr.querySelector('[data-action="view"]').addEventListener('click', () => {
            loadTagDetail(tag.name);
        });

        // Row click to select
        tr.addEventListener('click', (e) => {
            if (e.target.type !== 'checkbox' && e.target.tagName !== 'BUTTON') {
                const checkbox = tr.querySelector('input[type="checkbox"]');
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event('change', { bubbles: false }));
            }
        });

        tbody.appendChild(tr);
    });

    updateBulkOperationsBar();
}

// Update Bulk Operations Bar (separated for efficiency)
function updateBulkOperationsBar() {
    const bulkBar = document.getElementById('bulkOperationsBar');
    const bulkCount = document.getElementById('bulkSelectionCount');

    if (state.tags.selected.size > 0) {
        bulkBar.style.display = 'flex';
        bulkCount.textContent = `${state.tags.selected.size} selected`;
    } else {
        bulkBar.style.display = 'none';
    }
}

// Update Pagination
function updatePagination() {
    const prevBtn = document.getElementById('tagPrevBtn');
    const nextBtn = document.getElementById('tagNextBtn');
    const pageInfo = document.getElementById('tagPageInfo');

    prevBtn.disabled = state.tags.offset === 0;
    nextBtn.disabled = state.tags.offset + state.tags.limit >= state.tags.total;

    const currentPage = Math.floor(state.tags.offset / state.tags.limit) + 1;
    const totalPages = Math.ceil(state.tags.total / state.tags.limit);
    pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
}

// Load Tag Detail
async function loadTagDetail(tagName) {
    state.currentTag = tagName;
    const detailEmpty = document.getElementById('tagDetailEmpty');
    const detailContent = document.getElementById('tagDetailContent');

    detailEmpty.style.display = 'none';
    detailContent.innerHTML = '<div class="loading-state">Loading...</div>';
    detailContent.style.display = 'block';

    try {
        const response = await fetch(`/api/tags/${encodeURIComponent(tagName)}/detail`);
        const data = await response.json();

        detailContent.innerHTML = `
            <div class="detail-group">
                <div class="detail-label">Tag Name</div>
                <div class="detail-value tag-name">${data.tag.name}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">Usage Count</div>
                <div class="detail-value">${data.tag.count} image${data.tag.count !== 1 ? 's' : ''}</div>
            </div>
            <div class="detail-group">
                <div class="detail-label">Sample Images</div>
                <div class="sample-images-grid">
                    ${data.sample_images.map(img => `
                        <div class="sample-image">
                            <img src="/static/${img.thumb.startsWith('thumbnails/') || img.thumb.startsWith('images/') ? img.thumb : 'images/' + img.thumb}" alt="">
                        </div>
                    `).join('')}
                </div>
            </div>
            <div class="detail-group">
                <div class="detail-label">Base Category</div>
                <div class="detail-value">
                    <span class="tag-category ${data.tag.base_category}">${data.tag.base_category || 'none'}</span>
                </div>
            </div>
            <div class="detail-group">
                <div class="detail-label">Extended Category</div>
                <div class="detail-value">${data.tag.extended_category || 'None'}</div>
            </div>
            <div class="detail-group">
                <button class="editor-btn editor-btn-primary" onclick="window.renameTag('${tagName}')">Rename</button>
            </div>
        `;
    } catch (error) {
        console.error('Failed to load tag detail:', error);
        detailContent.innerHTML = '<div class="loading-state">Error loading tag detail</div>';
    }
}

// Search Images
async function searchImages() {
    const query = document.getElementById('imageSearchInput').value.trim();
    if (!query) {
        showNotification('Please enter a search query', 'warning');
        return;
    }

    state.images.searchQuery = query;
    state.images.offset = 0; // Reset pagination
    const infoState = document.getElementById('imageInfoState');
    const imageGrid = document.getElementById('imageGrid');

    infoState.textContent = 'Searching...';
    imageGrid.innerHTML = '';

    try {
        // Use configurable limit from state
        const limit = state.images.limit || 50;
        const response = await fetch(`/api/images?query=${encodeURIComponent(query)}&offset=${state.images.offset}&limit=${limit}`);
        const data = await response.json();

        state.images.data = data.images || [];

        if (state.images.data.length === 0) {
            infoState.textContent = 'No results found';
        } else {
            infoState.textContent = `Found ${state.images.data.length} image${state.images.data.length !== 1 ? 's' : ''}`;
            updateImageGrid();
        }
    } catch (error) {
        console.error('Failed to search images:', error);
        infoState.textContent = 'Error searching images';
        showNotification('Failed to search images', 'error');
    }
}

// Update Image Grid (optimized to avoid excessive re-renders)
function updateImageGrid() {
    const imageGrid = document.getElementById('imageGrid');

    // Only update if grid is empty or needs refresh
    if (imageGrid.children.length !== state.images.data.length) {
        imageGrid.innerHTML = '';

        state.images.data.forEach(image => {
            // Handle both API response format (with 'path' and 'thumb') and simple filepath
            const filepath = image.path || image.filepath || image;
            const thumbnailPath = image.thumb || filepath;

            const div = document.createElement('div');
            div.className = 'image-grid-item';
            div.dataset.filepath = filepath;

            div.innerHTML = `
                <img src="/${thumbnailPath}" alt="">
                <input type="checkbox" class="image-checkbox" data-filepath="${filepath}">
            `;

            const checkbox = div.querySelector('.image-checkbox');
            checkbox.addEventListener('change', (e) => {
                e.stopPropagation();
                const fp = e.target.dataset.filepath;
                if (e.target.checked) {
                    state.images.selected.add(fp);
                } else {
                    state.images.selected.delete(fp);
                }
                div.classList.toggle('selected', e.target.checked);
            });

            div.addEventListener('click', (e) => {
                if (e.target !== checkbox) {
                    checkbox.checked = !checkbox.checked;
                    checkbox.dispatchEvent(new Event('change', { bubbles: false }));
                }
            });

            imageGrid.appendChild(div);
        });
    }

    // Update checked states and selected class
    state.images.data.forEach(image => {
        const filepath = image.path || image.filepath || image;
        const div = imageGrid.querySelector(`[data-filepath="${filepath}"]`);
        if (div) {
            const checkbox = div.querySelector('.image-checkbox');
            const isSelected = state.images.selected.has(filepath);
            checkbox.checked = isSelected;
            div.classList.toggle('selected', isSelected);
        }
    });
}

// Add Selected Images to Working Set
function addSelectedToWorkingSet() {
    const selected = Array.from(state.images.selected);
    if (selected.length === 0) {
        showNotification('No images selected', 'warning');
        return;
    }

    // Add to working set, avoiding duplicates
    // Normalize filepaths by removing 'images/' prefix if present
    selected.forEach(filepath => {
        const normalizedPath = filepath.replace(/^images\//, '');
        if (!state.workingSet.images.includes(normalizedPath)) {
            state.workingSet.images.push(normalizedPath);
        }
    });

    state.workingSet.source = `search:${state.images.searchQuery}`;
    state.workingSet.createdAt = Date.now();

    saveWorkingSetToStorage();
    updateWorkingSetDisplay();

    showNotification(`Added ${selected.length} image${selected.length !== 1 ? 's' : ''} to working set`, 'success');

    // Clear selection
    state.images.selected.clear();
    updateImageGrid();
}

// Clear Working Set
function clearWorkingSet() {
    if (state.workingSet.images.length === 0) {
        return;
    }

    if (confirm('Clear all images from working set?')) {
        state.workingSet.images = [];
        state.workingSet.source = 'manual';
        state.workingSet.createdAt = Date.now();

        saveWorkingSetToStorage();
        updateWorkingSetDisplay();

        showNotification('Working set cleared', 'info');
    }
}

// Load Common Tags
async function loadCommonTags() {
    if (state.workingSet.images.length === 0) {
        document.getElementById('allTagsChips').innerHTML = '<span class="empty-state">No common tags</span>';
        document.getElementById('someTagsChips').innerHTML = '<span class="empty-state">No tags</span>';
        return;
    }

    try {
        const filepaths = state.workingSet.images.join(',');
        const response = await fetch(`/api/images/common_tags?filepaths=${encodeURIComponent(filepaths)}`);
        const data = await response.json();

        // Display ALL tags
        const allTagsChips = document.getElementById('allTagsChips');
        if (data.all.length === 0) {
            allTagsChips.innerHTML = '<span class="empty-state">No common tags</span>';
        } else {
            allTagsChips.innerHTML = data.all.map(tag => `
                <span class="tag-chip removable" onclick="queueTagForRemoval('${tag}')">
                    ${tag}<span class="tag-chip-remove">×</span>
                </span>
            `).join('');
        }

        // Display SOME tags
        const someTagsChips = document.getElementById('someTagsChips');
        if (data.some.length === 0) {
            someTagsChips.innerHTML = '<span class="empty-state">No tags</span>';
        } else {
            someTagsChips.innerHTML = data.some.slice(0, 20).map(item => `
                <span class="tag-chip" title="${item.count}/${state.workingSet.images.length} images (${item.percentage}%)">
                    ${item.tag} (${item.percentage}%)
                </span>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to load common tags:', error);
    }
}

// Add Tag to Queue
function addTagToQueue(type, tag) {
    const queueId = type === 'add' ? 'addTagQueue' : 'removeTagQueue';
    const queue = document.getElementById(queueId);

    const chip = document.createElement('span');
    chip.className = 'tag-chip removable';
    chip.dataset.tagName = tag; // Store tag name as data attribute
    chip.innerHTML = `${tag}<span class="tag-chip-remove" onclick="this.parentElement.remove()">×</span>`;
    queue.appendChild(chip);
}

// Queue Tag for Removal (called from template string)
window.queueTagForRemoval = function (tag) {
    addTagToQueue('remove', tag);
};

// Apply Bulk Add Tags
async function applyBulkAddTags() {
    const queue = document.getElementById('addTagQueue');
    const chips = queue.querySelectorAll('.tag-chip');
    const tags = Array.from(chips).map(chip => chip.dataset.tagName || chip.textContent.replace('×', '').trim());

    if (tags.length === 0) {
        showNotification('No tags to add', 'warning');
        return;
    }

    if (state.workingSet.images.length === 0) {
        showNotification('No images in working set', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/images/bulk_add_tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filepaths: state.workingSet.images,
                tags: tags
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        queue.innerHTML = '';
        loadCommonTags();
    } catch (error) {
        console.error('Failed to add tags:', error);
        showNotification('Failed to add tags', 'error');
    }
}

// Apply Bulk Remove Tags
async function applyBulkRemoveTags() {
    const queue = document.getElementById('removeTagQueue');
    const chips = queue.querySelectorAll('.tag-chip');
    const tags = Array.from(chips).map(chip => chip.dataset.tagName || chip.textContent.replace('×', '').trim());

    if (tags.length === 0) {
        showNotification('No tags to remove', 'warning');
        return;
    }

    if (state.workingSet.images.length === 0) {
        showNotification('No images in working set', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/images/bulk_remove_tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filepaths: state.workingSet.images,
                tags: tags
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        queue.innerHTML = '';
        loadCommonTags();
    } catch (error) {
        console.error('Failed to remove tags:', error);
        showNotification('Failed to remove tags', 'error');
    }
}

// Bulk Categorize
async function bulkCategorize() {
    const baseCategory = document.getElementById('bulkBaseCategorySelect').value;
    const extendedCategory = document.getElementById('bulkExtendedCategoryInput').value.trim();

    if (!baseCategory && !extendedCategory) {
        showNotification('Please select a base category or enter an extended category', 'warning');
        return;
    }

    if (state.tags.selected.size === 0) {
        showNotification('No tags selected', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/tags/bulk_categorize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tag_names: Array.from(state.tags.selected),
                base_category: baseCategory,
                extended_category: extendedCategory
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        state.tags.selected.clear();
        loadTags();
    } catch (error) {
        console.error('Failed to categorize tags:', error);
        showNotification('Failed to categorize tags', 'error');
    }
}

// Show Merge Modal
function showMergeModal() {
    if (state.tags.selected.size < 2) {
        showNotification('Select at least 2 tags to merge', 'warning');
        return;
    }

    const modal = document.getElementById('mergeModal');
    const tagsList = document.getElementById('mergeTagsList');
    const targetSelect = document.getElementById('mergeTargetSelect');

    tagsList.innerHTML = Array.from(state.tags.selected).map(tag =>
        `<div>• ${tag}</div>`
    ).join('');

    targetSelect.innerHTML = Array.from(state.tags.selected).map(tag =>
        `<option value="${tag}">${tag}</option>`
    ).join('');

    modal.style.display = 'flex';
}

// Confirm Merge
async function confirmMerge() {
    const targetTag = document.getElementById('mergeTargetSelect').value;
    const createAliases = document.getElementById('mergeCreateAliases').checked;

    try {
        const response = await fetch('/api/tags/merge', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_tags: Array.from(state.tags.selected),
                target_tag: targetTag,
                create_aliases: createAliases
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        window.closeModal('mergeModal');
        state.tags.selected.clear();
        loadTags();
    } catch (error) {
        console.error('Failed to merge tags:', error);
        showNotification('Failed to merge tags', 'error');
    }
}

// Show Delete Modal
function showDeleteModal() {
    if (state.tags.selected.size === 0) {
        showNotification('No tags selected', 'warning');
        return;
    }

    const modal = document.getElementById('deleteModal');
    const tagsList = document.getElementById('deleteTagsList');

    tagsList.innerHTML = Array.from(state.tags.selected).map(tag =>
        `<div>• ${tag}</div>`
    ).join('');

    modal.style.display = 'flex';
}

// Confirm Delete
async function confirmDelete() {
    const removeFromImages = document.getElementById('deleteRemoveFromImages').checked;

    try {
        const response = await fetch('/api/tags/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tag_names: Array.from(state.tags.selected),
                remove_from_images: removeFromImages
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        window.closeModal('deleteModal');
        state.tags.selected.clear();
        loadTags();
    } catch (error) {
        console.error('Failed to delete tags:', error);
        showNotification('Failed to delete tags', 'error');
    }
}

// Rename Tag (exposed to window for template string)
window.renameTag = function (tagName) {
    const modal = document.getElementById('renameModal');
    document.getElementById('renameCurrentName').textContent = tagName;
    document.getElementById('renameNewName').value = '';
    modal.style.display = 'flex';
};

// Confirm Rename
async function confirmRename() {
    const oldName = document.getElementById('renameCurrentName').textContent;
    const newName = document.getElementById('renameNewName').value.trim();
    const createAlias = document.getElementById('renameCreateAlias').checked;

    if (!newName) {
        showNotification('Please enter a new name', 'warning');
        return;
    }

    try {
        const response = await fetch('/api/tags/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_name: oldName,
                new_name: newName,
                create_alias: createAlias
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        window.closeModal('renameModal');
        loadTags();
        if (state.currentTag === oldName) {
            loadTagDetail(newName);
        }
    } catch (error) {
        console.error('Failed to rename tag:', error);
        showNotification('Failed to rename tag', 'error');
    }
}

// Load Stats
async function loadStats() {
    const statsContainer = document.getElementById('statsContainer');
    statsContainer.innerHTML = '<div class="loading-state">Loading statistics...</div>';

    try {
        const response = await fetch('/api/tags/stats');
        const data = await response.json();

        statsContainer.innerHTML = `
            <div class="stats-overview">
                <div class="stat-card">
                    <div class="stat-card-label">Total Tags</div>
                    <div class="stat-card-value">${data.overview.total_tags.toLocaleString()}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">Total Images</div>
                    <div class="stat-card-value">${data.overview.total_images.toLocaleString()}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">Categorized</div>
                    <div class="stat-card-value">${data.overview.categorized.toLocaleString()}</div>
                    <div class="stat-card-sub">${data.overview.categorized_percentage}%</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">Uncategorized</div>
                    <div class="stat-card-value">${data.overview.uncategorized.toLocaleString()}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">Avg Tags/Image</div>
                    <div class="stat-card-value">${data.overview.avg_tags_per_image}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-card-label">Orphaned Tags</div>
                    <div class="stat-card-value">${data.overview.orphaned.toLocaleString()}</div>
                </div>
            </div>
            
            <div class="stat-section">
                <h3>By Base Category</h3>
                <div class="category-breakdown">
                    ${Object.entries(data.by_base_category || {}).map(([cat, count]) => `
                        <div class="category-item">
                            <span class="tag-category ${cat}">${cat}</span>
                            <span>${count.toLocaleString()}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="stat-section">
                <h3>Top Tags</h3>
                <div class="top-tags-list">
                    ${data.top_tags.map((tag, i) => `
                        <div class="top-tag-item">
                            <span>${i + 1}. ${tag.name}</span>
                            <span>${tag.count.toLocaleString()}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Failed to load stats:', error);
        statsContainer.innerHTML = '<div class="loading-state">Error loading statistics</div>';
    }
}

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

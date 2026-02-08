// Tag Implications Manager JavaScript - Redesigned
import { showSuccess, showError, showInfo } from './utils/notifications.js';

// State management
let selectedTag = null;
let selectedImplication = null;
let selectedSuggestions = new Set();
let selectedActive = new Set();
let viewMode = 'all'; // 'all', 'suggestions', 'active'
let filterQuery = '';
let typeFilters = new Set(['all']);
let sourceCategoryFilters = new Set(['all']);
let impliedCategoryFilters = new Set(['all']);
let allImplications = { suggestions: [], active: [] };

// Pagination state
let paginationState = {
    currentPage: 1,
    totalPages: 1,
    totalSuggestions: 0,
    hasMore: false,
    isLoading: false,
    limit: 50
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    initializeTagSearch();
    initializeViewModeToggle();
    initializeTypeFilters();
    initializeCategoryFilters();
    // initializeCollapsibleSections(); // Using inline handlers now
    initializeBulkActions();
    initializeFilterInput();
    initializeClearActions();
    initializeManualCreation();
    initializeKeyboardShortcuts();

    // Load initial data
    loadAllSuggestions();
});

// Tag Search with Autocomplete
function initializeTagSearch() {
    const searchInput = document.getElementById('tagSearchInput');
    const dropdown = document.getElementById('tagSearchDropdown');
    let searchTimeout;

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();

        clearTimeout(searchTimeout);

        if (query.length < 2) {
            dropdown.classList.remove('active');
            return;
        }

        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/autocomplete?q=${encodeURIComponent(query)}&limit=10`);
                const data = await response.json();

                // Extract tags from groups
                let tags = [];
                if (data.groups && data.groups.length > 0) {
                    const tagGroup = data.groups.find(g => g.name === 'Tags');
                    if (tagGroup && tagGroup.items) {
                        tags = tagGroup.items.map(item => ({
                            name: item.tag || item.label,
                            category: item.category || 'general'
                        }));
                    }
                }

                if (tags.length > 0) {
                    dropdown.innerHTML = tags.map(tag => `
                        <div class="autocomplete-item" data-tag="${tag.name}">
                            <span class="tag-badge ${tag.category}">${tag.name}</span>
                        </div>
                    `).join('');
                    dropdown.classList.add('active');

                    // Add click handlers
                    dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
                        item.addEventListener('click', () => {
                            selectTag(item.dataset.tag);
                            dropdown.classList.remove('active');
                            searchInput.value = '';
                        });
                    });
                } else {
                    dropdown.classList.remove('active');
                }
            } catch (error) {
                console.error('Error fetching tag suggestions:', error);
            }
        }, 300);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });
}

// Select a tag and load its implications
async function selectTag(tagName) {
    try {
        const response = await fetch(`/api/implications/for-tag/${encodeURIComponent(tagName)}`);
        const data = await response.json();

        selectedTag = data.tag;

        if (!selectedTag) {
            showError(`Tag "${tagName}" not found`);
            return;
        }

        // Update selected tag info
        const infoSection = document.getElementById('selectedTagInfo');
        const badge = document.getElementById('selectedTagBadge');
        const impliesCount = document.getElementById('impliesCount');
        const impliedByCount = document.getElementById('impliedByCount');

        badge.textContent = selectedTag.name;
        badge.className = `tag-badge ${selectedTag.category}`;
        impliesCount.textContent = data.implies.length;
        impliedByCount.textContent = data.implied_by.length;
        infoSection.style.display = 'block';

        // Store implications for this tag
        allImplications.suggestions = data.suggestions;
        allImplications.active = [...data.implies, ...data.implied_by];

        renderImplications();
        showInfo(`Loaded implications for "${tagName}"`);
    } catch (error) {
        console.error('Error loading tag implications:', error);
        showError('Failed to load tag implications');
    }
}

// View Mode Toggle
function initializeViewModeToggle() {
    const toggleButtons = document.querySelectorAll('.view-mode-toggle .toggle-btn');

    toggleButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            toggleButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            viewMode = btn.dataset.mode;
            renderImplications();
        });
    });
}

// Type Filters
function initializeTypeFilters() {
    const checkboxes = document.querySelectorAll('input[name="typeFilter"]');

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            const value = checkbox.value;

            if (value === 'all') {
                if (checkbox.checked) {
                    typeFilters.clear();
                    typeFilters.add('all');
                    checkboxes.forEach(cb => {
                        if (cb.value !== 'all') cb.checked = false;
                    });
                }
            } else {
                typeFilters.delete('all');
                document.querySelector('input[name="typeFilter"][value="all"]').checked = false;

                if (checkbox.checked) {
                    typeFilters.add(value);
                } else {
                    typeFilters.delete(value);
                }

                if (typeFilters.size === 0) {
                    typeFilters.add('all');
                    document.querySelector('input[name="typeFilter"][value="all"]').checked = true;
                }
            }

            // Reload data from server with new filters
            loadAllSuggestions();
        });
    });
}

// Category Filters
function initializeCategoryFilters() {
    // Source category filters
    const sourceCheckboxes = document.querySelectorAll('input[name="sourceCategoryFilter"]');
    sourceCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            handleCategoryFilterChange(checkbox, sourceCategoryFilters, sourceCheckboxes, 'sourceCategoryFilter');
        });
    });

    // Implied category filters
    const impliedCheckboxes = document.querySelectorAll('input[name="impliedCategoryFilter"]');
    impliedCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            handleCategoryFilterChange(checkbox, impliedCategoryFilters, impliedCheckboxes, 'impliedCategoryFilter');
        });
    });
}

function handleCategoryFilterChange(checkbox, filterSet, allCheckboxes, filterName) {
    const value = checkbox.value;

    if (value === 'all') {
        if (checkbox.checked) {
            filterSet.clear();
            filterSet.add('all');
            allCheckboxes.forEach(cb => {
                if (cb.value !== 'all') cb.checked = false;
            });
        }
    } else {
        filterSet.delete('all');
        document.querySelector(`input[name="${filterName}"][value="all"]`).checked = false;

        if (checkbox.checked) {
            filterSet.add(value);
        } else {
            filterSet.delete(value);
        }

        if (filterSet.size === 0) {
            filterSet.add('all');
            document.querySelector(`input[name="${filterName}"][value="all"]`).checked = true;
        }
    }

    // Reload data from server with new filters
    loadAllSuggestions();
}

// Collapsible Sections - Handled inline in HTML
/*
function initializeCollapsibleSections() {
    document.querySelectorAll('.collapsible-header, .section-header').forEach(header => {
        header.addEventListener('click', (e) => {
            // Prevent checkbox clicks from triggering collapse
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'LABEL') {
                return;
            }
            
            const target = header.dataset.target;
            if (target) {
                const content = document.getElementById(target);
                if (content) {
                    header.classList.toggle('collapsed');
                    content.classList.toggle('collapsed');
                }
            }
        });
    });
}
*/

// Bulk Actions
function initializeBulkActions() {
    const selectAllCheckbox = document.getElementById('selectAllSuggestions');
    const selectAllActiveCheckbox = document.getElementById('selectAllActive');
    const bulkApproveBtn = document.getElementById('bulkApproveBtn');
    const bulkDismissBtn = document.getElementById('bulkDismissBtn');
    const clearSelectionBtn = document.getElementById('clearSelectionBtn');

    // Suggestions Select All
    selectAllCheckbox?.addEventListener('change', (e) => {
        const checkboxes = document.querySelectorAll('.implication-checkbox[data-group="suggestion"]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const item = cb.closest('.implication-item');
            if (e.target.checked) {
                selectedSuggestions.add(item.dataset.id);
                item.classList.add('selected');
            } else {
                selectedSuggestions.delete(item.dataset.id);
                item.classList.remove('selected');
            }
        });
        updateBulkActionsBar();
    });

    // Active Implications Select All (Visible Only)
    selectAllActiveCheckbox?.addEventListener('change', (e) => {
        // Only select currently visible active implication checkboxes
        const checkboxes = document.querySelectorAll('.implication-checkbox[data-group="active"]');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const item = cb.closest('.implication-item');
            if (e.target.checked) {
                selectedActive.add(item.dataset.id);
                item.classList.add('selected');
            } else {
                selectedActive.delete(item.dataset.id);
                item.classList.remove('selected');
            }
        });
        updateBulkActionsBar();
    });

    bulkApproveBtn?.addEventListener('click', bulkApprove);
    bulkDismissBtn?.addEventListener('click', bulkDismissOrDelete);
    clearSelectionBtn?.addEventListener('click', clearSelection);
}

function toggleSuggestionSelection(suggestionId, checkbox) {
    const item = checkbox.closest('.implication-item');

    if (checkbox.checked) {
        selectedSuggestions.add(suggestionId);
        item.classList.add('selected');
    } else {
        selectedSuggestions.delete(suggestionId);
        item.classList.remove('selected');
    }

    updateBulkActionsBar();
}

function updateBulkActionsBar() {
    const bar = document.getElementById('bulkActionsBar');
    const count = document.getElementById('selectionCount');

    const totalSelected = selectedSuggestions.size + selectedActive.size;

    if (totalSelected > 0) {
        bar.style.display = 'flex';
        count.textContent = `${totalSelected} selected`;

        // Show/Hide buttons based on selection type
        const approveBtn = document.getElementById('bulkApproveBtn');
        const dismissBtn = document.getElementById('bulkDismissBtn');

        if (selectedSuggestions.size > 0 && selectedActive.size === 0) {
            approveBtn.style.display = 'block';
            dismissBtn.textContent = 'Dismiss All';
            dismissBtn.classList.remove('action-btn-danger');
            dismissBtn.classList.add('action-btn-warning');
        } else if (selectedSuggestions.size === 0 && selectedActive.size > 0) {
            approveBtn.style.display = 'none';
            dismissBtn.textContent = 'Delete Selected';
            dismissBtn.classList.remove('action-btn-warning');
            dismissBtn.classList.add('action-btn-danger');
        } else {
            // Mixed selection ? Usually avoid, but if happens:
            approveBtn.style.display = 'block';
            dismissBtn.textContent = 'Dismiss/Delete All';
        }

    } else {
        bar.style.display = 'none';
    }
}

async function bulkApprove() {
    if (selectedSuggestions.size === 0) {
        showInfo('No suggestions selected');
        return;
    }

    const suggestions = Array.from(selectedSuggestions).map(id => {
        const item = document.querySelector(`[data-id="${id}"]`);
        return {
            source_tag: item.dataset.source,
            implied_tag: item.dataset.implied,
            inference_type: item.dataset.type,
            confidence: parseFloat(item.dataset.confidence)
        };
    });

    try {
        const response = await fetch('/api/implications/bulk-approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ suggestions })
        });

        const result = await response.json();

        showSuccess(`Approved ${result.success_count} of ${result.total} suggestions`);

        if (result.errors.length > 0) {
            console.error('Bulk approve errors:', result.errors);
        }

        clearSelection();

        // Reload implications
        if (selectedTag) {
            selectTag(selectedTag.name);
        } else {
            loadAllSuggestions();
        }
    } catch (error) {
        console.error('Error bulk approving:', error);
        showError('Failed to approve suggestions');
    }
}

// Helper for individual selection toggling
window.toggleActiveSelection = function (id, checkbox) {
    const item = checkbox.closest('.implication-item');

    if (checkbox.checked) {
        selectedActive.add(id);
        item.classList.add('selected');
    } else {
        selectedActive.delete(id);
        item.classList.remove('selected');
    }

    updateBulkActionsBar();
};

async function bulkDismissOrDelete() {
    // If we have selected suggestions, dismiss them
    if (selectedSuggestions.size > 0) {
        await bulkDismiss();
    }

    // If we have selected active implications, delete them
    if (selectedActive.size > 0) {
        await bulkDeleteActive();
    }
}

async function bulkDeleteActive() {
    if (!confirm(`Are you sure you want to delete ${selectedActive.size} active implications?`)) {
        return;
    }

    let deletedCount = 0;
    const errors = [];

    // We implement this by calling individual delete endpoints for now since we didn't add a bulk-delete endpoint
    // Or we could add one. For now, sequential calls are acceptable if not too many, 
    // but better to add a bulk endpoint if we expect many. Given the task scope, let's try to stick to existing tools first
    // but a loop is fine for "Select All" of reasonable size.
    // Actually, "Select All" might select thousands. We should add a bulk delete endpoint properly or batch it.
    // For now, let's implement a client-side loop but with parallel requests (semaphore limited) or sequential.

    // Collecting data
    const toDelete = [];
    selectedActive.forEach(id => {
        const item = document.querySelector(`[data-id="${id}"]`);
        if (item) {
            toDelete.push({
                source_tag: item.dataset.source,
                implied_tag: item.dataset.implied
            });
        }
    });

    for (const impl of toDelete) {
        try {
            const response = await fetch('/api/implications/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(impl)
            });
            if (response.ok) {
                deletedCount++;
                // Remove from UI immediately
                const item = document.querySelector(`.implication-item[data-source="${impl.source_tag}"][data-implied="${impl.implied_tag}"]`);
                if (item) item.remove();
            } else {
                errors.push(`${impl.source_tag}->${impl.implied_tag}`);
            }
        } catch (e) {
            errors.push(`${impl.source_tag}->${impl.implied_tag}`);
        }
    }

    if (deletedCount > 0) {
        showSuccess(`Deleted ${deletedCount} implications`);
    }
    if (errors.length > 0) {
        showError(`Failed to delete ${errors.length} implications`);
    }

    // Determine if we need to reload or just clear selection
    // Since we removed from DOM, we can just clear selection state
    selectedActive.clear();
    const activeHeaderCheckbox = document.getElementById('selectAllActive');
    if (activeHeaderCheckbox) activeHeaderCheckbox.checked = false;
    updateBulkActionsBar();
}

async function bulkDismiss() {
    const suggestionsToDismiss = Array.from(selectedSuggestions);

    suggestionsToDismiss.forEach(id => {
        const item = document.querySelector(`[data-id="${id}"]`);
        if (item) item.remove();
    });

    showSuccess(`Dismissed ${suggestionsToDismiss.length} suggestions`);
    selectedSuggestions.clear();
    const suggestionHeaderCheckbox = document.getElementById('selectAllSuggestions');
    if (suggestionHeaderCheckbox) suggestionHeaderCheckbox.checked = false;
    updateBulkActionsBar();
}

function clearSelection() {
    selectedSuggestions.clear();
    selectedActive.clear();
    document.querySelectorAll('.implication-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.implication-item').forEach(item => item.classList.remove('selected'));

    const s1 = document.getElementById('selectAllSuggestions');
    if (s1) s1.checked = false;
    const s2 = document.getElementById('selectAllActive');
    if (s2) s2.checked = false;

    updateBulkActionsBar();
}

// Helper to build filter query string
function getFilterQueryString() {
    const params = new URLSearchParams();

    // Type filters
    if (!typeFilters.has('all')) {
        // Find which one is selected
        for (const type of typeFilters) {
            params.append('type', type);
        }
    }

    // Source Category filters
    if (!sourceCategoryFilters.has('all')) {
        for (const cat of sourceCategoryFilters) {
            params.append('source_categories[]', cat); // Use [] convention for arrays
        }
    }

    // Implied Category filters
    for (const cat of impliedCategoryFilters) {
        params.append('implied_categories[]', cat);
    }

    if (filterQuery) {
        params.append('q', filterQuery);
    }

    return params.toString();
}

// Filter Input
function initializeFilterInput() {
    const input = document.getElementById('filterInput');
    let timeout;

    input?.addEventListener('input', (e) => {
        const query = e.target.value.trim().toLowerCase();

        clearTimeout(timeout);
        timeout = setTimeout(() => {
            filterQuery = query;

            // For suggestions, we reload from server to get paginated results with filter
            loadAllSuggestions();
            // Active implications are filtered client-side (unless we decide to move that to server too)
        }, 300);
    });
}

// Clear Actions
function initializeClearActions() {
    const clearAllBtn = document.getElementById('clearAllBtn');
    const modal = document.getElementById('clearAllRulesModal');
    const cancelBtn = document.getElementById('clearAllRulesCancelBtn');
    const submitBtn = document.getElementById('clearAllRulesSubmitBtn');
    const closeBtn = modal?.querySelector('.close');

    clearAllBtn?.addEventListener('click', () => {
        modal.style.display = 'block';
    });

    cancelBtn?.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    closeBtn?.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    submitBtn?.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/implications/delete-all', {
                method: 'POST'
            });
            const result = await response.json();

            showSuccess(`Deleted ${result.count} implication rules`);
            modal.style.display = 'none';

            // Reload everything
            loadAllSuggestions();

        } catch (error) {
            console.error('Error clearing all rules:', error);
            showError('Failed to clear rules');
        }
    });

    // existing clear implied tags logic ...
    const clearImpliedBtn = document.getElementById('clearImpliedTagsBtn');
    // ... rest is likely handled by inline onclicks or existing code if present, 
    // but the button ID in HTML shows 'clearImpliedTagsBtn' which wasn't in original JS init?
    // Let's check if it was initialized elsewhere. 
    // Ah, previous file content didn't show specific init for it, maybe it was missing or I missed it.
    // The HTML has id="clearImpliedTagsBtn".

    const clearImpliedModal = document.getElementById('clearImpliedModal');
    if (clearImpliedBtn && clearImpliedModal) {
        clearImpliedBtn.addEventListener('click', () => clearImpliedModal.style.display = 'block');
        document.getElementById('clearImpliedCancelBtn')?.addEventListener('click', () => clearImpliedModal.style.display = 'none');
        clearImpliedModal.querySelector('.close')?.addEventListener('click', () => clearImpliedModal.style.display = 'none');

        document.getElementById('clearImpliedSubmitBtn')?.addEventListener('click', async () => {
            const reapply = document.getElementById('clearImpliedReapplyCheckbox').checked;
            try {
                let url = reapply ? '/api/implications/clear-and-reapply' : '/api/implications/clear-tags';
                showInfo('Processing... this may take a while');

                const response = await fetch(url, { method: 'POST' });
                const result = await response.json();

                showSuccess(result.message);
                clearImpliedModal.style.display = 'none';
            } catch (e) {
                showError('Operation failed');
            }
        });
    }
}

// Load suggestions with pagination (first page)
async function loadAllSuggestions() {
    try {
        // Reset pagination state
        paginationState.currentPage = 1;
        paginationState.isLoading = true;

        // Show loading state in UI
        const listEl = document.getElementById('suggestionsList');
        if (listEl) listEl.innerHTML = '<div class="loading-message">Loading suggestions...</div>';

        const queryString = getFilterQueryString();
        const response = await fetch(`/api/implications/suggestions?page=1&limit=${paginationState.limit}&${queryString}`);
        const data = await response.json();

        // Update pagination state from response
        paginationState.currentPage = data.page;
        paginationState.totalPages = data.total_pages;
        paginationState.totalSuggestions = data.total;
        paginationState.hasMore = data.has_more;
        paginationState.isLoading = false;

        // Store suggestions (already flat list from new API)
        allImplications.suggestions = data.suggestions;

        // Also load all active implications (only if not already loaded or if we want to refresh them too)
        // For active ones, we usually load once. But if we want to support filtering active ones server-side later we could.
        // For now, active implications are small enough to keep client-side or we can leave as is.
        // Let's assume active implications are still fetched all at once for now as per original code.
        if (allImplications.active.length === 0) {
            const activeResponse = await fetch('/api/implications/all');
            const activeData = await activeResponse.json();
            allImplications.active = activeData.implications;
        }

        renderImplications(true); // Pass true to indicate suggestions are already filtered
    } catch (error) {
        console.error('Error loading suggestions:', error);
        showError('Failed to load suggestions');
        paginationState.isLoading = false;
    }
}

// Load more suggestions (next page)
async function loadMoreSuggestions() {
    if (paginationState.isLoading || !paginationState.hasMore) {
        return;
    }

    try {
        paginationState.isLoading = true;
        updateLoadMoreButton();

        const nextPage = paginationState.currentPage + 1;
        const queryString = getFilterQueryString();
        const response = await fetch(`/api/implications/suggestions?page=${nextPage}&limit=${paginationState.limit}&${queryString}`);
        const data = await response.json();

        // Update pagination state
        paginationState.currentPage = data.page;
        paginationState.totalPages = data.total_pages;
        paginationState.hasMore = data.has_more;
        paginationState.isLoading = false;

        // Append new suggestions to existing list
        allImplications.suggestions = [...allImplications.suggestions, ...data.suggestions];

        renderImplications(true);
    } catch (error) {
        console.error('Error loading more suggestions:', error);
        showError('Failed to load more suggestions');
        paginationState.isLoading = false;
        updateLoadMoreButton();
    }
}

// Update load more button state
function updateLoadMoreButton() {
    const btn = document.getElementById('loadMoreBtn');
    if (!btn) return;

    if (paginationState.isLoading) {
        btn.textContent = 'Loading...';
        btn.disabled = true;
    } else if (paginationState.hasMore) {
        btn.textContent = `Load More (${allImplications.suggestions.length} of ${paginationState.totalSuggestions})`;
        btn.disabled = false;
    } else {
        btn.textContent = `All ${paginationState.totalSuggestions} suggestions loaded`;
        btn.disabled = true;
    }
}

// Expose loadMoreSuggestions globally
window.loadMoreSuggestions = loadMoreSuggestions;

// Render implications based on current filters
function renderImplications(skipSuggestionFiltering = false) {
    // If suggestions come from server already filtered, use them as is (or filter defensively but careful not to double filter if logic differed)
    // Since we reuse filterImplications logic on server which is 1:1, it's safe to re-filter, 
    // BUT we want to avoid hiding things if the client state is slightly out of sync or if we just want to show what server gave.
    // However, for pagination consistency, we should trust the server's return.
    let suggestions = skipSuggestionFiltering ?
        allImplications.suggestions :
        filterImplications(allImplications.suggestions, true);

    let active = filterImplications(allImplications.active, false);

    // Apply view mode
    if (viewMode === 'suggestions') {
        active = [];
    } else if (viewMode === 'active') {
        suggestions = [];
    }

    // Update counts - show loaded vs total for suggestions
    const suggestionsCountText = paginationState.totalSuggestions > 0
        ? `${suggestions.length} of ${paginationState.totalSuggestions}`
        : suggestions.length;
    document.getElementById('suggestionsBadge').textContent = suggestionsCountText;
    document.getElementById('activeBadge').textContent = active.length;

    const totalShown = suggestions.length + active.length;
    const totalAvailable = paginationState.totalSuggestions + active.length;
    document.getElementById('headerCount').textContent = paginationState.hasMore
        ? `Showing ${totalShown} of ${totalAvailable} implications`
        : `Showing ${totalShown} implications`;

    // Render lists
    renderSuggestionsList(suggestions);
    renderActiveList(active);
}

function filterImplications(implications, isSuggestion) {
    return implications.filter(impl => {
        // Text query filter (client-side for active implications)
        if (!isSuggestion && filterQuery) {
            const source = impl.source_tag.toLowerCase();
            const implied = impl.implied_tag.toLowerCase();
            if (!source.includes(filterQuery) && !implied.includes(filterQuery)) {
                return false;
            }
        }

        // Type filter
        const type = isSuggestion ? impl.pattern_type : impl.inference_type;
        if (!typeFilters.has('all') && !typeFilters.has(type)) {
            return false;
        }

        // Source category filter
        const sourceCategory = impl.source_category || 'general';
        if (!sourceCategoryFilters.has('all')) {
            // Check for exclusions (values starting with !)
            for (const filter of sourceCategoryFilters) {
                if (filter.startsWith('!') && sourceCategory === filter.slice(1)) {
                    return false;
                }
            }
            // Check for inclusions
            const inclusions = [...sourceCategoryFilters].filter(f => !f.startsWith('!'));
            if (inclusions.length > 0 && !inclusions.includes(sourceCategory)) {
                return false;
            }
        }

        // Implied category filter
        const impliedCategory = impl.implied_category || 'general';
        if (!impliedCategoryFilters.has('all')) {
            // Check for exclusions (values starting with !)
            for (const filter of impliedCategoryFilters) {
                if (filter.startsWith('!') && impliedCategory === filter.slice(1)) {
                    return false;
                }
            }
            // Check for inclusions
            const inclusions = [...impliedCategoryFilters].filter(f => !f.startsWith('!'));
            if (inclusions.length > 0 && !inclusions.includes(impliedCategory)) {
                return false;
            }
        }

        return true;
    });
}

function renderSuggestionsList(suggestions) {
    const listEl = document.getElementById('suggestionsList');

    if (suggestions.length === 0) {
        listEl.innerHTML = '<div class="loading-message">No suggestions found</div>';
        return;
    }

    listEl.innerHTML = suggestions.map((s, idx) => {
        const id = `suggestion-${idx}`;
        const confidence = s.confidence || 0.9;
        const confidencePercent = Math.round(confidence * 100);
        const confidenceClass = confidence >= 0.9 ? 'high' : confidence >= 0.7 ? 'medium' : '';

        return `
            <div class="implication-item" 
                 data-id="${id}"
                 data-source="${s.source_tag}"
                 data-implied="${s.implied_tag}"
                 data-type="${s.pattern_type}"
                 data-confidence="${confidence}">
                <input type="checkbox" class="implication-checkbox" data-group="suggestion" onchange="window.toggleSuggestionSelection('${id}', this)">
                <div class="implication-flow">
                    <span class="tag-badge">${s.source_tag}</span>
                    <span class="flow-arrow">→</span>
                    <span class="tag-badge">${s.implied_tag}</span>
                </div>
                <span class="type-badge">${s.pattern_type.replace('_', ' ')}</span>
                <div class="confidence-meter">
                    <div class="confidence-bar">
                        <div class="confidence-fill ${confidenceClass}" style="width: ${confidencePercent}%"></div>
                    </div>
                    <span class="confidence-percentage">${confidencePercent}%</span>
                </div>
                <div class="implication-actions">
                    <button class="icon-btn approve-icon-btn" onclick="window.approveSingle('${id}')" title="Approve">✓</button>
                    <button class="icon-btn dismiss-icon-btn" onclick="window.dismissSingle('${id}')" title="Dismiss">✗</button>
                </div>
            </div>
        `;
    }).join('');

    // Add Load More button if there are more suggestions to load
    if (paginationState.hasMore && !selectedTag) {
        const loadMoreHtml = `
            <div class="load-more-container">
                <button id="loadMoreBtn" class="load-more-btn" onclick="window.loadMoreSuggestions()">
                    Load More (${allImplications.suggestions.length} of ${paginationState.totalSuggestions})
                </button>
            </div>
        `;
        listEl.insertAdjacentHTML('beforeend', loadMoreHtml);
    } else if (!paginationState.hasMore && paginationState.totalSuggestions > paginationState.limit) {
        // Show "all loaded" message if we've loaded everything
        const allLoadedHtml = `
            <div class="load-more-container">
                <span class="all-loaded-message">All ${paginationState.totalSuggestions} suggestions loaded</span>
            </div>
        `;
        listEl.insertAdjacentHTML('beforeend', allLoadedHtml);
    }

    // Add click handlers to items
    listEl.querySelectorAll('.implication-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.implication-checkbox') && !e.target.closest('.implication-actions')) {
                selectImplication(item.dataset.id, true);
            }
        });
    });
}

function renderActiveList(active) {
    const listEl = document.getElementById('activeList');

    if (active.length === 0) {
        listEl.innerHTML = '<div class="loading-message">No active implications</div>';
        return;
    }

    listEl.innerHTML = active.map((impl, idx) => {
        const id = `active-${idx}`;
        const sourceTag = impl.source_tag;
        const impliedTag = impl.implied_tag;
        const sourceCategory = impl.source_category || 'general';
        const impliedCategory = impl.implied_category || impl.implied_category || 'general';
        const confidence = impl.confidence || 1.0;
        const confidencePercent = Math.round(confidence * 100);
        const confidenceClass = confidence >= 0.9 ? 'high' : confidence >= 0.7 ? 'medium' : '';

        return `
            <div class="implication-item" 
                 data-id="${id}"
                 data-source="${sourceTag}"
                 data-implied="${impliedTag}"
                 data-type="${impl.inference_type}">
                 <input type="checkbox" class="implication-checkbox" data-group="active" onchange="window.toggleActiveSelection('${id}', this)">
                <div class="implication-flow">
                    <span class="tag-badge ${sourceCategory}">${sourceTag}</span>
                    <span class="flow-arrow">→</span>
                    <span class="tag-badge ${impliedCategory}">${impliedTag}</span>
                </div>
                <span class="type-badge">${impl.inference_type}</span>
                <div class="confidence-meter">
                    <div class="confidence-bar">
                        <div class="confidence-fill ${confidenceClass}" style="width: ${confidencePercent}%"></div>
                    </div>
                    <span class="confidence-percentage">${confidencePercent}%</span>
                </div>
                <div class="implication-actions">
                    <button class="icon-btn chain-icon-btn" onclick="window.viewChain('${sourceTag}')" title="View Chain">🔗</button>
                    <button class="icon-btn delete-icon-btn" onclick="window.deleteImplication('${sourceTag}', '${impliedTag}')" title="Delete">🗑️</button>
                </div>
            </div>
        `;
    }).join('');

    // Add click handlers to items
    listEl.querySelectorAll('.implication-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.implication-actions')) {
                selectImplication(item.dataset.id, false);
            }
        });
    });
}

// Select an implication to show in detail panel
async function selectImplication(itemId, isSuggestion) {
    const item = document.querySelector(`[data - id= "${itemId}"]`);
    if (!item) return;

    const sourceTag = item.dataset.source;
    const impliedTag = item.dataset.implied;
    const type = item.dataset.type;

    selectedImplication = {
        id: itemId,
        source_tag: sourceTag,
        implied_tag: impliedTag,
        type: type,
        isSuggestion: isSuggestion,
        confidence: parseFloat(item.dataset.confidence || 1.0)
    };

    await renderDetailPanel();
}

async function renderDetailPanel() {
    const panel = document.getElementById('detailPanel');

    if (!selectedImplication) {
        panel.innerHTML = `
            < div class="detail-placeholder" >
                <div class="placeholder-icon">📋</div>
                <p>No implication selected</p>
                <p class="placeholder-hint">Click on an implication to view details</p>
            </div >
            `;
        return;
    }

    const { source_tag, implied_tag, type, isSuggestion, confidence } = selectedImplication;
    const confidencePercent = Math.round(confidence * 100);

    // Fetch chain and impact data
    let chainHtml = '';
    let impactHtml = '';

    try {
        const chainResponse = await fetch(`/ api / implications / chain / ${encodeURIComponent(implied_tag)} `);
        const chain = await chainResponse.json();
        chainHtml = renderChainTree(chain);

        if (isSuggestion) {
            const previewResponse = await fetch('/api/implications/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_tag, implied_tag })
            });
            const preview = await previewResponse.json();
            impactHtml = `
            < div class="detail-section" >
                    <div class="detail-section-title">Impact</div>
                    <div class="detail-section-content">
                        Approving will add <span class="impact-highlight">${preview.will_gain_tag} tags</span> to images
                    </div>
                </div >
            `;
        }
    } catch (error) {
        console.error('Error loading detail data:', error);
    }

    const actionsHtml = isSuggestion ? `
            < button class="detail-action-btn detail-approve-btn" onclick = "window.approveSingle('${selectedImplication.id}')" >
            ✓ Approve Suggestion
        </button >
            <button class="detail-action-btn detail-dismiss-btn" onclick="window.dismissSingle('${selectedImplication.id}')">
                ✗ Dismiss Suggestion
            </button>
        ` : `
            < button class="detail-action-btn detail-delete-btn" onclick = "window.deleteImplication('${source_tag}', '${implied_tag}')" >
            🗑️ Delete Implication
        </button >
            `;

    panel.innerHTML = `
            < div class="detail-content" >
            <div class="detail-header">
                <h3 class="detail-title">Implication Details</h3>
                <button class="close-detail-btn" onclick="window.closeDetail()">✕</button>
            </div>

            <div class="detail-diagram">
                <span class="tag-badge">${source_tag}</span>
                <div class="diagram-arrow">↓</div>
                <span class="tag-badge">${implied_tag}</span>
            </div>

            <div class="detail-stats">
                <div class="detail-stat">
                    <span class="detail-stat-label">Type</span>
                    <span class="type-badge">${type}</span>
                </div>
                <div class="detail-stat">
                    <span class="detail-stat-label">Confidence</span>
                    <span>${confidencePercent}%</span>
                </div>
            </div>

            ${impactHtml}

            <div class="detail-section">
                <div class="detail-section-title">Implication Chain</div>
                <div class="chain-tree">
                    ${chainHtml}
                </div>
            </div>

            <div class="detail-actions">
                ${actionsHtml}
            </div>
        </div >
            `;
}

function renderChainTree(node, depth = 0) {
    let html = `< div class="chain-node" style = "--depth: ${depth}" > ${node.tag}</div > `;

    if (node.implies && node.implies.length > 0) {
        html += `< div class="chain-connector" style = "--depth: ${depth}" >↓</div > `;
        node.implies.forEach(child => {
            html += renderChainTree(child, depth + 1);
        });
    }

    return html;
}

// Global functions for onclick handlers
window.toggleSuggestionSelection = toggleSuggestionSelection;

window.approveSingle = async function (itemId) {
    const item = document.querySelector(`[data - id="${itemId}"]`);
    if (!item) return;

    const suggestion = {
        source_tag: item.dataset.source,
        implied_tag: item.dataset.implied,
        inference_type: item.dataset.type,
        confidence: parseFloat(item.dataset.confidence),
        apply_now: document.getElementById('applyOnApproval')?.checked || false
    };

    try {
        const response = await fetch('/api/implications/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(suggestion)
        });

        const result = await response.json();
        let message = `Approved: ${suggestion.source_tag} → ${suggestion.implied_tag} `;
        if (result.applied_count > 0) {
            message += ` (applied to ${result.applied_count} images)`;
        }
        showSuccess(message);

        if (selectedTag) {
            selectTag(selectedTag.name);
        } else {
            loadAllSuggestions();
        }
    } catch (error) {
        console.error('Error approving:', error);
        showError('Failed to approve suggestion');
    }
};

window.dismissSingle = function (itemId) {
    const item = document.querySelector(`[data - id= "${itemId}"]`);
    if (item) {
        item.remove();
        showInfo('Suggestion dismissed');
    }
};

window.viewChain = async function (tagName) {
    try {
        const response = await fetch(`/ api / implications / chain / ${encodeURIComponent(tagName)} `);
        const chain = await response.json();

        // Show in a simple alert for now - could make a modal
        const chainText = renderChainText(chain);
        showInfo(`Implication Chain for ${tagName}: \n\n${chainText} `);
    } catch (error) {
        console.error('Error loading chain:', error);
        showError('Failed to load implication chain');
    }
};

function renderChainText(node, depth = 0) {
    let text = '  '.repeat(depth) + node.tag + '\n';
    if (node.implies && node.implies.length > 0) {
        node.implies.forEach(child => {
            text += renderChainText(child, depth + 1);
        });
    }
    return text;
}

window.deleteImplication = async function (sourceTag, impliedTag) {
    if (!confirm(`Delete implication: ${sourceTag} → ${impliedTag}?`)) {
        return;
    }

    try {
        const response = await fetch('/api/implications/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_tag: sourceTag, implied_tag: impliedTag })
        });

        const result = await response.json();
        showSuccess('Implication deleted');

        if (selectedTag) {
            selectTag(selectedTag.name);
        } else {
            loadAllSuggestions();
        }
    } catch (error) {
        console.error('Error deleting:', error);
        showError('Failed to delete implication');
    }
};

window.closeDetail = function () {
    selectedImplication = null;
    renderDetailPanel();
};

// Reusable Tag Autocomplete Setup
function setupTagAutocomplete(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;

    let searchTimeout;

    input.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        clearTimeout(searchTimeout);

        if (query.length < 2) {
            dropdown.classList.remove('active');
            return;
        }

        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/ api / autocomplete ? q = ${encodeURIComponent(query)}& limit=10`);
                const data = await response.json();

                // Extract tags from groups
                let tags = [];
                if (data.groups && data.groups.length > 0) {
                    const tagGroup = data.groups.find(g => g.name === 'Tags');
                    if (tagGroup && tagGroup.items) {
                        tags = tagGroup.items.map(item => ({
                            name: item.tag || item.label,
                            category: item.category || 'general'
                        }));
                    }
                }

                if (tags.length > 0) {
                    dropdown.innerHTML = tags.map(tag => `
            < div class="autocomplete-item" data - tag="${tag.name}" >
                <span class="tag-badge ${tag.category}">${tag.name}</span>
                        </div >
            `).join('');
                    dropdown.classList.add('active');

                    // Add click handlers
                    dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
                        item.addEventListener('click', () => {
                            input.value = item.dataset.tag;
                            dropdown.classList.remove('active');
                        });
                    });
                } else {
                    dropdown.classList.remove('active');
                }
            } catch (error) {
                console.error('Error fetching tag suggestions:', error);
            }
        }, 300);
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });
}

// Manual Creation Modal
function initializeManualCreation() {
    const createBtn = document.getElementById('createManualBtn');
    const modal = document.getElementById('manualModal');
    const closeBtn = modal.querySelector('.close');
    const previewBtn = document.getElementById('previewManualBtn');
    const submitBtn = document.getElementById('createManualSubmitBtn');

    // Setup autocomplete for both tag inputs
    setupTagAutocomplete('manualSourceTag', 'manualSourceTagDropdown');
    setupTagAutocomplete('manualImpliedTag', 'manualImpliedTagDropdown');

    createBtn.addEventListener('click', () => {
        modal.classList.add('active');
    });

    closeBtn.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });

    previewBtn.addEventListener('click', previewManualImplication);
    submitBtn.addEventListener('click', createManualImplication);
}

async function previewManualImplication() {
    const sourceTag = document.getElementById('manualSourceTag').value.trim();
    const impliedTag = document.getElementById('manualImpliedTag').value.trim();

    if (!sourceTag || !impliedTag) {
        showInfo('Please enter both source and implied tags');
        return;
    }

    try {
        const response = await fetch('/api/implications/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_tag: sourceTag, implied_tag: impliedTag })
        });

        const preview = await response.json();
        showInfo(`Preview: ${sourceTag} → ${impliedTag} \n\n` +
            `${preview.will_gain_tag} images will gain this tag\n` +
            `Chain: ${preview.chain_implications.join(' → ') || 'None'} `);
    } catch (error) {
        console.error('Error previewing:', error);
        showError('Failed to load preview');
    }
}

async function createManualImplication() {
    const sourceTag = document.getElementById('manualSourceTag').value.trim();
    const impliedTag = document.getElementById('manualImpliedTag').value.trim();

    if (!sourceTag || !impliedTag) {
        showInfo('Please enter both source and implied tags');
        return;
    }

    try {
        const response = await fetch('/api/implications/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_tag: sourceTag, implied_tag: impliedTag })
        });

        const result = await response.json();
        showSuccess(`Created implication: ${sourceTag} → ${impliedTag} `);

        // Close modal and reset
        document.getElementById('manualModal').classList.remove('active');
        document.getElementById('manualSourceTag').value = '';
        document.getElementById('manualImpliedTag').value = '';

        // Reload implications
        if (selectedTag) {
            selectTag(selectedTag.name);
        } else {
            loadAllSuggestions();
        }
    } catch (error) {
        console.error('Error creating:', error);
        showError('Failed to create implication');
    }
}

// Auto-Approve Naming Patterns
document.getElementById('autoApprovePatternBtn')?.addEventListener('click', async () => {
    const confirmMsg = `This will auto - approve ALL naming pattern suggestions.\n\nThese are character_(copyright) → copyright patterns with 92 % confidence.\n\nContinue ? `;

    if (!confirm(confirmMsg)) {
        return;
    }

    const btn = document.getElementById('autoApprovePatternBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span>⏳</span> Processing...';
    btn.disabled = true;

    try {
        const response = await fetch('/api/implications/auto-approve-pattern', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success_count > 0) {
            showSuccess(`Auto - approved ${result.success_count} of ${result.total} naming pattern implications!`);
        } else if (result.total === 0) {
            showInfo('No naming pattern suggestions to approve');
        } else {
            showError(`Failed to approve suggestions.Errors: ${result.errors.length} `);
        }

        // Reload suggestions
        loadAllSuggestions();
    } catch (error) {
        console.error('Error auto-approving naming patterns:', error);
        showError('Failed to auto-approve naming patterns');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
});

// Clear Implied Tags Modal
function initializeClearImpliedModal() {
    const modal = document.getElementById('clearImpliedModal');
    const openBtn = document.getElementById('clearImpliedTagsBtn');
    const closeBtn = modal?.querySelector('.close');
    const cancelBtn = document.getElementById('clearImpliedCancelBtn');
    const submitBtn = document.getElementById('clearImpliedSubmitBtn');
    const reapplyCheckbox = document.getElementById('clearImpliedReapplyCheckbox');

    if (!modal || !openBtn) return;

    openBtn.addEventListener('click', () => {
        modal.classList.add('active');
    });

    closeBtn?.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    cancelBtn?.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });

    submitBtn?.addEventListener('click', async () => {
        const reapply = reapplyCheckbox?.checked || false;

        submitBtn.textContent = reapply ? 'Clearing & Reapplying...' : 'Clearing...';
        submitBtn.disabled = true;

        try {
            const endpoint = reapply ? '/api/implications/clear-and-reapply' : '/api/implications/clear-tags';
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const result = await response.json();
            showSuccess(result.message);
            modal.classList.remove('active');
        } catch (error) {
            console.error('Error clearing tags:', error);
            showError('Failed to clear implied tags');
        } finally {
            submitBtn.textContent = 'Clear Tags';
            submitBtn.disabled = false;
        }
    });
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initializeClearImpliedModal();
});

// Auto-Approve Settings Modal
function initializeAutoApproveModal() {
    const modal = document.getElementById('autoApproveModal');
    const openBtn = document.getElementById('autoApproveConfidentBtn');
    const closeBtn = modal?.querySelector('.close');
    const refreshBtn = document.getElementById('autoApproveRefreshBtn');
    const submitBtn = document.getElementById('autoApproveSubmitBtn');
    const confidenceSlider = document.getElementById('minConfidenceSlider');
    const confidenceValue = document.getElementById('minConfidenceValue');
    const samplesSlider = document.getElementById('minSamplesSlider');
    const samplesValue = document.getElementById('minSamplesValue');

    if (!modal || !openBtn) return;

    // Open modal
    openBtn.addEventListener('click', () => {
        modal.classList.add('active');
        updateAutoApprovePreview();
    });

    // Close modal
    closeBtn?.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });

    // Update slider displays
    confidenceSlider?.addEventListener('input', () => {
        confidenceValue.textContent = `${confidenceSlider.value}% `;
    });

    confidenceSlider?.addEventListener('change', updateAutoApprovePreview);

    samplesSlider?.addEventListener('input', () => {
        samplesValue.textContent = samplesSlider.value;
    });

    samplesSlider?.addEventListener('change', updateAutoApprovePreview);

    // Refresh button
    refreshBtn?.addEventListener('click', updateAutoApprovePreview);

    // Submit button
    submitBtn?.addEventListener('click', executeAutoApprove);
}

async function updateAutoApprovePreview() {
    const preview = document.getElementById('autoApprovePreview');
    const minConfidence = parseInt(document.getElementById('minConfidenceSlider')?.value || 85) / 100;
    const minSamples = parseInt(document.getElementById('minSamplesSlider')?.value || 5);

    preview.innerHTML = '<div class="preview-count">Calculating...</div>';

    try {
        // Count matching suggestions from already loaded data
        const matching = allImplications.suggestions.filter(s => {
            const confidence = s.confidence || 0;
            const samples = s.sample_size || s.affected_images || 0;
            return s.pattern_type === 'correlation' &&
                confidence >= minConfidence &&
                samples >= minSamples;
        });

        preview.innerHTML = `
            < div class="preview-count" >
                <strong>${matching.length}</strong> suggestions match these criteria
            </div >
            ${matching.length > 0 ? `
                <div class="preview-examples">
                    <small>Examples:</small>
                    <ul>
                        ${matching.slice(0, 5).map(s => `
                            <li>${s.source_tag} → ${s.implied_tag} (${Math.round(s.confidence * 100)}%, ${s.sample_size || s.affected_images || '?'} samples)</li>
                        `).join('')}
                        ${matching.length > 5 ? `<li>...and ${matching.length - 5} more</li>` : ''}
                    </ul>
                </div>
            ` : ''
            }
        `;
    } catch (error) {
        preview.innerHTML = '<div class="preview-count">Error loading preview</div>';
    }
}

async function executeAutoApprove() {
    const minConfidence = parseInt(document.getElementById('minConfidenceSlider')?.value || 85) / 100;
    const minSamples = parseInt(document.getElementById('minSamplesSlider')?.value || 5);
    const applyNow = document.getElementById('autoApproveApplyNow')?.checked || false;

    const btn = document.getElementById('autoApproveSubmitBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '⏳ Processing...';
    btn.disabled = true;

    try {
        const requestBody = {
            min_confidence: minConfidence,
            min_sample_size: minSamples,
            apply_now: applyNow
        };

        // Add category filters if active
        if (!sourceCategoryFilters.has('all')) {
            requestBody.source_categories = [...sourceCategoryFilters];
        }
        if (!impliedCategoryFilters.has('all')) {
            requestBody.implied_categories = [...impliedCategoryFilters];
        }

        const response = await fetch('/api/implications/auto-approve-confident', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        const result = await response.json();

        if (result.success_count > 0) {
            let msg = `Auto - approved ${result.success_count} of ${result.total} implications!`;
            if (result.tags_applied) {
                msg += ` Applied ${result.tags_applied} tags.`;
            }
            showSuccess(msg);
            document.getElementById('autoApproveModal').classList.remove('active');
            loadAllSuggestions();
        } else if (result.total === 0) {
            showInfo('No suggestions matching criteria');
        } else {
            showError(`Failed: ${result.errors?.length || 0} errors`);
        }
    } catch (error) {
        console.error('Error auto-approving:', error);
        showError('Failed to auto-approve');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
    initializeAutoApproveModal();
});

// Keyboard Shortcuts
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ignore if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
            return;
        }

        switch (e.key) {
            case '/':
                e.preventDefault();
                document.getElementById('tagSearchInput').focus();
                break;
            case 'a':
                if (selectedSuggestions.size > 0) {
                    e.preventDefault();
                    bulkApprove();
                }
                break;
            case 'd':
                if (selectedSuggestions.size > 0) {
                    e.preventDefault();
                    bulkDismiss();
                }
                break;
            case 'Escape':
                closeDetail();
                break;
        }
    });
}

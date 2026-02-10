/**
 * Gallery Page Enhancements
 * - Grid size toggle (S/M/L) with localStorage persistence
 * - Filter sidebar toggle
 * - Quick filter functionality  
 * - Recent searches
 * - Keyboard navigation (hjkl, arrows, space selection, Ctrl+A, Ctrl+F)
 * - Active filters bar with editable chips
 */

(function () {
    'use strict';

    // ========================================================================
    // STATE
    // ========================================================================

    const state = {
        gridSize: localStorage.getItem('gallery-grid-size') || 'medium',
        sidebarOpen: localStorage.getItem('gallery-sidebar') !== 'false',
        recentSearches: JSON.parse(localStorage.getItem('recent-searches') || '[]'),
        focusedIndex: -1,
        activeFilters: [],
        spaceHeld: false,  // Track if space is being held for range selection
        searchFocused: false  // Track search focus state for Ctrl+F toggle
    };

    // ========================================================================
    // ELEMENTS
    // ========================================================================

    const getElements = () => ({
        gallery: document.querySelector('.gallery'),
        filterSidebar: document.querySelector('.filter-sidebar'),
        sidebarToggle: document.getElementById('sidebarToggle'),
        gridSizeBtns: document.querySelectorAll('.grid-size-btn'),

        searchInput: document.querySelector('#chipTextInput') || document.querySelector('.search-bar input'),
        thumbnails: document.querySelectorAll('.thumbnail'),
        galleryContent: document.querySelector('.gallery-content')
    });

    // ========================================================================
    // QUICK FILTERS DEFINITION
    // ========================================================================

    const quickFilters = {
        sort: [
            { label: 'Newest', query: 'order:new', icon: '🕒' },
            { label: 'Oldest', query: 'order:old', icon: '📜' },
            { label: 'Score', query: 'order:score', icon: '📈' },
            { label: 'Favorites', query: 'order:fav', icon: '❤️' }
        ],
        rating: [
            { label: 'General', query: 'rating:general', color: '#22c55e' },
            { label: 'Sensitive', query: 'rating:sensitive', color: '#eab308' },
            { label: 'Questionable', query: 'rating:questionable', color: '#f97316' },
            { label: 'Explicit', query: 'rating:explicit', color: '#ef4444' }
        ],
        source: [
            { label: 'Danbooru', query: 'source:danbooru' },
            { label: 'Gelbooru', query: 'source:gelbooru' },
            { label: 'e621', query: 'source:e621' },
            { label: 'Pixiv', query: 'source:pixiv' },
            { label: 'Local Tagger', query: 'source:local_tagger' }
        ],
        special: [
            { label: 'Has Parent', query: 'has:parent', icon: '↑' },
            { label: 'Has Children', query: 'has:child', icon: '↓' },
            { label: 'In Pool', query: 'has:pool', icon: '📚' },
            { label: 'Has Upscaled', query: 'has:upscaled', icon: '✨' },
            { label: 'GIFs', query: '.gif', icon: '🖼️' },
            { label: 'Videos', query: 'has:video', icon: '🎥' },
            { label: 'Favourites', query: 'is:favourite', icon: '⭐' }
        ]
    };

    // ========================================================================
    // INITIALIZATION
    // ========================================================================

    function init() {
        const els = getElements();

        // Parse current query from URL
        parseActiveFilters();

        // Apply initial states
        setGridSize(state.gridSize);
        setSidebarOpen(state.sidebarOpen);

        // Render dynamic content
        renderFilterSidebar();


        // Bind events
        bindEvents();
    }

    // ========================================================================
    // GRID SIZE
    // ========================================================================

    function setGridSize(size) {
        const els = getElements();
        if (!els.gallery) return;

        state.gridSize = size;
        els.gallery.classList.remove('grid-small', 'grid-medium', 'grid-large');
        els.gallery.classList.add(`grid-${size}`);

        els.gridSizeBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.size === size);
        });

        localStorage.setItem('gallery-grid-size', size);
    }

    // ========================================================================
    // SIDEBAR
    // ========================================================================

    function setSidebarOpen(open) {
        const els = getElements();
        if (!els.filterSidebar) return;

        state.sidebarOpen = open;
        els.filterSidebar.classList.toggle('collapsed', !open);
        els.sidebarToggle?.classList.toggle('active', open);
        localStorage.setItem('gallery-sidebar', open);
    }

    function toggleSidebar() {
        setSidebarOpen(!state.sidebarOpen);
    }

    // ========================================================================
    // ACTIVE FILTERS
    // ========================================================================

    function parseActiveFilters() {
        const params = new URLSearchParams(window.location.search);
        const query = params.get('query') || '';

        // Split by spaces, preserving quoted strings
        state.activeFilters = query.split(/\s+/).filter(f => f.trim());
    }

    // Get autocomplete instance for live filtering integration
    function getAutocompleteInstance() {
        // Access the autocomplete instance from the global window object
        // It's set by autocomplete.js after DOMContentLoaded
        return window.autocompleteInstance;
    }

    function addFilter(query) {
        const autocomplete = getAutocompleteInstance();

        // For rating, source, and order filters, make them exclusive (only one at a time)
        const isRating = query.startsWith('rating:');
        const isSource = query.startsWith('source:');
        const isOrder = query.startsWith('order:');

        if (autocomplete && autocomplete.chips) {
            // Remove conflicting filters from chips
            if (isRating) {
                autocomplete.chips = autocomplete.chips.filter(c => !c.token.startsWith('rating:'));
            } else if (isSource) {
                autocomplete.chips = autocomplete.chips.filter(c => !c.token.startsWith('source:'));
            } else if (isOrder) {
                autocomplete.chips = autocomplete.chips.filter(c => !c.token.startsWith('order:'));
            }

            // Check if already exists
            const exists = autocomplete.chips.some(c => c.token === query);
            if (!exists) {
                autocomplete.addChipFromText(query);
            } else {
                // Still re-render in case we removed conflicting filters
                autocomplete.renderChips();
                autocomplete.updateHiddenInput();
                autocomplete.triggerLiveFilter();
            }
        } else {
            // Fallback to page navigation if autocomplete not available
            if (isRating) {
                state.activeFilters = state.activeFilters.filter(f => !f.startsWith('rating:'));
            } else if (isSource) {
                state.activeFilters = state.activeFilters.filter(f => !f.startsWith('source:'));
            } else if (isOrder) {
                state.activeFilters = state.activeFilters.filter(f => !f.startsWith('order:'));
            }

            if (!state.activeFilters.includes(query)) {
                state.activeFilters.push(query);
                applyFilters();
            }
        }

        // Update local state and sidebar UI
        parseActiveFilters();
        updateSidebarActiveStates();
    }

    function removeFilter(query) {
        const autocomplete = getAutocompleteInstance();

        if (autocomplete && autocomplete.chips) {
            // Find and remove the chip with this query
            const chipIndex = autocomplete.chips.findIndex(c => c.token === query);
            if (chipIndex !== -1) {
                autocomplete.removeChip(chipIndex);
            }
        } else {
            // Fallback to page navigation
            state.activeFilters = state.activeFilters.filter(f => f !== query);
            applyFilters();
        }

        // Update local state and sidebar UI
        parseActiveFilters();
        updateSidebarActiveStates();
    }

    function updateFilter(oldQuery, newQuery) {
        const autocomplete = getAutocompleteInstance();

        if (autocomplete && autocomplete.chips) {
            const chipIndex = autocomplete.chips.findIndex(c => c.token === oldQuery);
            if (chipIndex !== -1) {
                autocomplete.chips[chipIndex] = autocomplete.parseToken(newQuery.trim());
                autocomplete.renderChips();
                autocomplete.updateHiddenInput();
                autocomplete.triggerLiveFilter();
            }
        } else {
            const idx = state.activeFilters.indexOf(oldQuery);
            if (idx !== -1) {
                state.activeFilters[idx] = newQuery.trim();
                applyFilters();
            }
        }

        parseActiveFilters();
        updateSidebarActiveStates();
    }

    function clearFilters() {
        const autocomplete = getAutocompleteInstance();

        if (autocomplete && autocomplete.chips) {
            autocomplete.chips = [];
            autocomplete.renderChips();
            autocomplete.updateHiddenInput();
            autocomplete.triggerLiveFilter();
        } else {
            state.activeFilters = [];
            applyFilters();
        }

        parseActiveFilters();
        updateSidebarActiveStates();
    }

    function applyFilters() {
        const query = state.activeFilters.join(' ');
        if (query) {
            window.location.href = `/?query=${encodeURIComponent(query)}`;
        } else {
            window.location.href = '/';
        }
    }

    function updateSidebarActiveStates() {
        const filterSidebar = document.querySelector('.filter-sidebar');
        if (!filterSidebar) return;

        // Get current query from autocomplete or URL
        const autocomplete = getAutocompleteInstance();
        let currentFilters = [];

        if (autocomplete && autocomplete.chips) {
            currentFilters = autocomplete.chips.map(c => c.token);
        } else {
            currentFilters = state.activeFilters;
        }

        // Update all filter items
        filterSidebar.querySelectorAll('.filter-item[data-query]').forEach(item => {
            const query = item.dataset.query;
            item.classList.toggle('active', currentFilters.includes(query));
        });
    }



    // ========================================================================
    // FILTER SIDEBAR
    // ========================================================================

    function renderFilterSidebar() {
        const els = getElements();
        if (!els.filterSidebar) return;

        let html = '';

        // Sort section
        html += `
            <div class="filter-section" data-section="sort">
                <div class="filter-section-header">
                    <span><span class="icon">🔃</span> Sort</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.sort.map(f => `
                        <div class="filter-item${state.activeFilters.includes(f.query) ? ' active' : ''}" data-query="${f.query}">
                            <span><span class="icon">${f.icon}</span> ${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Rating section
        html += `
            <div class="filter-section" data-section="rating">
                <div class="filter-section-header">
                    <span><span class="icon">⭐</span> Rating</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.rating.map(f => `
                        <div class="filter-item${state.activeFilters.includes(f.query) ? ' active' : ''}" data-query="${f.query}">
                            <span class="dot" style="background: ${f.color}"></span>
                            <span>${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Source section (collapsed by default)
        html += `
            <div class="filter-section" data-section="source">
                <div class="filter-section-header">
                    <span><span class="icon">📚</span> Source</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.source.map(f => `
                        <div class="filter-item${state.activeFilters.includes(f.query) ? ' active' : ''}" data-query="${f.query}">
                            <span>${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Special section (collapsed by default)
        html += `
            <div class="filter-section" data-section="special">
                <div class="filter-section-header">
                    <span><span class="icon">🔧</span> Special</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.special.map(f => `
                        <div class="filter-item${state.activeFilters.includes(f.query) ? ' active' : ''}" data-query="${f.query}">
                            <span>${f.icon || ''} ${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;

        // Recent searches
        if (state.recentSearches.length > 0) {
            html += `
                <div class="filter-section" data-section="recent">
                    <div class="filter-section-header">
                        <span><span class="icon">🕐</span> Recent</span>
                        <span class="arrow">▼</span>
                    </div>
                    <div class="filter-section-content">
                        ${state.recentSearches.slice(0, 5).map(s => `
                            <div class="filter-item" data-search="${escapeHtml(s)}">
                                <span>${escapeHtml(truncate(s, 25))}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        els.filterSidebar.innerHTML = html;

        // Bind section toggles
        els.filterSidebar.querySelectorAll('.filter-section-header').forEach(header => {
            header.addEventListener('click', () => {
                header.parentElement.classList.toggle('collapsed');
            });
        });

        // Bind filter items
        els.filterSidebar.querySelectorAll('.filter-item[data-query]').forEach(item => {
            item.addEventListener('click', () => {
                if (item.classList.contains('active')) {
                    removeFilter(item.dataset.query);
                } else {
                    addFilter(item.dataset.query);
                }
            });
        });

        // Bind recent search items
        els.filterSidebar.querySelectorAll('.filter-item[data-search]').forEach(item => {
            item.addEventListener('click', () => {
                window.location.href = `/?query=${encodeURIComponent(item.dataset.search)}`;
            });
        });
    }

    // ========================================================================
    // GRID UTILITIES
    // ========================================================================

    /**
     * Get number of columns in the current grid layout
     */
    function getGridColumns() {
        const gallery = document.querySelector('.gallery');
        const thumbs = document.querySelectorAll('.thumbnail');
        if (!gallery || thumbs.length < 2) return 4;

        // Get the first row by finding how many thumbnails share the same top offset
        const firstTop = thumbs[0].offsetTop;
        let columnsInFirstRow = 0;
        for (const thumb of thumbs) {
            if (thumb.offsetTop === firstTop) {
                columnsInFirstRow++;
            } else {
                break;
            }
        }
        return columnsInFirstRow || 4;
    }

    /**
     * Get row and column position for a given index
     */
    function getGridPosition(index) {
        const cols = getGridColumns();
        return {
            row: Math.floor(index / cols),
            col: index % cols
        };
    }

    /**
     * Get index from row and column
     */
    function getIndexFromPosition(row, col) {
        const cols = getGridColumns();
        return row * cols + col;
    }

    // ========================================================================
    // SELECTION INTEGRATION
    // ========================================================================

    /**
     * Toggle selection on a specific thumbnail
     * Works with bulk-delete.js if selection mode is enabled
     */
    function toggleThumbnailSelection(thumb) {
        if (!thumb) return;

        const checkbox = thumb.querySelector('.image-select-checkbox');
        if (!checkbox) return;

        // Auto-enable selection mode if not already active
        const selectionToggle = document.getElementById('selection-toggle');
        if (selectionToggle && checkbox.style.display === 'none') {
            // Trigger selection mode
            selectionToggle.click();
        }

        // Toggle the checkbox
        checkbox.checked = !checkbox.checked;

        // Dispatch change event to notify bulk-delete.js
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    }

    /**
     * Select all visible thumbnails
     */
    function selectAllVisible() {
        const selectAllBtn = document.getElementById('select-all-btn');
        const selectionToggle = document.getElementById('selection-toggle');

        // Enable selection mode first if needed
        if (selectionToggle && !selectionToggle.classList.contains('active')) {
            selectionToggle.click();
        }

        // Click the select all button if it exists
        if (selectAllBtn) {
            selectAllBtn.click();
        }
    }

    // ========================================================================
    // KEYBOARD NAVIGATION
    // ========================================================================

    function handleKeyboard(e) {
        // Explicitly ignore Tab to prevent any conflicts
        if (e.key === 'Tab') return;

        const els = getElements();

        // Ignore if typing in an input (except for Escape and Ctrl shortcuts)
        const isTyping = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';

        // Ctrl+F - toggle search focus
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            if (state.searchFocused && els.searchInput) {
                els.searchInput.blur();
                state.searchFocused = false;
            } else if (els.searchInput) {
                els.searchInput.focus();
                state.searchFocused = true;
            }
            return;
        }

        // Ctrl+A - select all visible (only when not typing)
        if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !isTyping) {
            e.preventDefault();
            selectAllVisible();
            return;
        }

        // Escape - blur search / deselect
        if (e.key === 'Escape') {
            if (document.activeElement) {
                document.activeElement.blur();
                state.searchFocused = false;
            }
            return;
        }

        // Rest of shortcuts only work when not typing
        if (isTyping) return;

        const thumbnails = Array.from(document.querySelectorAll('.thumbnail'));
        if (thumbnails.length === 0) return;

        const cols = getGridColumns();
        const currentPos = getGridPosition(state.focusedIndex);
        const totalRows = Math.ceil(thumbnails.length / cols);

        let newIndex = state.focusedIndex;

        switch (e.key) {
            // Sidebar toggle
            case 's':
            case 'S':
                e.preventDefault();
                toggleSidebar();
                return;

            // Move down
            case 'j':
            case 'ArrowDown':
                e.preventDefault();
                if (state.focusedIndex === -1) {
                    // Start at first item
                    newIndex = 0;
                } else {
                    // Move down one row
                    const nextRowIndex = getIndexFromPosition(currentPos.row + 1, currentPos.col);
                    if (nextRowIndex < thumbnails.length) {
                        newIndex = nextRowIndex;
                    }
                }
                break;

            // Move up
            case 'k':
            case 'ArrowUp':
                e.preventDefault();
                if (state.focusedIndex === -1) {
                    newIndex = 0;
                } else if (currentPos.row > 0) {
                    newIndex = getIndexFromPosition(currentPos.row - 1, currentPos.col);
                }
                break;

            // Move left
            case 'h':
            case 'ArrowLeft':
                e.preventDefault();
                if (state.focusedIndex === -1) {
                    newIndex = 0;
                } else if (currentPos.col > 0) {
                    // Stay within same row
                    newIndex = state.focusedIndex - 1;
                }
                break;

            // Move right
            case 'l':
            case 'ArrowRight':
                e.preventDefault();
                if (state.focusedIndex === -1) {
                    newIndex = 0;
                } else {
                    const nextIndex = state.focusedIndex + 1;
                    const nextPos = getGridPosition(nextIndex);
                    // Only move right if still on same row and valid
                    if (nextIndex < thumbnails.length && nextPos.row === currentPos.row) {
                        newIndex = nextIndex;
                    }
                }
                break;

            // Select focused image
            case ' ':
                e.preventDefault();
                if (state.focusedIndex >= 0 && thumbnails[state.focusedIndex]) {
                    toggleThumbnailSelection(thumbnails[state.focusedIndex]);
                }
                return;

            // Open focused image
            case 'Enter':
                if (state.focusedIndex >= 0 && thumbnails[state.focusedIndex]) {
                    thumbnails[state.focusedIndex].querySelector('a')?.click();
                }
                return;

            default:
                return;
        }

        // Update focus if index changed
        if (newIndex !== state.focusedIndex) {
            state.focusedIndex = newIndex;
            focusThumbnail(thumbnails[state.focusedIndex]);

            // If space is held, also select the new thumbnail
            if (state.spaceHeld && thumbnails[state.focusedIndex]) {
                const checkbox = thumbnails[state.focusedIndex].querySelector('.image-select-checkbox');
                if (checkbox && !checkbox.checked) {
                    toggleThumbnailSelection(thumbnails[state.focusedIndex]);
                }
            }
        }
    }

    function handleKeyUp(e) {
        if (e.key === ' ') {
            state.spaceHeld = false;
        }
    }

    function handleKeyDownForSpace(e) {
        if (e.key === ' ' && !e.repeat) {
            const isTyping = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';
            if (!isTyping) {
                state.spaceHeld = true;
            }
        }
    }

    function focusThumbnail(thumb) {
        if (!thumb) return;

        document.querySelectorAll('.thumbnail.focused').forEach(t => t.classList.remove('focused'));
        thumb.classList.add('focused');
        thumb.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    // Track search focus state
    function handleSearchFocus() {
        state.searchFocused = true;
    }

    function handleSearchBlur() {
        state.searchFocused = false;
    }

    // ========================================================================
    // RECENT SEARCHES
    // ========================================================================

    function saveRecentSearch(query) {
        if (!query) return;

        state.recentSearches = state.recentSearches.filter(s => s !== query);
        state.recentSearches.unshift(query);
        state.recentSearches = state.recentSearches.slice(0, 10);

        localStorage.setItem('recent-searches', JSON.stringify(state.recentSearches));
    }

    // ========================================================================
    // EVENTS
    // ========================================================================

    function bindEvents() {
        const els = getElements();

        // Grid size buttons
        els.gridSizeBtns.forEach(btn => {
            btn.addEventListener('click', () => setGridSize(btn.dataset.size));
        });

        // Sidebar toggle
        els.sidebarToggle?.addEventListener('click', toggleSidebar);

        // Close sidebar when clicking backdrop (mobile)
        els.filterSidebar?.addEventListener('click', e => {
            if (e.target === els.filterSidebar && window.innerWidth <= 1024) {
                toggleSidebar();
            }
        });

        // Keyboard navigation
        document.addEventListener('keydown', handleKeyboard);
        document.addEventListener('keydown', handleKeyDownForSpace);
        document.addEventListener('keyup', handleKeyUp);

        // Track search focus for Ctrl+F toggle
        els.searchInput?.addEventListener('focus', handleSearchFocus);
        els.searchInput?.addEventListener('blur', handleSearchBlur);

        // Save search on form submit
        const searchForm = document.querySelector('.search-bar form');
        searchForm?.addEventListener('submit', () => {
            const input = document.querySelector('#searchInput');
            if (input?.value) {
                saveRecentSearch(input.value);
            }
        });

        // Intercept space key in search input to add to filters bar instead of chips

    }

    // ========================================================================
    // UTILITIES
    // ========================================================================

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function truncate(str, len) {
        return str.length > len ? str.substring(0, len) + '...' : str;
    }

    // ========================================================================
    // INIT
    // ========================================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

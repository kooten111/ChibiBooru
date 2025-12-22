/**
 * Gallery Page Enhancements
 * - Grid size toggle (S/M/L) with localStorage persistence
 * - Filter sidebar toggle
 * - Quick filter functionality  
 * - Recent searches
 * - Keyboard navigation (J/K, Ctrl+F, Enter, Escape)
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
        activeFilters: []
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

    function addFilter(query) {
        // For rating and source filters, make them exclusive (only one at a time)
        const isRating = query.startsWith('rating:');
        const isSource = query.startsWith('source:');

        if (isRating) {
            // Remove any existing rating filters
            state.activeFilters = state.activeFilters.filter(f => !f.startsWith('rating:'));
        } else if (isSource) {
            // Remove any existing source filters  
            state.activeFilters = state.activeFilters.filter(f => !f.startsWith('source:'));
        } else if (query.startsWith('order:')) {
            // Remove any existing order filters
            state.activeFilters = state.activeFilters.filter(f => !f.startsWith('order:'));
        }

        if (!state.activeFilters.includes(query)) {
            state.activeFilters.push(query);
            applyFilters();
        }
    }

    function removeFilter(query) {
        state.activeFilters = state.activeFilters.filter(f => f !== query);
        applyFilters();
    }

    function updateFilter(oldQuery, newQuery) {
        const idx = state.activeFilters.indexOf(oldQuery);
        if (idx !== -1) {
            state.activeFilters[idx] = newQuery.trim();
            applyFilters();
        }
    }

    function clearFilters() {
        state.activeFilters = [];
        applyFilters();
    }

    function applyFilters() {
        const query = state.activeFilters.join(' ');
        if (query) {
            window.location.href = `/?query=${encodeURIComponent(query)}`;
        } else {
            window.location.href = '/';
        }
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
    // KEYBOARD NAVIGATION
    // ========================================================================

    function handleKeyboard(e) {
        // Explicitly ignore Tab to prevent any conflicts
        if (e.key === 'Tab') return;

        const els = getElements();

        // Ignore if typing in an input (except for Escape and Ctrl+F)
        const isTyping = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';

        // Ctrl+F - focus search (prevent browser find)
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            els.searchInput?.focus();
            return;
        }

        // Escape - blur search
        if (e.key === 'Escape') {
            if (document.activeElement) {
                document.activeElement.blur();
            }
            return;
        }

        // Rest of shortcuts only work when not typing
        if (isTyping) return;

        const thumbnails = Array.from(document.querySelectorAll('.thumbnail'));

        switch (e.key) {
            case 'j':
            case 'ArrowDown':
                e.preventDefault();
                state.focusedIndex = Math.min(state.focusedIndex + 1, thumbnails.length - 1);
                focusThumbnail(thumbnails[state.focusedIndex]);
                break;

            case 'k':
            case 'ArrowUp':
                e.preventDefault();
                state.focusedIndex = Math.max(state.focusedIndex - 1, 0);
                focusThumbnail(thumbnails[state.focusedIndex]);
                break;

            case 'ArrowRight':
                e.preventDefault();
                state.focusedIndex = Math.min(state.focusedIndex + 1, thumbnails.length - 1);
                focusThumbnail(thumbnails[state.focusedIndex]);
                break;

            case 'ArrowLeft':
                e.preventDefault();
                state.focusedIndex = Math.max(state.focusedIndex - 1, 0);
                focusThumbnail(thumbnails[state.focusedIndex]);
                break;

            case 'Enter':
                if (state.focusedIndex >= 0 && thumbnails[state.focusedIndex]) {
                    thumbnails[state.focusedIndex].querySelector('a')?.click();
                }
                break;
        }
    }

    function focusThumbnail(thumb) {
        if (!thumb) return;

        document.querySelectorAll('.thumbnail.focused').forEach(t => t.classList.remove('focused'));
        thumb.classList.add('focused');
        thumb.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

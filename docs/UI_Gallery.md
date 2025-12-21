# 3. Gallery / Front Page (index.html)

## Current Problems

- No quick filter sidebar - have to type everything
- Header takes up space even when browsing
- No saved/recent searches
- Grid size not adjustable
- No keyboard navigation

## Proposed Layout

```text
┌──────────────────────────────────────────────────────────────────┐
│ Logo   [Search input........................] [S][M][L] [◧] [🎲] │
├────────────────────────────────────────────────────────────────── │
│ Filters: [rating:general ✕] [1girl ✕]              2,847 results │
├────────────┬─────────────────────────────────────────────────────┤
│ ▼ Rating   │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
│   ● General│  │     │ │     │ │     │ │     │ │     │ │     │   │
│   ○ Sensit.│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘   │
│   ○ Quest. │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
│   ○ Explic.│  │     │ │     │ │     │ │     │ │     │ │     │   │
│            │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘   │
│ ▶ Source   │                                                     │
│ ▶ Special  │  (scrollable grid)                                  │
│ ▼ Recent   │                                                     │
│   1girl... │                                                     │
│   artist.. │                                                     │
│ ▶ Top Tags │                                                     │
└────────────┴─────────────────────────────────────────────────────┘
                                        [J]/[K] navigate • [?] help
```

## Files to Modify

### static/css/gallery.css (new file)

```css
/* ============================================================================
   GALLERY PAGE - Improved Layout
   ============================================================================ */

.gallery-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* Compact Header */
.gallery-page .header {
    height: 48px;
    padding: 0 var(--spacing-lg);
    flex-shrink: 0;
}

.gallery-page .header-content {
    height: 100%;
    display: flex;
    align-items: center;
    gap: var(--spacing-lg);
}

.gallery-page .header h1 {
    font-size: 1.25rem;
}

.gallery-page .search-bar {
    flex: 1;
    max-width: 600px;
}

.gallery-page .search-bar input {
    height: 36px;
    padding: 0 var(--spacing-md);
}

/* Header controls */
.header-controls {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
}

.grid-size-toggle {
    display: flex;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    padding: 2px;
}

.grid-size-btn {
    padding: 4px 8px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.grid-size-btn.active {
    background: var(--primary-blue);
    color: white;
}

.header-btn {
    padding: 6px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.header-btn:hover {
    color: var(--text-primary);
}

.header-btn.active {
    background: var(--primary-blue-light);
    color: var(--primary-blue);
}

/* Active Filters Bar */
.active-filters-bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-lg);
    background: var(--bg-secondary);
    border-bottom: var(--border-width) solid var(--border-color);
    flex-wrap: wrap;
}

.active-filters-bar:empty {
    display: none;
}

.filters-label {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    text-transform: uppercase;
}

.filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    background: var(--primary-blue-light);
    border-radius: var(--radius-lg);
    font-size: var(--font-size-xs);
    color: var(--primary-blue);
}

.filter-chip .remove {
    cursor: pointer;
    opacity: 0.7;
}

.filter-chip .remove:hover {
    opacity: 1;
}

.clear-filters {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    background: none;
    border: none;
    cursor: pointer;
}

.clear-filters:hover {
    color: var(--text-primary);
}

.results-count {
    margin-left: auto;
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

/* Main Layout */
.gallery-layout {
    flex: 1;
    display: flex;
    overflow: hidden;
}

/* Filter Sidebar */
.filter-sidebar {
    width: 224px;
    flex-shrink: 0;
    background: var(--bg-secondary);
    border-right: var(--border-width) solid var(--border-color);
    overflow-y: auto;
    padding: var(--spacing-md);
    transition: width 0.2s ease, opacity 0.2s ease;
}

.filter-sidebar.collapsed {
    width: 0;
    padding: 0;
    opacity: 0;
    overflow: hidden;
}

/* Filter Sections */
.filter-section {
    margin-bottom: var(--spacing-md);
}

.filter-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--spacing-xs) 0;
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
    user-select: none;
}

.filter-section-header:hover {
    color: var(--text-secondary);
}

.filter-section-header .icon {
    font-size: 0.875rem;
}

.filter-section-header .arrow {
    font-size: 0.625rem;
    transition: transform 0.2s;
}

.filter-section.collapsed .arrow {
    transform: rotate(-90deg);
}

.filter-section-content {
    padding-top: var(--spacing-xs);
}

.filter-section.collapsed .filter-section-content {
    display: none;
}

/* Filter Items */
.filter-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-xs) var(--spacing-sm);
    margin: 2px 0;
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.filter-item:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.filter-item.active {
    background: var(--primary-blue-light);
    color: var(--primary-blue);
}

.filter-item .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.filter-item .count {
    margin-left: auto;
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

/* Gallery Content */
.gallery-content {
    flex: 1;
    overflow-y: auto;
    padding: var(--spacing-md);
}

/* Grid Size Variations */
.gallery.grid-small {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    grid-auto-rows: 8px;
}

.gallery.grid-small .thumbnail {
    grid-row: span 12;
}

.gallery.grid-medium {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    grid-auto-rows: 10px;
}

.gallery.grid-medium .thumbnail {
    grid-row: span 16;
}

.gallery.grid-large {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    grid-auto-rows: 12px;
}

.gallery.grid-large .thumbnail {
    grid-row: span 20;
}

/* Thumbnail Hover Overlay */
.thumbnail .hover-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(0,0,0,0.8), transparent 50%);
    opacity: 0;
    transition: opacity var(--transition-normal);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: var(--spacing-sm);
    pointer-events: none;
}

.thumbnail:hover .hover-overlay {
    opacity: 1;
}

.hover-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
}

.hover-tag {
    font-size: 9px;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.2);
    color: white;
}

.hover-tag.character {
    background: rgba(255, 182, 193, 0.4);
}

.hover-tag.copyright {
    background: rgba(147, 112, 219, 0.4);
}

/* Rating Indicator */
.thumbnail .rating-dot {
    position: absolute;
    top: 6px;
    left: 6px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 1px solid rgba(0,0,0,0.3);
}

.thumbnail .rating-dot.general { background: #22c55e; }
.thumbnail .rating-dot.sensitive { background: #eab308; }
.thumbnail .rating-dot.questionable { background: #f97316; }
.thumbnail .rating-dot.explicit { background: #ef4444; }

/* Keyboard Shortcuts Hint */
.keyboard-hint {
    position: fixed;
    bottom: var(--spacing-md);
    right: var(--spacing-md);
    padding: var(--spacing-xs) var(--spacing-md);
    background: var(--bg-secondary);
    border: var(--border-width) solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.keyboard-hint kbd {
    padding: 2px 6px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
}

/* Responsive */
@media (max-width: 1024px) {
    .filter-sidebar {
        position: fixed;
        left: 0;
        top: 48px;
        bottom: 0;
        z-index: 100;
        box-shadow: var(--shadow-xl);
    }
    
    .filter-sidebar.collapsed {
        transform: translateX(-100%);
    }
}
```

### static/js/gallery.js (new file)

```javascript
// Gallery Page Enhancements

(function() {
    'use strict';
    
    // State
    const state = {
        gridSize: localStorage.getItem('gallery-grid-size') || 'medium',
        sidebarOpen: localStorage.getItem('gallery-sidebar') !== 'false',
        activeFilters: [],
        recentSearches: JSON.parse(localStorage.getItem('recent-searches') || '[]'),
        focusedIndex: -1
    };
    
    // Elements
    const els = {
        gallery: document.querySelector('.gallery'),
        filterSidebar: document.querySelector('.filter-sidebar'),
        sidebarToggle: document.getElementById('sidebarToggle'),
        gridSizeBtns: document.querySelectorAll('.grid-size-btn'),
        filterItems: document.querySelectorAll('.filter-item'),
        activeFiltersBar: document.querySelector('.active-filters-bar'),
        searchInput: document.querySelector('.search-bar input'),
        thumbnails: document.querySelectorAll('.thumbnail')
    };
    
    // Quick filter definitions
    const quickFilters = {
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
    
    // Initialize
    function init() {
        setGridSize(state.gridSize);
        setSidebarOpen(state.sidebarOpen);
        renderFilterSidebar();
        bindEvents();
    }
    
    // Grid Size
    function setGridSize(size) {
        state.gridSize = size;
        els.gallery?.classList.remove('grid-small', 'grid-medium', 'grid-large');
        els.gallery?.classList.add(`grid-${size}`);
        
        els.gridSizeBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.size === size);
        });
        
        localStorage.setItem('gallery-grid-size', size);
    }
    
    // Sidebar
    function setSidebarOpen(open) {
        state.sidebarOpen = open;
        els.filterSidebar?.classList.toggle('collapsed', !open);
        els.sidebarToggle?.classList.toggle('active', open);
        localStorage.setItem('gallery-sidebar', open);
    }
    
    function toggleSidebar() {
        setSidebarOpen(!state.sidebarOpen);
    }
    
    // Filters
    function addFilter(query) {
        if (!state.activeFilters.includes(query)) {
            state.activeFilters.push(query);
            updateActiveFiltersBar();
            applyFilters();
        }
    }
    
    function removeFilter(query) {
        state.activeFilters = state.activeFilters.filter(f => f !== query);
        updateActiveFiltersBar();
        applyFilters();
    }
    
    function clearFilters() {
        state.activeFilters = [];
        updateActiveFiltersBar();
        applyFilters();
    }
    
    function updateActiveFiltersBar() {
        if (!els.activeFiltersBar) return;
        
        if (state.activeFilters.length === 0) {
            els.activeFiltersBar.innerHTML = '';
            return;
        }
        
        els.activeFiltersBar.innerHTML = `
            <span class="filters-label">Filters:</span>
            ${state.activeFilters.map(f => `
                <span class="filter-chip">
                    ${f}
                    <span class="remove" data-filter="${f}">✕</span>
                </span>
            `).join('')}
            <button class="clear-filters">Clear all</button>
            <span class="results-count">${document.querySelectorAll('.thumbnail:not([style*="display: none"])').length} results</span>
        `;
        
        // Bind remove buttons
        els.activeFiltersBar.querySelectorAll('.remove').forEach(btn => {
            btn.addEventListener('click', () => removeFilter(btn.dataset.filter));
        });
        
        els.activeFiltersBar.querySelector('.clear-filters')?.addEventListener('click', clearFilters);
    }
    
    function applyFilters() {
        // Update URL and reload, or filter client-side
        const query = state.activeFilters.join(' ');
        if (query) {
            window.location.href = `/?query=${encodeURIComponent(query)}`;
        } else {
            window.location.href = '/';
        }
    }
    
    // Render filter sidebar
    function renderFilterSidebar() {
        if (!els.filterSidebar) return;
        
        let html = '';
        
        // Rating section
        html += `
            <div class="filter-section" data-section="rating">
                <div class="filter-section-header">
                    <span><span class="icon">⭐</span> Rating</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.rating.map(f => `
                        <div class="filter-item" data-query="${f.query}">
                            <span class="dot" style="background: ${f.color}"></span>
                            <span>${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        // Source section
        html += `
            <div class="filter-section collapsed" data-section="source">
                <div class="filter-section-header">
                    <span><span class="icon">📚</span> Source</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.source.map(f => `
                        <div class="filter-item" data-query="${f.query}">
                            <span>${f.label}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
        
        // Special section
        html += `
            <div class="filter-section collapsed" data-section="special">
                <div class="filter-section-header">
                    <span><span class="icon">🔧</span> Special</span>
                    <span class="arrow">▼</span>
                </div>
                <div class="filter-section-content">
                    ${quickFilters.special.map(f => `
                        <div class="filter-item" data-query="${f.query}">
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
                            <div class="filter-item" data-search="${s}">
                                <span>${s}</span>
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
            item.addEventListener('click', () => addFilter(item.dataset.query));
        });
        
        // Bind recent search items
        els.filterSidebar.querySelectorAll('.filter-item[data-search]').forEach(item => {
            item.addEventListener('click', () => {
                window.location.href = `/?query=${encodeURIComponent(item.dataset.search)}`;
            });
        });
    }
    
    // Save search to recent
    function saveRecentSearch(query) {
        if (!query) return;
        
        state.recentSearches = state.recentSearches.filter(s => s !== query);
        state.recentSearches.unshift(query);
        state.recentSearches = state.recentSearches.slice(0, 10);
        
        localStorage.setItem('recent-searches', JSON.stringify(state.recentSearches));
    }
    
    // Keyboard navigation
    function handleKeyboard(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        const thumbnails = Array.from(document.querySelectorAll('.thumbnail'));
        
        switch(e.key) {
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
            case 'Enter':
                if (state.focusedIndex >= 0 && thumbnails[state.focusedIndex]) {
                    thumbnails[state.focusedIndex].querySelector('a')?.click();
                }
                break;
            case '/':
                e.preventDefault();
                els.searchInput?.focus();
                break;
            case 'Escape':
                els.searchInput?.blur();
                break;
        }
    }
    
    function focusThumbnail(thumb) {
        if (!thumb) return;
        
        document.querySelectorAll('.thumbnail.focused').forEach(t => t.classList.remove('focused'));
        thumb.classList.add('focused');
        thumb.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
    // Bind events
    function bindEvents() {
        // Grid size buttons
        els.gridSizeBtns.forEach(btn => {
            btn.addEventListener('click', () => setGridSize(btn.dataset.size));
        });
        
        // Sidebar toggle
        els.sidebarToggle?.addEventListener('click', toggleSidebar);
        
        // Keyboard
        document.addEventListener('keydown', handleKeyboard);
        
        // Save search on form submit
        document.querySelector('.search-bar form')?.addEventListener('submit', () => {
            saveRecentSearch(els.searchInput?.value);
        });
    }
    
    // Initialize
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
```

### templates/index.html

Add body class and new structure:

```html
<body class="gallery-page">
    {% include 'header.html' %}
    
    <!-- Active Filters Bar -->
    <div class="active-filters-bar" id="activeFiltersBar">
        <!-- Populated by JS -->
    </div>
    
    <div class="gallery-layout">
        <!-- Filter Sidebar -->
        <div class="filter-sidebar" id="filterSidebar">
            <!-- Populated by JS -->
        </div>
        
        <!-- Gallery Content -->
        <div class="gallery-content">
            <div class="gallery grid-medium" id="gallery">
                {% for image in images %}
                <div class="thumbnail skeleton" data-image-path="{{ image.path }}">
                    <!-- Existing thumbnail content -->
                    
                    <!-- Add hover overlay -->
                    <div class="hover-overlay">
                        <div class="hover-tags">
                            <!-- JS can populate this -->
                        </div>
                    </div>
                    
                    <!-- Add rating dot -->
                    <div class="rating-dot general"></div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    
    <!-- Keyboard hint -->
    <div class="keyboard-hint">
        <kbd>J</kbd>/<kbd>K</kbd> navigate • <kbd>Enter</kbd> open • <kbd>/</kbd> search
    </div>
    
    <script src="{{ url_for('static', filename='js/gallery.js') }}"></script>
</body>
```

### Modify header.html for gallery page

Add header controls:

```html
{% if request.endpoint == 'main.home' %}
<div class="header-controls">
    <div class="grid-size-toggle">
        <button class="grid-size-btn" data-size="small">S</button>
        <button class="grid-size-btn active" data-size="medium">M</button>
        <button class="grid-size-btn" data-size="large">L</button>
    </div>
    <button class="header-btn" id="sidebarToggle" title="Toggle filters">◧</button>
    <a href="/random" class="header-btn" title="Random image">🎲</a>
</div>
{% endif %}
```

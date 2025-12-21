# Tag Browser Overhaul - Implementation Guide

## Overview

This guide details the redesign of the Tag Browser (`/tags`) to become a comprehensive Tag Management interface that incorporates tag categorization functionality.

### Current Problems

| Issue | Impact |
|-------|--------|
| Tag browser is just a flat list | Not useful for management tasks |
| Tag categorization is separate page | Context switching, duplicated UI |
| No sample image preview | Hard to understand what a tag represents |
| No bulk operations | Tedious to manage many tags |
| No relationship visibility | Can't see implications or aliases |
| Can't find problem tags easily | Orphaned, uncategorized tags hidden |
| No keyboard shortcuts | Slow for power users |

### Solution

Unified three-panel Tag Management interface:
- **Left**: Filters and quick actions
- **Center**: Tag list (table or grid view)
- **Right**: Tag detail panel with preview and editing

---

## Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│ ChibiBooru › Tag Manager                    8,432 cat │ 1,203 need review│
├─────────────────┬────────────────────────────────────┬───────────────────┤
│ [Search tags..] │ Showing 847 tags           [≡] [⊞] │ tag_name          │
├─────────────────┼────────────────────────────────────┤ 1,234 images      │
│ ▼ Status        │ ☐ │ tag_name    │ cat  │ ext │ ### │                   │
│   ● All (9635)  │ ☐ │ 1girl       │ gen  │ Sub │4521 │ Sample Images     │
│   ○ Uncateg.    │ ☐ │ blue_hair   │ gen  │ Hair│1243 │ ┌───┐┌───┐┌───┐  │
│   ○ Needs Ext.  │ ☐ │ sitting     │ gen  │  —  │ 876 │ │   ││   ││   │  │
│   ○ Orphaned    │ ☐ │ smile       │ gen  │  —  │2341 │ └───┘└───┘└───┘  │
│                 │                                    │                   │
│ ▼ Category      │                                    │ Base Category     │
│   ☐ Character   │                                    │ [general     ▼]   │
│   ☐ Copyright   │                                    │                   │
│   ☐ Artist      │                                    │ Extended Cat.     │
│   ☐ General     │                                    │ [— Not set — ▼]   │
│                 │                                    │                   │
│ ▶ Extended      │                                    │ Implications      │
│ ▶ Sort By       │                                    │ tag → parent_tag  │
│                 │                                    │                   │
│ ─────────────── │                                    │ [Rename] [Merge]  │
│ ⚡ Auto-Categ.  │                                    │ [Delete]          │
│ 🔗 Implications │                                    │                   │
└─────────────────┴────────────────────────────────────┴───────────────────┘
│ ↑↓ navigate │ Space select │ 1-9 set category │ E edit │ D delete │ ?   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Files to Create/Modify

### New Files
- `static/css/tag-browser.css` - Dedicated styles
- `static/js/pages/tag-browser.js` - Page logic module

### Modified Files
- `templates/tags.html` - Complete rewrite
- `routers/web.py` - Minor updates to route
- `routers/api/tags.py` - New endpoints for tag management

---

## Template: `templates/tags.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Tag Manager - {{ app_name }}</title>
    <link rel="icon" href="{{ url_for('static', filename='favicon.svg') }}" type="image/svg+xml">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/variables.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/base.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/components.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/tag-browser.css') }}">
</head>
<body class="tag-browser-page">
    <!-- Compact Header -->
    <header class="tb-header">
        <div class="tb-header-left">
            <a href="{{ url_for('main.home') }}" class="tb-logo">{{ app_name }}</a>
            <span class="tb-breadcrumb">›</span>
            <span class="tb-title">Tag Manager</span>
        </div>
        <div class="tb-header-right">
            <div class="tb-quick-stats">
                <span class="stat"><span class="value" id="statCategorized">—</span> categorized</span>
                <span class="stat warning"><span class="value" id="statUncategorized">—</span> need review</span>
            </div>
            <div class="tb-header-actions">
                <button class="icon-btn" id="importBtn" title="Import categorizations">
                    <span class="icon">📥</span>
                </button>
                <button class="icon-btn" id="exportBtn" title="Export categorizations">
                    <span class="icon">📤</span>
                </button>
            </div>
        </div>
    </header>
    
    <!-- Bulk Actions Bar (hidden by default) -->
    <div class="tb-bulk-bar" id="bulkBar" style="display: none;">
        <span class="bulk-count"><span id="selectedCount">0</span> tags selected</span>
        <div class="bulk-actions">
            <button class="bulk-btn" id="bulkSetCategory">
                <span class="icon">🏷️</span> Set Category
            </button>
            <button class="bulk-btn" id="bulkSetExtended">
                <span class="icon">📁</span> Set Extended
            </button>
            <button class="bulk-btn" id="bulkMerge">
                <span class="icon">🔀</span> Merge
            </button>
            <button class="bulk-btn danger" id="bulkDelete">
                <span class="icon">🗑️</span> Delete
            </button>
        </div>
        <div class="bulk-selection">
            <button class="text-btn" id="selectAll">Select all visible</button>
            <button class="text-btn" id="clearSelection">Clear</button>
        </div>
    </div>
    
    <!-- Main Layout -->
    <div class="tb-layout">
        <!-- Left Panel: Filters -->
        <aside class="tb-filters" id="filtersPanel">
            <!-- Search -->
            <div class="tb-search">
                <span class="search-icon">🔍</span>
                <input type="text" id="tagSearch" placeholder="Search tags...">
            </div>
            
            <!-- Status Filter -->
            <div class="filter-section" data-section="status">
                <button class="filter-header">
                    <span>Status</span>
                    <span class="arrow">▼</span>
                </button>
                <div class="filter-content">
                    <label class="filter-option">
                        <input type="radio" name="status" value="all" checked>
                        <span class="label">All Tags</span>
                        <span class="count" id="countAll">—</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="status" value="uncategorized">
                        <span class="label">Uncategorized</span>
                        <span class="count warning" id="countUncategorized">—</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="status" value="needs_extended">
                        <span class="label">Needs Extended</span>
                        <span class="count" id="countNeedsExtended">—</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="status" value="orphaned">
                        <span class="label">Unused (0 images)</span>
                        <span class="count danger" id="countOrphaned">—</span>
                    </label>
                </div>
            </div>
            
            <!-- Base Category Filter -->
            <div class="filter-section" data-section="category">
                <button class="filter-header">
                    <span>Category</span>
                    <span class="arrow">▼</span>
                </button>
                <div class="filter-content">
                    <label class="filter-option" data-category="character">
                        <input type="checkbox" name="category" value="character">
                        <span class="dot" style="--color: var(--tag-character)"></span>
                        <span class="label">Character</span>
                    </label>
                    <label class="filter-option" data-category="copyright">
                        <input type="checkbox" name="category" value="copyright">
                        <span class="dot" style="--color: var(--tag-copyright)"></span>
                        <span class="label">Copyright</span>
                    </label>
                    <label class="filter-option" data-category="artist">
                        <input type="checkbox" name="category" value="artist">
                        <span class="dot" style="--color: var(--tag-artist)"></span>
                        <span class="label">Artist</span>
                    </label>
                    <label class="filter-option" data-category="species">
                        <input type="checkbox" name="category" value="species">
                        <span class="dot" style="--color: var(--tag-species)"></span>
                        <span class="label">Species</span>
                    </label>
                    <label class="filter-option" data-category="meta">
                        <input type="checkbox" name="category" value="meta">
                        <span class="dot" style="--color: var(--tag-meta)"></span>
                        <span class="label">Meta</span>
                    </label>
                    <label class="filter-option" data-category="general">
                        <input type="checkbox" name="category" value="general">
                        <span class="dot" style="--color: var(--tag-general)"></span>
                        <span class="label">General</span>
                    </label>
                </div>
            </div>
            
            <!-- Extended Category Filter (collapsed by default) -->
            <div class="filter-section collapsed" data-section="extended">
                <button class="filter-header">
                    <span>Extended Category</span>
                    <span class="arrow">▼</span>
                </button>
                <div class="filter-content scrollable" id="extendedFilters">
                    <!-- Populated by JavaScript from API -->
                </div>
            </div>
            
            <!-- Sort -->
            <div class="filter-section collapsed" data-section="sort">
                <button class="filter-header">
                    <span>Sort By</span>
                    <span class="arrow">▼</span>
                </button>
                <div class="filter-content">
                    <label class="filter-option">
                        <input type="radio" name="sort" value="count_desc" checked>
                        <span class="label">Count (High → Low)</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="sort" value="count_asc">
                        <span class="label">Count (Low → High)</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="sort" value="alpha_asc">
                        <span class="label">Name (A → Z)</span>
                    </label>
                    <label class="filter-option">
                        <input type="radio" name="sort" value="alpha_desc">
                        <span class="label">Name (Z → A)</span>
                    </label>
                </div>
            </div>
            
            <!-- Quick Actions -->
            <div class="filter-actions">
                <button class="action-btn" id="autoCategorizeBtn">
                    <span class="icon">⚡</span> Auto-Categorize
                </button>
                <a href="{{ url_for('main.implications_manager') }}" class="action-btn">
                    <span class="icon">🔗</span> Implications
                </a>
            </div>
        </aside>
        
        <!-- Center Panel: Tag List -->
        <main class="tb-list">
            <!-- List Header -->
            <div class="tb-list-header">
                <span class="list-count">
                    Showing <span id="visibleCount">—</span> tags
                </span>
                <div class="list-controls">
                    <div class="view-toggle">
                        <button class="view-btn active" data-view="list" title="List view">≡</button>
                        <button class="view-btn" data-view="grid" title="Grid view">⊞</button>
                    </div>
                    <button class="icon-btn" id="toggleDetail" title="Toggle detail panel">
                        <span class="icon">👁</span>
                    </button>
                </div>
            </div>
            
            <!-- List View (default) -->
            <div class="tb-table-container" id="listView">
                <table class="tb-table">
                    <thead>
                        <tr>
                            <th class="col-checkbox">
                                <input type="checkbox" id="selectAllCheckbox">
                            </th>
                            <th class="col-name">Tag Name</th>
                            <th class="col-category">Category</th>
                            <th class="col-extended">Extended</th>
                            <th class="col-count">Count</th>
                            <th class="col-actions"></th>
                        </tr>
                    </thead>
                    <tbody id="tagTableBody">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>
                
                <!-- Loading / Load More -->
                <div class="load-more" id="loadMore">
                    <button class="load-more-btn" id="loadMoreBtn">Load more tags...</button>
                </div>
            </div>
            
            <!-- Grid View (hidden by default) -->
            <div class="tb-grid-container" id="gridView" style="display: none;">
                <div class="tb-grid" id="tagGrid">
                    <!-- Populated by JavaScript -->
                </div>
            </div>
        </main>
        
        <!-- Right Panel: Tag Detail -->
        <aside class="tb-detail" id="detailPanel">
            <!-- Empty State -->
            <div class="detail-empty" id="detailEmpty">
                <p>Select a tag to view details</p>
            </div>
            
            <!-- Detail Content (hidden by default) -->
            <div class="detail-content" id="detailContent" style="display: none;">
                <!-- Header -->
                <div class="detail-header">
                    <div class="detail-title">
                        <h2 id="detailTagName">—</h2>
                        <p id="detailTagCount">— images</p>
                    </div>
                    <button class="close-btn" id="closeDetail">✕</button>
                </div>
                
                <!-- Sample Images -->
                <div class="detail-section">
                    <h3>Sample Images</h3>
                    <div class="sample-grid" id="sampleImages">
                        <!-- 6 sample image slots -->
                    </div>
                    <a href="#" class="view-all-link" id="viewAllLink">View all images →</a>
                </div>
                
                <!-- Category Editor -->
                <div class="detail-section">
                    <h3>Base Category</h3>
                    <select id="detailCategory" class="detail-select">
                        <option value="character">Character</option>
                        <option value="copyright">Copyright</option>
                        <option value="artist">Artist</option>
                        <option value="species">Species</option>
                        <option value="meta">Meta</option>
                        <option value="general">General</option>
                    </select>
                </div>
                
                <!-- Extended Category Editor -->
                <div class="detail-section">
                    <h3>Extended Category</h3>
                    <select id="detailExtended" class="detail-select">
                        <option value="">— Not set —</option>
                        <!-- Populated by JavaScript -->
                    </select>
                    <p class="detail-hint">
                        Press <kbd>1</kbd>-<kbd>9</kbd> or <kbd>Q</kbd>-<kbd>Z</kbd> to quick-assign
                    </p>
                </div>
                
                <!-- Implications -->
                <div class="detail-section">
                    <h3>Implications</h3>
                    <div class="implications-list" id="implicationsList">
                        <!-- Populated by JavaScript -->
                    </div>
                    <button class="add-btn" id="addImplication">+ Add implication</button>
                </div>
                
                <!-- Aliases -->
                <div class="detail-section">
                    <h3>Aliases</h3>
                    <div class="aliases-list" id="aliasesList">
                        <span class="empty-text">No aliases</span>
                    </div>
                    <button class="add-btn" id="addAlias">+ Add alias</button>
                </div>
                
                <!-- Actions -->
                <div class="detail-actions">
                    <button class="action-btn" id="renameTag">
                        <span class="icon">✏️</span> Rename
                    </button>
                    <button class="action-btn" id="mergeTag">
                        <span class="icon">🔀</span> Merge Into...
                    </button>
                    <button class="action-btn danger" id="deleteTag">
                        <span class="icon">🗑️</span> Delete
                    </button>
                </div>
            </div>
        </aside>
    </div>
    
    <!-- Keyboard Shortcuts Bar -->
    <footer class="tb-shortcuts">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>Space</kbd> select</span>
        <span><kbd>1-9</kbd> set extended</span>
        <span><kbd>E</kbd> edit</span>
        <span><kbd>D</kbd> delete</span>
        <span><kbd>/</kbd> search</span>
        <span><kbd>?</kbd> all shortcuts</span>
    </footer>
    
    <!-- Modals -->
    <div id="modalContainer"></div>
    
    <script type="module" src="{{ url_for('static', filename='js/pages/tag-browser.js') }}"></script>
</body>
</html>
```

---

## Styles: `static/css/tag-browser.css`

```css
/* ============================================================================
   TAG BROWSER PAGE
   ============================================================================ */

.tag-browser-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg-primary);
}

/* Header */
.tb-header {
    flex-shrink: 0;
    height: 48px;
    background: var(--bg-secondary);
    border-bottom: var(--border-width) solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--spacing-lg);
}

.tb-header-left {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
}

.tb-logo {
    color: var(--primary-blue);
    font-weight: var(--font-weight-semibold);
    text-decoration: none;
}

.tb-breadcrumb {
    color: var(--text-muted);
}

.tb-title {
    color: var(--text-primary);
    font-weight: var(--font-weight-medium);
}

.tb-header-right {
    display: flex;
    align-items: center;
    gap: var(--spacing-lg);
}

.tb-quick-stats {
    display: flex;
    gap: var(--spacing-lg);
    font-size: var(--font-size-xs);
}

.tb-quick-stats .stat {
    color: var(--text-muted);
}

.tb-quick-stats .stat .value {
    font-weight: var(--font-weight-semibold);
    color: var(--success);
}

.tb-quick-stats .stat.warning .value {
    color: var(--warning);
}

.tb-header-actions {
    display: flex;
    gap: var(--spacing-xs);
}

.icon-btn {
    padding: var(--spacing-xs);
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.icon-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.icon-btn .icon {
    font-size: 1rem;
}

/* Bulk Actions Bar */
.tb-bulk-bar {
    flex-shrink: 0;
    background: rgba(59, 130, 246, 0.1);
    border-bottom: 1px solid rgba(59, 130, 246, 0.3);
    padding: var(--spacing-sm) var(--spacing-lg);
    display: flex;
    align-items: center;
    gap: var(--spacing-lg);
}

.bulk-count {
    font-size: var(--font-size-sm);
    color: var(--primary-blue);
}

.bulk-count span {
    font-weight: var(--font-weight-semibold);
}

.bulk-actions {
    display: flex;
    gap: var(--spacing-sm);
}

.bulk-btn {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: var(--spacing-xs) var(--spacing-sm);
    background: var(--bg-tertiary);
    border: none;
    border-radius: var(--radius-md);
    font-size: var(--font-size-xs);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.bulk-btn:hover {
    background: var(--bg-secondary);
    color: var(--text-primary);
}

.bulk-btn.danger {
    background: rgba(239, 68, 68, 0.2);
    color: var(--danger);
}

.bulk-btn.danger:hover {
    background: rgba(239, 68, 68, 0.3);
}

.bulk-selection {
    margin-left: auto;
    display: flex;
    gap: var(--spacing-md);
}

.text-btn {
    background: none;
    border: none;
    font-size: var(--font-size-xs);
    color: var(--text-muted);
    cursor: pointer;
}

.text-btn:hover {
    color: var(--text-secondary);
}

/* Main Layout */
.tb-layout {
    flex: 1;
    display: flex;
    overflow: hidden;
}

/* Filters Panel */
.tb-filters {
    width: 220px;
    flex-shrink: 0;
    background: var(--bg-secondary);
    border-right: var(--border-width) solid var(--border-color);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.tb-search {
    flex-shrink: 0;
    position: relative;
    padding: var(--spacing-md);
}

.tb-search .search-icon {
    position: absolute;
    left: calc(var(--spacing-md) + 10px);
    top: 50%;
    transform: translateY(-50%);
    font-size: 0.875rem;
    pointer-events: none;
}

.tb-search input {
    width: 100%;
    padding: var(--spacing-sm) var(--spacing-sm) var(--spacing-sm) 36px;
    background: var(--bg-tertiary);
    border: var(--border-width) solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--font-size-sm);
}

.tb-search input:focus {
    outline: none;
    border-color: var(--primary-blue);
}

/* Filter Sections */
.filter-section {
    border-bottom: var(--border-width) solid var(--border-color);
}

.filter-header {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-sm) var(--spacing-md);
    background: none;
    border: none;
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    cursor: pointer;
}

.filter-header:hover {
    color: var(--text-secondary);
}

.filter-header .arrow {
    font-size: 0.625rem;
    transition: transform 0.2s;
}

.filter-section.collapsed .filter-header .arrow {
    transform: rotate(-90deg);
}

.filter-content {
    padding: 0 var(--spacing-md) var(--spacing-md);
}

.filter-section.collapsed .filter-content {
    display: none;
}

.filter-content.scrollable {
    max-height: 200px;
    overflow-y: auto;
}

.filter-option {
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

.filter-option:hover {
    background: var(--bg-tertiary);
}

.filter-option input {
    margin: 0;
}

.filter-option .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color);
}

.filter-option .label {
    flex: 1;
}

.filter-option .count {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.filter-option .count.warning {
    color: var(--warning);
}

.filter-option .count.danger {
    color: var(--danger);
}

/* Filter Actions */
.filter-actions {
    padding: var(--spacing-md);
    margin-top: auto;
    border-top: var(--border-width) solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
}

.action-btn {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-md);
    background: transparent;
    border: none;
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    cursor: pointer;
    text-decoration: none;
    transition: all var(--transition-normal);
}

.action-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.action-btn .icon {
    font-size: 1rem;
}

/* Tag List Panel */
.tb-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-width: 0;
}

.tb-list-header {
    flex-shrink: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--bg-secondary);
    border-bottom: var(--border-width) solid var(--border-color);
}

.list-count {
    font-size: var(--font-size-sm);
    color: var(--text-muted);
}

.list-count span {
    color: var(--text-primary);
    font-weight: var(--font-weight-medium);
}

.list-controls {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
}

.view-toggle {
    display: flex;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    padding: 2px;
}

.view-btn {
    padding: 4px 8px;
    background: transparent;
    border: none;
    border-radius: var(--radius-xs);
    color: var(--text-muted);
    cursor: pointer;
    font-size: 0.875rem;
}

.view-btn.active {
    background: var(--bg-secondary);
    color: var(--text-primary);
}

/* Table View */
.tb-table-container {
    flex: 1;
    overflow-y: auto;
}

.tb-table {
    width: 100%;
    border-collapse: collapse;
}

.tb-table thead {
    position: sticky;
    top: 0;
    background: var(--bg-secondary);
    z-index: 10;
}

.tb-table th {
    padding: var(--spacing-sm) var(--spacing-md);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    color: var(--text-muted);
    text-transform: uppercase;
    text-align: left;
    border-bottom: var(--border-width) solid var(--border-color);
}

.tb-table td {
    padding: var(--spacing-sm) var(--spacing-md);
    border-bottom: var(--border-width) solid var(--border-color);
}

.tb-table tbody tr {
    cursor: pointer;
    transition: background var(--transition-normal);
}

.tb-table tbody tr:hover {
    background: var(--bg-tertiary);
}

.tb-table tbody tr.selected {
    background: rgba(59, 130, 246, 0.1);
}

.col-checkbox {
    width: 40px;
}

.col-name {
    min-width: 200px;
}

.col-category {
    width: 100px;
}

.col-extended {
    width: 140px;
}

.col-count {
    width: 80px;
    text-align: right;
}

.col-actions {
    width: 40px;
}

/* Tag Name Cell */
.tag-name-cell {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
}

.tag-name-cell .name {
    color: var(--text-primary);
    font-weight: var(--font-weight-medium);
}

.tag-name-cell .badge {
    padding: 2px 6px;
    font-size: var(--font-size-xs);
    border-radius: var(--radius-sm);
    font-weight: var(--font-weight-medium);
}

.tag-name-cell .badge.needs-review {
    background: rgba(251, 146, 60, 0.2);
    color: var(--warning);
}

/* Category Badge */
.category-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: var(--radius-md);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-medium);
}

.category-badge.character {
    background: var(--tag-character-bg);
    color: var(--tag-character);
}

.category-badge.copyright {
    background: var(--tag-copyright-bg);
    color: var(--tag-copyright);
}

.category-badge.artist {
    background: var(--tag-artist-bg);
    color: var(--tag-artist);
}

.category-badge.species {
    background: var(--tag-species-bg);
    color: var(--tag-species);
}

.category-badge.meta {
    background: var(--tag-meta-bg);
    color: var(--tag-meta);
}

.category-badge.general {
    background: var(--tag-general-bg);
    color: var(--tag-general);
}

/* Extended Category */
.extended-text {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.extended-text.empty {
    color: var(--text-muted);
    opacity: 0.5;
}

/* Count */
.count-text {
    font-size: var(--font-size-sm);
    color: var(--text-secondary);
    font-family: var(--font-mono);
}

/* Load More */
.load-more {
    padding: var(--spacing-lg);
    text-align: center;
}

.load-more-btn {
    padding: var(--spacing-sm) var(--spacing-xl);
    background: var(--bg-tertiary);
    border: var(--border-width) solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.load-more-btn:hover {
    background: var(--bg-secondary);
    border-color: var(--primary-blue);
    color: var(--primary-blue);
}

/* Grid View */
.tb-grid-container {
    flex: 1;
    overflow-y: auto;
    padding: var(--spacing-md);
}

.tb-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: var(--spacing-sm);
}

.grid-tag-card {
    padding: var(--spacing-md);
    background: var(--bg-tertiary);
    border: var(--border-width) solid var(--border-color);
    border-radius: var(--radius-lg);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.grid-tag-card:hover {
    border-color: var(--border-color-hover);
}

.grid-tag-card.selected {
    border-color: var(--primary-blue);
    background: rgba(59, 130, 246, 0.1);
}

.grid-tag-card .card-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm);
}

.grid-tag-card .tag-name {
    font-weight: var(--font-weight-medium);
    color: var(--text-primary);
    font-size: var(--font-size-sm);
}

.grid-tag-card .card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.grid-tag-card .count {
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

/* Detail Panel */
.tb-detail {
    width: 320px;
    flex-shrink: 0;
    background: var(--bg-secondary);
    border-left: var(--border-width) solid var(--border-color);
    overflow-y: auto;
}

.detail-empty {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-style: italic;
}

.detail-content {
    padding: var(--spacing-lg);
}

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: var(--spacing-lg);
}

.detail-title h2 {
    margin: 0;
    font-size: var(--font-size-lg);
    color: var(--text-primary);
    word-break: break-all;
}

.detail-title p {
    margin: var(--spacing-xs) 0 0;
    font-size: var(--font-size-sm);
    color: var(--text-muted);
}

.close-btn {
    padding: 4px 8px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 1rem;
}

.close-btn:hover {
    color: var(--text-primary);
}

/* Detail Sections */
.detail-section {
    margin-bottom: var(--spacing-lg);
}

.detail-section h3 {
    margin: 0 0 var(--spacing-sm);
    font-size: var(--font-size-xs);
    font-weight: var(--font-weight-semibold);
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Sample Images Grid */
.sample-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
}

.sample-grid .sample-img {
    aspect-ratio: 1;
    background: var(--bg-tertiary);
    border-radius: var(--radius-md);
    overflow: hidden;
}

.sample-grid .sample-img img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.view-all-link {
    display: inline-block;
    margin-top: var(--spacing-sm);
    font-size: var(--font-size-xs);
    color: var(--primary-blue);
    text-decoration: none;
}

.view-all-link:hover {
    text-decoration: underline;
}

/* Detail Select */
.detail-select {
    width: 100%;
    padding: var(--spacing-sm) var(--spacing-md);
    background: var(--bg-tertiary);
    border: var(--border-width) solid var(--border-color);
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--font-size-sm);
}

.detail-select:focus {
    outline: none;
    border-color: var(--primary-blue);
}

.detail-hint {
    margin-top: var(--spacing-xs);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.detail-hint kbd {
    padding: 2px 6px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
}

/* Implications & Aliases Lists */
.implications-list,
.aliases-list {
    font-size: var(--font-size-sm);
}

.implication-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: var(--spacing-xs) 0;
    color: var(--text-secondary);
}

.implication-item .arrow {
    color: var(--text-muted);
}

.implication-item .tag {
    color: var(--primary-blue);
}

.empty-text {
    color: var(--text-muted);
    font-style: italic;
}

.add-btn {
    margin-top: var(--spacing-xs);
    padding: 0;
    background: none;
    border: none;
    font-size: var(--font-size-xs);
    color: var(--primary-blue);
    cursor: pointer;
}

.add-btn:hover {
    text-decoration: underline;
}

/* Detail Actions */
.detail-actions {
    padding-top: var(--spacing-lg);
    border-top: var(--border-width) solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
}

.detail-actions .action-btn {
    justify-content: center;
    background: var(--bg-tertiary);
    border: var(--border-width) solid var(--border-color);
}

.detail-actions .action-btn:hover {
    border-color: var(--border-color-hover);
}

.detail-actions .action-btn.danger {
    background: rgba(239, 68, 68, 0.1);
    border-color: rgba(239, 68, 68, 0.3);
    color: var(--danger);
}

.detail-actions .action-btn.danger:hover {
    background: rgba(239, 68, 68, 0.2);
}

/* Keyboard Shortcuts Bar */
.tb-shortcuts {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: var(--spacing-lg);
    padding: var(--spacing-xs) var(--spacing-lg);
    background: var(--bg-secondary);
    border-top: var(--border-width) solid var(--border-color);
    font-size: var(--font-size-xs);
    color: var(--text-muted);
}

.tb-shortcuts kbd {
    padding: 2px 6px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    font-family: var(--font-mono);
    margin-right: 4px;
}

/* Responsive */
@media (max-width: 1200px) {
    .tb-detail {
        position: fixed;
        right: 0;
        top: 48px;
        bottom: 0;
        z-index: 100;
        box-shadow: var(--shadow-xl);
        transform: translateX(100%);
        transition: transform 0.2s ease;
    }
    
    .tb-detail.open {
        transform: translateX(0);
    }
}

@media (max-width: 768px) {
    .tb-filters {
        position: fixed;
        left: 0;
        top: 48px;
        bottom: 0;
        z-index: 100;
        box-shadow: var(--shadow-xl);
        transform: translateX(-100%);
        transition: transform 0.2s ease;
    }
    
    .tb-filters.open {
        transform: translateX(0);
    }
    
    .tb-shortcuts {
        display: none;
    }
}
```

---

## JavaScript: `static/js/pages/tag-browser.js`

```javascript
// Tag Browser Page Module

const TagBrowser = (function() {
    'use strict';
    
    // State
    const state = {
        tags: [],
        selectedTag: null,
        selectedTags: new Set(),
        filters: {
            search: '',
            status: 'all',
            categories: [],
            extendedCategories: [],
            sort: 'count_desc'
        },
        pagination: {
            offset: 0,
            limit: 100,
            hasMore: true
        },
        viewMode: 'list',
        extendedCategories: [],
        loading: false
    };
    
    // DOM Elements
    let els = {};
    
    // Initialize
    async function init() {
        cacheElements();
        bindEvents();
        await loadExtendedCategories();
        await loadStats();
        await loadTags();
    }
    
    function cacheElements() {
        els = {
            // Search
            tagSearch: document.getElementById('tagSearch'),
            
            // Filters
            statusFilters: document.querySelectorAll('input[name="status"]'),
            categoryFilters: document.querySelectorAll('input[name="category"]'),
            sortFilters: document.querySelectorAll('input[name="sort"]'),
            extendedFiltersContainer: document.getElementById('extendedFilters'),
            
            // Bulk
            bulkBar: document.getElementById('bulkBar'),
            selectedCount: document.getElementById('selectedCount'),
            selectAll: document.getElementById('selectAll'),
            clearSelection: document.getElementById('clearSelection'),
            selectAllCheckbox: document.getElementById('selectAllCheckbox'),
            
            // List
            tagTableBody: document.getElementById('tagTableBody'),
            tagGrid: document.getElementById('tagGrid'),
            listView: document.getElementById('listView'),
            gridView: document.getElementById('gridView'),
            visibleCount: document.getElementById('visibleCount'),
            loadMoreBtn: document.getElementById('loadMoreBtn'),
            
            // View toggle
            viewBtns: document.querySelectorAll('.view-btn'),
            
            // Detail panel
            detailPanel: document.getElementById('detailPanel'),
            detailEmpty: document.getElementById('detailEmpty'),
            detailContent: document.getElementById('detailContent'),
            detailTagName: document.getElementById('detailTagName'),
            detailTagCount: document.getElementById('detailTagCount'),
            sampleImages: document.getElementById('sampleImages'),
            viewAllLink: document.getElementById('viewAllLink'),
            detailCategory: document.getElementById('detailCategory'),
            detailExtended: document.getElementById('detailExtended'),
            implicationsList: document.getElementById('implicationsList'),
            closeDetail: document.getElementById('closeDetail'),
            toggleDetail: document.getElementById('toggleDetail'),
            
            // Stats
            statCategorized: document.getElementById('statCategorized'),
            statUncategorized: document.getElementById('statUncategorized'),
            countAll: document.getElementById('countAll'),
            countUncategorized: document.getElementById('countUncategorized'),
            
            // Filter sections
            filterSections: document.querySelectorAll('.filter-section')
        };
    }
    
    function bindEvents() {
        // Search
        let searchTimeout;
        els.tagSearch?.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                state.filters.search = e.target.value.trim().toLowerCase();
                resetAndReload();
            }, 300);
        });
        
        // Status filters
        els.statusFilters.forEach(input => {
            input.addEventListener('change', (e) => {
                state.filters.status = e.target.value;
                resetAndReload();
            });
        });
        
        // Category filters
        els.categoryFilters.forEach(input => {
            input.addEventListener('change', () => {
                state.filters.categories = Array.from(els.categoryFilters)
                    .filter(i => i.checked)
                    .map(i => i.value);
                resetAndReload();
            });
        });
        
        // Sort filters
        els.sortFilters.forEach(input => {
            input.addEventListener('change', (e) => {
                state.filters.sort = e.target.value;
                resetAndReload();
            });
        });
        
        // Filter section toggles
        els.filterSections.forEach(section => {
            const header = section.querySelector('.filter-header');
            header?.addEventListener('click', () => {
                section.classList.toggle('collapsed');
            });
        });
        
        // View mode toggle
        els.viewBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                setViewMode(btn.dataset.view);
            });
        });
        
        // Load more
        els.loadMoreBtn?.addEventListener('click', loadMoreTags);
        
        // Bulk actions
        els.selectAll?.addEventListener('click', selectAllVisible);
        els.clearSelection?.addEventListener('click', clearSelection);
        els.selectAllCheckbox?.addEventListener('change', (e) => {
            if (e.target.checked) {
                selectAllVisible();
            } else {
                clearSelection();
            }
        });
        
        // Detail panel
        els.closeDetail?.addEventListener('click', closeDetail);
        els.toggleDetail?.addEventListener('click', toggleDetailPanel);
        
        // Category change in detail
        els.detailCategory?.addEventListener('change', async (e) => {
            if (state.selectedTag) {
                await updateTagCategory(state.selectedTag.name, e.target.value);
            }
        });
        
        // Extended category change in detail
        els.detailExtended?.addEventListener('change', async (e) => {
            if (state.selectedTag) {
                await updateTagExtendedCategory(state.selectedTag.name, e.target.value);
            }
        });
        
        // Keyboard navigation
        document.addEventListener('keydown', handleKeyboard);
    }
    
    // API Functions
    async function loadExtendedCategories() {
        try {
            const response = await fetch('/api/tag_categorize/stats');
            const data = await response.json();
            state.extendedCategories = data.extended_categories || [];
            renderExtendedFilters();
            populateExtendedDropdown();
        } catch (error) {
            console.error('Failed to load extended categories:', error);
        }
    }
    
    async function loadStats() {
        try {
            const response = await fetch('/api/tag_categorize/stats');
            const data = await response.json();
            
            els.statCategorized.textContent = data.categorized?.toLocaleString() || '—';
            els.statUncategorized.textContent = data.uncategorized?.toLocaleString() || '—';
            els.countAll.textContent = data.total_tags?.toLocaleString() || '—';
            els.countUncategorized.textContent = data.uncategorized?.toLocaleString() || '—';
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }
    
    async function loadTags(append = false) {
        if (state.loading) return;
        state.loading = true;
        
        try {
            const params = new URLSearchParams({
                offset: state.pagination.offset,
                limit: state.pagination.limit,
                search: state.filters.search,
                status: state.filters.status,
                sort: state.filters.sort
            });
            
            if (state.filters.categories.length > 0) {
                params.set('categories', state.filters.categories.join(','));
            }
            
            if (state.filters.extendedCategories.length > 0) {
                params.set('extended', state.filters.extendedCategories.join(','));
            }
            
            const response = await fetch(`/api/tags/browse?${params}`);
            const data = await response.json();
            
            if (append) {
                state.tags = [...state.tags, ...data.tags];
            } else {
                state.tags = data.tags || [];
            }
            
            state.pagination.hasMore = data.has_more;
            state.pagination.offset += data.tags?.length || 0;
            
            renderTags();
            updateVisibleCount();
            
        } catch (error) {
            console.error('Failed to load tags:', error);
        } finally {
            state.loading = false;
        }
    }
    
    function resetAndReload() {
        state.pagination.offset = 0;
        state.tags = [];
        loadTags();
    }
    
    function loadMoreTags() {
        if (state.pagination.hasMore) {
            loadTags(true);
        }
    }
    
    async function loadTagDetails(tagName) {
        try {
            const response = await fetch(`/api/tag_categorize/tag_details?tag_name=${encodeURIComponent(tagName)}`);
            return await response.json();
        } catch (error) {
            console.error('Failed to load tag details:', error);
            return null;
        }
    }
    
    async function updateTagCategory(tagName, category) {
        try {
            const response = await fetch('/api/tags/update_category', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_name: tagName, category })
            });
            
            if (response.ok) {
                // Update local state
                const tag = state.tags.find(t => t.name === tagName);
                if (tag) tag.category = category;
                renderTags();
            }
        } catch (error) {
            console.error('Failed to update tag category:', error);
        }
    }
    
    async function updateTagExtendedCategory(tagName, extendedCategory) {
        try {
            const response = await fetch('/api/tag_categorize/set', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tag_name: tagName, category: extendedCategory || null })
            });
            
            if (response.ok) {
                // Update local state
                const tag = state.tags.find(t => t.name === tagName);
                if (tag) tag.extended_category = extendedCategory || null;
                renderTags();
            }
        } catch (error) {
            console.error('Failed to update extended category:', error);
        }
    }
    
    // Render Functions
    function renderTags() {
        if (state.viewMode === 'list') {
            renderTableView();
        } else {
            renderGridView();
        }
    }
    
    function renderTableView() {
        if (!els.tagTableBody) return;
        
        els.tagTableBody.innerHTML = state.tags.map(tag => `
            <tr class="${state.selectedTag?.name === tag.name ? 'selected' : ''}" 
                data-tag="${escapeHtml(tag.name)}">
                <td class="col-checkbox">
                    <input type="checkbox" 
                           ${state.selectedTags.has(tag.name) ? 'checked' : ''}
                           onchange="TagBrowser.toggleSelection('${escapeHtml(tag.name)}')">
                </td>
                <td class="col-name">
                    <div class="tag-name-cell">
                        <span class="name">${escapeHtml(tag.name)}</span>
                        ${tag.needs_review ? '<span class="badge needs-review">needs review</span>' : ''}
                    </div>
                </td>
                <td class="col-category">
                    <span class="category-badge ${tag.category}">${tag.category}</span>
                </td>
                <td class="col-extended">
                    ${tag.extended_category 
                        ? `<span class="extended-text">${getExtendedCategoryName(tag.extended_category)}</span>`
                        : '<span class="extended-text empty">—</span>'
                    }
                </td>
                <td class="col-count">
                    <span class="count-text">${tag.usage_count?.toLocaleString() || 0}</span>
                </td>
                <td class="col-actions">
                    <button class="icon-btn" onclick="TagBrowser.showContextMenu(event, '${escapeHtml(tag.name)}')">
                        ⋮
                    </button>
                </td>
            </tr>
        `).join('');
        
        // Bind row clicks
        els.tagTableBody.querySelectorAll('tr').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'BUTTON') {
                    selectTag(row.dataset.tag);
                }
            });
        });
    }
    
    function renderGridView() {
        if (!els.tagGrid) return;
        
        els.tagGrid.innerHTML = state.tags.map(tag => `
            <div class="grid-tag-card ${state.selectedTag?.name === tag.name ? 'selected' : ''}"
                 data-tag="${escapeHtml(tag.name)}">
                <div class="card-header">
                    <span class="tag-name">${escapeHtml(tag.name)}</span>
                    <input type="checkbox"
                           ${state.selectedTags.has(tag.name) ? 'checked' : ''}
                           onchange="TagBrowser.toggleSelection('${escapeHtml(tag.name)}')">
                </div>
                <div class="card-footer">
                    <span class="category-badge ${tag.category}">${tag.category}</span>
                    <span class="count">${tag.usage_count?.toLocaleString() || 0}</span>
                </div>
            </div>
        `).join('');
        
        // Bind card clicks
        els.tagGrid.querySelectorAll('.grid-tag-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') {
                    selectTag(card.dataset.tag);
                }
            });
        });
    }
    
    function renderExtendedFilters() {
        if (!els.extendedFiltersContainer) return;
        
        els.extendedFiltersContainer.innerHTML = state.extendedCategories.map(cat => `
            <label class="filter-option">
                <input type="checkbox" name="extended" value="${cat[0]}">
                <span class="label">${cat[1]}</span>
                <span class="shortcut">${cat[2]}</span>
            </label>
        `).join('');
        
        // Bind extended filter changes
        els.extendedFiltersContainer.querySelectorAll('input').forEach(input => {
            input.addEventListener('change', () => {
                state.filters.extendedCategories = Array.from(
                    els.extendedFiltersContainer.querySelectorAll('input:checked')
                ).map(i => i.value);
                resetAndReload();
            });
        });
    }
    
    function populateExtendedDropdown() {
        if (!els.detailExtended) return;
        
        const options = state.extendedCategories.map(cat => 
            `<option value="${cat[0]}">[${cat[2]}] ${cat[1]}</option>`
        ).join('');
        
        els.detailExtended.innerHTML = `<option value="">— Not set —</option>${options}`;
    }
    
    function renderDetailPanel(tag, details) {
        if (!tag) {
            els.detailEmpty.style.display = 'flex';
            els.detailContent.style.display = 'none';
            return;
        }
        
        els.detailEmpty.style.display = 'none';
        els.detailContent.style.display = 'block';
        
        els.detailTagName.textContent = tag.name;
        els.detailTagCount.textContent = `${tag.usage_count?.toLocaleString() || 0} images`;
        els.viewAllLink.href = `/?query=${encodeURIComponent(tag.name)}`;
        
        // Set category dropdowns
        els.detailCategory.value = tag.category || 'general';
        els.detailExtended.value = tag.extended_category || '';
        
        // Sample images
        if (details?.sample_images) {
            els.sampleImages.innerHTML = details.sample_images.slice(0, 6).map(img => `
                <div class="sample-img">
                    <a href="/view/${encodeURIComponent(img)}">
                        <img src="/static/thumbnails/${img}" alt="" loading="lazy">
                    </a>
                </div>
            `).join('');
        } else {
            els.sampleImages.innerHTML = Array(6).fill('<div class="sample-img"></div>').join('');
        }
        
        // Implications
        if (details?.implications?.length > 0) {
            els.implicationsList.innerHTML = details.implications.map(imp => `
                <div class="implication-item">
                    <span class="tag">${escapeHtml(tag.name)}</span>
                    <span class="arrow">→</span>
                    <span class="tag">${escapeHtml(imp)}</span>
                </div>
            `).join('');
        } else {
            els.implicationsList.innerHTML = '<span class="empty-text">No implications</span>';
        }
    }
    
    // Selection
    async function selectTag(tagName) {
        const tag = state.tags.find(t => t.name === tagName);
        if (!tag) return;
        
        state.selectedTag = tag;
        renderTags();
        
        const details = await loadTagDetails(tagName);
        renderDetailPanel(tag, details);
        
        // On mobile, open detail panel
        if (window.innerWidth < 1200) {
            els.detailPanel?.classList.add('open');
        }
    }
    
    function toggleSelection(tagName) {
        if (state.selectedTags.has(tagName)) {
            state.selectedTags.delete(tagName);
        } else {
            state.selectedTags.add(tagName);
        }
        updateBulkBar();
    }
    
    function selectAllVisible() {
        state.tags.forEach(tag => state.selectedTags.add(tag.name));
        renderTags();
        updateBulkBar();
    }
    
    function clearSelection() {
        state.selectedTags.clear();
        renderTags();
        updateBulkBar();
    }
    
    function updateBulkBar() {
        const count = state.selectedTags.size;
        els.selectedCount.textContent = count;
        els.bulkBar.style.display = count > 0 ? 'flex' : 'none';
        els.selectAllCheckbox.checked = count > 0 && count === state.tags.length;
        els.selectAllCheckbox.indeterminate = count > 0 && count < state.tags.length;
    }
    
    // View Mode
    function setViewMode(mode) {
        state.viewMode = mode;
        
        els.viewBtns.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === mode);
        });
        
        els.listView.style.display = mode === 'list' ? 'block' : 'none';
        els.gridView.style.display = mode === 'grid' ? 'block' : 'none';
        
        renderTags();
    }
    
    // Detail Panel
    function closeDetail() {
        state.selectedTag = null;
        renderDetailPanel(null);
        els.detailPanel?.classList.remove('open');
    }
    
    function toggleDetailPanel() {
        els.detailPanel?.classList.toggle('open');
    }
    
    // Keyboard Navigation
    function handleKeyboard(e) {
        // Ignore if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }
        
        const currentIndex = state.tags.findIndex(t => t.name === state.selectedTag?.name);
        
        switch(e.key) {
            case 'ArrowDown':
            case 'j':
                e.preventDefault();
                if (currentIndex < state.tags.length - 1) {
                    selectTag(state.tags[currentIndex + 1].name);
                }
                break;
                
            case 'ArrowUp':
            case 'k':
                e.preventDefault();
                if (currentIndex > 0) {
                    selectTag(state.tags[currentIndex - 1].name);
                }
                break;
                
            case ' ':
                e.preventDefault();
                if (state.selectedTag) {
                    toggleSelection(state.selectedTag.name);
                }
                break;
                
            case '/':
                e.preventDefault();
                els.tagSearch?.focus();
                break;
                
            case 'Escape':
                closeDetail();
                els.tagSearch?.blur();
                break;
                
            // Extended category shortcuts (1-9, q-z)
            default:
                if (state.selectedTag) {
                    const cat = state.extendedCategories.find(c => c[2] === e.key);
                    if (cat) {
                        e.preventDefault();
                        updateTagExtendedCategory(state.selectedTag.name, cat[0]);
                        els.detailExtended.value = cat[0];
                    }
                }
        }
    }
    
    // Helpers
    function updateVisibleCount() {
        els.visibleCount.textContent = state.tags.length.toLocaleString();
    }
    
    function getExtendedCategoryName(key) {
        const cat = state.extendedCategories.find(c => c[0] === key);
        return cat ? cat[1] : key;
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Public API
    return {
        init,
        toggleSelection,
        selectAllVisible,
        clearSelection,
        showContextMenu: (e, tagName) => {
            e.stopPropagation();
            // TODO: Implement context menu
            console.log('Context menu for:', tagName);
        }
    };
})();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => TagBrowser.init());

// Export for module usage
export default TagBrowser;
```

---

## New API Endpoint: `/api/tags/browse`

Add to `routers/api/tags.py`:

```python
@api_blueprint.route('/tags/browse', methods=['GET'])
@api_handler()
async def api_browse_tags():
    """
    Browse tags with filtering, sorting, and pagination.
    
    Query Parameters:
        offset: Starting position (default: 0)
        limit: Max tags to return (default: 100, max: 500)
        search: Search term for tag names
        status: Filter by status (all, uncategorized, needs_extended, orphaned)
        categories: Comma-separated list of base categories
        extended: Comma-separated list of extended categories
        sort: Sort order (count_desc, count_asc, alpha_asc, alpha_desc)
    """
    from database import get_db_connection
    
    offset = request.args.get('offset', 0, type=int)
    limit = min(request.args.get('limit', 100, type=int), 500)
    search = request.args.get('search', '').strip().lower()
    status = request.args.get('status', 'all')
    categories = request.args.get('categories', '').split(',') if request.args.get('categories') else []
    extended = request.args.get('extended', '').split(',') if request.args.get('extended') else []
    sort = request.args.get('sort', 'count_desc')
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Build query
        conditions = []
        params = []
        
        # Search filter
        if search:
            conditions.append("t.name LIKE ?")
            params.append(f"%{search}%")
        
        # Status filter
        if status == 'uncategorized':
            conditions.append("t.extended_category IS NULL AND t.category IN ('general', 'meta')")
        elif status == 'needs_extended':
            conditions.append("t.extended_category IS NULL")
        elif status == 'orphaned':
            conditions.append("usage_count = 0")
        
        # Category filter
        if categories:
            placeholders = ','.join('?' * len(categories))
            conditions.append(f"t.category IN ({placeholders})")
            params.extend(categories)
        
        # Extended category filter
        if extended:
            placeholders = ','.join('?' * len(extended))
            conditions.append(f"t.extended_category IN ({placeholders})")
            params.extend(extended)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Sort
        sort_map = {
            'count_desc': 'usage_count DESC',
            'count_asc': 'usage_count ASC',
            'alpha_asc': 't.name ASC',
            'alpha_desc': 't.name DESC'
        }
        order_clause = sort_map.get(sort, 'usage_count DESC')
        
        # Query with count
        query = f"""
            SELECT 
                t.id,
                t.name,
                t.category,
                t.extended_category,
                COUNT(DISTINCT it.image_id) as usage_count,
                CASE 
                    WHEN t.extended_category IS NULL AND t.category IN ('general', 'meta') 
                    THEN 1 ELSE 0 
                END as needs_review
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE {where_clause}
            GROUP BY t.id, t.name, t.category, t.extended_category
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        
        params.extend([limit + 1, offset])  # +1 to check if there are more
        cur.execute(query, params)
        
        rows = cur.fetchall()
        has_more = len(rows) > limit
        tags = [dict(row) for row in rows[:limit]]
        
        return {
            'tags': tags,
            'has_more': has_more,
            'offset': offset,
            'limit': limit
        }
```

---

## Implementation Checklist

### Phase 1: Core Structure
- [ ] Create `static/css/tag-browser.css`
- [ ] Create `static/js/pages/tag-browser.js`
- [ ] Rewrite `templates/tags.html`
- [ ] Add `/api/tags/browse` endpoint

### Phase 2: Filtering & Search
- [ ] Status filters (all, uncategorized, needs extended, orphaned)
- [ ] Category filters
- [ ] Extended category filters
- [ ] Search with debounce
- [ ] Sort options

### Phase 3: Detail Panel
- [ ] Sample images display
- [ ] Category dropdowns
- [ ] Implications list
- [ ] Aliases list
- [ ] Action buttons (rename, merge, delete)

### Phase 4: Bulk Operations
- [ ] Multi-select with checkboxes
- [ ] Bulk category assignment
- [ ] Bulk extended category assignment
- [ ] Bulk delete (with confirmation)
- [ ] Bulk merge

### Phase 5: Keyboard Navigation
- [ ] Arrow keys / J/K navigation
- [ ] Space to select
- [ ] Number keys for extended categories
- [ ] / to focus search
- [ ] ESC to close panels

### Phase 6: Polish
- [ ] Loading states
- [ ] Error handling
- [ ] Mobile responsive
- [ ] Persistence (view mode, panel state)
- [ ] Import/Export integration

---

## Testing

- [ ] Filter combinations work correctly
- [ ] Pagination loads more tags
- [ ] Detail panel updates on selection
- [ ] Category changes persist
- [ ] Bulk operations work
- [ ] Keyboard shortcuts function
- [ ] Mobile layout works
- [ ] Performance with 10k+ tags

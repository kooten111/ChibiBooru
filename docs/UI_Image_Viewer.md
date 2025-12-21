# 2. Image Viewer (image.html)

## Current Problems

- 300px fixed sidebars waste space for portrait images
- Actions bar below image eats vertical space
- No way to hide UI for focused viewing
- No keyboard navigation

## Proposed Layout

### Normal Mode:
```text
┌──────────────────────────────────────────────────────────────────┐
│ Header (compact, 48px)                          [◧] [◨] [⛶]     │
├────────────┬──────────────────────────────────┬──────────────────┤
│ Tags       │                                  │ Info             │
│ 256px      │         Image                    │ 256px            │
│ Collapsible│         (maximized)              │ Collapsible      │
│            │                                  │                  │
│            │    ┌─────────────────────────┐   │ Similar          │
│            │    │                         │   │ ┌───┐ ┌───┐      │
│            │    │                         │   │ │   │ │   │      │
│            │    │                         │   │ └───┘ └───┘      │
│            │    │                         │   │                  │
│            │    └─────────────────────────┘   │                  │
│            │                                  │                  │
│            │    [◀] [⛶] [🔍] [👁] [💾] [🗑] [▶]  │                  │
└────────────┴──────────────────────────────────┴──────────────────┘
```

### Focus Mode (press F):
```text
┌──────────────────────────────────────────────────────────────────┐
│                                                              [✕] │
│                                                                  │
│                    ┌─────────────────────────┐                   │
│                    │                         │                   │
│                    │         Image           │                   │
│                    │       (fullscreen)      │                   │
│                    │                         │                   │
│                    └─────────────────────────┘                   │
│                                                                  │
│              [◀] [⛶] [🔍] [💾] [🗑] [▶]                           │
│                                                                  │
│              ESC to exit • scroll to zoom                        │
└──────────────────────────────────────────────────────────────────┘
```

## Files to Modify

### static/css/components.css

Add/modify these rules:

```css
/* ============================================================================
   IMAGE PAGE - Improved Layout
   ============================================================================ */

body.image-page {
    overflow: hidden;
    height: 100vh;
}

/* Compact header for image page */
.image-page .header {
    height: 48px;
    padding: 0 var(--spacing-lg);
}

.image-page .header-content {
    height: 100%;
}

/* Grid Container - narrower sidebars */
.image-page .container {
    display: grid;
    grid-template-columns: var(--sidebar-width, 256px) 1fr var(--sidebar-width, 256px);
    max-width: none;
    margin: 0;
    padding: var(--spacing-md);
    gap: var(--spacing-md);
    height: calc(100vh - 48px);
    overflow: hidden;
}

/* Sidebar collapse states */
.image-page .sidebar-left,
.image-page .sidebar-right {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    transition: width 0.2s ease, opacity 0.2s ease;
}

.image-page .sidebar-left.collapsed,
.image-page .sidebar-right.collapsed {
    width: 0 !important;
    opacity: 0;
    padding: 0;
    overflow: hidden;
}

.image-page.left-collapsed .container {
    grid-template-columns: 0 1fr var(--sidebar-width, 256px);
}

.image-page.right-collapsed .container {
    grid-template-columns: var(--sidebar-width, 256px) 1fr 0;
}

.image-page.left-collapsed.right-collapsed .container {
    grid-template-columns: 0 1fr 0;
}

/* Main content area */
.image-page .main-content {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    position: relative;
}

/* Image view - takes all available space */
.image-page .image-view {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 0;
    overflow: hidden;
    position: relative;
}

.image-page .image-view img,
.image-page .image-view video {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    border-radius: var(--radius-lg);
    cursor: zoom-in;
}

/* Floating action bar */
.image-page .floating-actions {
    position: absolute;
    bottom: var(--spacing-lg);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 4px;
    background: rgba(0, 0, 0, 0.8);
    backdrop-filter: blur(8px);
    padding: var(--spacing-xs) var(--spacing-md);
    border-radius: 9999px;
    border: 1px solid var(--border-color);
    box-shadow: var(--shadow-xl);
}

.floating-actions .action-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 50%;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition-normal);
    font-size: 1.1rem;
}

.floating-actions .action-btn:hover {
    background: var(--bg-tertiary);
    color: var(--text-primary);
}

.floating-actions .action-btn.danger:hover {
    background: rgba(239, 68, 68, 0.2);
    color: #ef4444;
}

.floating-actions .action-btn.success:hover {
    background: rgba(34, 197, 94, 0.2);
    color: #22c55e;
}

.floating-actions .divider {
    width: 1px;
    height: 24px;
    background: var(--border-color);
    margin: 0 4px;
}

/* Sidebar toggle buttons in header */
.sidebar-toggles {
    display: flex;
    gap: 4px;
}

.sidebar-toggle {
    padding: 6px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    transition: all var(--transition-normal);
}

.sidebar-toggle:hover {
    color: var(--text-primary);
}

.sidebar-toggle.active {
    background: var(--primary-blue-light);
    color: var(--primary-blue);
}

/* Focus mode */
body.focus-mode {
    background: black;
}

body.focus-mode .header,
body.focus-mode .sidebar-left,
body.focus-mode .sidebar-right {
    display: none !important;
}

body.focus-mode .container {
    grid-template-columns: 1fr;
    height: 100vh;
    padding: 0;
}

body.focus-mode .image-view {
    padding: var(--spacing-lg);
}

body.focus-mode .image-view img {
    max-height: calc(100vh - 100px);
    cursor: grab;
}

body.focus-mode .image-view img:active {
    cursor: grabbing;
}

body.focus-mode .floating-actions {
    bottom: var(--spacing-xl);
}

body.focus-mode .focus-exit {
    position: fixed;
    top: var(--spacing-lg);
    right: var(--spacing-lg);
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.5);
    border: none;
    border-radius: 50%;
    color: white;
    font-size: 1.25rem;
    cursor: pointer;
    z-index: 100;
}

body.focus-mode .focus-hint {
    position: fixed;
    bottom: 80px;
    left: 50%;
    transform: translateX(-50%);
    color: var(--text-muted);
    font-size: var(--font-size-xs);
    pointer-events: none;
    animation: fadeOut 3s forwards;
}

@keyframes fadeOut {
    0%, 80% { opacity: 1; }
    100% { opacity: 0; }
}
```

### templates/image.html

Replace the main content structure:

```html
<body class="image-page">
    {% include 'header.html' %}
    
    <div class="container">
        <!-- Left Sidebar: Tags -->
        <div class="sidebar-left" id="sidebarLeft">
            <!-- Keep existing tags content -->
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <div class="image-view" id="imageView">
                {% if filepath.endswith('.mp4') or filepath.endswith('.webm') %}
                <video controls autoplay loop muted>
                    <source src="/static/{% if not filepath.startswith('images/') %}images/{% endif %}{{ filepath | urlencode_path }}" type="video/{{ 'mp4' if filepath.endswith('.mp4') else 'webm' }}">
                </video>
                {% else %}
                <img src="/static/{% if not filepath.startswith('images/') %}images/{% endif %}{{ filepath | urlencode_path }}" 
                     alt="{{ filepath.split('/')[-1] }}"
                     id="mainImage">
                {% endif %}
            </div>
            
            <!-- Floating Action Bar -->
            <div class="floating-actions">
                <button class="action-btn" id="prevBtn" title="Previous (←)">◀</button>
                <div class="divider"></div>
                <button class="action-btn" id="focusBtn" title="Focus mode (F)">⛶</button>
                <a href="{{ url_for('main.similar', filepath=filepath) }}" class="action-btn" title="Find similar">🔍</a>
                <a href="{{ url_for('main.similar_visual', filepath=filepath) }}" class="action-btn" title="Visual similar">👁</a>
                <a href="/static/{% if not filepath.startswith('images/') %}images/{% endif %}{{ filepath | urlencode_path }}" 
                   download class="action-btn success" title="Download">💾</a>
                <button class="action-btn danger" id="deleteBtn" title="Delete">🗑</button>
                <div class="divider"></div>
                <button class="action-btn" id="nextBtn" title="Next (→)">▶</button>
            </div>
        </div>
        
        <!-- Right Sidebar: Info + Related -->
        <div class="sidebar-right" id="sidebarRight">
            <!-- Keep existing metadata and related content -->
        </div>
    </div>
    
    <!-- Focus mode exit button (hidden by default) -->
    <button class="focus-exit" id="focusExit" style="display: none;">✕</button>
    <div class="focus-hint" id="focusHint" style="display: none;">ESC to exit • scroll to zoom • drag to pan</div>
```

### Add to header.html (image page only)

```html
{% if request.endpoint == 'main.show_image' %}
<div class="sidebar-toggles">
    <button class="sidebar-toggle active" id="toggleLeft" title="Toggle tags panel">◧</button>
    <button class="sidebar-toggle active" id="toggleRight" title="Toggle info panel">◨</button>
    <button class="sidebar-toggle" id="toggleFocus" title="Focus mode (F)">⛶</button>
</div>
{% endif %}
```

### static/js/image-viewer.js (new file)

```javascript
// Image Viewer Enhancements

(function() {
    'use strict';
    
    const body = document.body;
    const sidebarLeft = document.getElementById('sidebarLeft');
    const sidebarRight = document.getElementById('sidebarRight');
    const toggleLeft = document.getElementById('toggleLeft');
    const toggleRight = document.getElementById('toggleRight');
    const toggleFocus = document.getElementById('toggleFocus');
    const focusBtn = document.getElementById('focusBtn');
    const focusExit = document.getElementById('focusExit');
    const focusHint = document.getElementById('focusHint');
    const mainImage = document.getElementById('mainImage');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    
    // Sidebar toggle
    function toggleSidebar(side) {
        if (side === 'left') {
            body.classList.toggle('left-collapsed');
            sidebarLeft.classList.toggle('collapsed');
            toggleLeft?.classList.toggle('active');
        } else {
            body.classList.toggle('right-collapsed');
            sidebarRight.classList.toggle('collapsed');
            toggleRight?.classList.toggle('active');
        }
        
        // Save preference
        localStorage.setItem('sidebar-left', !body.classList.contains('left-collapsed'));
        localStorage.setItem('sidebar-right', !body.classList.contains('right-collapsed'));
    }
    
    // Focus mode
    function enterFocusMode() {
        body.classList.add('focus-mode');
        focusExit.style.display = 'flex';
        focusHint.style.display = 'block';
        
        // Reset hint animation
        focusHint.style.animation = 'none';
        focusHint.offsetHeight; // Trigger reflow
        focusHint.style.animation = null;
    }
    
    function exitFocusMode() {
        body.classList.remove('focus-mode');
        focusExit.style.display = 'none';
        focusHint.style.display = 'none';
    }
    
    // Navigation
    function navigate(direction) {
        // Get related images from sidebar
        const relatedLinks = document.querySelectorAll('.related-thumb');
        if (relatedLinks.length > 0) {
            const targetIndex = direction === 'next' ? 0 : relatedLinks.length - 1;
            relatedLinks[targetIndex].click();
        }
    }
    
    // Keyboard shortcuts
    function handleKeyboard(e) {
        // Ignore if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        
        switch(e.key) {
            case 'f':
            case 'F':
                e.preventDefault();
                if (body.classList.contains('focus-mode')) {
                    exitFocusMode();
                } else {
                    enterFocusMode();
                }
                break;
            case 'Escape':
                if (body.classList.contains('focus-mode')) {
                    exitFocusMode();
                }
                break;
            case 'ArrowLeft':
                navigate('prev');
                break;
            case 'ArrowRight':
                navigate('next');
                break;
            case 'h':
            case 'H':
                toggleSidebar('left');
                break;
            case 'l':
            case 'L':
                toggleSidebar('right');
                break;
        }
    }
    
    // Zoom functionality for focus mode
    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let startX, startY;
    
    function handleWheel(e) {
        if (!body.classList.contains('focus-mode') || !mainImage) return;
        
        e.preventDefault();
        const delta = e.deltaY > 0 ? 0.9 : 1.1;
        scale = Math.min(Math.max(0.5, scale * delta), 5);
        updateImageTransform();
    }
    
    function handleMouseDown(e) {
        if (!body.classList.contains('focus-mode') || !mainImage) return;
        
        isDragging = true;
        startX = e.clientX - translateX;
        startY = e.clientY - translateY;
        mainImage.style.cursor = 'grabbing';
    }
    
    function handleMouseMove(e) {
        if (!isDragging) return;
        
        translateX = e.clientX - startX;
        translateY = e.clientY - startY;
        updateImageTransform();
    }
    
    function handleMouseUp() {
        isDragging = false;
        if (mainImage) mainImage.style.cursor = 'grab';
    }
    
    function updateImageTransform() {
        if (mainImage) {
            mainImage.style.transform = `translate(${translateX}px, ${translateY}px) scale(${scale})`;
        }
    }
    
    function resetZoom() {
        scale = 1;
        translateX = 0;
        translateY = 0;
        updateImageTransform();
    }
    
    // Bind events
    toggleLeft?.addEventListener('click', () => toggleSidebar('left'));
    toggleRight?.addEventListener('click', () => toggleSidebar('right'));
    toggleFocus?.addEventListener('click', enterFocusMode);
    focusBtn?.addEventListener('click', enterFocusMode);
    focusExit?.addEventListener('click', exitFocusMode);
    prevBtn?.addEventListener('click', () => navigate('prev'));
    nextBtn?.addEventListener('click', () => navigate('next'));
    
    document.addEventListener('keydown', handleKeyboard);
    document.addEventListener('wheel', handleWheel, { passive: false });
    mainImage?.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    
    // Double-click to reset zoom
    mainImage?.addEventListener('dblclick', resetZoom);
    
    // Restore sidebar preferences
    if (localStorage.getItem('sidebar-left') === 'false') {
        toggleSidebar('left');
    }
    if (localStorage.getItem('sidebar-right') === 'false') {
        toggleSidebar('right');
    }
    
})();
```

// static/js/family-badge.js
// Filmstrip-style floating badge for displaying parent/child image relationships
// Compact design with hover enlargement

class FamilyBadge {
    constructor(container, familyData, insertAfterElement = null) {
        this.container = container;
        this.familyData = familyData;
        this.insertAfterElement = insertAfterElement;
        this.visible = true;

        this.parents = familyData.filter(img => img.type === 'parent');
        this.children = familyData.filter(img => img.type === 'child');

        if (this.familyData.length === 0) return;

        this.render();
        this.attachEvents();
    }

    render() {
        // Create the filmstrip container
        this.strip = document.createElement('div');
        this.strip.className = 'family-filmstrip visible';
        this.strip.innerHTML = `
            <div class="filmstrip-content">
                ${this.renderFilmstrip()}
            </div>
            <button class="filmstrip-toggle" title="Hide family images">×</button>
        `;

        // Insert as sibling after the specified element, or append to container
        if (this.insertAfterElement) {
            this.insertAfterElement.insertAdjacentElement('afterend', this.strip);
        } else {
            this.container.appendChild(this.strip);
        }
    }

    renderFilmstrip() {
        // Order: parents -> current marker -> children
        let html = '';

        // Parent thumbnails
        this.parents.forEach(img => {
            html += this.renderThumb(img, 'parent');
        });

        // Current image marker
        html += `<div class="filmstrip-current" title="Current image">●</div>`;

        // Child thumbnails
        this.children.forEach(img => {
            html += this.renderThumb(img, 'child');
        });

        return html;
    }

    renderThumb(img, type) {
        const thumbPath = img.thumb.startsWith('thumbnails/') || img.thumb.startsWith('images/')
            ? `/static/${img.thumb}`
            : `/static/images/${img.thumb}`;
        const viewPath = img.path.startsWith('images/')
            ? `/view/${img.path}`
            : `/view/images/${img.path}`;

        return `
            <a href="${viewPath}" class="filmstrip-thumb filmstrip-thumb-${type}" title="${type === 'parent' ? 'Parent' : 'Child'}">
                <div class="filmstrip-perfs top"></div>
                <img src="${thumbPath}" alt="${type}" loading="lazy">
                <div class="filmstrip-perfs bottom"></div>
                <span class="filmstrip-type-badge">${type === 'parent' ? 'P' : 'C'}</span>
            </a>
        `;
    }

    attachEvents() {
        const toggleBtn = this.strip.querySelector('.filmstrip-toggle');

        // Toggle visibility
        toggleBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // Hover preview enlargement
        const thumbs = this.strip.querySelectorAll('.filmstrip-thumb');
        thumbs.forEach(thumb => {
            thumb.addEventListener('mouseenter', () => this.showHoverPreview(thumb));
            thumb.addEventListener('mouseleave', () => this.hideHoverPreview());
        });
    }

    toggle() {
        if (this.visible) {
            this.hide();
        } else {
            this.show();
        }
    }

    show() {
        this.visible = true;
        this.strip.classList.add('visible');
        this.strip.classList.remove('hidden');
        const toggleBtn = this.strip.querySelector('.filmstrip-toggle');
        toggleBtn.innerHTML = '×';
        toggleBtn.title = 'Hide family images';
    }

    hide() {
        this.visible = false;
        this.strip.classList.remove('visible');
        this.strip.classList.add('hidden');
        const toggleBtn = this.strip.querySelector('.filmstrip-toggle');
        toggleBtn.innerHTML = `🔗 ${this.familyData.length}`;
        toggleBtn.title = 'Show family images';
    }

    showHoverPreview(thumbElement) {
        this.hideHoverPreview();

        const img = thumbElement.querySelector('img');
        if (!img) return;

        // Create enlarged preview
        this.preview = document.createElement('div');
        this.preview.className = 'filmstrip-preview';
        this.preview.innerHTML = `<img src="${img.src}" alt="Preview">`;

        // Position above the thumbnail
        const rect = thumbElement.getBoundingClientRect();
        this.preview.style.left = `${rect.left + rect.width / 2}px`;
        this.preview.style.bottom = `${window.innerHeight - rect.top + 8}px`;

        document.body.appendChild(this.preview);

        requestAnimationFrame(() => {
            this.preview.classList.add('visible');
        });
    }

    hideHoverPreview() {
        if (this.preview) {
            this.preview.remove();
            this.preview = null;
        }
    }
}

// Global initialization function that can be called after lazy loading
function initializeFamilyBadge() {
    const familyDataEl = document.getElementById('familyImagesData');
    // Find the actions-row container to append the filmstrip beside the action bar
    const actionsRow = document.querySelector('.actions-row');

    if (familyDataEl && actionsRow) {
        try {
            const familyData = JSON.parse(familyDataEl.textContent || '[]');
            if (familyData.length > 0) {
                // Remove existing family badge if present
                const existingBadge = actionsRow.querySelector('.family-filmstrip');
                if (existingBadge) {
                    existingBadge.remove();
                }
                // Append filmstrip to the actions-row container (beside the action bar)
                new FamilyBadge(actionsRow, familyData);
            }
        } catch (e) {
            console.error('Failed to parse family images data:', e);
        }
    }
}

// Export to global scope for lazy loader
window.initializeFamilyBadge = initializeFamilyBadge;

// Initialize on DOM ready (for pages that have family data in initial load)
document.addEventListener('DOMContentLoaded', initializeFamilyBadge);

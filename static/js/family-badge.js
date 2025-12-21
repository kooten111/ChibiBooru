// static/js/family-badge.js
// Floating badge component for displaying parent/child image relationships

class FamilyBadge {
    constructor(container, familyData) {
        this.container = container;
        this.familyData = familyData;
        this.expanded = false;

        this.parents = familyData.filter(img => img.type === 'parent');
        this.children = familyData.filter(img => img.type === 'child');

        if (this.familyData.length === 0) return;

        this.render();
        this.attachEvents();
    }

    render() {
        // Create badge button
        this.badge = document.createElement('div');
        this.badge.className = 'family-badge';
        this.badge.innerHTML = `
            <button class="family-badge-button">
                <span class="family-badge-icon">🔗</span>
                <span class="family-badge-text">Family (${this.familyData.length})</span>
                <span class="family-badge-arrow">▼</span>
            </button>
        `;

        // Create expanded panel
        this.panel = document.createElement('div');
        this.panel.className = 'family-badge-panel';
        this.panel.innerHTML = this.renderPanelContent();

        this.badge.appendChild(this.panel);
        this.container.appendChild(this.badge);
    }

    renderPanelContent() {
        let html = '';

        if (this.parents.length > 0) {
            html += `
                <div class="family-group">
                    <div class="family-group-header parent">
                        Parent (${this.parents.length})
                    </div>
                    <div class="family-group-thumbs">
                        ${this.parents.map(img => this.renderThumb(img, 'parent')).join('')}
                    </div>
                </div>
            `;
        }

        if (this.children.length > 0) {
            html += `
                <div class="family-group">
                    <div class="family-group-header child">
                        Children (${this.children.length})
                    </div>
                    <div class="family-group-thumbs">
                        ${this.children.map(img => this.renderThumb(img, 'child')).join('')}
                    </div>
                </div>
            `;
        }

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
            <a href="${viewPath}" class="family-thumb family-thumb-${type}">
                <img src="${thumbPath}" alt="${type}" loading="lazy">
            </a>
        `;
    }

    attachEvents() {
        const button = this.badge.querySelector('.family-badge-button');

        button.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // Close when clicking outside
        document.addEventListener('click', (e) => {
            if (this.expanded && !this.badge.contains(e.target)) {
                this.collapse();
            }
        });

        // Prevent panel clicks from closing
        this.panel.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    toggle() {
        if (this.expanded) {
            this.collapse();
        } else {
            this.expand();
        }
    }

    expand() {
        this.expanded = true;
        this.badge.classList.add('expanded');
    }

    collapse() {
        this.expanded = false;
        this.badge.classList.remove('expanded');
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    const familyDataEl = document.getElementById('familyImagesData');
    const imageView = document.querySelector('.image-view');

    if (familyDataEl && imageView) {
        try {
            const familyData = JSON.parse(familyDataEl.textContent || '[]');
            if (familyData.length > 0) {
                new FamilyBadge(imageView, familyData);
            }
        } catch (e) {
            console.error('Failed to parse family images data:', e);
        }
    }
});

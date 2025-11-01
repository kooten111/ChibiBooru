import { escapeHtml, formatCount } from './utils/helpers.js';
import { showNotification } from './utils/notifications.js';

class TagEditor {
    constructor() {
        this.tags = {}; // Organized by category
        this.isEditing = false;
        this.originalTags = {};
        this.debounceTimer = null;
        this.categories = ['artist', 'copyright', 'character', 'species', 'general', 'meta'];
        this.activeInputCategory = null;
    }

    toggleEditMode() {
        console.log('toggleEditMode called, current state:', this.isEditing);

        if (!this.isEditing) {
            this.startEditing();
        } else {
            this.cancelEdit();
        }
    }

    startEditing() {
        console.log('Starting edit mode');

        // Get current tags from the page
        this.loadCurrentTags();
        this.originalTags = JSON.parse(JSON.stringify(this.tags)); // Deep copy
        this.isEditing = true;

        console.log('Current tags:', this.tags);

        // Transform the display
        this.renderEditMode();

        // Update button
        const editBtn = document.querySelector('.actions-bar .btn-primary');
        if (editBtn) {
            editBtn.textContent = '💾 Save Tags';
            editBtn.classList.add('editing-mode');
        }

        // Add cancel button if it doesn't exist
        let cancelBtn = document.getElementById('cancelEditBtn');
        if (!cancelBtn) {
            cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn btn-secondary';
            cancelBtn.textContent = '✖️ Cancel';
            cancelBtn.id = 'cancelEditBtn';
            editBtn.after(cancelBtn);
        }
    }

    loadCurrentTags() {
        // Load tags from the categorized display
        this.tags = {
            artist: [],
            copyright: [],
            character: [],
            species: [],
            general: [],
            meta: []
        };

        // Try to parse from the existing tag categories on the page
        this.categories.forEach(category => {
            const categoryDiv = document.querySelector(`.tag-category.${category}`);
            if (categoryDiv) {
                const tagItems = categoryDiv.querySelectorAll('.tag-item a');
                tagItems.forEach(link => {
                    // Skip delta items (manual modifications)
                    if (link.closest('.delta-added') || link.closest('.delta-removed')) {
                        return;
                    }

                    const tag = link.textContent.trim();
                    // Remove any leading + or - that might be from delta display
                    const cleanTag = tag.replace(/^[+-]+/, '');
                    if (cleanTag && !this.tags[category].includes(cleanTag)) {
                        this.tags[category].push(cleanTag);
                    }
                });
            }
        });
    }

    renderEditMode() {
        const tagsList = document.querySelector('.tags-list');
        if (!tagsList) {
            console.error('tags-list not found');
            return;
        }

        // Hide all panels in left sidebar except where we'll place the editor
        const sidebarLeft = document.getElementById('sidebarLeft');
        if (sidebarLeft) {
            sidebarLeft.classList.add('editing-mode');
            // Hide all other sections in sidebar
            const sections = sidebarLeft.querySelectorAll('.section-content');
            sections.forEach(section => {
                if (section.id !== 'tags-content') {
                    section.style.display = 'none';
                }
            });
        }

        // Hide right sidebar completely
        const sidebarRight = document.getElementById('sidebarRight');
        if (sidebarRight) {
            sidebarRight.style.display = 'none';
        }

        // Hide the normal tag display
        tagsList.style.display = 'none';

        // Remove existing editor if present
        const existing = document.getElementById('inlineTagEditor');
        if (existing) {
            existing.remove();
        }

        // Create editing interface
        const editContainer = document.createElement('div');
        editContainer.className = 'inline-tag-editor panel';
        editContainer.id = 'inlineTagEditor';
        editContainer.innerHTML = `
            <h3>Editing Tags</h3>
            <div class="editable-categories-list" id="editableCategoriesList">
                ${this.renderCategoriesHTML()}
            </div>
        `;

        tagsList.after(editContainer);

        // Create suggestions dropdown as a fixed element
        let suggestionsEl = document.getElementById('tagSuggestions');
        if (!suggestionsEl) {
            suggestionsEl = document.createElement('div');
            suggestionsEl.id = 'tagSuggestions';
            suggestionsEl.className = 'tag-suggestions';
            document.body.appendChild(suggestionsEl);
        }

        this.attachEditEvents();

        console.log('Edit mode rendered');
    }

    renderCategoriesHTML() {
        return this.categories.map(category => {
            const categoryTags = this.tags[category] || [];
            const categoryTitle = this.getCategoryTitle(category);
            const categoryIcon = this.getCategoryIcon(category);

            return `
                <div class="edit-category-section" data-category="${category}">
                    <div class="edit-category-header">
                        <span class="category-icon">${categoryIcon}</span>
                        <span class="category-title">${categoryTitle}</span>
                    </div>
                    <div class="edit-category-tags" id="tags-${category}">
                        ${categoryTags.map((tag, idx) => this.renderTagItemHTML(tag, category, idx)).join('')}
                    </div>
                    <button class="add-tag-btn" data-category="${category}">
                        + ADD
                    </button>
                </div>
            `;
        }).join('');
    }

    renderTagItemHTML(tag, category, idx) {
        // Get tag count if available
        const countText = this.getTagCount(tag);

        return `
            <div class="edit-tag-row" data-category="${category}" data-index="${idx}">
                <button class="remove-tag-btn" data-category="${category}" data-index="${idx}">✖</button>
                <span class="tag-name">${escapeHtml(tag)}</span>
                ${countText ? `<span class="tag-count">${countText}</span>` : ''}
            </div>
        `;
    }

    getTagCount(tag) {
        // Try to find the tag count from the original page display
        const tagItems = document.querySelectorAll('.tag-item a');
        for (let item of tagItems) {
            if (item.textContent.trim() === tag) {
                const countSpan = item.parentElement.querySelector('.tag-count');
                if (countSpan) {
                    return countSpan.textContent;
                }
            }
        }
        return '';
    }

    getCategoryTitle(category) {
        const titles = {
            artist: 'Artist',
            copyright: 'Copyright',
            character: 'Character',
            species: 'Species',
            general: 'General',
            meta: 'Meta'
        };
        return titles[category] || category.charAt(0).toUpperCase() + category.slice(1);
    }

    getCategoryIcon(category) {
        const icons = {
            artist: '🎨',
            copyright: '©️',
            character: '👤',
            species: '🐾',
            general: '🏷️',
            meta: '⚙️'
        };
        return icons[category] || '🏷️';
    }

    attachEditEvents() {
        const editContainer = document.getElementById('inlineTagEditor');
        if (!editContainer) return;

        // Add button click handlers
        editContainer.querySelectorAll('.add-tag-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const category = btn.getAttribute('data-category');
                this.showAddTagInput(category);
            });
        });

        // Remove button click handlers
        editContainer.querySelectorAll('.remove-tag-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const category = btn.getAttribute('data-category');
                const index = parseInt(btn.getAttribute('data-index'));
                this.removeTag(category, index);
            });
        });
    }

    showAddTagInput(category) {
        // Remove any existing input rows first
        document.querySelectorAll('.add-tag-input-row').forEach(row => row.remove());

        const tagsContainer = document.getElementById(`tags-${category}`);
        if (!tagsContainer) return;

        // Create input row
        const inputRow = document.createElement('div');
        inputRow.className = 'add-tag-input-row edit-tag-row';
        inputRow.innerHTML = `
            <input type="text"
                   class="new-tag-input"
                   data-category="${category}"
                   placeholder="Type tag name..."
                   autocomplete="off">
        `;

        tagsContainer.appendChild(inputRow);

        const input = inputRow.querySelector('.new-tag-input');
        input.focus();

        this.activeInputCategory = category;

        // Input event for autocomplete
        input.addEventListener('input', (e) => this.handleTagInput(e, category));

        // Keydown for Enter and Escape
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const tag = input.value.trim();
                if (tag) {
                    this.addTag(tag, category);
                    inputRow.remove();
                }
            } else if (e.key === 'Escape') {
                inputRow.remove();
                this.hideSuggestions();
            }
        });

        // Blur to remove input if clicking outside
        input.addEventListener('blur', (e) => {
            // Delay to allow clicking suggestions
            setTimeout(() => {
                if (!document.activeElement?.closest('.tag-suggestions')) {
                    inputRow.remove();
                    this.hideSuggestions();
                }
            }, 200);
        });
    }

    handleTagInput(e, category) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value.trim();

        if (query.length < 2) {
            this.hideSuggestions();
            return;
        }

        this.debounceTimer = setTimeout(() => {
            this.fetchSuggestions(query, category);
        }, 150);
    }

    fetchSuggestions(query, category) {
        fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                // Filter suggestions by category
                if (data.groups && data.groups.length > 0) {
                    this.displaySuggestions(data, category);
                } else {
                    this.hideSuggestions();
                }
            })
            .catch(err => console.error('Autocomplete error:', err));
    }

    displaySuggestions(data, filterCategory) {
        const suggestionsEl = document.getElementById('tagSuggestions');
        if (!suggestionsEl) return;

        let html = '';

        if (data.groups) {
            // Find tags group
            const tagsGroup = data.groups.find(g => g.name === 'Tags');
            if (tagsGroup) {
                // Filter by category
                const filteredItems = tagsGroup.items.filter(item => {
                    const itemCategory = item.category || 'general';
                    return itemCategory === filterCategory;
                });

                filteredItems.forEach(item => {
                    const displayText = item.display || item.tag;
                    const countText = item.count ? formatCount(item.count) : '';
                    const icon = this.getCategoryIcon(item.category || 'general');

                    html += `
                        <div class="autocomplete-item" data-tag="${escapeHtml(item.tag)}">
                            <div class="autocomplete-left">
                                <span class="autocomplete-icon">${icon}</span>
                                <span class="autocomplete-tag">${escapeHtml(displayText)}</span>
                            </div>
                            ${countText ? `<span class="autocomplete-count">${countText}</span>` : ''}
                        </div>
                    `;
                });
            }
        }

        if (!html) {
            this.hideSuggestions();
            return;
        }

        suggestionsEl.innerHTML = html;

        // Position below the input
        const input = document.querySelector('.new-tag-input');
        if (input) {
            const rect = input.getBoundingClientRect();
            suggestionsEl.style.top = `${rect.bottom + 8}px`;
            suggestionsEl.style.left = `${rect.left}px`;
            suggestionsEl.style.width = `${rect.width}px`;
        }

        // Attach click handlers
        suggestionsEl.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('mousedown', (e) => {
                e.preventDefault(); // Prevent input blur
                const tag = item.getAttribute('data-tag');
                this.addTag(tag, filterCategory);
                document.querySelector('.add-tag-input-row')?.remove();
                this.hideSuggestions();
            });
        });

        suggestionsEl.classList.add('active');
    }

    hideSuggestions() {
        const suggestionsEl = document.getElementById('tagSuggestions');
        if (suggestionsEl) {
            suggestionsEl.classList.remove('active');
        }
    }

    addTag(tag, category) {
        tag = tag.trim().toLowerCase().replace(/\s+/g, '_');

        if (!tag) return;

        if (!this.tags[category]) {
            this.tags[category] = [];
        }

        if (this.tags[category].includes(tag)) {
            showNotification('Tag already exists in this category', 'warning');
            return;
        }

        // Check if tag exists in other categories
        for (let cat of this.categories) {
            if (cat !== category && this.tags[cat] && this.tags[cat].includes(tag)) {
                showNotification(`Tag exists in ${cat} category. Remove it there first.`, 'warning');
                return;
            }
        }

        this.tags[category].push(tag);
        this.refreshCategoryTags(category);
        showNotification(`Added to ${category}`, 'info');
    }

    removeTag(category, index) {
        const row = document.querySelector(`[data-category="${category}"][data-index="${index}"].edit-tag-row`);
        if (row) {
            row.style.animation = 'fadeOut 0.2s ease-out';
            setTimeout(() => {
                this.tags[category].splice(index, 1);
                this.refreshCategoryTags(category);
                showNotification('Tag removed', 'info');
            }, 150);
        }
    }

    refreshCategoryTags(category) {
        const tagsContainer = document.getElementById(`tags-${category}`);
        if (!tagsContainer) return;

        const categoryTags = this.tags[category] || [];
        tagsContainer.innerHTML = categoryTags.map((tag, idx) =>
            this.renderTagItemHTML(tag, category, idx)
        ).join('');

        // Re-attach event handlers for this category's remove buttons
        tagsContainer.querySelectorAll('.remove-tag-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const cat = btn.getAttribute('data-category');
                const idx = parseInt(btn.getAttribute('data-index'));
                this.removeTag(cat, idx);
            });
        });
    }

    renderViewMode() {
        console.log('Rendering view mode');

        const editContainer = document.getElementById('inlineTagEditor');
        if (editContainer) {
            editContainer.remove();
        }

        const tagsList = document.querySelector('.tags-list');
        if (tagsList) {
            tagsList.style.display = 'block';
        }

        // Restore left sidebar panels
        const sidebarLeft = document.getElementById('sidebarLeft');
        if (sidebarLeft) {
            sidebarLeft.classList.remove('editing-mode');
            // Show all sections in sidebar again
            const sections = sidebarLeft.querySelectorAll('.section-content');
            sections.forEach(section => {
                section.style.display = '';
            });
        }

        // Restore right sidebar
        const sidebarRight = document.getElementById('sidebarRight');
        if (sidebarRight) {
            sidebarRight.style.display = '';
        }

        // Reset button
        const editBtn = document.querySelector('.actions-bar .btn-primary');
        if (editBtn) {
            editBtn.textContent = '📝 Edit Tags';
            editBtn.classList.remove('editing-mode');
        }

        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) {
            cancelBtn.remove();
        }

        this.isEditing = false;

        // Clean up suggestions
        this.hideSuggestions();
    }

    saveTags() {
        console.log('Saving tags:', this.tags);

        const filepath = document.getElementById('imageFilepath')?.value;
        if (!filepath) {
            console.error('No filepath found');
            showNotification('Error: No filepath', 'error');
            return;
        }

        const editBtn = document.querySelector('.actions-bar .btn-primary');
        if (editBtn) {
            editBtn.textContent = 'Saving...';
            editBtn.disabled = true;
        }

        // Prepare categorized tags for backend
        const categorizedTags = {
            tags_artist: this.tags.artist.join(' '),
            tags_copyright: this.tags.copyright.join(' '),
            tags_character: this.tags.character.join(' '),
            tags_species: this.tags.species.join(' '),
            tags_general: this.tags.general.join(' '),
            tags_meta: this.tags.meta.join(' ')
        };

        fetch('/api/edit_tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filepath: filepath,
                categorized_tags: categorizedTags
            })
        })
        .then(res => {
            const contentType = res.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                console.error('Response is not JSON, got:', contentType);
                return res.text().then(text => {
                    console.error('Response body:', text.substring(0, 500));
                    throw new Error('Server returned non-JSON response');
                });
            }
            return res.json();
        })
        .then(data => {
            if (data.status === 'success') {
                showNotification('Tags saved!', 'success');
                this.renderViewMode();
                setTimeout(() => location.reload(), 500);
            } else {
                throw new Error(data.error || 'Save failed');
            }
        })
        .catch(err => {
            console.error('Save error:', err);
            showNotification('Failed to save: ' + err.message, 'error');
            if (editBtn) {
                editBtn.textContent = '💾 Save Tags';
                editBtn.disabled = false;
            }
        });
    }

    cancelEdit() {
        console.log('Cancelling edit');
        this.tags = JSON.parse(JSON.stringify(this.originalTags));
        this.renderViewMode();
        showNotification('Changes cancelled', 'info');
    }


}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeOut {
        to {
            opacity: 0;
            transform: scale(0.8);
        }
    }

    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateX(100px);
        }
    }

    @keyframes slideOut {
        to {
            opacity: 0;
            transform: translateX(100px);
        }
    }
`;
document.head.appendChild(style);

// Create instance and expose it globally
window.tagEditor = new TagEditor();

// Global function for the button
function toggleTagEditor() {
    console.log('toggleTagEditor called');

    if (window.tagEditor.isEditing) {
        const editBtn = document.querySelector('.actions-bar .btn-primary');
        if (editBtn && editBtn.classList.contains('editing-mode')) {
            window.tagEditor.saveTags();
        } else {
            window.tagEditor.toggleEditMode();
        }
    } else {
        window.tagEditor.toggleEditMode();
    }
}

// Attach cancel handler
document.addEventListener('click', (e) => {
    if (e.target.id === 'cancelEditBtn') {
        window.tagEditor.cancelEdit();
    }
});

// Expose functions globally for onclick handlers
window.toggleTagEditor = toggleTagEditor;
window.saveTags = saveTags;

// Legacy function for compatibility
function saveTags() {
    window.tagEditor.saveTags();
}

console.log('Tag editor loaded');

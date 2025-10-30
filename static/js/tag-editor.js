class TagEditor {
    constructor() {
        this.tags = {}; // Now organized by category
        this.isEditing = false;
        this.originalTags = {};
        this.suggestions = null;
        this.debounceTimer = null;
        this.categories = ['character', 'copyright', 'artist', 'species', 'meta', 'general'];
        this.selectedCategory = 'general'; // Default category
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
            character: [],
            copyright: [],
            artist: [],
            species: [],
            meta: [],
            general: []
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
            <div class="category-selector">
                ${this.categories.map(cat => `
                    <button class="category-btn ${cat === this.selectedCategory ? 'active' : ''}" 
                            data-category="${cat}">
                        ${this.getCategoryIcon(cat)} ${this.capitalize(cat)}
                    </button>
                `).join('')}
            </div>
            <div class="editable-tags-list" id="editableTagsList"></div>
            <div class="add-tag-section">
                <input type="text"
                       id="addTagInput"
                       class="add-tag-input"
                       placeholder="Type to add a ${this.selectedCategory} tag..."
                       autocomplete="off">
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

        // Attach category button handlers
        editContainer.querySelectorAll('.category-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const category = btn.getAttribute('data-category');
                this.selectCategory(category);
            });
        });

        this.renderTags();
        this.attachEditEvents();

        console.log('Edit mode rendered');
    }

    getCategoryIcon(category) {
        const icons = {
            character: '👤',
            copyright: '©️',
            artist: '🎨',
            species: '🐾',
            meta: '⚙️',
            general: '🏷️'
        };
        return icons[category] || '🏷️';
    }

    capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    selectCategory(category) {
        this.selectedCategory = category;
        
        // Update button states
        document.querySelectorAll('.category-btn').forEach(btn => {
            if (btn.getAttribute('data-category') === category) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        
        // Update placeholder
        const input = document.getElementById('addTagInput');
        if (input) {
            input.placeholder = `Type to add a ${category} tag...`;
            input.focus();
        }
        
        this.renderTags();
    }

    renderTags() {
        const list = document.getElementById('editableTagsList');
        if (!list) {
            console.error('editableTagsList not found');
            return;
        }
        
        const categoryTags = this.tags[this.selectedCategory] || [];
        
        if (categoryTags.length === 0) {
            list.innerHTML = `<div class="no-tags-message">No ${this.selectedCategory} tags yet</div>`;
        } else {
            list.innerHTML = categoryTags.map((tag, idx) => `
                <div class="editable-tag-item" data-index="${idx}" data-category="${this.selectedCategory}">
                    <span class="tag-text">${this.escapeHtml(tag)}</span>
                    <span class="tag-category-badge">${this.selectedCategory}</span>
                    <button class="tag-remove-btn" data-index="${idx}" title="Remove">✖</button>
                </div>
            `).join('');
            
            // Attach remove handlers
            list.querySelectorAll('.tag-remove-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const index = parseInt(e.target.getAttribute('data-index'));
                    this.removeTag(this.selectedCategory, index);
                });
            });
        }
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

        // Clean up suggestions dropdown
        if (this.suggestions) {
            this.suggestions.classList.remove('active');
            this.suggestions.remove();
            this.suggestions = null;
        }

        // Remove event handlers
        if (this.clickOutsideHandler) {
            document.removeEventListener('click', this.clickOutsideHandler);
        }
        if (this.scrollHandler) {
            document.removeEventListener('scroll', this.scrollHandler, true);
        }
        if (this.resizeHandler) {
            window.removeEventListener('resize', this.resizeHandler);
        }
    }

    attachEditEvents() {
        const input = document.getElementById('addTagInput');
        if (!input) {
            console.error('addTagInput not found');
            return;
        }

        this.suggestions = document.getElementById('tagSuggestions');

        input.addEventListener('input', (e) => this.handleInput(e));
        input.addEventListener('keydown', (e) => this.handleKeydown(e));

        // Click outside to close suggestions
        const closeHandler = (e) => {
            if (!e.target.closest('.add-tag-section') && !e.target.closest('#tagSuggestions')) {
                this.suggestions?.classList.remove('active');
            }
        };

        // Remove old handler if exists
        document.removeEventListener('click', this.clickOutsideHandler);
        this.clickOutsideHandler = closeHandler;
        document.addEventListener('click', closeHandler);

        // Reposition on scroll/resize
        const repositionHandler = () => {
            if (this.suggestions?.classList.contains('active')) {
                this.repositionSuggestions();
            }
        };

        // Remove old handlers if exist
        document.removeEventListener('scroll', this.scrollHandler, true);
        window.removeEventListener('resize', this.resizeHandler);

        this.scrollHandler = repositionHandler;
        this.resizeHandler = repositionHandler;

        document.addEventListener('scroll', repositionHandler, true);
        window.addEventListener('resize', repositionHandler);
    }

    repositionSuggestions() {
        const input = document.getElementById('addTagInput');
        if (input && this.suggestions) {
            const rect = input.getBoundingClientRect();
            this.suggestions.style.top = `${rect.bottom + 8}px`;
            this.suggestions.style.left = `${rect.left}px`;
            this.suggestions.style.width = `${rect.width}px`;
            this.suggestions.style.minWidth = '300px';
        }
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value.trim();
        
        if (query.length < 2) {
            this.suggestions?.classList.remove('active');
            return;
        }
        
        this.debounceTimer = setTimeout(() => {
            this.fetchSuggestions(query);
        }, 150);
    }

    handleKeydown(e) {
        const input = e.target;
        
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const tag = input.value.trim();
            if (tag) {
                this.addTag(tag, this.selectedCategory);
            }
        } else if (e.key === 'Escape') {
            this.suggestions?.classList.remove('active');
            input.blur();
        }
    }

    fetchSuggestions(query) {
        fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`)
            .then(res => res.json())
            .then(data => {
                // Handle new grouped format
                if (data.groups && data.groups.length > 0) {
                    this.displaySuggestions(data);
                } else {
                    this.suggestions?.classList.remove('active');
                }
            })
            .catch(err => console.error('Autocomplete error:', err));
    }

    displaySuggestions(data) {
        if (!this.suggestions) return;

        // Handle grouped autocomplete response
        let html = '';

        if (data.groups) {
            // New grouped format
            data.groups.forEach(group => {
                if (group.items.length === 0) return;

                // Only show tags group in tag editor (skip filters)
                if (group.name === 'Tags') {
                    group.items.forEach(item => {
                        const displayText = item.display || item.tag;
                        const countText = item.count ? this.formatCount(item.count) : '';
                        const icon = this.getCategoryIcon(item.category || 'general');

                        html += `
                            <div class="autocomplete-item" data-tag="${this.escapeHtml(item.tag)}" data-category="${this.escapeHtml(item.category || '')}">
                                <div class="autocomplete-left">
                                    <span class="autocomplete-icon">${icon}</span>
                                    <span class="autocomplete-tag">${this.escapeHtml(displayText)}</span>
                                </div>
                                ${countText ? `<span class="autocomplete-count">${countText}</span>` : ''}
                            </div>
                        `;
                    });
                }
            });
        }

        if (!html) {
            this.suggestions?.classList.remove('active');
            return;
        }

        this.suggestions.innerHTML = html;

        // Position the fixed dropdown below the input
        const input = document.getElementById('addTagInput');
        if (input) {
            const rect = input.getBoundingClientRect();
            this.suggestions.style.top = `${rect.bottom + 8}px`;
            this.suggestions.style.left = `${rect.left}px`;
            this.suggestions.style.width = `${rect.width}px`;
        }

        // Attach click handlers
        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.getAttribute('data-tag');
                const category = item.getAttribute('data-category');
                // Use the suggested category if available, otherwise use selected category
                const targetCategory = category && category !== '' ? category : this.selectedCategory;
                this.addTag(tag, targetCategory);
            });
        });

        this.suggestions.classList.add('active');
    }

    addTag(tag, category) {
        tag = tag.trim().toLowerCase().replace(/\s+/g, '_');
        
        if (!tag) return;
        
        if (!this.tags[category]) {
            this.tags[category] = [];
        }
        
        if (this.tags[category].includes(tag)) {
            this.showNotification('Tag already exists in this category', 'warning');
            return;
        }
        
        // Check if tag exists in other categories
        for (let cat of this.categories) {
            if (cat !== category && this.tags[cat] && this.tags[cat].includes(tag)) {
                this.showNotification(`Tag exists in ${cat} category. Remove it there first.`, 'warning');
                return;
            }
        }
        
        this.tags[category].push(tag);
        this.renderTags();
        
        const input = document.getElementById('addTagInput');
        if (input) {
            input.value = '';
        }
        this.suggestions?.classList.remove('active');
        input?.focus();
        
        this.showNotification(`Added to ${category}`, 'info');
    }

    removeTag(category, index) {
        const item = document.querySelector(`[data-category="${category}"][data-index="${index}"]`);
        if (item) {
            item.style.animation = 'fadeOut 0.2s ease-out';
            setTimeout(() => {
                this.tags[category].splice(index, 1);
                this.renderTags();
                this.showNotification('Tag removed', 'info');
            }, 150);
        }
    }

    saveTags() {
        console.log('Saving tags:', this.tags);
        
        const filepath = document.getElementById('imageFilepath')?.value;
        if (!filepath) {
            console.error('No filepath found');
            this.showNotification('Error: No filepath', 'error');
            return;
        }
        
        const editBtn = document.querySelector('.actions-bar .btn-primary');
        if (editBtn) {
            editBtn.textContent = 'Saving...';
            editBtn.disabled = true;
        }

        // Prepare categorized tags for backend
        const categorizedTags = {
            tags_character: this.tags.character.join(' '),
            tags_copyright: this.tags.copyright.join(' '),
            tags_artist: this.tags.artist.join(' '),
            tags_species: this.tags.species.join(' '),
            tags_meta: this.tags.meta.join(' '),
            tags_general: this.tags.general.join(' ')
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
            // Check if response is actually JSON
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
                this.showNotification('Tags saved!', 'success');
                // Exit edit mode and reload
                this.renderViewMode();
                setTimeout(() => location.reload(), 500);
            } else {
                throw new Error(data.error || 'Save failed');
            }
        })
        .catch(err => {
            console.error('Save error:', err);
            this.showNotification('Failed to save: ' + err.message, 'error');
            if (editBtn) {
                editBtn.textContent = '💾 Save Tags';
                editBtn.disabled = false;
            }
        });
    }

    cancelEdit() {
        console.log('Cancelling edit');
        this.tags = JSON.parse(JSON.stringify(this.originalTags)); // Deep copy
        this.renderViewMode();
        this.showNotification('Changes cancelled', 'info');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatCount(count) {
        if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
        if (count >= 1000) return (count / 1000).toFixed(1) + 'k';
        return count;
    }

    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.textContent = message;
        notification.className = 'editor-notification ' + type;
        notification.style.cssText = `
            position: fixed;
            top: 100px;
            right: 30px;
            padding: 12px 20px;
            background: ${type === 'error' ? '#ff6b6b' : type === 'warning' ? '#ff9966' : type === 'success' ? '#4caf50' : '#4a9eff'};
            color: white;
            border-radius: 10px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            z-index: 10000;
            font-weight: 600;
            animation: slideIn 0.2s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOut 0.2s ease-out';
            setTimeout(() => notification.remove(), 200);
        }, 2000);
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

// Create instance and expose it globally for other scripts to use
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

// Legacy function for compatibility
function saveTags() {
    window.tagEditor.saveTags();
}

console.log('Tag editor with categories loaded');
import { escapeHtml, formatCount, getCategoryIcon } from './utils/helpers.js';
import { showNotification } from './utils/notifications.js';

class TagEditor {
    constructor() {
        this.tags = {}; // Organized by category
        this.relations = [];
        this.isEditing = false;
        this.originalTags = {};
        this.originalRelations = [];
        this.debounceTimer = null;
        this.categories = ['artist', 'copyright', 'character', 'species', 'general', 'meta'];
        this.activeInputCategory = null;
        this.nextTempRelationId = 1;
    }

    toggleEditMode() {
        if (!this.isEditing) {
            this.startEditing();
        } else {
            this.cancelEdit();
        }
    }

    startEditing() {
        // Get current tags from the page
        this.loadCurrentTags();
        this.loadCurrentRelations();
        this.originalTags = JSON.parse(JSON.stringify(this.tags)); // Deep copy
        this.originalRelations = JSON.parse(JSON.stringify(this.relations));
        this.isEditing = true;

        // Transform the display
        this.renderEditMode();

        const toolbar = document.getElementById('imageToolbar');
        if (toolbar) {
            toolbar.classList.add('image-toolbar--editing');
        }

        const imageViewWrapper = document.querySelector('.image-page .image-view-wrapper');
        if (imageViewWrapper) {
            imageViewWrapper.classList.add('image-view-wrapper--toolbar-lock');
        }

        // Update button
        const editBtn = document.querySelector('.toolbar-btn.primary') || document.querySelector('.actions-grid .action-btn.primary');
        if (editBtn) {
            editBtn.innerHTML = '<span class="toolbar-icon">💾</span>';
            editBtn.title = 'Save Changes';
            editBtn.classList.add('editing-mode');
        }

        // Add cancel button if it doesn't exist
        let cancelBtn = document.getElementById('cancelEditBtn');
        if (!cancelBtn) {
            cancelBtn = document.createElement('button');
            cancelBtn.className = 'toolbar-btn toolbar-btn--text danger';
            cancelBtn.innerHTML = '<span class="toolbar-btn__icon toolbar-icon">❌</span><span class="toolbar-btn__label">Cancel</span>';
            cancelBtn.id = 'cancelEditBtn';
            cancelBtn.title = 'Cancel Editing';
            editBtn.after(cancelBtn);
        }

        // Add clear deltas button if it doesn't exist
        let clearDeltasBtn = document.getElementById('clearDeltasBtn');
        if (!clearDeltasBtn) {
            clearDeltasBtn = document.createElement('button');
            clearDeltasBtn.className = 'toolbar-btn toolbar-btn--text';
            clearDeltasBtn.innerHTML = '<span class="toolbar-btn__icon toolbar-icon">🧹</span><span class="toolbar-btn__label">Clear Deltas</span>';
            clearDeltasBtn.id = 'clearDeltasBtn';
            clearDeltasBtn.title = 'Clear manual modification markers';
            cancelBtn.after(clearDeltasBtn);
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
        // We iterate all .tag-category elements found on page
        const categoryDivs = document.querySelectorAll('.tag-category');
        categoryDivs.forEach(categoryDiv => {
            // Determine category key from data attribute or class
            let categoryKey = categoryDiv.dataset.category;
            if (!categoryKey) {
                // Fallback to class checking
                for (const cat of this.categories) {
                    if (categoryDiv.classList.contains(cat)) {
                        categoryKey = cat;
                        break;
                    }
                }
            }

            if (!categoryKey || !this.tags[categoryKey]) return;

            const tagItems = categoryDiv.querySelectorAll('.tag-chip:not(.delta-added):not(.delta-removed)');
            tagItems.forEach(link => {
                // Extract tag name from text nodes only (excluding count span)
                let tagText = '';
                for (const node of link.childNodes) {
                    if (node.nodeType === Node.TEXT_NODE) tagText += node.textContent;
                }
                const cleanTag = tagText.trim().replace(/^[⚡+-]+\s*/, '');
                if (cleanTag && !this.tags[categoryKey].includes(cleanTag)) {
                    this.tags[categoryKey].push(cleanTag);
                }
            });
        });
    }

    loadCurrentRelations() {
        const relationDataEl = document.getElementById('manualRelationsData');
        if (!relationDataEl) {
            this.relations = [];
            return;
        }

        try {
            const parsed = JSON.parse(relationDataEl.textContent || '[]');
            this.relations = Array.isArray(parsed) ? parsed.map(relation => ({
                id: relation.id,
                other_image_id: relation.other_image_id,
                other_filepath: relation.other_filepath,
                display_type: relation.display_type,
                source: relation.source || 'manual',
                created_at: relation.created_at || null
            })) : [];
        } catch (err) {
            console.error('Failed to parse relation data:', err);
            this.relations = [];
        }
    }

    renderEditMode() {
        const tagsList = document.querySelector('.tags-scroll');
        if (!tagsList) {
            console.error('tags-scroll not found');
            return;
        }

        // Hide all panels in left sidebar except where we'll place the editor
        const sidebarLeft = document.getElementById('sidebarLeft');
        if (sidebarLeft) {
            sidebarLeft.classList.add('editing-mode');
            // Hide all other sections in sidebar except tags and actions
            const sections = sidebarLeft.querySelectorAll('.sidebar-section');
            sections.forEach(section => {
                if (section.id !== 'tags-content' && section.id !== 'actions-content') {
                    section.style.display = 'none';
                }
            });
        }

        // Add class to container to adjust grid layout
        const container = document.querySelector('.image-page .container');
        if (container) {
            container.classList.add('tag-editor-expanded');
        }

        // Replace the right sidebar contents with the relations editor
        const sidebarRight = document.getElementById('sidebarRight');
        if (sidebarRight) {
            sidebarRight.style.display = '';
            sidebarRight.classList.add('editing-mode');

            const rightContent = document.getElementById('sidebar-right-content');
            if (rightContent) {
                if (!rightContent.dataset.originalHtml) {
                    rightContent.dataset.originalHtml = rightContent.innerHTML;
                }
                rightContent.innerHTML = this.renderRelationsSidebarHTML();
            }
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
    }

    renderCategoriesHTML() {
        return this.categories.map(category => {
            const categoryTags = this.tags[category] || [];
            const categoryTitle = this.getCategoryTitle(category);
            const categoryIcon = getCategoryIcon(category);

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
        const tagChips = document.querySelectorAll('.tag-chip');
        for (let chip of tagChips) {
            // Extract tag name from text nodes only
            let tagText = '';
            for (const node of chip.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) tagText += node.textContent;
            }
            if (tagText.trim().replace(/^[⚡+-]+\s*/, '') === tag) {
                const cntSpan = chip.querySelector('.cnt');
                if (cntSpan) {
                    return cntSpan.textContent;
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

    renderRelationsSidebarHTML() {
        return `
            <div class="inline-relations-editor panel" id="inlineRelationsEditor">
                <div class="inline-relations-header">🔗 Relations</div>
                <div class="inline-relations-body">
                    <div class="edit-relations-help">
                        Use local image IDs. Manual parent/child edits reject cycles and reverse parent links.
                    </div>
                    <div class="edit-category-tags edit-relations-list" id="relations-list">
                        ${this.renderRelationsListHTML()}
                    </div>
                    <button class="add-tag-btn" id="addRelationBtn">
                        + ADD RELATION
                    </button>
                </div>
            </div>
        `;
    }

    renderRelationsListHTML() {
        if (!this.relations.length) {
            return '<div class="edit-empty-state">No relations</div>';
        }

        return this.relations.map((relation, index) => this.renderRelationItemHTML(relation, index)).join('');
    }

    renderRelationItemHTML(relation, index) {
        const relationId = escapeHtml(String(relation.id ?? `tmp-${index}`));
        const filepath = escapeHtml(relation.other_filepath || '');
        const source = escapeHtml(relation.source || 'manual');
        const imageId = escapeHtml(String(relation.other_image_id));

        return `
            <div class="edit-tag-row edit-relation-row" data-relation-index="${index}" data-relation-id="${relationId}">
                <button class="remove-tag-btn remove-relation-btn" data-relation-index="${index}">✖</button>
                <div class="relation-summary">
                    <span class="relation-target">#${imageId}</span>
                    <span class="relation-path" title="${filepath}">${filepath}</span>
                    <span class="relation-source">${source}</span>
                </div>
                <select class="relation-type-select" data-relation-index="${index}">
                    ${this.renderRelationTypeOptions(relation.display_type)}
                </select>
            </div>
        `;
    }

    renderRelationTypeOptions(selectedType) {
        const types = [
            ['parent', 'Parent'],
            ['child', 'Child'],
            ['sibling', 'Sibling']
        ];

        return types.map(([value, label]) =>
            `<option value="${value}"${value === selectedType ? ' selected' : ''}>${label}</option>`
        ).join('');
    }



    attachEditEvents() {
        const editContainer = document.getElementById('inlineTagEditor');
        const relationsContainer = document.getElementById('inlineRelationsEditor');
        if (!editContainer && !relationsContainer) return;

        // Add button click handlers
        editContainer?.querySelectorAll('.add-tag-btn').forEach(btn => {
            if (btn.id === 'addRelationBtn') {
                return;
            }
            btn.addEventListener('click', () => {
                const category = btn.getAttribute('data-category');
                if (!category) {
                    return;
                }
                this.showAddTagInput(category);
            });
        });

        // Remove button click handlers
        editContainer?.querySelectorAll('.remove-tag-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (btn.classList.contains('remove-relation-btn')) {
                    return;
                }
                const category = btn.getAttribute('data-category');
                const index = parseInt(btn.getAttribute('data-index'));
                this.removeTag(category, index);
            });
        });

        relationsContainer?.querySelectorAll('.remove-relation-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const index = parseInt(btn.getAttribute('data-relation-index'), 10);
                this.removeRelation(index);
            });
        });

        relationsContainer?.querySelectorAll('.relation-type-select').forEach(select => {
            select.addEventListener('change', () => {
                const index = parseInt(select.getAttribute('data-relation-index'), 10);
                this.updateRelationType(index, select.value);
            });
        });

        const addRelationBtn = document.getElementById('addRelationBtn');
        if (addRelationBtn) {
            addRelationBtn.addEventListener('click', () => this.showAddRelationInput());
        }
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
                    const icon = getCategoryIcon(item.category || 'general');

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

    refreshRelations() {
        const relationContainer = document.getElementById('relations-list');
        if (!relationContainer) return;

        relationContainer.innerHTML = this.renderRelationsListHTML();

        relationContainer.querySelectorAll('.remove-relation-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const index = parseInt(btn.getAttribute('data-relation-index'), 10);
                this.removeRelation(index);
            });
        });

        relationContainer.querySelectorAll('.relation-type-select').forEach(select => {
            select.addEventListener('change', () => {
                const index = parseInt(select.getAttribute('data-relation-index'), 10);
                this.updateRelationType(index, select.value);
            });
        });
    }

    showAddRelationInput() {
        document.querySelectorAll('.add-relation-input-row').forEach(row => row.remove());

        const relationContainer = document.getElementById('relations-list');
        if (!relationContainer) return;

        const inputRow = document.createElement('div');
        inputRow.className = 'add-relation-input-row edit-tag-row edit-relation-row';
        inputRow.innerHTML = `
            <button class="remove-tag-btn cancel-add-relation-btn" type="button">✖</button>
            <div class="relation-add-fields">
                <input type="number" min="1" class="new-relation-id-input" placeholder="Target image ID">
                <select class="new-relation-type-select">
                    ${this.renderRelationTypeOptions('sibling')}
                </select>
            </div>
        `;

        relationContainer.appendChild(inputRow);

        const idInput = inputRow.querySelector('.new-relation-id-input');
        const typeSelect = inputRow.querySelector('.new-relation-type-select');
        const cancelBtn = inputRow.querySelector('.cancel-add-relation-btn');

        const commit = () => {
            const otherImageId = parseInt(idInput.value, 10);
            if (!Number.isInteger(otherImageId) || otherImageId <= 0) {
                showNotification('Enter a valid target image ID', 'warning');
                return;
            }

            this.addRelation(otherImageId, typeSelect.value);
            inputRow.remove();
        };

        idInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                commit();
            } else if (e.key === 'Escape') {
                inputRow.remove();
            }
        });

        typeSelect.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                commit();
            }
        });

        cancelBtn.addEventListener('click', () => inputRow.remove());
        idInput.focus();
    }

    addRelation(otherImageId, displayType) {
        const currentImageId = this.getCurrentImageId();
        if (!currentImageId) {
            showNotification('Current image ID is unavailable', 'error');
            return;
        }

        if (otherImageId === currentImageId) {
            showNotification('An image cannot relate to itself', 'warning');
            return;
        }

        if (this.relations.some(relation => relation.other_image_id === otherImageId)) {
            showNotification('A relation to that image already exists', 'warning');
            return;
        }

        this.relations.push({
            id: `tmp-${this.nextTempRelationId++}`,
            other_image_id: otherImageId,
            other_filepath: '(will resolve on save)',
            display_type: displayType,
            source: 'manual',
            created_at: null
        });
        this.refreshRelations();
        showNotification('Relation staged', 'info');
    }

    removeRelation(index) {
        const relation = this.relations[index];
        if (!relation) {
            return;
        }

        this.relations.splice(index, 1);
        this.refreshRelations();
        showNotification('Relation removed', 'info');
    }

    updateRelationType(index, displayType) {
        if (!this.relations[index]) {
            return;
        }

        this.relations[index].display_type = displayType;
        showNotification('Relation updated', 'info');
    }

    getCurrentImageId() {
        const imageId = parseInt(document.getElementById('imageId')?.value || '', 10);
        return Number.isInteger(imageId) && imageId > 0 ? imageId : null;
    }

    getRelationChanges() {
        const originalById = new Map(this.originalRelations.filter(relation => relation.id != null).map(relation => [String(relation.id), relation]));
        const currentById = new Map(this.relations.filter(relation => relation.id != null && !String(relation.id).startsWith('tmp-')).map(relation => [String(relation.id), relation]));

        const deletions = this.originalRelations
            .filter(relation => relation.id != null)
            .filter(relation => !currentById.has(String(relation.id)))
            .map(relation => ({ relation_id: relation.id }));

        const updates = this.relations
            .filter(relation => relation.id != null && !String(relation.id).startsWith('tmp-'))
            .filter(relation => {
                const original = originalById.get(String(relation.id));
                return original && original.display_type !== relation.display_type;
            })
            .map(relation => ({
                relation_id: relation.id,
                other_image_id: relation.other_image_id,
                display_type: relation.display_type
            }));

        const creations = this.relations
            .filter(relation => String(relation.id).startsWith('tmp-'))
            .map(relation => ({
                other_image_id: relation.other_image_id,
                display_type: relation.display_type
            }));

        return { deletions, updates, creations };
    }

    hasTagChanges() {
        return JSON.stringify(this.tags) !== JSON.stringify(this.originalTags);
    }

    hasRelationChanges() {
        const { deletions, updates, creations } = this.getRelationChanges();
        return deletions.length > 0 || updates.length > 0 || creations.length > 0;
    }

    renderViewMode() {
        const editContainer = document.getElementById('inlineTagEditor');
        if (editContainer) {
            editContainer.remove();
        }

        const tagsList = document.querySelector('.tags-scroll');
        if (tagsList) {
            tagsList.style.display = '';
        }

        // Restore left sidebar panels
        const sidebarLeft = document.getElementById('sidebarLeft');
        if (sidebarLeft) {
            sidebarLeft.classList.remove('editing-mode');
            // Show all sections in sidebar again
            const sections = sidebarLeft.querySelectorAll('.sidebar-section');
            sections.forEach(section => {
                section.style.display = '';
            });
        }

        // Remove container class to restore grid layout
        const container = document.querySelector('.image-page .container');
        if (container) {
            container.classList.remove('tag-editor-expanded');
        }

        const toolbar = document.getElementById('imageToolbar');
        if (toolbar) {
            toolbar.classList.remove('image-toolbar--editing');
        }

        const imageViewWrapper = document.querySelector('.image-page .image-view-wrapper');
        if (imageViewWrapper) {
            imageViewWrapper.classList.remove('image-view-wrapper--toolbar-lock');
        }

        // Restore right sidebar
        const sidebarRight = document.getElementById('sidebarRight');
        if (sidebarRight) {
            sidebarRight.style.display = '';
            sidebarRight.classList.remove('editing-mode');
        }

        const rightContent = document.getElementById('sidebar-right-content');
        if (rightContent && rightContent.dataset.originalHtml) {
            rightContent.innerHTML = rightContent.dataset.originalHtml;
        }

        // Reset button
        const editBtn = document.querySelector('.toolbar-btn.primary') || document.querySelector('.actions-grid .action-btn.primary');
        if (editBtn) {
            editBtn.innerHTML = '<span class="toolbar-icon">📝</span>';
            editBtn.title = 'Edit Tags and Relations';
            editBtn.classList.remove('editing-mode');
        }

        const cancelBtn = document.getElementById('cancelEditBtn');
        if (cancelBtn) {
            cancelBtn.remove();
        }

        const clearDeltasBtn = document.getElementById('clearDeltasBtn');
        if (clearDeltasBtn) {
            clearDeltasBtn.remove();
        }

        this.isEditing = false;

        // Clean up suggestions
        this.hideSuggestions();
    }

    async saveTags() {
        const filepath = document.getElementById('imageFilepath')?.value;
        const imageId = this.getCurrentImageId();
        if (!filepath) {
            console.error('No filepath found');
            showNotification('Error: No filepath', 'error');
            return;
        }
        if (!imageId) {
            console.error('No image ID found');
            showNotification('Error: No image ID', 'error');
            return;
        }

        if (!this.hasTagChanges() && !this.hasRelationChanges()) {
            showNotification('No changes to save', 'info');
            this.renderViewMode();
            return;
        }

        const editBtn = document.querySelector('.toolbar-btn.primary') || document.querySelector('.actions-grid .action-btn.primary');
        if (editBtn) {
            editBtn.innerHTML = '<span class="toolbar-icon">💾</span>';
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

        try {
            if (this.hasTagChanges()) {
                const tagResponse = await fetch('/api/edit_tags', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filepath: filepath,
                        categorized_tags: categorizedTags
                    })
                });
                const tagData = await this.parseJsonResponse(tagResponse);
                if (tagData.status !== 'success' && tagData.success !== true) {
                    throw new Error(tagData.error || 'Tag save failed');
                }
            }

            if (this.hasRelationChanges()) {
                await this.saveRelationChanges(imageId);
            }

            showNotification('Changes saved!', 'success');
            this.renderViewMode();
            setTimeout(() => location.reload(), 500);
        } catch (err) {
            console.error('Save error:', err);
            showNotification('Failed to save: ' + err.message, 'error');
            if (editBtn) {
                editBtn.innerHTML = '<span class="toolbar-icon">💾</span>';
                editBtn.title = 'Save Changes';
                editBtn.disabled = false;
            }
        }
    }

    async saveRelationChanges(imageId) {
        const { deletions, updates, creations } = this.getRelationChanges();

        for (const relation of deletions) {
            const response = await fetch(`/api/image-relations/${relation.relation_id}`, {
                method: 'DELETE'
            });
            await this.parseJsonResponse(response);
        }

        for (const relation of updates) {
            const response = await fetch(`/api/image-relations/${relation.relation_id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_id: imageId,
                    other_image_id: relation.other_image_id,
                    display_type: relation.display_type
                })
            });
            await this.parseJsonResponse(response);
        }

        for (const relation of creations) {
            const response = await fetch('/api/image-relations', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image_id: imageId,
                    other_image_id: relation.other_image_id,
                    display_type: relation.display_type
                })
            });
            await this.parseJsonResponse(response);
        }
    }

    async parseJsonResponse(response) {
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Response is not JSON:', text.substring(0, 500));
            throw new Error('Server returned non-JSON response');
        }

        const data = await response.json();
        if (!response.ok || data.success === false) {
            throw new Error(data.error || `Request failed with ${response.status}`);
        }
        return data;
    }

    cancelEdit() {
        this.tags = JSON.parse(JSON.stringify(this.originalTags));
        this.relations = JSON.parse(JSON.stringify(this.originalRelations));
        this.renderViewMode();
        showNotification('Changes cancelled', 'info');
    }

    async clearDeltas() {
        // Get the current filepath from the data attribute
        const imageViewContainer = document.getElementById('imageViewContainer');
        if (!imageViewContainer) {
            showNotification('Could not find image container', 'error');
            return;
        }

        const filepath = imageViewContainer.dataset.filepath;
        if (!filepath) {
            showNotification('Could not find image path', 'error');
            return;
        }

        // Confirm with user
        if (!confirm('Clear all manual modification markers for this image?\n\nThis will remove the strikethrough/crossed-out tags and reset the delta tracking.\n\nNote: This does NOT change the actual tags, only the modification markers.')) {
            return;
        }

        try {
            const response = await fetch('/api/clear_deltas', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ filepath })
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showNotification(result.message, 'success');
                // Reload the page to show updated deltas
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                showNotification(result.error || 'Failed to clear deltas', 'error');
            }
        } catch (err) {
            console.error('Clear deltas error:', err);
            showNotification('Failed to clear deltas: ' + err.message, 'error');
        }
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
    if (window.tagEditor.isEditing) {
        const editBtn = document.querySelector('.toolbar-btn.primary') || document.querySelector('.actions-grid .action-btn.primary');
        if (editBtn && editBtn.classList.contains('editing-mode')) {
            window.tagEditor.saveTags();
        } else {
            window.tagEditor.toggleEditMode();
        }
    } else {
        window.tagEditor.toggleEditMode();
    }
}

// Attach cancel and clear deltas handlers
document.addEventListener('click', (e) => {
    const cancelButton = e.target.closest('#cancelEditBtn');
    if (cancelButton) {
        window.tagEditor.cancelEdit();
        return;
    }

    const clearDeltasButton = e.target.closest('#clearDeltasBtn');
    if (clearDeltasButton) {
        window.tagEditor.clearDeltas();
    }
});

// Expose functions globally for onclick handlers
window.toggleTagEditor = toggleTagEditor;
window.saveTags = saveTags;

// Legacy function for compatibility
function saveTags() {
    window.tagEditor.saveTags();
}

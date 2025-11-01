// static/js/autocomplete.js
import { escapeHtml, formatCount } from './utils/helpers.js';

class Autocomplete {
    constructor(chipInputId = 'chipTextInput', suggestionsId = 'autocompleteSuggestions') {
        this.chipTextInput = document.getElementById(chipInputId);
        this.chipInputChips = document.getElementById('chipInputChips');
        this.chipInputWrapper = document.getElementById('chipInputWrapper');
        this.hiddenInput = document.getElementById('searchInput');
        this.suggestions = document.getElementById(suggestionsId);
        this.clearButton = document.getElementById('searchClear');
        this.searchForm = document.getElementById('searchForm');

        this.debounceTimer = null;
        this.selectedIndex = -1;
        this.currentSuggestions = [];
        this.chips = [];

        if (!this.chipTextInput || !this.suggestions) {
            console.error('Autocomplete: Required elements not found');
            return;
        }

        this.init();
        this.loadInitialQuery();
    }

    init() {
        // Input event for autocomplete
        this.chipTextInput.addEventListener('input', this.handleInput.bind(this));

        // Keydown for navigation and chip creation
        this.chipTextInput.addEventListener('keydown', this.handleKeydown.bind(this));

        // Focus handler
        this.chipTextInput.addEventListener('focus', this.handleFocus.bind(this));

        // Click on wrapper to focus input or remove chip
        this.chipInputWrapper.addEventListener('click', (e) => {
            // Check if clicking on a chip to remove it
            if (e.target.closest('.search-chip')) {
                const chip = e.target.closest('.search-chip');
                const index = parseInt(chip.getAttribute('data-index'), 10);
                if (!isNaN(index)) {
                    this.removeChip(index);
                }
            } else if (e.target === this.chipInputWrapper || e.target === this.chipInputChips) {
                this.chipTextInput.focus();
            }
        });

        // Click outside to close suggestions
        document.addEventListener('click', this.handleClickOutside.bind(this));

        // Form submit handler
        if (this.searchForm) {
            this.searchForm.addEventListener('submit', () => {
                // Add current text as chip if not empty
                const currentText = this.chipTextInput.value.trim();
                if (currentText) {
                    this.addChipFromText(currentText);
                }
                this.updateHiddenInput();
            });
        }
    }

    loadInitialQuery() {
        // Parse initial query from hidden input and create chips
        const initialQuery = this.hiddenInput.value.trim();
        if (initialQuery) {
            const tokens = initialQuery.split(/\s+/);
            tokens.forEach(token => {
                if (token) {
                    this.addChipFromText(token);
                }
            });
        }
        this.updateClearButton();
    }

    getCategoryIcon(category) {
        const icons = {
            'character': '👤',
            'copyright': '©️',
            'artist': '🎨',
            'species': '🐾',
            'general': '🏷️',
            'meta': '⚙️'
        };
        return icons[category] || '🏷️';
    }

    parseToken(token) {
        let type = 'tag';
        let display = token;
        let icon = '🏷️';
        let category = null;

        // Category filters (character:, copyright:, etc.)
        const categoryMatch = token.match(/^(character|copyright|artist|species|meta|general):(.+)$/);
        if (categoryMatch) {
            category = categoryMatch[1];
            const tag = categoryMatch[2];
            type = category;
            display = tag;
            icon = this.getCategoryIcon(category);
        } else if (token.startsWith('source:')) {
            type = 'source';
            display = token.split(':')[1];
            icon = '🌐';
        } else if (token.startsWith('filename:')) {
            type = 'filename';
            display = token.split(':')[1];
            icon = '📁';
        } else if (token.startsWith('pool:')) {
            type = 'pool';
            display = token.split(':')[1];
            icon = '📚';
        } else if (token.startsWith('has:')) {
            type = 'filter';
            display = token;
            icon = '🔗';
        } else if (token.startsWith('.')) {
            type = 'extension';
            display = token;
            icon = '📄';
        } else if (token.startsWith('-')) {
            type = 'negative';
            display = token.substring(1);
            icon = '🚫';
        }

        return { token, type, display, icon, category };
    }

    addChipFromText(text) {
        const trimmed = text.trim();
        if (!trimmed) return;

        const parsed = this.parseToken(trimmed);
        this.chips.push(parsed);
        this.renderChips();
        this.updateHiddenInput();
        this.updateClearButton();
    }

    addChipFromAutocomplete(tag, category = null) {
        let token = tag;
        // Always use category prefix if category is provided and not empty
        if (category && category !== '') {
            token = `${category}:${tag}`;
        }

        this.addChipFromText(token);
        this.chipTextInput.value = '';
        this.suggestions.classList.remove('active');
        this.chipTextInput.focus();

        // Visual feedback
        this.chipInputWrapper.style.borderColor = 'rgba(135, 206, 235, 0.8)';
        setTimeout(() => {
            this.chipInputWrapper.style.borderColor = '';
        }, 200);
    }

    removeChip(index) {
        this.chips.splice(index, 1);
        this.renderChips();
        this.updateHiddenInput();
        this.updateClearButton();
        this.chipTextInput.focus();
    }

    removeLastChip() {
        if (this.chips.length > 0) {
            this.chips.pop();
            this.renderChips();
            this.updateHiddenInput();
            this.updateClearButton();
        }
    }

    renderChips() {
        this.chipInputChips.innerHTML = this.chips.map((chip, index) => `
            <div class="search-chip ${chip.type}" data-index="${index}">
                <span class="search-chip-icon">${chip.icon}</span>
                <span class="search-chip-text">${escapeHtml(chip.display)}</span>
            </div>
        `).join('');
    }

    updateHiddenInput() {
        this.hiddenInput.value = this.chips.map(chip => chip.token).join(' ');
    }

    updateClearButton() {
        // No clear button anymore
    }

    showSuggestions(data) {
        // Handle both old (array) and new (grouped) formats
        if (Array.isArray(data)) {
            this.showLegacySuggestions(data);
            return;
        }

        if (!data.groups || data.groups.length === 0) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.currentSuggestions = [];
        let html = '';
        let itemIndex = 0;

        data.groups.forEach(group => {
            if (group.items.length === 0) return;

            html += `<div class="autocomplete-group">
                <div class="autocomplete-group-header">${group.name}</div>`;

            group.items.forEach(item => {
                const displayText = item.display || item.tag;
                const countText = item.count ? formatCount(item.count) : '';
                const icon = item.category ? this.getCategoryIcon(item.category) : '🏷️';
                const typeClass = item.type || 'tag';
                const categoryBadge = item.category ? `<span class="category-badge ${item.category}">${item.category}</span>` : '';

                html += `
                    <div class="autocomplete-item ${typeClass}"
                         data-tag="${escapeHtml(item.tag)}"
                         data-category="${escapeHtml(item.category || '')}"
                         data-index="${itemIndex}"
                         style="animation-delay: ${itemIndex * 0.01}s">
                        <div class="autocomplete-left">
                            <span class="autocomplete-icon">${icon}</span>
                            <span class="autocomplete-tag">${escapeHtml(displayText)}</span>
                            ${categoryBadge}
                        </div>
                        ${countText ? `<span class="autocomplete-count">${countText}</span>` : ''}
                    </div>
                `;

                this.currentSuggestions.push(item);
                itemIndex++;
            });

            html += '</div>';
        });

        this.suggestions.innerHTML = html;
        this.selectedIndex = -1;
        this.suggestions.classList.add('active');

        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.getAttribute('data-tag');
                const category = item.getAttribute('data-category');
                this.addChipFromAutocomplete(tag, category);
            });

            item.addEventListener('mouseenter', () => {
                item.style.transform = 'translateX(5px)';
            });

            item.addEventListener('mouseleave', () => {
                if (!item.classList.contains('selected')) {
                    item.style.transform = 'translateX(0)';
                }
            });
        });
    }

    showLegacySuggestions(data) {
        if (data.length === 0) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.currentSuggestions = data;
        this.selectedIndex = -1;

        this.suggestions.innerHTML = data.map((item, idx) => {
            const displayText = item.display || item.tag;
            const countText = item.count ? this.formatCount(item.count) : '';
            const icon = item.icon || '🏷️';
            const typeClass = item.type || 'tag';

            return `
                <div class="autocomplete-item ${typeClass}" data-tag="${escapeHtml(item.tag)}" data-index="${idx}" style="animation-delay: ${idx * 0.01}s">
                    <div class="autocomplete-left">
                        <span class="autocomplete-icon">${icon}</span>
                        <span class="autocomplete-tag">${escapeHtml(displayText)}</span>
                    </div>
                    ${countText ? `<span class="autocomplete-count">${countText}</span>` : ''}
                </div>
            `;
        }).join('');

        this.suggestions.classList.add('active');

        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.getAttribute('data-tag');
                this.addChipFromAutocomplete(tag);
            });

            item.addEventListener('mouseenter', () => {
                item.style.transform = 'translateX(5px)';
            });

            item.addEventListener('mouseleave', () => {
                if (!item.classList.contains('selected')) {
                    item.style.transform = 'translateX(0)';
                }
            });
        });
    }


    updateSelection(direction) {
        const items = this.suggestions.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        if (this.selectedIndex >= 0 && this.selectedIndex < items.length) {
            items[this.selectedIndex].classList.remove('selected');
            items[this.selectedIndex].style.transform = 'translateX(0)';
        }

        this.selectedIndex += direction;
        if (this.selectedIndex < 0) this.selectedIndex = items.length - 1;
        if (this.selectedIndex >= items.length) this.selectedIndex = 0;

        items[this.selectedIndex].classList.add('selected');
        items[this.selectedIndex].style.transform = 'translateX(5px)';
        items[this.selectedIndex].scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    handleFocus() {
        const query = this.chipTextInput.value.trim();
        if (query.length >= 2) {
            this.performSearch(query);
        }
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value;

        // Update clear button immediately
        this.updateClearButton();

        if (query.length < 2) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.debounceTimer = setTimeout(() => {
            this.performSearch(query);
        }, 200);
    }

    performSearch(query) {
        fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`)
            .then(res => {
                if (!res.ok) throw new Error('Network response was not ok');
                return res.json();
            })
            .then(data => this.showSuggestions(data))
            .catch(err => {
                console.error('Autocomplete error:', err);
                this.suggestions.classList.remove('active');
            });
    }

    handleKeydown(e) {
        const hasActiveSuggestions = this.suggestions.classList.contains('active');

        // Backspace: Delete last chip if input is empty
        if (e.key === 'Backspace' && this.chipTextInput.value === '') {
            e.preventDefault();
            this.removeLastChip();
            return;
        }

        // Enter: Create chip from current text OR select from autocomplete
        if (e.key === 'Enter') {
            if (hasActiveSuggestions && this.selectedIndex >= 0 && this.selectedIndex < this.currentSuggestions.length) {
                e.preventDefault();
                const suggestion = this.currentSuggestions[this.selectedIndex];
                this.addChipFromAutocomplete(suggestion.tag, suggestion.category);
            } else {
                const currentText = this.chipTextInput.value.trim();
                if (currentText) {
                    e.preventDefault();
                    this.addChipFromText(currentText);
                    this.chipTextInput.value = '';
                    this.suggestions.classList.remove('active');
                }
                // If empty and has chips, allow form submission
            }
            return;
        }

        // Space: Create chip from current text
        if (e.key === ' ') {
            const currentText = this.chipTextInput.value.trim();
            if (currentText) {
                e.preventDefault();
                this.addChipFromText(currentText);
                this.chipTextInput.value = '';
                this.suggestions.classList.remove('active');
            }
            return;
        }

        // Tab: Select from autocomplete if available
        if (e.key === 'Tab' && hasActiveSuggestions) {
            if (this.selectedIndex >= 0 && this.selectedIndex < this.currentSuggestions.length) {
                e.preventDefault();
                const suggestion = this.currentSuggestions[this.selectedIndex];
                this.addChipFromAutocomplete(suggestion.tag, suggestion.category);
            }
            return;
        }

        // Arrow navigation
        if (hasActiveSuggestions) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this.updateSelection(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                this.updateSelection(-1);
            }
        }

        // Escape: Close suggestions
        if (e.key === 'Escape') {
            this.suggestions.classList.remove('active');
            this.chipTextInput.blur();
        }
    }

    handleClickOutside(e) {
        if (!e.target.closest('.autocomplete-container')) {
            this.suggestions.classList.remove('active');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new Autocomplete('chipTextInput', 'autocompleteSuggestions');
});

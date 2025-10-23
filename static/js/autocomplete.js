// static/js/autocomplete.js
class Autocomplete {
    constructor(inputId, suggestionsId, filterChipsId = 'filterChips') {
        this.searchInput = document.getElementById(inputId);
        this.suggestions = document.getElementById(suggestionsId);
        this.filterChipsContainer = document.getElementById(filterChipsId);
        this.clearButton = document.getElementById('searchClear');
        this.debounceTimer = null;
        this.selectedIndex = -1;
        this.currentSuggestions = [];
        this.activeFilters = new Set();

        if (!this.searchInput || !this.suggestions) {
            console.error('Autocomplete: Required elements not found');
            return;
        }

        this.searchInput.addEventListener('input', this.handleInput.bind(this));
        this.searchInput.addEventListener('keydown', this.handleKeydown.bind(this));
        this.searchInput.addEventListener('focus', this.handleFocus.bind(this));
        document.addEventListener('click', this.handleClickOutside.bind(this));

        // Clear button handler
        if (this.clearButton) {
            this.clearButton.addEventListener('click', () => {
                this.searchInput.value = '';
                this.updateFilterChips();
                this.updateClearButton();
                this.suggestions.classList.remove('active');
                this.searchInput.focus();
            });
        }

        // Parse initial query to show chips
        this.updateFilterChips();
        this.updateClearButton();
    }

    updateClearButton() {
        if (!this.clearButton) return;
        this.clearButton.style.display = this.searchInput.value.trim() ? 'flex' : 'none';
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
                const countText = item.count ? this.formatCount(item.count) : '';
                const icon = item.category ? this.getCategoryIcon(item.category) : '🏷️';
                const typeClass = item.type || 'tag';
                const categoryBadge = item.category ? `<span class="category-badge ${item.category}">${item.category}</span>` : '';

                html += `
                    <div class="autocomplete-item ${typeClass}" data-tag="${this.escapeHtml(item.tag)}" data-index="${itemIndex}" style="animation-delay: ${itemIndex * 0.01}s">
                        <div class="autocomplete-left">
                            <span class="autocomplete-icon">${icon}</span>
                            <span class="autocomplete-tag">${this.escapeHtml(displayText)}</span>
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
                this.insertTag(tag);
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
                <div class="autocomplete-item ${typeClass}" data-tag="${this.escapeHtml(item.tag)}" data-index="${idx}" style="animation-delay: ${idx * 0.01}s">
                    <div class="autocomplete-left">
                        <span class="autocomplete-icon">${icon}</span>
                        <span class="autocomplete-tag">${this.escapeHtml(displayText)}</span>
                    </div>
                    ${countText ? `<span class="autocomplete-count">${countText}</span>` : ''}
                </div>
            `;
        }).join('');

        this.suggestions.classList.add('active');

        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.getAttribute('data-tag');
                this.insertTag(tag);
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

    updateFilterChips() {
        if (!this.filterChipsContainer) return;

        const query = this.searchInput.value.trim();
        if (!query) {
            this.filterChipsContainer.innerHTML = '';
            this.filterChipsContainer.style.display = 'none';
            return;
        }

        const tokens = query.split(/\s+/);
        const chips = [];

        tokens.forEach(token => {
            let type = 'tag';
            let display = token;
            let icon = '🏷️';

            if (token.startsWith('source:')) {
                type = 'source';
                display = token.split(':')[1];
                icon = '🌐';
            } else if (token.startsWith('filename:')) {
                type = 'filename';
                display = `file: ${token.split(':')[1]}`;
                icon = '📁';
            } else if (token.startsWith('pool:')) {
                type = 'pool';
                display = `pool: ${token.split(':')[1]}`;
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
                display = token;
                icon = '🚫';
            }

            chips.push({ token, type, display, icon });
        });

        if (chips.length === 0) {
            this.filterChipsContainer.innerHTML = '';
            this.filterChipsContainer.style.display = 'none';
            return;
        }

        this.filterChipsContainer.innerHTML = chips.map(chip => `
            <div class="filter-chip ${chip.type}">
                <span class="chip-icon">${chip.icon}</span>
                <span class="chip-text">${this.escapeHtml(chip.display)}</span>
                <button class="chip-remove" data-token="${this.escapeHtml(chip.token)}">&times;</button>
            </div>
        `).join('');
        this.filterChipsContainer.style.display = 'flex';

        // Add click handlers for remove buttons
        this.filterChipsContainer.querySelectorAll('.chip-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const token = btn.getAttribute('data-token');
                this.removeToken(token);
            });
        });
    }

    removeToken(token) {
        const tokens = this.searchInput.value.trim().split(/\s+/);
        const filtered = tokens.filter(t => t !== token);
        this.searchInput.value = filtered.join(' ');
        if (this.searchInput.value) this.searchInput.value += ' ';
        this.updateFilterChips();
        this.searchInput.focus();
    }

    formatCount(count) {
        if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
        if (count >= 1000) return (count / 1000).toFixed(1) + 'k';
        return count.toString();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    insertTag(tag) {
        const tokens = this.searchInput.value.trim().split(/\s+/);
        tokens.pop();
        tokens.push(tag);
        this.searchInput.value = tokens.join(' ') + ' ';
        this.suggestions.classList.remove('active');
        this.updateFilterChips();
        this.searchInput.focus();

        this.searchInput.style.borderColor = 'rgba(135, 206, 235, 0.8)';
        setTimeout(() => {
            this.searchInput.style.borderColor = '';
        }, 200);
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
        const query = this.searchInput.value.trim();
        if (query.length >= 2) {
            this.performSearch(query);
        }
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value;

        // Update filter chips and clear button immediately
        this.updateFilterChips();
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
        if (!this.suggestions.classList.contains('active')) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.updateSelection(1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.updateSelection(-1);
        } else if (e.key === 'Enter') {
            if (this.selectedIndex >= 0 && this.selectedIndex < this.currentSuggestions.length) {
                e.preventDefault();
                this.insertTag(this.currentSuggestions[this.selectedIndex].tag);
            }
        } else if (e.key === 'Escape') {
            this.suggestions.classList.remove('active');
            this.searchInput.blur();
        } else if (e.key === 'Tab') {
            if (this.selectedIndex >= 0 && this.selectedIndex < this.currentSuggestions.length) {
                e.preventDefault();
                this.insertTag(this.currentSuggestions[this.selectedIndex].tag);
            }
        }
    }

    handleClickOutside(e) {
        if (!e.target.closest('.autocomplete-container')) {
            this.suggestions.classList.remove('active');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new Autocomplete('searchInput', 'autocompleteSuggestions');
});
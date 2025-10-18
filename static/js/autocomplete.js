// static/js/autocomplete.js
class Autocomplete {
    constructor(inputId, suggestionsId) {
        this.searchInput = document.getElementById(inputId);
        this.suggestions = document.getElementById(suggestionsId);
        this.debounceTimer = null;
        this.selectedIndex = -1;
        this.currentSuggestions = [];

        if (!this.searchInput || !this.suggestions) {
            console.error('Autocomplete: Required elements not found');
            return;
        }

        this.searchInput.addEventListener('input', this.handleInput.bind(this));
        this.searchInput.addEventListener('keydown', this.handleKeydown.bind(this));
        this.searchInput.addEventListener('focus', this.handleFocus.bind(this));
        document.addEventListener('click', this.handleClickOutside.bind(this));
    }

    showSuggestions(data) {
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
                <div class="autocomplete-item ${typeClass}" data-tag="${this.escapeHtml(item.tag)}" style="animation-delay: ${idx * 0.01}s">
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
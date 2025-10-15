class Autocomplete {
    constructor(inputId, suggestionsId) {
        this.searchInput = document.getElementById(inputId);
        this.suggestions = document.getElementById(suggestionsId);
        this.selectedIndex = -1;
        this.currentSuggestions = [];
        this.debounceTimer = null;
        
        this.init();
    }
    
    init() {
        this.searchInput.addEventListener('input', (e) => this.handleInput(e));
        this.searchInput.addEventListener('keydown', (e) => this.handleKeydown(e));
        document.addEventListener('click', (e) => this.handleClickOutside(e));
    }
    
    formatCount(count) {
        if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
        if (count >= 1000) return (count / 1000).toFixed(1) + 'k';
        return count.toString();
    }
    
    showSuggestions(data) {
        this.currentSuggestions = data;
        this.selectedIndex = -1;
        
        if (data.length === 0) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.suggestions.innerHTML = data.map((item, idx) => `
            <div class="autocomplete-item" data-index="${idx}">
                <span class="autocomplete-tag">${item.tag}</span>
                <span class="autocomplete-count">${this.formatCount(item.count)}</span>
            </div>
        `).join('');
        
        this.suggestions.classList.add('active');

        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.querySelector('.autocomplete-tag').textContent;
                this.insertTag(tag);
            });
        });
    }
    
    insertTag(tag) {
        const tokens = this.searchInput.value.trim().split(/\s+/);
        tokens.pop();
        tokens.push(tag);
        this.searchInput.value = tokens.join(' ') + ' ';
        this.suggestions.classList.remove('active');
        this.searchInput.focus();
    }
    
    updateSelection(direction) {
        const items = this.suggestions.querySelectorAll('.autocomplete-item');
        if (items.length === 0) return;

        if (this.selectedIndex >= 0 && this.selectedIndex < items.length) {
            items[this.selectedIndex].classList.remove('selected');
        }

        this.selectedIndex += direction;
        if (this.selectedIndex < 0) this.selectedIndex = items.length - 1;
        if (this.selectedIndex >= items.length) this.selectedIndex = 0;

        items[this.selectedIndex].classList.add('selected');
        items[this.selectedIndex].scrollIntoView({ block: 'nearest' });
    }
    
    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value;

        if (query.length < 2) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.debounceTimer = setTimeout(() => {
            fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => this.showSuggestions(data))
                .catch(err => console.error('Autocomplete error:', err));
        }, 200);
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
        }
    }
    
    handleClickOutside(e) {
        if (!e.target.closest('.autocomplete-container')) {
            this.suggestions.classList.remove('active');
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new Autocomplete('searchInput', 'autocompleteSuggestions');
});
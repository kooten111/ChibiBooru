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
        this.searchInput.addEventListener('focus', () => this.handleFocus());
        document.addEventListener('click', (e) => this.handleClickOutside(e));
        
        // Add smooth focus effect
        this.searchInput.addEventListener('focus', () => {
            this.searchInput.style.transform = 'translateY(-2px)';
        });
        
        this.searchInput.addEventListener('blur', () => {
            setTimeout(() => {
                this.searchInput.style.transform = 'translateY(0)';
            }, 200);
        });
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
                <span class="autocomplete-tag">${this.escapeHtml(item.tag)}</span>
                <span class="autocomplete-count">${this.formatCount(item.count)}</span>
            </div>
        `).join('');
        
        this.suggestions.classList.add('active');

        // Add click handlers with animation delay
        this.suggestions.querySelectorAll('.autocomplete-item').forEach((item, idx) => {
            item.style.animationDelay = `${idx * 0.01}s`;
            item.addEventListener('click', () => {
                const tag = item.querySelector('.autocomplete-tag').textContent;
                this.insertTag(tag);
            });
            
            // Add hover sound effect (optional, can be removed)
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
        
        // Add subtle flash effect
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
        // Re-trigger search if there's already input
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

// Add smooth page transitions on load
document.addEventListener('DOMContentLoaded', () => {
    // Initialize autocomplete
    new Autocomplete('searchInput', 'autocompleteSuggestions');
    
    // Detect image aspect ratios and add classes
    const thumbnails = document.querySelectorAll('.thumbnail');
    thumbnails.forEach((thumb, index) => {
        thumb.style.animationDelay = `${(index % 6) * 0.02}s`;
        
        const img = thumb.querySelector('img');
        if (img) {
            // If image already loaded
            if (img.complete) {
                classifyImage(img, thumb);
            } else {
                // Wait for image to load
                img.addEventListener('load', () => classifyImage(img, thumb));
            }
        }
    });
    
    // Add smooth scroll behavior
    document.documentElement.style.scrollBehavior = 'smooth';
    
    // Add loading state to search form
    const searchForm = document.getElementById('searchForm');
    if (searchForm) {
        searchForm.addEventListener('submit', (e) => {
            const button = searchForm.querySelector('button[type="submit"]');
            button.style.opacity = '0.7';
            button.textContent = 'Searching...';
        });
    }
});

function classifyImage(img, container) {
    const aspectRatio = img.naturalWidth / img.naturalHeight;
    
    // Wide images (aspect ratio > 1.5)
    if (aspectRatio > 1.5) {
        container.classList.add('wide');
    }
    // Tall images (aspect ratio < 0.7)
    else if (aspectRatio < 0.7) {
        container.classList.add('tall');
    }
}
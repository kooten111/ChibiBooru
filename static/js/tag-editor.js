class TagEditor {
    constructor() {
        this.tags = [];
        this.input = null;
        this.container = null;
        this.suggestions = null;
        this.debounceTimer = null;
    }

    init(existingTags) {
        this.tags = existingTags.filter(t => t.trim() !== '');
        this.input = document.getElementById('tagEditorInput');
        this.container = document.getElementById('tagChips');
        this.suggestions = document.getElementById('tagEditorSuggestions');
        
        this.render();
        this.attachEvents();
    }

    render() {
        this.container.innerHTML = this.tags.map((tag, idx) => `
            <div class="tag-chip" data-index="${idx}">
                <span class="tag-chip-text">${tag}</span>
                <button class="tag-chip-remove" onclick="tagEditor.removeTag(${idx})">&times;</button>
            </div>
        `).join('');
    }

    attachEvents() {
        this.input.addEventListener('input', (e) => this.handleInput(e));
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        document.addEventListener('click', (e) => this.handleClickOutside(e));
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value.trim();

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

    showSuggestions(data) {
        if (data.length === 0) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.suggestions.innerHTML = data.map((item, idx) => `
            <div class="autocomplete-item" data-tag="${item.tag}">
                <span class="autocomplete-tag">${item.tag}</span>
                <span class="autocomplete-count">${this.formatCount(item.count)}</span>
            </div>
        `).join('');
        
        this.suggestions.classList.add('active');

        this.suggestions.querySelectorAll('.autocomplete-item').forEach(item => {
            item.addEventListener('click', () => {
                const tag = item.getAttribute('data-tag');
                this.addTag(tag);
            });
        });
    }

    formatCount(count) {
        if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
        if (count >= 1000) return (count / 1000).toFixed(1) + 'k';
        return count.toString();
    }

    handleKeydown(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const tag = this.input.value.trim();
            if (tag) {
                this.addTag(tag);
            }
        } else if (e.key === 'Escape') {
            this.suggestions.classList.remove('active');
        } else if (e.key === 'Backspace' && this.input.value === '' && this.tags.length > 0) {
            e.preventDefault();
            this.removeTag(this.tags.length - 1);
        }
    }

    handleClickOutside(e) {
        if (!e.target.closest('.tag-editor')) {
            this.suggestions.classList.remove('active');
        }
    }

    addTag(tag) {
        tag = tag.trim().toLowerCase().replace(/\s+/g, '_');
        if (tag && !this.tags.includes(tag)) {
            this.tags.push(tag);
            this.render();
        }
        this.input.value = '';
        this.suggestions.classList.remove('active');
        this.input.focus();
    }

    removeTag(index) {
        this.tags.splice(index, 1);
        this.render();
    }

    getTags() {
        return this.tags.join(' ');
    }
}

const tagEditor = new TagEditor();

function toggleTagEditor() {
    const editor = document.getElementById('tagEditor');
    const isActive = editor.classList.toggle('active');
    
    if (isActive) {
        // Initialize with existing tags
        const existingTags = document.querySelectorAll('.tag-item a');
        const tags = Array.from(existingTags).map(a => a.textContent.trim());
        tagEditor.init(tags);
        document.getElementById('tagEditorInput').focus();
    }
}

function saveTags() {
    const tags = tagEditor.getTags();
    const filepath = document.getElementById('imageFilepath').value;

    fetch('/api/edit_tags', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            filepath: filepath,
            tags: tags
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            location.reload();
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        alert('Error saving tags: ' + error);
    });
}

function confirmDelete() {
    if (!confirm('Are you sure you want to delete this image? This cannot be undone.')) {
        return;
    }

    const filepath = document.getElementById('imageFilepath').value;

    fetch('/api/delete_image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            filepath: filepath
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            window.location.href = '/';
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(error => {
        alert('Error deleting image: ' + error);
    });
}
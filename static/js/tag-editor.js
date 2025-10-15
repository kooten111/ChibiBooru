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
        
        // Focus input with delay for smooth animation
        setTimeout(() => {
            this.input.focus();
        }, 50);
    }

    render() {
        this.container.innerHTML = this.tags.map((tag, idx) => `
            <div class="tag-chip" data-index="${idx}" style="animation-delay: ${idx * 0.02}s">
                <span class="tag-chip-text">${this.escapeHtml(tag)}</span>
                <button class="tag-chip-remove" onclick="tagEditor.removeTag(${idx})" title="Remove tag">&times;</button>
            </div>
        `).join('');
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    attachEvents() {
        this.input.addEventListener('input', (e) => this.handleInput(e));
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        document.addEventListener('click', (e) => this.handleClickOutside(e));
        
        // Add visual feedback on input focus
        this.input.addEventListener('focus', () => {
            this.input.parentElement.style.transform = 'translateY(-2px)';
        });
        
        this.input.addEventListener('blur', () => {
            setTimeout(() => {
                this.input.parentElement.style.transform = 'translateY(0)';
            }, 200);
        });
    }

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        const query = e.target.value.trim();

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

    showSuggestions(data) {
        if (data.length === 0) {
            this.suggestions.classList.remove('active');
            return;
        }

        this.suggestions.innerHTML = data.map((item, idx) => `
            <div class="autocomplete-item" data-tag="${this.escapeHtml(item.tag)}" style="animation-delay: ${idx * 0.01}s">
                <span class="autocomplete-tag">${this.escapeHtml(item.tag)}</span>
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
            
            // Flash the container
            this.container.style.borderColor = 'rgba(135, 206, 235, 0.6)';
            setTimeout(() => {
                this.container.style.borderColor = '';
            }, 200);
        } else if (this.tags.includes(tag)) {
            // Visual feedback for duplicate
            this.showNotification('Tag already added', 'warning');
        }
        
        this.input.value = '';
        this.suggestions.classList.remove('active');
        this.input.focus();
    }

    removeTag(index) {
        const chip = this.container.querySelector(`[data-index="${index}"]`);
        if (chip) {
            chip.style.animation = 'chipOut 0.2s ease-out';
            setTimeout(() => {
                this.tags.splice(index, 1);
                this.render();
            }, 150);
        }
    }

    getTags() {
        return this.tags.join(' ');
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 100px;
            right: 30px;
            padding: 12px 20px;
            background: ${type === 'warning' ? 'linear-gradient(135deg, #ff9966 0%, #ff6b6b 100%)' : 'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)'};
            color: white;
            border-radius: 10px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            z-index: 10000;
            font-weight: 600;
            animation: slideInRight 0.2s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.2s ease-out';
            setTimeout(() => notification.remove(), 200);
        }, 2000);
    }
}

// Add CSS animations dynamically
const style = document.createElement('style');
style.textContent = `
    @keyframes chipOut {
        to {
            opacity: 0;
            transform: scale(0.8) translateY(-10px);
        }
    }
    
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(100px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideOutRight {
        to {
            opacity: 0;
            transform: translateX(100px);
        }
    }
`;
document.head.appendChild(style);

const tagEditor = new TagEditor();

function toggleTagEditor() {
    const editor = document.getElementById('tagEditor');
    const isActive = editor.classList.toggle('active');
    
    if (isActive) {
        // Initialize with existing tags
        const existingTags = document.querySelectorAll('.tag-item a');
        const tags = Array.from(existingTags).map(a => a.textContent.trim());
        tagEditor.init(tags);
    } else {
        // Clear suggestions when closing
        const suggestions = document.getElementById('tagEditorSuggestions');
        if (suggestions) {
            suggestions.classList.remove('active');
        }
    }
}

function saveTags() {
    const tags = tagEditor.getTags();
    const filepath = document.getElementById('imageFilepath').value;
    
    // Show loading state
    const saveBtn = event.target;
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.7';

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
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            tagEditor.showNotification('Tags saved successfully!', 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    })
    .catch(error => {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
        saveBtn.style.opacity = '1';
        tagEditor.showNotification('Error: ' + error.message, 'error');
    });
}

function confirmDelete() {
    if (!confirm('Are you sure you want to delete this image? This cannot be undone.')) {
        return;
    }

    const filepath = document.getElementById('imageFilepath').value;
    
    // Show loading overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        animation: fadeIn 0.3s ease-out;
    `;
    overlay.innerHTML = `
        <div style="
            color: white;
            font-size: 1.2em;
            font-weight: 600;
            padding: 30px 50px;
            background: linear-gradient(135deg, rgba(30, 30, 45, 0.95) 0%, rgba(40, 40, 60, 0.95) 100%);
            border-radius: 16px;
            box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
        ">
            Deleting image...
        </div>
    `;
    document.body.appendChild(overlay);

    fetch('/api/delete_image', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            filepath: filepath
        })
    })
    .then(response => {
        if (!response.ok) throw new Error('Network response was not ok');
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            overlay.querySelector('div').textContent = 'Image deleted successfully!';
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    })
    .catch(error => {
        overlay.remove();
        tagEditor.showNotification('Error: ' + error.message, 'error');
    });
}
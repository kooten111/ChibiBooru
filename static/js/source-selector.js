// Source Selector JavaScript

function openSourceModal() {
    // Simply show the pre-rendered modal
    const modal = document.getElementById('sourceModal');
    if (!modal) {
        alert('Source selector not available');
        return;
    }
    
    modal.classList.add('active');
    
    // Add event listeners
    modal.addEventListener('click', handleModalClick);
    document.addEventListener('keydown', handleEscape);
}

function handleModalClick(e) {
    // Close if clicking the modal background (not the content)
    if (e.target.id === 'sourceModal') {
        closeSourceModal();
    }
}

function handleEscape(e) {
    if (e.key === 'Escape') {
        closeSourceModal();
    }
}

function closeSourceModal() {
    const modal = document.getElementById('sourceModal');
    if (modal) {
        modal.classList.remove('active');
        modal.removeEventListener('click', handleModalClick);
    }
    document.removeEventListener('keydown', handleEscape);
}

async function switchSource(sourceName) {
    const filepath = document.getElementById('imageFilepath').value;

    if (!filepath) {
        alert('Error: Image filepath not found');
        return;
    }

    // Show loading state
    const sourceOption = document.querySelector(`.source-option[onclick="switchSource('${sourceName}')"]`);
    if (sourceOption) {
        sourceOption.classList.add('switching');
        const originalHTML = sourceOption.innerHTML;

        // Different message for merged sources
        const loadingMessage = sourceName === 'merged'
            ? `<div class="source-option-header">
                <span class="source-emoji">🔀</span>
                <span class="source-name">Merging all sources...</span>
               </div>`
            : `<div class="source-option-header">
                <span class="source-emoji">⏳</span>
                <span class="source-name">Switching...</span>
               </div>`;

        sourceOption.innerHTML = loadingMessage;

        // Restore after timeout in case of error
        setTimeout(() => {
            if (sourceOption.classList.contains('switching')) {
                sourceOption.innerHTML = originalHTML;
                sourceOption.classList.remove('switching');
            }
        }, 10000);
    }
    
    try {
        const response = await fetch('/api/switch_source', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                filepath: filepath,
                source: sourceName
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Reload the page to show updated tags
            window.location.reload();
        } else {
            alert('Error switching source: ' + (result.error || 'Unknown error'));
            if (sourceOption) {
                sourceOption.innerHTML = originalHTML;
                sourceOption.classList.remove('switching');
            }
        }
    } catch (error) {
        console.error('Error switching source:', error);
        alert('Error switching source: ' + error.message);
        if (sourceOption) {
            sourceOption.classList.remove('switching');
        }
    }
}
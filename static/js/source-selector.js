// Source Selector JavaScript
let currentActiveSource = null;

function initializeSourceSelector() {
    const currentSource = document.getElementById('currentSource')?.value;
    if (currentSource) {
        currentActiveSource = currentSource;
    }
}

async function switchSource(sourceName) {
    const filepath = document.getElementById('imageFilepath').value;
    
    if (!filepath) {
        alert('Error: Image filepath not found');
        return;
    }
    
    // Show loading state
    const sourceOption = document.querySelector(`[data-source="${sourceName}"]`);
    if (sourceOption) {
        sourceOption.classList.add('source-switching');
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
                sourceOption.classList.remove('source-switching');
            }
        }
    } catch (error) {
        console.error('Error switching source:', error);
        alert('Error switching source: ' + error.message);
        if (sourceOption) {
            sourceOption.classList.remove('source-switching');
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeSourceSelector);
let systemStatusInterval = null;
const SYSTEM_SECRET = localStorage.getItem('system_secret') || prompt('Enter system secret:');

if (SYSTEM_SECRET) {
    localStorage.setItem('system_secret', SYSTEM_SECRET);
}

function loadSystemStatus() {
    fetch('/api/system/status')
        .then(res => res.json())
        .then(data => {
            const statusDiv = document.getElementById('systemStatus');
            if (!statusDiv) return;
            
            const monitor = data.monitor;
            const collection = data.collection;
            
            statusDiv.innerHTML = `
                <div class="status-grid">
                    <div class="status-item ${monitor.running ? 'active' : 'inactive'}">
                        <div class="status-label">Monitor Status</div>
                        <div class="status-value">${monitor.running ? '▶️ Running' : '⏸️ Stopped'}</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">Check Interval</div>
                        <div class="status-value">${monitor.interval_seconds}s</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">Last Check</div>
                        <div class="status-value">${monitor.last_check || 'Never'}</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">Last Scan Found</div>
                        <div class="status-value highlight">${monitor.last_scan_found}</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">Total Processed</div>
                        <div class="status-value highlight">${monitor.total_processed}</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">Total Images</div>
                        <div class="status-value highlight">${collection.total_images}</div>
                    </div>
                    
                    <div class="status-item">
                        <div class="status-label">With Metadata</div>
                        <div class="status-value highlight">${collection.with_metadata}</div>
                    </div>
                    
                    <div class="status-item ${collection.unprocessed > 0 ? 'inactive' : ''}">
                        <div class="status-label">Unprocessed</div>
                        <div class="status-value">${collection.unprocessed}</div>
                    </div>
                </div>
            `;
        })
        .catch(err => {
            console.error('Error loading system status:', err);
        });
}

function systemAction(endpoint, buttonElement, successMessage) {
    if (!SYSTEM_SECRET) {
        alert('No system secret configured');
        return;
    }
    
    const originalText = buttonElement.textContent;
    buttonElement.textContent = 'Processing...';
    buttonElement.disabled = true;
    
    fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: `secret=${encodeURIComponent(SYSTEM_SECRET)}`
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification(data.message || successMessage, 'success');
            loadSystemStatus();
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    })
    .catch(err => {
        showNotification('Error: ' + err.message, 'error');
    })
    .finally(() => {
        buttonElement.textContent = originalText;
        buttonElement.disabled = false;
    });
}

function systemScanImages() {
    systemAction('/api/system/scan', event.target, 'Scan completed');
}

function systemRebuildTags() {
    systemAction('/api/system/rebuild', event.target, 'Tags rebuilt');
}

function systemGenerateThumbnails() {
    systemAction('/api/system/thumbnails', event.target, 'Thumbnails generated');
}

function systemReloadData() {
    systemAction('/api/reload', event.target, 'Data reloaded');
}

function systemStartMonitor() {
    systemAction('/api/system/monitor/start', event.target, 'Monitor started');
}

function systemStopMonitor() {
    systemAction('/api/system/monitor/stop', event.target, 'Monitor stopped');
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        right: 30px;
        padding: 15px 25px;
        background: ${type === 'error' ? 'linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)' : 
                     type === 'success' ? 'linear-gradient(135deg, #51cf66 0%, #37b24d 100%)' :
                     'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)'};
        color: white;
        border-radius: 10px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        z-index: 10000;
        font-weight: 600;
        max-width: 400px;
        animation: slideInRight 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// Add notification animations
const style = document.createElement('style');
style.textContent = `
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
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100px);
        }
    }
`;
document.head.appendChild(style);

// Auto-refresh status when system panel is open
document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver((mutations) => {
        const systemPanel = document.getElementById('system-panel');
        if (systemPanel && systemPanel.classList.contains('active')) {
            if (!systemStatusInterval) {
                loadSystemStatus();
                systemStatusInterval = setInterval(loadSystemStatus, 5000);
            }
        } else {
            if (systemStatusInterval) {
                clearInterval(systemStatusInterval);
                systemStatusInterval = null;
            }
        }
    });
    
    const panelsContainer = document.getElementById('statsPanelsContainer');
    if (panelsContainer) {
        observer.observe(panelsContainer, {
            attributes: true,
            subtree: true,
            attributeFilter: ['class']
        });
    }
});

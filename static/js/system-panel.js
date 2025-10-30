// static/js/system-panel.js
var systemStatusInterval = null;
var SYSTEM_SECRET = localStorage.getItem('system_secret');

function updateSecretUI() {
    const secretSection = document.getElementById('secretSection');
    const actionsSection = document.getElementById('systemActionsSection');
    
    if (!secretSection || !actionsSection) return;
    
    if (SYSTEM_SECRET) {
        secretSection.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px; padding: 15px; background: rgba(74, 158, 111, 0.2); border-radius: 10px; border: 1px solid rgba(144, 238, 144, 0.3);">
                <span style="color: #90ee90; font-weight: 600;">✓ System secret configured</span>
                <button class="btn btn-danger" onclick="clearSystemSecret(event)" style="margin-left: auto; padding: 8px 16px;">
                    Change Secret
                </button>
            </div>
        `;
        actionsSection.style.display = 'block';
    } else {
        secretSection.innerHTML = `
            <div style="padding: 20px; background: rgba(255, 107, 107, 0.2); border-radius: 10px; border: 1px solid rgba(255, 107, 107, 0.3);">
                <h4 style="margin: 0 0 15px 0; color: #ff6b6b; font-size: 1em;">System Secret Required</h4>
                <p style="margin: 0 0 15px 0; color: #d0d0d0; font-size: 0.9em;">
                    Enter the RELOAD_SECRET from your environment variables.
                </p>
                <div style="display: flex; gap: 10px;">
                    <input type="password" id="secretInput" placeholder="Enter system secret..." 
                           style="flex: 1; padding: 12px; background: rgba(20, 20, 30, 0.8); border: 2px solid rgba(135, 206, 235, 0.3); border-radius: 10px; color: #e8e8e8; font-size: 0.95em;"
                           onkeypress="if(event.key==='Enter') saveSystemSecret()">
                    <button class="btn btn-success" onclick="saveSystemSecret()" style="padding: 12px 24px;">
                        Save Secret
                    </button>
                </div>
            </div>
        `;
        actionsSection.style.display = 'none';
    }
}

function saveSystemSecret() {
    const input = document.getElementById('secretInput');
    if (!input) return;
    
    const secret = input.value.trim();
    if (!secret) {
        showNotification('Please enter a secret', 'error');
        return;
    }
    
    SYSTEM_SECRET = secret;
    localStorage.setItem('system_secret', secret);
    showNotification('Secret saved successfully', 'success');
    updateSecretUI();
    loadSystemStatus();
    loadLogs();
}

function clearSystemSecret(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    showConfirm('Are you sure you want to change the system secret?', () => {
        SYSTEM_SECRET = null;
        localStorage.removeItem('system_secret');
        showNotification('Secret cleared', 'success');
        updateSecretUI();
    });
}

function loadLogs() {
    if (!SYSTEM_SECRET) return;

    fetch('/api/system/logs')
        .then(res => res.json())
        .then(logs => {
            const logsDiv = document.getElementById('systemLogs');
            if (!logsDiv) return;

            if (logs.length === 0) {
                logsDiv.innerHTML = '<div class="log-entry info">No recent activity</div>';
                return;
            }

            logsDiv.innerHTML = logs.map(log => `
                <div class="log-entry ${log.type}">
                    <span style="color: #87ceeb; margin-right: 10px;">[${log.timestamp}]</span>
                    ${log.message}
                </div>
            `).join('');
        })
        .catch(err => console.error('Error loading logs:', err));
}

function loadSystemStatus() {
    if (!SYSTEM_SECRET) return;
    
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
                        <div class="status-value">${monitor.running ? '🟢 Running' : '🔴 Stopped'}</div>
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
                        <div class="status-value">${monitor.last_scan_found}</div>
                    </div>
                    <div class="status-item">
                        <div class="status-label">Total Processed</div>
                        <div class="status-value">${monitor.total_processed}</div>
                    </div>
                    <div class="status-item">
                        <div class="status-label">Total Images</div>
                        <div class="status-value">${collection.total_images}</div>
                    </div>
                    <div class="status-item ${collection.unprocessed > 0 ? 'warning' : 'inactive'}">
                        <div class="status-label">Unprocessed</div>
                        <div class="status-value">${collection.unprocessed}</div>
                    </div>
                </div>
            `;
            
            updateMonitorButton(monitor.running);
        })
        .catch(err => {
            console.error('Error loading system status:', err);
        });
}

function updateMonitorButton(isRunning) {
    const btn = document.getElementById('monitorToggleBtn');
    if (!btn) return;
    
    if (isRunning) {
        btn.className = 'btn btn-danger';
        btn.innerHTML = '⏸️ Stop Monitor';
        btn.onclick = (e) => systemStopMonitor(e);
    } else {
        btn.className = 'btn btn-success';
        btn.innerHTML = '▶️ Start Monitor';
        btn.onclick = (e) => systemStartMonitor(e);
    }
}

function systemAction(endpoint, buttonElement, actionName, body = null) {
    if (!SYSTEM_SECRET) {
        showNotification('System secret not configured', 'error');
        return;
    }
    
    const originalText = buttonElement ? buttonElement.innerHTML : '';
    if (buttonElement) {
        buttonElement.innerHTML = `<span style="display: inline-block; animation: spin 1s linear infinite;">⚙️</span> Processing...`;
        buttonElement.disabled = true;
    }
    
    loadLogs();
    
    const url = `${endpoint}?secret=${encodeURIComponent(SYSTEM_SECRET)}`;
    const options = {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : null
    };
    
    fetch(url, options)
    .then(async res => {
        const contentType = res.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await res.text();
            console.error('Non-JSON response:', text);
            throw new Error(`Server returned non-JSON response. Status: ${res.status}`);
        }
        return res.json();
    })
    .then(data => {
        if (data.status === 'success') {
            const msg = data.message || `${actionName} completed`;
            showNotification(msg, 'success');
            loadLogs();
            loadSystemStatus();
        } else if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            showNotification('Invalid system secret', 'error');
            updateSecretUI();
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    })
    .catch(err => {
        const errMsg = `${actionName} failed: ${err.message}`;
        showNotification(errMsg, 'error');
        console.error('Full error:', err);
    })
    .finally(() => {
        if (buttonElement) {
            buttonElement.innerHTML = originalText;
            buttonElement.disabled = false;
        }
    });
}

function systemScanImages(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/scan', event.target, 'Scan & Process');
}

function systemRebuildTags(event) {
    if (event) event.preventDefault();
    showConfirm('This will delete and re-import all data from your metadata files. Are you sure?', () => {
        systemAction('/api/system/rebuild', event.target, 'Rebuild Tags');
    });
}

function systemRebuildCategorized(event) {
    if (event) event.preventDefault();
    const buttonElement = event ? event.target : null;
    showConfirm('This will fix tag displays by populating categorized tag data for all images. This is safe to run. Continue?', () => {
        systemAction('/api/system/rebuild_categorized', buttonElement, 'Rebuild Categorized Tags');
    });
}

function systemRecategorizeTags(event) {
    if (event) event.preventDefault();
    showConfirm('This will check all general tags and move them to the correct category (artist/character/copyright/meta) if they exist as categorized tags elsewhere. Continue?', () => {
        systemAction('/api/system/recategorize', event.target, 'Recategorize Tags');
    });
}

function systemGenerateThumbnails(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/thumbnails', event.target, 'Generate Thumbnails');
}

function systemReloadData(event) {
    if (event) event.preventDefault();
    systemAction('/api/reload', event.target, 'Reload Data');
}

function systemDeduplicate(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/deduplicate', event.target, 'Deduplicate', { dry_run: false });
}

function systemCleanOrphans(event) {
    if (event) event.preventDefault();
    showConfirm('This will remove database entries for images that no longer exist on disk. Proceed?', () => {
        systemAction('/api/system/clean_orphans', event.target, 'Clean Orphans', { dry_run: false });
    });
}

function systemBulkRetryTagging(event) {
    if (event) event.preventDefault();

    const overlay = document.createElement('div');
    overlay.className = 'custom-confirm-overlay';
    overlay.innerHTML = `
        <div class="custom-confirm-modal" style="max-width: 550px;">
            <h3 style="margin: 0 0 15px 0; color: #87ceeb;">🔄 Bulk Retry Tagging Options</h3>
            <p style="margin: 0 0 20px 0; color: #d0d0d0; line-height: 1.5;">
                This will retry tagging for all locally-tagged images. Choose your preferred method:
            </p>
            <div style="display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px;">
                <button class="retry-option-btn" data-option="online-only" style="padding: 15px; background: rgba(74, 158, 255, 0.2); border: 2px solid rgba(74, 158, 255, 0.4); border-radius: 8px; color: #87ceeb; cursor: pointer; text-align: left; transition: all 0.2s;">
                    <div style="font-weight: 600; margin-bottom: 5px;">🌐 Online Sources Only</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Try Danbooru, e621, and SauceNao. Keep current tags if nothing found.</div>
                </button>
                <button class="retry-option-btn" data-option="with-fallback" style="padding: 15px; background: rgba(251, 146, 60, 0.2); border: 2px solid rgba(251, 146, 60, 0.4); border-radius: 8px; color: #ff9966; cursor: pointer; text-align: left; transition: all 0.2s;">
                    <div style="font-weight: 600; margin-bottom: 5px;">🤖 With Local AI Fallback</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Try online sources first, then re-run local AI tagger if nothing found.</div>
                </button>
            </div>
            <div class="button-group">
                <button class="btn-cancel">Cancel</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnCancel = modal.querySelector('.btn-cancel');
    const optionBtns = modal.querySelectorAll('.retry-option-btn');

    // Add hover effects
    optionBtns.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
        });
        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'none';
        });
        btn.addEventListener('click', function() {
            const option = this.dataset.option;
            overlay.remove();
            const skipLocalFallback = option === 'online-only';
            systemAction('/api/bulk_retry_tagging', event.target, 'Bulk Retry Tagging', { skip_local_fallback: skipLocalFallback });
        });
    });

    btnCancel.onclick = () => overlay.remove();
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };
}

function systemStartMonitor(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/monitor/start', event.target, 'Start Monitor');
}

function systemStopMonitor(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/monitor/stop', event.target, 'Stop Monitor');
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed; top: 100px; right: 30px; padding: 15px 25px;
        background: ${type === 'error' ? 'linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)' : 
                     type === 'success' ? 'linear-gradient(135deg, #51cf66 0%, #37b24d 100%)' :
                     'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)'};
        color: white; border-radius: 10px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
        z-index: 10002; font-weight: 600; max-width: 400px;
        animation: slideInRight 0.3s ease-out;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// Auto-refresh status when system panel is open
document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver(() => {
        const systemPanel = document.getElementById('system-panel');
        if (systemPanel && systemPanel.classList.contains('active')) {
            updateSecretUI();
            if (!systemStatusInterval && SYSTEM_SECRET) {
                loadSystemStatus();
                loadLogs();
                systemStatusInterval = setInterval(() => {
                    loadSystemStatus();
                    loadLogs();
                }, 5000);
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
        observer.observe(panelsContainer, { attributes: true, subtree: true, attributeFilter: ['class'] });
    }
});

function toggleDebugOptions() {
    const debugOptions = document.getElementById('debugOptions');
    const toggleButton = document.querySelector('.debug-toggle');
    
    debugOptions.classList.toggle('open');
    toggleButton.classList.toggle('expanded');
}
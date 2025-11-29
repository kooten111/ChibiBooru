// static/js/system-panel.js
var systemStatusInterval = null;
var SYSTEM_SECRET = localStorage.getItem('system_secret');

function updateSecretUI() {
    const secretSection = document.getElementById('secretSection');
    const actionsSection = document.getElementById('systemActionsSection');

    if (!secretSection || !actionsSection) return;

    // Clear existing content
    secretSection.innerHTML = '';

    if (SYSTEM_SECRET) {
        const template = document.getElementById('secret-configured-template');
        const clone = template.content.cloneNode(true);
        secretSection.appendChild(clone);
        actionsSection.style.display = 'block';
    } else {
        const template = document.getElementById('secret-required-template');
        const clone = template.content.cloneNode(true);

        // Add enter key listener to the input after appending
        secretSection.appendChild(clone);
        const input = secretSection.querySelector('#secretInput');
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') saveSystemSecret();
            });
        }

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

            // Clear existing logs
            logsDiv.innerHTML = '';

            if (logs.length === 0) {
                const entry = createLogEntry('No recent activity', 'info');
                logsDiv.appendChild(entry);
                return;
            }

            logs.forEach(log => {
                const entry = createLogEntry(log.message, log.type, log.timestamp);
                logsDiv.appendChild(entry);
            });
        })
        .catch(err => console.error('Error loading logs:', err));
}

function createLogEntry(message, type, timestamp) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;

    if (timestamp) {
        const timeSpan = document.createElement('span');
        timeSpan.style.color = '#87ceeb';
        timeSpan.style.marginRight = '10px';
        timeSpan.textContent = `[${timestamp}]`;
        entry.appendChild(timeSpan);
    }

    const messageText = document.createTextNode(message);
    entry.appendChild(messageText);

    return entry;
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

            // Clear and rebuild status grid
            statusDiv.innerHTML = '';
            const grid = document.createElement('div');
            grid.className = 'status-grid';

            // Create status items
            grid.appendChild(createStatusItem(
                'Monitor Status',
                monitor.running ? '🟢 Running' : '🔴 Stopped',
                monitor.running ? 'active' : 'inactive'
            ));

            grid.appendChild(createStatusItem('Check Interval', `${monitor.interval_seconds}s`));
            grid.appendChild(createStatusItem('Last Check', monitor.last_check || 'Never'));
            grid.appendChild(createStatusItem('Last Scan Found', monitor.last_scan_found));
            grid.appendChild(createStatusItem('Total Processed', monitor.total_processed));
            grid.appendChild(createStatusItem('Total Images', collection.total_images));
            grid.appendChild(createStatusItem(
                'Unprocessed',
                collection.unprocessed,
                collection.unprocessed > 0 ? 'warning' : 'inactive'
            ));

            statusDiv.appendChild(grid);
            updateMonitorButton(monitor.running);
        })
        .catch(err => {
            console.error('Error loading system status:', err);
        });
}

function createStatusItem(label, value, statusClass = '') {
    const item = document.createElement('div');
    item.className = `status-item ${statusClass}`;

    const labelDiv = document.createElement('div');
    labelDiv.className = 'status-label';
    labelDiv.textContent = label;

    const valueDiv = document.createElement('div');
    valueDiv.className = 'status-value';
    valueDiv.textContent = value;

    item.appendChild(labelDiv);
    item.appendChild(valueDiv);

    return item;
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
        buttonElement.innerHTML = '<span class="processing-spinner">⚙️</span> Processing...';
        buttonElement.disabled = true;
    }

    loadLogs();

    const url = `${endpoint}?secret=${encodeURIComponent(SYSTEM_SECRET)}`;
    const options = {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : null
    };

    let isBackgroundTask = false;

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
            } else if (data.status === 'started' && data.task_id) {
                // Background task started - poll for progress
                isBackgroundTask = true;
                showNotification(`${actionName} started in background`, 'info');
                pollTaskProgress(data.task_id, actionName, buttonElement, originalText);
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
            // Don't reset button if it's a background task (polling will handle it)
            if (buttonElement && !isBackgroundTask) {
                buttonElement.innerHTML = originalText;
                buttonElement.disabled = false;
            }
        });
}

function pollTaskProgress(taskId, actionName, buttonElement, originalText) {
    const pollInterval = 1000; // Poll every second

    const updateButton = (status) => {
        if (buttonElement && status.progress !== undefined && status.total !== undefined) {
            const percentage = status.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;
            buttonElement.innerHTML = `⏳ ${percentage}% (${status.progress}/${status.total})`;
        }
    };

    const poll = () => {
        fetch(`/api/task_status?task_id=${encodeURIComponent(taskId)}`)
            .then(res => res.json())
            .then(status => {
                console.log('Task status:', status);

                updateButton(status);

                if (status.status === 'completed') {
                    const msg = status.result?.message || `${actionName} completed successfully`;
                    showNotification(msg, 'success');
                    if (buttonElement) {
                        buttonElement.innerHTML = originalText;
                        buttonElement.disabled = false;
                    }
                    loadLogs();
                    loadSystemStatus();
                } else if (status.status === 'failed') {
                    showNotification(`${actionName} failed: ${status.error}`, 'error');
                    if (buttonElement) {
                        buttonElement.innerHTML = originalText;
                        buttonElement.disabled = false;
                    }
                } else if (status.status === 'running' || status.status === 'pending') {
                    // Continue polling
                    setTimeout(poll, pollInterval);
                } else {
                    // Unknown status
                    if (buttonElement) {
                        buttonElement.innerHTML = originalText;
                        buttonElement.disabled = false;
                    }
                }
            })
            .catch(err => {
                console.error('Error polling task status:', err);
                showNotification(`Error checking ${actionName} progress`, 'error');
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
            });
    };

    // Start polling
    poll();
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

function systemApplyMergedSources(event) {
    if (event) event.preventDefault();
    showConfirm('This will merge tags from all available sources for images with multiple sources. Continue?', () => {
        systemAction('/api/system/apply_merged_sources', event.target, 'Apply Merged Sources');
    });
}

function systemRecountTags(event) {
    if (event) event.preventDefault();
    showConfirm('This will recount all tag usage statistics. Continue?', () => {
        systemAction('/api/system/recount_tags', event.target, 'Recount Tags');
    });
}

function systemReindexDatabase(event) {
    if (event) event.preventDefault();
    showConfirm('This will optimize the database (VACUUM and REINDEX). This may take a few seconds. Continue?', () => {
        systemAction('/api/system/reindex', event.target, 'Optimize Database');
    });
}

function systemBulkRetryTagging(event) {
    if (event) event.preventDefault();

    const template = document.getElementById('retry-tagging-modal-template');
    const clone = template.content.cloneNode(true);
    const overlay = clone.querySelector('.custom-confirm-overlay');

    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnCancel = modal.querySelector('.btn-cancel');
    const optionBtns = modal.querySelectorAll('.retry-option-btn');

    // Add hover and click handlers
    optionBtns.forEach(btn => {
        btn.addEventListener('mouseenter', function () {
            this.style.transform = 'translateY(-2px)';
            this.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
        });
        btn.addEventListener('mouseleave', function () {
            this.style.transform = 'translateY(0)';
            this.style.boxShadow = 'none';
        });
        btn.addEventListener('click', function () {
            const option = this.dataset.option;
            document.body.removeChild(overlay);
            const skipLocalFallback = option === 'online-only';
            systemAction('/api/bulk_retry_tagging', event.target, 'Bulk Retry Tagging', { skip_local_fallback: skipLocalFallback });
        });
    });

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };

    document.body.appendChild(overlay);
}

function systemDatabaseHealthCheck(event) {
    if (event) event.preventDefault();

    const template = document.getElementById('health-check-modal-template');
    const clone = template.content.cloneNode(true);
    const overlay = clone.querySelector('.custom-confirm-overlay');

    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnConfirm = modal.querySelector('.btn-confirm');
    const btnCancel = modal.querySelector('.btn-cancel');
    const autoFixCheckbox = modal.querySelector('#healthCheckAutoFix');
    const tagDeltasCheckbox = modal.querySelector('#healthCheckTagDeltas');
    const thumbnailsCheckbox = modal.querySelector('#healthCheckThumbnails');

    btnConfirm.onclick = () => {
        document.body.removeChild(overlay);
        systemAction('/api/database_health_check', event.target, 'Database Health Check', {
            auto_fix: autoFixCheckbox.checked,
            include_tag_deltas: tagDeltasCheckbox.checked,
            include_thumbnails: thumbnailsCheckbox.checked
        });
    };

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };

    document.body.appendChild(overlay);
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

    let gradient;
    if (type === 'error') {
        gradient = 'linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)';
    } else if (type === 'success') {
        gradient = 'linear-gradient(135deg, #51cf66 0%, #37b24d 100%)';
    } else {
        gradient = 'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)';
    }

    notification.style.cssText = `
        position: fixed; top: 100px; right: 30px; padding: 15px 25px;
        background: ${gradient};
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

// static/js/system-panel.js
import { showNotification } from './utils/notifications.js';

var systemStatusInterval = null;
var SYSTEM_SECRET = localStorage.getItem('system_secret');

async function validateStoredSecret() {
    if (!SYSTEM_SECRET) return;

    try {
        const response = await fetch(`/api/system/validate_secret?secret=${encodeURIComponent(SYSTEM_SECRET)}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (!data.success || !data.valid) {
            // Stored secret is invalid, clear it
            SYSTEM_SECRET = null;
            localStorage.removeItem('system_secret');
        }
    } catch (err) {
        console.error('Error validating stored secret:', err);
    }
}

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

async function saveSystemSecret() {
    const input = document.getElementById('secretInput');
    if (!input) return;

    const secret = input.value.trim();
    if (!secret) {
        showNotification('Please enter a secret', 'error');
        return;
    }

    // Disable input while validating
    input.disabled = true;

    try {
        // Validate the secret with the backend
        const response = await fetch(`/api/system/validate_secret?secret=${encodeURIComponent(secret)}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success && data.valid) {
            // Secret is valid, save it
            SYSTEM_SECRET = secret;
            localStorage.setItem('system_secret', secret);
            showNotification('Secret saved successfully', 'success');
            updateSecretUI();
            loadSystemStatus();
            loadLogs();
        } else {
            // Secret is invalid
            showNotification('Invalid system secret', 'error');
            input.value = '';
        }
    } catch (err) {
        console.error('Error validating secret:', err);
        showNotification('Error validating secret', 'error');
    } finally {
        input.disabled = false;
    }
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

    // Ensure we have the button element, not an icon inside it
    if (buttonElement && buttonElement.tagName !== 'BUTTON') {
        buttonElement = buttonElement.closest('button');
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

function systemGenerateHashes(event) {
    if (event) event.preventDefault();
    systemAction('/api/similarity/generate-hashes', event.target, 'Generate Image Hashes');
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

function systemBulkRetagLocal(event) {
    if (event) event.preventDefault();
    showConfirm('This will run the local AI tagger on EVERY image and save all predictions with confidence scores. This takes a while. Continue?', () => {
        systemAction('/api/system/bulk_retag_local', event.target, 'Rescan All Images');
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

            const params = {};
            if (option === 'online-only') {
                params.skip_local_fallback = true;
            } else if (option === 'pixiv-only') {
                params.pixiv_only = true;
            }

            systemAction('/api/bulk_retry_tagging', event.target, 'Bulk Retry Tagging', params);
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

// Auto-refresh status when system panel is open
document.addEventListener('DOMContentLoaded', () => {
    const observer = new MutationObserver(async () => {
        const systemPanel = document.getElementById('system-panel');
        if (systemPanel && systemPanel.classList.contains('active')) {
            // Validate stored secret first
            await validateStoredSecret();

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

function systemClearImpliedTags(event) {
    if (event) event.preventDefault();

    const template = document.getElementById('clear-implied-tags-modal-template');
    const clone = template.content.cloneNode(true);
    const overlay = clone.querySelector('.custom-confirm-overlay');

    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnConfirm = modal.querySelector('.btn-confirm');
    const btnCancel = modal.querySelector('.btn-cancel');
    const reapplyCheckbox = modal.querySelector('#clearImpliedReapply');

    btnConfirm.onclick = () => {
        const reapply = reapplyCheckbox.checked;
        document.body.removeChild(overlay);

        // Call the appropriate implications API endpoint
        const buttonElement = event ? event.target.closest('button') : null;
        const originalText = buttonElement ? buttonElement.innerHTML : '';

        if (buttonElement) {
            buttonElement.innerHTML = reapply
                ? '<span class="processing-spinner">⚙️</span> Clearing & Reapplying...'
                : '<span class="processing-spinner">⚙️</span> Clearing...';
            buttonElement.disabled = true;
        }

        loadLogs?.();

        const endpoint = reapply ? '/api/implications/clear-and-reapply' : '/api/implications/clear-tags';

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(res => res.json())
            .then(data => {
                if (data.message) {
                    if (typeof showNotification === 'function') {
                        showNotification(data.message, 'success');
                    } else {
                        alert(data.message);
                    }
                    loadLogs?.();
                } else if (data.error) {
                    const msg = `Error: ${data.error}`;
                    if (typeof showNotification === 'function') {
                        showNotification(msg, 'error');
                    } else {
                        alert(msg);
                    }
                }
            })
            .catch(err => {
                const msg = `Error: ${err.message}`;
                if (typeof showNotification === 'function') {
                    showNotification(msg, 'error');
                } else {
                    alert(msg);
                }
            })
            .finally(() => {
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
                loadLogs?.();
            });
    };

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };

    document.body.appendChild(overlay);
}

// Export functions to global scope for onclick handlers
window.toggleDebugOptions = toggleDebugOptions;
window.systemScanImages = systemScanImages;
window.systemReloadData = systemReloadData;
window.systemRebuildTags = systemRebuildTags;
window.systemRebuildCategorized = systemRebuildCategorized;
window.systemRecategorizeTags = systemRecategorizeTags;
window.systemGenerateThumbnails = systemGenerateThumbnails;
window.systemGenerateHashes = systemGenerateHashes;
window.systemDeduplicate = systemDeduplicate;
window.systemCleanOrphans = systemCleanOrphans;
window.systemApplyMergedSources = systemApplyMergedSources;
window.systemRecountTags = systemRecountTags;
window.systemReindexDatabase = systemReindexDatabase;
window.systemBulkRetagLocal = systemBulkRetagLocal;
window.systemBulkRetryTagging = systemBulkRetryTagging;
window.systemDatabaseHealthCheck = systemDatabaseHealthCheck;
window.systemStartMonitor = systemStartMonitor;
window.systemStopMonitor = systemStopMonitor;
window.systemClearImpliedTags = systemClearImpliedTags;
window.saveSystemSecret = saveSystemSecret;
window.clearSystemSecret = clearSystemSecret;


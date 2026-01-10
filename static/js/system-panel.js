// static/js/system-panel.js
// v2.1 - Fixed duplicate function declaration and toggleDebugOptions export
import { showNotification } from './utils/notifications.js';

var systemStatusInterval = null;
// SECURITY NOTE: System secret is stored in localStorage for convenience.
// This is vulnerable to XSS attacks. For production deployments, consider:
// 1. Using httpOnly cookies (requires backend changes)
// 2. Implementing Content Security Policy (CSP) headers
// 3. Ensuring all user inputs are properly sanitized
// 4. Using sessionStorage instead if persistence across tabs isn't required
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
        if (!buttonElement) return;

        if (status.total !== undefined && status.progress !== undefined) {
            // Count-based progress
            const percentage = status.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;
            buttonElement.innerHTML = `⏳ ${percentage}% (${status.progress}/${status.total})`;
        } else if (status.progress !== undefined) {
            // Percentage-based progress (ML worker style)
            buttonElement.innerHTML = `⏳ ${status.progress}%`;
            // If message is short enough, append it
            if (status.message && status.message.length < 30) {
                buttonElement.innerHTML += ` <span style="font-size:0.8em">(${status.message})</span>`;
            }
        } else if (status.message) {
            // Message only
            buttonElement.innerHTML = `⏳ ${status.message}`;
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
    showConfirm('This will generate perceptual hashes for images without them. Continue?', () => {
        systemAction('/api/similarity/generate-hashes', event.target, 'Generate Image Hashes');
    });
}


/**
 * Show a progress modal for long-running background tasks.
 * @param {string} endpoint - The API endpoint to call
 * @param {string} actionName - Human-readable name for the action
 */
function showProgressModal(endpoint, actionName) {
    if (!SYSTEM_SECRET) {
        showNotification('System secret not configured', 'error');
        return;
    }

    // Clone and show the modal
    const template = document.getElementById('progress-modal-template');
    if (!template) {
        console.error('Progress modal template not found, falling back to button progress');
        systemAction(endpoint, null, actionName);
        return;
    }

    const clone = template.content.cloneNode(true);
    const overlay = clone.querySelector('.progress-modal-overlay');
    const modal = overlay.querySelector('.progress-modal');
    const titleEl = overlay.querySelector('#progress-title');
    const statusEl = overlay.querySelector('#progress-status-text');
    const progressBar = overlay.querySelector('#progress-bar-fill');
    const detailsEl = overlay.querySelector('#progress-details');

    titleEl.textContent = actionName;
    document.body.appendChild(overlay);

    // Start the task
    const url = `${endpoint}?secret=${encodeURIComponent(SYSTEM_SECRET)}`;

    fetch(url, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'started' && data.task_id) {
                // Poll for progress
                pollProgressModal(data.task_id, actionName, overlay, modal, statusEl, progressBar, detailsEl);
            } else if (data.error === 'Unauthorized') {
                localStorage.removeItem('system_secret');
                SYSTEM_SECRET = null;
                showNotification('Invalid system secret', 'error');
                updateSecretUI();
                document.body.removeChild(overlay);
            } else {
                throw new Error(data.error || 'Failed to start task');
            }
        })
        .catch(err => {
            showNotification(`${actionName} failed: ${err.message}`, 'error');
            document.body.removeChild(overlay);
        });
}

function pollProgressModal(taskId, actionName, overlay, modal, statusEl, progressBar, detailsEl) {
    const pollInterval = 500; // Poll every 500ms for smoother updates

    const poll = () => {
        fetch(`/api/task_status?task_id=${encodeURIComponent(taskId)}`)
            .then(res => res.json())
            .then(status => {
                // Update progress UI
                if (status.progress !== undefined && status.total !== undefined) {
                    const percentage = status.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;
                    progressBar.style.width = `${percentage}%`;
                    detailsEl.textContent = `${status.progress.toLocaleString()} / ${status.total.toLocaleString()} (${percentage}%)`;
                }

                if (status.message) {
                    statusEl.textContent = status.message;
                }

                if (status.status === 'completed') {
                    // Show success state
                    modal.classList.add('success');
                    statusEl.textContent = 'Complete!';
                    progressBar.style.width = '100%';

                    const msg = status.result?.message || `${actionName} completed successfully`;

                    // Close modal after short delay
                    setTimeout(() => {
                        document.body.removeChild(overlay);
                        showNotification(msg, 'success');
                        loadLogs();
                        loadSystemStatus();
                    }, 800);
                } else if (status.status === 'failed') {
                    document.body.removeChild(overlay);
                    showNotification(`${actionName} failed: ${status.error}`, 'error');
                } else if (status.status === 'running' || status.status === 'pending') {
                    // Continue polling
                    setTimeout(poll, pollInterval);
                } else {
                    // Unknown status, close modal
                    document.body.removeChild(overlay);
                }
            })
            .catch(err => {
                console.error('Error polling task status:', err);
                document.body.removeChild(overlay);
                showNotification(`Error checking ${actionName} progress`, 'error');
            });
    };

    // Start polling
    poll();
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
    showConfirm('This will apply the current merge setting to all images with multiple sources. If merging is enabled, tags will be merged. If disabled, images will revert to their primary source. Continue?', () => {
        systemAction('/api/system/apply_merged_sources', event.target, 'Apply Source Merge Setting');
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

function toggleDebugOptions(event) {
    // Try to get the button from event, or fall back to querySelector
    const toggleButton = event?.target?.closest('.debug-toggle') || document.querySelector('.debug-toggle');

    // Find the debug options container - could be sibling or in the same section
    const debugSection = toggleButton?.closest('.debug-section');
    const debugOptions = debugSection?.querySelector('#debugOptions') || document.getElementById('debugOptions');

    if (!debugOptions || !toggleButton) {
        console.error('Debug options elements not found', { debugOptions, toggleButton });
        return;
    }

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

async function systemFindBrokenImages(event) {
    if (event) event.preventDefault();

    const template = document.getElementById('broken-images-modal-template');
    const clone = template.content.cloneNode(true);
    const overlay = clone.querySelector('.custom-confirm-overlay');

    const modal = overlay.querySelector('.custom-confirm-modal');
    const loadingDiv = modal.querySelector('#brokenImagesLoading');
    const contentDiv = modal.querySelector('#brokenImagesContent');
    const summaryP = modal.querySelector('#brokenImagesSummary');
    const listDiv = modal.querySelector('#brokenImagesList');
    const btnMoveToIngest = modal.querySelector('#brokenMoveToIngest');
    const btnRetry = modal.querySelector('#brokenRetry');
    const btnDelete = modal.querySelector('#brokenDelete');
    const btnCancel = modal.querySelector('.btn-cancel');

    document.body.appendChild(overlay);

    // Fetch broken images
    try {
        const response = await fetch('/api/system/broken_images');
        const data = await response.json();

        loadingDiv.style.display = 'none';
        contentDiv.style.display = 'block';

        if (data.total_broken === 0) {
            summaryP.textContent = '✓ No broken images found! All images have proper tags, hashes, and embeddings.';
            btnMoveToIngest.style.display = 'none';
            btnRetry.style.display = 'none';
            btnDelete.style.display = 'none';
        } else {
            summaryP.innerHTML = `Found <strong>${data.total_broken}</strong> broken images${data.has_more ? ' (showing first 100 below)' : ''}.<br/><small>Actions will apply to all ${data.total_broken} images.</small>`;
            // Show list of broken images
            listDiv.innerHTML = data.images.map(img => {
                const issues = img.issues.map(i => {
                    switch (i) {
                        case 'missing_phash': return '⚠️ No hash';
                        case 'no_tags': return '⚠️ No tags';
                        case 'missing_embedding': return '⚠️ No embedding';
                        case 'invalid_embedding_dim': return '⚠️ Corrupted embedding';
                        default: return i;
                    }
                }).join(', ');
                return `<div style="padding: 4px 0; border-bottom: 1px solid #333;">
                    <code>${img.filepath}</code><br/>
                    <small style="color: #e67e22;">${issues}</small>
                </div>`;
            }).join('');

            // Actions will process ALL broken images (not just displayed ones)
            const totalCount = data.total_broken;

            const performAction = async (action) => {
                const actionNames = {
                    'delete': 'Moving to ingest',
                    'retry': 'Retrying',
                    'delete_permanent': 'Deleting permanently'
                };

                showNotification(`${actionNames[action]} ${totalCount} images...`, 'info');
                document.body.removeChild(overlay);

                try {
                    // Send empty image_ids to process ALL broken images
                    const res = await fetch(`/api/system/broken_images/cleanup?secret=${encodeURIComponent(SYSTEM_SECRET)}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ action, image_ids: [] })
                    });
                    const result = await res.json();

                    if (result.status === 'success') {
                        showNotification(result.message, 'success');
                        loadSystemStatus?.();
                        loadLogs?.();
                    } else {
                        showNotification(`Error: ${result.error}`, 'error');
                    }
                } catch (err) {
                    showNotification(`Error: ${err.message}`, 'error');
                }
            };

            btnMoveToIngest.onclick = () => performAction('delete');
            btnRetry.onclick = () => performAction('retry');
            btnDelete.onclick = () => {
                if (confirm('This will PERMANENTLY DELETE the files. Are you sure?')) {
                    performAction('delete_permanent');
                }
            };
        }
    } catch (err) {
        loadingDiv.textContent = `Error: ${err.message}`;
    }

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };
}

window.systemFindBrokenImages = systemFindBrokenImages;

// System page JavaScript - Consolidated from system-panel.js
import { showNotification } from '../utils/notifications.js';

// System secret management
var SYSTEM_SECRET = localStorage.getItem('system_secret');
var systemStatusInterval = null;

// SECURITY NOTE: System secret is stored in localStorage for convenience.
// This is vulnerable to XSS attacks. For production deployments, consider:
// 1. Using httpOnly cookies (requires backend changes)
// 2. Implementing Content Security Policy (CSP) headers
// 3. Ensuring all user inputs are properly sanitized
// 4. Using sessionStorage instead if persistence across tabs isn't required

let settingsData = {};
let settingsChanged = {};

// Section switching and initialization
document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeSettings();
    initializeStatus();
    initializeLogs();
    initializeOverview();

    // Initialize secret UI immediately
    setTimeout(() => {
        validateStoredSecret().then(() => {
            updateSecretUI();
            const secret = localStorage.getItem('system_secret');
            if (secret) {
                loadSystemStatus();
                loadLogs();
                // Start auto-refresh
                if (!systemStatusInterval) {
                    systemStatusInterval = setInterval(() => {
                        loadSystemStatus();
                        loadLogs();
                    }, 5000);
                }
            }
        });
    }, 300);
});

function initializeNavigation() {
    const navButtons = document.querySelectorAll('.system-nav-btn');
    const sections = document.querySelectorAll('.system-section');

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetSection = btn.dataset.section;

            // Update active states
            navButtons.forEach(b => b.classList.remove('active'));
            sections.forEach(s => s.classList.remove('active'));

            btn.classList.add('active');
            const section = document.getElementById(`${targetSection}-section`);
            if (section) {
                section.classList.add('active');
            }

            // Load content if needed
            const secret = localStorage.getItem('system_secret');
            if (targetSection === 'overview' && secret) {
                loadSystemStatus();
                loadLogs();
            }
        });
    });
}

function initializeOverview() {
    // Setup logs expand/collapse
    const expandBtn = document.getElementById('logsExpandBtn');
    const logsContainer = document.querySelector('.logs-container-overview');

    if (expandBtn && logsContainer) {
        let isExpanded = false;
        expandBtn.addEventListener('click', () => {
            isExpanded = !isExpanded;
            logsContainer.classList.toggle('expanded', isExpanded);
            expandBtn.textContent = isExpanded ? '▼' : '▲';
        });
    }

    // Constrain activity log height to match left column
    constrainActivityLogHeight();
    window.addEventListener('resize', constrainActivityLogHeight);

    // Load initial data if Overview is active
    const secret = localStorage.getItem('system_secret');
    if (secret) {
        setTimeout(() => {
            loadSystemStatus();
            loadLogs();
        }, 500);
    }
}

function constrainActivityLogHeight() {
    const leftColumn = document.querySelector('.overview-left-column');
    const rightColumn = document.querySelector('.overview-right-column');
    const logsCard = document.querySelector('.overview-right-column .logs-card');

    if (leftColumn && rightColumn && logsCard) {
        // Reset any previously set heights to recalculate
        rightColumn.style.maxHeight = '';
        logsCard.style.maxHeight = '';

        // Get the actual content height of the cards in the left column
        requestAnimationFrame(() => {
            const cards = Array.from(leftColumn.querySelectorAll('.system-card'));
            if (cards.length > 0) {
                // Get bounding rects for all cards
                const cardRects = cards.map(card => card.getBoundingClientRect());
                const firstCardTop = Math.min(...cardRects.map(rect => rect.top));
                const lastCardBottom = Math.max(...cardRects.map(rect => rect.bottom));

                // Calculate actual content height (from top of first card to bottom of last card)
                const actualContentHeight = lastCardBottom - firstCardTop;

                if (actualContentHeight > 0) {
                    // Set max-height on the right column container to match actual card content height
                    rightColumn.style.maxHeight = actualContentHeight + 'px';
                    // Also ensure the logs card respects this constraint
                    logsCard.style.maxHeight = '100%';
                }
            } else {
                // Fallback: use column height if no cards found
                const leftHeight = leftColumn.offsetHeight;
                if (leftHeight > 0) {
                    rightColumn.style.maxHeight = leftHeight + 'px';
                    logsCard.style.maxHeight = '100%';
                }
            }
        });
    }
}

// Function to update status pills in header
window.updateStatusPills = function (monitor, collection) {
    const statusBar = document.getElementById('systemStatusBar');
    if (!statusBar) return;

    const pills = statusBar.querySelectorAll('.status-pill');
    if (pills.length < 4) return;

    // Monitor status
    const monitorPill = pills[0];
    const monitorValue = monitorPill.querySelector('.status-value');
    if (monitorValue) {
        monitorValue.textContent = monitor.running ? 'Running' : 'Stopped';
        monitorPill.className = 'status-pill ' + (monitor.running ? 'active' : 'inactive');
    }

    // Images count
    const imagesPill = pills[1];
    const imagesValue = imagesPill.querySelector('.status-value');
    if (imagesValue) {
        imagesValue.textContent = collection.total_images ? collection.total_images.toLocaleString() : '-';
    }

    // Unprocessed count
    const unprocessedPill = pills[2];
    const unprocessedValue = unprocessedPill.querySelector('.status-value');
    if (unprocessedValue) {
        unprocessedValue.textContent = collection.unprocessed || 0;
        unprocessedPill.className = 'status-pill ' + (collection.unprocessed > 0 ? 'warning' : '');
    }

    // Tagged percentage
    const taggedPill = pills[3];
    const taggedValue = taggedPill.querySelector('.status-value');
    if (taggedValue && collection.total_images > 0) {
        const taggedCount = collection.tagged || 0;
        const percentage = Math.round((taggedCount / collection.total_images) * 100);
        taggedValue.textContent = `${percentage}%`;
    } else if (taggedValue) {
        taggedValue.textContent = '-';
    }
};

// Secret Management
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

    if (!secretSection) return;

    // Clear existing content
    secretSection.innerHTML = '';

    if (SYSTEM_SECRET) {
        const template = document.getElementById('secret-configured-template');
        const clone = template.content.cloneNode(true);
        secretSection.appendChild(clone);
    } else {
        const template = document.getElementById('secret-required-template');
        const clone = template.content.cloneNode(true);
        secretSection.appendChild(clone);
    }
}

// Modal functions for secret input
function showSecretModal() {
    const modal = document.getElementById('secretModal');
    if (modal) {
        modal.style.display = 'flex';
        const input = modal.querySelector('#secretInput');
        if (input) {
            input.focus();
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    saveSystemSecret();
                    closeSecretModal();
                }
            });
        }
    }
}

function closeSecretModal() {
    const modal = document.getElementById('secretModal');
    if (modal) {
        modal.style.display = 'none';
        const input = modal.querySelector('#secretInput');
        if (input) input.value = '';
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

    window.showConfirm('Are you sure you want to change the system secret?', () => {
        SYSTEM_SECRET = null;
        localStorage.removeItem('system_secret');
        showNotification('Secret cleared', 'success');
        updateSecretUI();
    });
}

// Status and Logs Loading
function loadSystemStatus() {
    if (!SYSTEM_SECRET) return;

    fetch('/api/system/status')
        .then(res => res.json())
        .then(data => {
            const monitor = data.monitor;
            const collection = data.collection;

            // Update status pills in header
            if (window.updateStatusPills) {
                window.updateStatusPills(monitor, collection);
            }

            // Update Overview section
            updateOverviewStatus(monitor, collection);

            // Update legacy status div for backwards compatibility
            const statusDiv = document.getElementById('systemStatus');
            if (statusDiv) {
                statusDiv.innerHTML = '';
                const grid = document.createElement('div');
                grid.className = 'status-grid';

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
            }

            updateMonitorButton(monitor.running);
        })
        .catch(err => {
            console.error('Error loading system status:', err);
        });
}

function updateOverviewStatus(monitor, collection) {
    // Update monitor stats
    const monitorStats = document.getElementById('monitorStats');
    if (monitorStats) {
        const stats = monitorStats.querySelectorAll('.monitor-stat');
        if (stats.length >= 3) {
            const intervalValue = stats[0].querySelector('.monitor-value');
            const lastCheckValue = stats[1].querySelector('.monitor-value');
            const processedValue = stats[2].querySelector('.monitor-value');

            if (intervalValue) intervalValue.textContent = `${monitor.interval_seconds || 0}s`;
            if (lastCheckValue) lastCheckValue.textContent = monitor.last_check || 'Never';
            if (processedValue) processedValue.textContent = (monitor.total_processed || 0).toLocaleString();
        }
    }

    // Update collection stats
    const collectionStats = document.getElementById('collectionStats');
    if (collectionStats) {
        const stats = collectionStats.querySelectorAll('.collection-stat');
        if (stats.length >= 4) {
            const totalValue = stats[0].querySelector('.collection-value');
            const taggedValue = stats[1].querySelector('.collection-value');
            const ratedValue = stats[2].querySelector('.collection-value');
            const pendingValue = stats[3].querySelector('.collection-value');
            const pendingStat = stats[3];

            const total = collection.total_images || 0;
            if (totalValue) totalValue.textContent = total.toLocaleString();

            // Show Tagged and Rated as percentages
            if (taggedValue) {
                if (total > 0) {
                    const taggedPct = Math.round(((collection.tagged || 0) / total) * 100);
                    taggedValue.textContent = `${taggedPct}%`;
                } else {
                    taggedValue.textContent = '-';
                }
            }
            if (ratedValue) {
                if (total > 0) {
                    const ratedPct = Math.round(((collection.rated || 0) / total) * 100);
                    ratedValue.textContent = `${ratedPct}%`;
                } else {
                    ratedValue.textContent = '-';
                }
            }
            if (pendingValue) pendingValue.textContent = (collection.unprocessed || 0).toLocaleString();

            // Update warning state for pending
            if (pendingStat) {
                if (collection.unprocessed > 0) {
                    pendingStat.classList.add('collection-warning');
                } else {
                    pendingStat.classList.remove('collection-warning');
                }
            }
        }
    }
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
        btn.className = 'monitor-btn monitor-btn-stop';
        btn.textContent = '⏹ Stop';
        btn.onclick = (e) => systemStopMonitor(e);
    } else {
        btn.className = 'monitor-btn monitor-btn-start';
        btn.textContent = '▶ Start';
        btn.onclick = (e) => systemStartMonitor(e);
    }
}

function loadLogs() {
    if (!SYSTEM_SECRET) return;

    fetch('/api/system/logs')
        .then(res => res.json())
        .then(logs => {
            // Update Overview logs container
            const overviewLogsDiv = document.getElementById('systemLogsOverview');
            if (overviewLogsDiv) {
                overviewLogsDiv.innerHTML = '';

                if (logs.length === 0) {
                    const entry = createLogEntry('No recent activity', 'info');
                    overviewLogsDiv.appendChild(entry);
                } else {
                    logs.forEach(log => {
                        const entry = createLogEntry(log.message, log.type, log.timestamp);
                        overviewLogsDiv.appendChild(entry);
                    });
                }

                // Recalculate log container height after populating
                constrainActivityLogHeight();
            }

            // Update legacy logs container for backwards compatibility
            const logsDiv = document.getElementById('systemLogs');
            if (logsDiv) {
                logsDiv.innerHTML = '';

                if (logs.length === 0) {
                    const entry = createLogEntry('No recent activity', 'info');
                    logsDiv.appendChild(entry);
                } else {
                    logs.forEach(log => {
                        const entry = createLogEntry(log.message, log.type, log.timestamp);
                        logsDiv.appendChild(entry);
                    });
                }
            }
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

// System Actions
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

// Individual System Action Functions
function systemScanImages(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/scan', event.target, 'Scan & Process');
}

function systemReloadData(event) {
    if (event) event.preventDefault();
    systemAction('/api/reload', event.target, 'Reload Data');
}

function systemRebuildTags(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will delete and re-import all data from your metadata files. Are you sure?', () => {
        systemAction('/api/system/rebuild', event.target, 'Rebuild Tags');
    });
}

function systemRebuildCategorized(event) {
    if (event) event.preventDefault();
    const buttonElement = event ? event.target : null;
    window.showConfirm('This will fix tag displays by populating categorized tag data for all images. This is safe to run. Continue?', () => {
        systemAction('/api/system/rebuild_categorized', buttonElement, 'Rebuild Categorized Tags');
    });
}

function systemRecategorizeTags(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will check all general tags and move them to the correct category (artist/character/copyright/meta) if they exist as categorized tags elsewhere. Continue?', () => {
        systemAction('/api/system/recategorize', event.target, 'Recategorize Tags');
    });
}

function systemGenerateThumbnails(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/thumbnails', event.target, 'Generate Thumbnails');
}

function systemGenerateHashes(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will generate perceptual hashes for images without them. Continue?', () => {
        systemAction('/api/similarity/generate-hashes', event.target, 'Generate Image Hashes');
    });
}

function systemDeduplicate(event) {
    if (event) event.preventDefault();
    systemAction('/api/system/deduplicate', event.target, 'Deduplicate', { dry_run: false });
}

function systemCleanOrphans(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will remove database entries for images that no longer exist on disk. Proceed?', () => {
        systemAction('/api/system/clean_orphans', event.target, 'Clean Orphans', { dry_run: false });
    });
}

function systemApplyMergedSources(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will apply the current merge setting to all images with multiple sources. If merging is enabled, tags will be merged. If disabled, images will revert to their primary source. Continue?', () => {
        systemAction('/api/system/apply_merged_sources', event.target, 'Apply Source Merge Setting');
    });
}

function systemRecountTags(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will recount all tag usage statistics. Continue?', () => {
        systemAction('/api/system/recount_tags', event.target, 'Recount Tags');
    });
}

function systemReindexDatabase(event) {
    if (event) event.preventDefault();
    window.showConfirm('This will optimize the database (VACUUM and REINDEX). This may take a few seconds. Continue?', () => {
        systemAction('/api/system/reindex', event.target, 'Optimize Database');
    });
}

function systemReprocessImages(event) {
    if (event) event.preventDefault();

    const template = document.getElementById('reprocess-images-modal-template');
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

            // Route to appropriate endpoint based on option
            switch (option) {
                case 'find-online':
                    // Try online sources for locally-tagged images, keep current if nothing found
                    systemAction('/api/bulk_retry_tagging', event.target, 'Find Online Sources', { skip_local_fallback: true });
                    break;
                case 'refresh-local':
                    // Re-run local AI on locally-tagged images only
                    systemAction('/api/system/bulk_retag_local', event.target, 'Refresh Local AI', { local_only: true });
                    break;
                case 'complement-pixiv':
                    // Try online for Pixiv, fall back to local AI
                    systemAction('/api/bulk_retry_tagging', event.target, 'Complement Pixiv', { complement_pixiv: true });
                    break;
                case 'retag-all':
                    // Confirm dangerous action
                    window.showConfirm('This will re-run the AI tagger on EVERY image, including those with good online data. This takes a long time. Continue?', () => {
                        systemAction('/api/system/bulk_retag_local', event.target, 'Retag Everything');
                    });
                    break;
                case 'reprocess-all':
                    // Confirm dangerous action
                    window.showConfirm('This will run the full reprocessing pipeline on EVERY image. This overwrites existing data and takes a very long time. Continue?', () => {
                        systemAction('/api/bulk_retry_tagging', event.target, 'Reprocess All', { reprocess_all: true });
                    });
                    break;
            }
        });
    });

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };

    document.body.appendChild(overlay);
}

// Keep for backwards compatibility
function systemBulkRetagLocal(event) {
    systemReprocessImages(event);
}

function systemBulkRetryTagging(event) {
    systemReprocessImages(event);
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

        loadLogs();

        const endpoint = reapply ? '/api/implications/clear-and-reapply' : '/api/implications/clear-tags';

        fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(res => res.json())
            .then(data => {
                if (data.message) {
                    showNotification(data.message, 'success');
                    loadLogs();
                } else if (data.error) {
                    showNotification(`Error: ${data.error}`, 'error');
                }
            })
            .catch(err => {
                showNotification(`Error: ${err.message}`, 'error');
            })
            .finally(() => {
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
                loadLogs();
            });
    };

    btnCancel.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = (e) => {
        if (e.target === overlay) document.body.removeChild(overlay);
    };

    document.body.appendChild(overlay);
}

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
                        loadSystemStatus();
                        loadLogs();
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

// Settings Management
async function initializeSettings() {
    await loadSettings();
    setupSettingsSearch();
    setupSaveButton();
    setupReloadButton();
}

async function loadSettings() {
    try {
        const response = await fetch('/api/system/config');

        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = `HTTP error! status: ${response.status}`;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.error || errorData.message || errorMessage;
            } catch (e) {
                // Not JSON, use text
            }
            throw new Error(errorMessage);
        }

        const data = await response.json();

        // Check if response contains error field
        if (data.error) {
            throw new Error(data.error || 'Failed to load settings');
        }

        // Check if response is an error response (has status field that's not success)
        if (data.status === 'error') {
            throw new Error(data.message || data.error || 'Failed to load settings');
        }

        // Validate data structure - should be an object with category keys mapping to arrays
        if (!data || typeof data !== 'object') {
            throw new Error('Invalid response format');
        }

        // Additional validation: check if it looks like settings data (has at least one array value)
        // vs error response (has status/error/message fields but no array values)
        const hasArrayValues = Object.values(data).some(v => Array.isArray(v));
        const hasErrorFields = ('status' in data && data.status !== 'success') || 'error' in data || ('message' in data && !hasArrayValues);

        if (hasErrorFields && !hasArrayValues) {
            // This looks like an error response, not settings
            throw new Error(data.error || data.message || 'Failed to load settings');
        }

        // Final check: if no array values at all, this is probably not settings data
        if (!hasArrayValues) {
            throw new Error('Response does not contain valid settings data');
        }

        // Filter out API metadata fields (success, status, error, message) that might be added by api_handler
        const metadataFields = ['success', 'status', 'error', 'message'];
        const filteredData = {};
        for (const [key, value] of Object.entries(data)) {
            if (!metadataFields.includes(key)) {
                filteredData[key] = value;
            }
        }

        settingsData = filteredData;
        renderSettings(filteredData);
    } catch (err) {
        console.error('Error loading settings:', err);
        showNotification(`Failed to load settings: ${err.message}`, 'error');

        // Show error in settings container
        const container = document.getElementById('settingsCategories');
        if (container) {
            container.innerHTML = `<div class="error-message">Error loading settings: ${err.message}</div>`;
        }
    }
}

function renderSettings(categorizedSettings) {
    const container = document.getElementById('settingsCategories');
    if (!container) {
        console.error('Settings container not found');
        return;
    }

    container.innerHTML = '';

    // Validate input
    if (!categorizedSettings || typeof categorizedSettings !== 'object') {
        console.error('Invalid settings data:', categorizedSettings);
        container.innerHTML = '<div class="error-message">Failed to load settings: Invalid data structure</div>';
        return;
    }

    // Category icons mapping
    const categoryIcons = {
        'Application': '🏠',
        'AI Tagging': '🤖',
        'Database': '💾',
        'Similarity': '🔍',
        'Storage': '💿',
        'Network': '🌐',
        'Security': '🔒',
        'Performance': '⚡',
        'UI': '🎨',
        'Other': '📦'
    };

    // Sort categories
    const categories = Object.keys(categorizedSettings).sort();

    categories.forEach(category => {
        const categoryData = categorizedSettings[category];

        // Ensure category data is an array
        if (!Array.isArray(categoryData)) {
            console.warn(`Category "${category}" is not an array:`, categoryData);
            return; // Skip this category
        }

        // Skip empty categories
        if (categoryData.length === 0) {
            return;
        }

        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'settings-category';
        categoryDiv.dataset.category = category;

        const icon = categoryIcons[category] || '📦';
        const header = document.createElement('div');
        header.className = 'settings-category-header';
        header.innerHTML = `<h3><span class="category-icon">${icon}</span>${category}</h3>`;
        categoryDiv.appendChild(header);

        const itemsDiv = document.createElement('div');
        itemsDiv.className = 'settings-category-items';

        categoryData.forEach(setting => {
            if (!setting || typeof setting !== 'object') {
                console.warn('Invalid setting object:', setting);
                return;
            }
            const item = createSettingItem(setting);
            itemsDiv.appendChild(item);
        });

        categoryDiv.appendChild(itemsDiv);
        container.appendChild(categoryDiv);
    });
}

function createSettingItem(setting) {
    const item = document.createElement('div');
    item.className = 'setting-item';
    item.dataset.key = setting.key;

    const label = document.createElement('label');
    label.className = 'setting-label';
    label.textContent = setting.key;
    if (setting.description) {
        label.title = setting.description;
    }

    const input = createSettingInput(setting);
    const desc = document.createElement('div');
    desc.className = 'setting-description';
    desc.textContent = setting.description || '';

    // Vertical layout: label on top, input in middle, description at bottom
    item.appendChild(label);
    item.appendChild(input);
    item.appendChild(desc);

    return item;
}

function createSettingInput(setting) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-input-wrapper';

    let input;

    if (setting.type === 'bool') {
        input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = setting.value === true || setting.value === 'true';
        input.addEventListener('change', () => {
            settingsChanged[setting.key] = input.checked;
            markChanged(wrapper, true);
        });
    } else if (setting.type === 'list') {
        input = document.createElement('textarea');
        const listValue = Array.isArray(setting.value) ? setting.value : (setting.value ? [setting.value] : []);
        input.value = listValue.length > 0 ? listValue.join(', ') : '';
        input.placeholder = 'Comma-separated values';
        input.rows = 2;
        input.style.minWidth = '300px';
        input.style.width = '100%';
        input.addEventListener('input', () => {
            settingsChanged[setting.key] = input.value.split(',').map(v => v.trim()).filter(v => v);
            markChanged(wrapper, true);
        });
    } else if (setting.type === 'dict') {
        input = document.createElement('textarea');
        input.value = typeof setting.value === 'object' ? JSON.stringify(setting.value, null, 2) : (setting.value || '{}');
        input.placeholder = 'JSON object';
        input.rows = 4;
        input.addEventListener('input', () => {
            try {
                settingsChanged[setting.key] = JSON.parse(input.value);
                markChanged(wrapper, true);
            } catch (e) {
                markChanged(wrapper, false);
            }
        });
    } else {
        input = document.createElement('input');
        input.type = setting.type === 'int' || setting.type === 'float' ? 'number' : 'text';

        // Always show the actual value - backend should provide defaults
        if (setting.value !== null && setting.value !== undefined) {
            input.value = setting.value;
        } else {
            input.value = '';
        }

        if (setting.min !== undefined) {
            input.min = setting.min;
        }
        if (setting.max !== undefined) {
            input.max = setting.max;
        }

        input.addEventListener('input', () => {
            let value = input.value;
            if (setting.type === 'int') {
                value = value === '' ? null : parseInt(value);
            } else if (setting.type === 'float') {
                value = value === '' ? null : parseFloat(value);
            }
            settingsChanged[setting.key] = value;
            markChanged(wrapper, true);
        });
    }

    input.className = 'setting-input';
    wrapper.appendChild(input);

    return wrapper;
}

function markChanged(wrapper, valid) {
    wrapper.classList.toggle('changed', valid);
    wrapper.classList.toggle('invalid', !valid);
}

function setupSettingsSearch() {
    const searchInput = document.getElementById('settingsSearch');
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        const categories = document.querySelectorAll('.settings-category');

        categories.forEach(category => {
            const items = category.querySelectorAll('.setting-item');
            let hasVisible = false;

            items.forEach(item => {
                const key = item.dataset.key.toLowerCase();
                const desc = item.querySelector('.setting-description').textContent.toLowerCase();
                const matches = key.includes(query) || desc.includes(query);

                item.style.display = matches ? '' : 'none';
                if (matches) hasVisible = true;
            });

            category.style.display = hasVisible ? '' : 'none';
        });
    });
}

function setupSaveButton() {
    const saveBtn = document.getElementById('saveSettingsBtn');
    saveBtn.addEventListener('click', async () => {
        if (Object.keys(settingsChanged).length === 0) {
            showNotification('No changes to save', 'info');
            return;
        }

        const secret = localStorage.getItem('system_secret');
        if (!secret) {
            showNotification('Please set the System Secret first (click the 🔐 button in the header)', 'error');
            return;
        }

        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';

        try {
            const response = await fetch(`/api/system/config/update?secret=${encodeURIComponent(secret || '')}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsChanged)
            });

            const data = await response.json();

            if (data.status === 'success') {
                showNotification('Settings saved successfully', 'success');
                settingsChanged = {};
                // Reload settings to get updated values
                await loadSettings();
            } else if (data.error && data.error.includes('secret')) {
                showNotification('Invalid system secret. Please re-enter your secret.', 'error');
            } else {
                showNotification(`Error: ${data.errors ? Object.values(data.errors).join(', ') : (data.error || 'Failed to save')}`, 'error');
            }
        } catch (err) {
            console.error('Error saving settings:', err);
            showNotification('Failed to save settings: ' + err.message, 'error');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Changes';
        }
    });
}

function setupReloadButton() {
    const reloadBtn = document.getElementById('reloadConfigBtn');
    reloadBtn.addEventListener('click', async () => {
        reloadBtn.disabled = true;
        try {
            const response = await fetch('/api/system/config/reload', { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                showNotification('Config reloaded', 'success');
                await loadSettings();
            }
        } catch (err) {
            showNotification('Failed to reload config', 'error');
        } finally {
            reloadBtn.disabled = false;
        }
    });
}

function initializeStatus() {
    // Status will be loaded when overview section is shown
    // Also load on initial page load if overview is active
    setTimeout(() => {
        const secret = localStorage.getItem('system_secret');
        const overviewSection = document.getElementById('overview-section');
        if (secret && overviewSection && overviewSection.classList.contains('active')) {
            loadSystemStatus();
        }
    }, 100);
}

function initializeLogs() {
    // Logs will be loaded when overview section is active
    setInterval(() => {
        const secret = localStorage.getItem('system_secret');
        const overviewSection = document.getElementById('overview-section');
        if (secret && overviewSection && overviewSection.classList.contains('active')) {
            loadLogs();
        }
    }, 5000);
}

// Export functions to window for onclick handlers
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
window.showSecretModal = showSecretModal;
window.closeSecretModal = closeSecretModal;
window.systemFindBrokenImages = systemFindBrokenImages;
window.loadSystemStatus = loadSystemStatus;
window.loadLogs = loadLogs;
window.updateSecretUI = updateSecretUI;
window.validateStoredSecret = validateStoredSecret;


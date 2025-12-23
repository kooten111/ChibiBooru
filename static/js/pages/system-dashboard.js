// System Dashboard JavaScript
import { showNotification } from '../utils/notifications.js';

let SYSTEM_SECRET = localStorage.getItem('system_secret');
let statusInterval = null;
let activeTasks = new Set();

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', () => {
    initializeDashboard();
    setupCollapsibleSections();
    setupLogFilters();
});

async function initializeDashboard() {
    // Validate stored secret
    await validateStoredSecret();
    
    // Update UI based on secret status
    updateSecretUI();
    
    if (SYSTEM_SECRET) {
        // Load initial data
        await loadSystemStatus();
        await loadActivityLog();
        
        // Start periodic updates
        statusInterval = setInterval(async () => {
            await loadSystemStatus();
            await loadActivityLog();
            await pollActiveTasks();
        }, 5000);
    }
}

async function validateStoredSecret() {
    if (!SYSTEM_SECRET) return;
    
    try {
        const response = await fetch(`/api/system/validate_secret?secret=${encodeURIComponent(SYSTEM_SECRET)}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (!data.success || !data.valid) {
            SYSTEM_SECRET = null;
            localStorage.removeItem('system_secret');
            console.log('Stored secret was invalid and has been cleared');
        }
    } catch (err) {
        console.error('Error validating stored secret:', err);
    }
}

function updateSecretUI() {
    const secretSection = document.getElementById('secretSection');
    const actionPanels = document.querySelectorAll('.action-panel');
    
    if (!secretSection) return;
    
    secretSection.innerHTML = '';
    
    if (SYSTEM_SECRET) {
        const template = document.getElementById('secret-configured-template');
        const clone = template.content.cloneNode(true);
        secretSection.appendChild(clone);
        
        // Show action panels
        actionPanels.forEach(panel => {
            if (panel !== secretSection.closest('.action-panel')) {
                panel.style.display = 'block';
            }
        });
    } else {
        const template = document.getElementById('secret-required-template');
        const clone = template.content.cloneNode(true);
        secretSection.appendChild(clone);
        
        // Add enter key listener
        const input = secretSection.querySelector('#secretInput');
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') saveSystemSecret();
            });
        }
        
        // Hide action panels except monitor control (show status only)
        actionPanels.forEach(panel => {
            if (panel.id !== 'monitorControlPanel') {
                panel.style.display = 'none';
            }
        });
    }
}

async function loadSystemStatus() {
    try {
        const response = await fetch('/api/system/status');
        const data = await response.json();
        
        updateStatusCards(data);
        updateSystemInfo(data);
    } catch (err) {
        console.error('Error loading system status:', err);
    }
}

function updateStatusCards(data) {
    const monitor = data.monitor;
    const collection = data.collection;
    
    // Monitor Status
    const monitorValue = document.getElementById('monitorStatusValue');
    const monitorIndicator = document.getElementById('monitorIndicator');
    if (monitorValue && monitorIndicator) {
        monitorValue.textContent = monitor.running ? 'Running' : 'Stopped';
        monitorIndicator.className = `status-indicator ${monitor.running ? 'running' : 'stopped'}`;
    }
    
    // Total Images
    const totalImagesValue = document.getElementById('totalImagesValue');
    const unprocessedSubtext = document.getElementById('unprocessedSubtext');
    if (totalImagesValue) {
        totalImagesValue.textContent = collection.total_images.toLocaleString();
    }
    if (unprocessedSubtext) {
        const unprocessed = collection.unprocessed || 0;
        unprocessedSubtext.textContent = unprocessed > 0 
            ? `${unprocessed} unprocessed` 
            : 'All processed';
    }
    
    // Total Tags (placeholder - would need API endpoint)
    const totalTagsValue = document.getElementById('totalTagsValue');
    if (totalTagsValue) {
        totalTagsValue.textContent = '-';
    }
    
    // Storage (placeholder - would need API endpoint)
    const storageValue = document.getElementById('storageValue');
    if (storageValue) {
        storageValue.textContent = '-';
    }
    
    // Health
    const healthValue = document.getElementById('healthValue');
    const healthSubtext = document.getElementById('healthSubtext');
    const healthIndicator = document.getElementById('healthIndicator');
    if (healthValue && healthSubtext && healthIndicator) {
        const unprocessed = collection.unprocessed || 0;
        if (unprocessed === 0) {
            healthValue.textContent = 'Good';
            healthSubtext.textContent = 'No issues detected';
            healthIndicator.className = 'status-indicator good';
        } else if (unprocessed < 10) {
            healthValue.textContent = 'OK';
            healthSubtext.textContent = `${unprocessed} to process`;
            healthIndicator.className = 'status-indicator warning';
        } else {
            healthValue.textContent = 'Attention';
            healthSubtext.textContent = `${unprocessed} to process`;
            healthIndicator.className = 'status-indicator warning';
        }
    }
    
    // Update monitor toggle button
    updateMonitorButton(monitor.running);
}

function updateSystemInfo(data) {
    const monitor = data.monitor;
    
    const lastScanInfo = document.getElementById('lastScanInfo');
    if (lastScanInfo) {
        lastScanInfo.textContent = monitor.last_check || 'Never';
    }
    
    const scanIntervalInfo = document.getElementById('scanIntervalInfo');
    if (scanIntervalInfo) {
        scanIntervalInfo.textContent = `${monitor.interval_seconds}s`;
    }
    
    const totalProcessedInfo = document.getElementById('totalProcessedInfo');
    if (totalProcessedInfo) {
        totalProcessedInfo.textContent = monitor.total_processed.toLocaleString();
    }
    
    // Placeholders for DB size and thumbnails
    const dbSizeInfo = document.getElementById('dbSizeInfo');
    if (dbSizeInfo) {
        dbSizeInfo.textContent = '-';
    }
    
    const thumbDirSizeInfo = document.getElementById('thumbDirSizeInfo');
    if (thumbDirSizeInfo) {
        thumbDirSizeInfo.textContent = '-';
    }
}

function updateMonitorButton(isRunning) {
    const btn = document.getElementById('monitorToggleBtn');
    if (!btn) return;
    
    if (isRunning) {
        btn.className = 'btn btn-danger';
        btn.innerHTML = '⏸️ Stop Monitor';
        btn.onclick = (e) => actionStopMonitor(e);
    } else {
        btn.className = 'btn btn-success';
        btn.innerHTML = '▶️ Start Monitor';
        btn.onclick = (e) => actionStartMonitor(e);
    }
}

async function loadActivityLog() {
    if (!SYSTEM_SECRET) return;
    
    try {
        const response = await fetch('/api/system/logs');
        const logs = await response.json();
        
        const logContainer = document.getElementById('activityLog');
        if (!logContainer) return;
        
        // Clear existing logs
        logContainer.innerHTML = '';
        
        if (logs.length === 0) {
            const entry = createLogEntry('No recent activity', 'info');
            logContainer.appendChild(entry);
            return;
        }
        
        logs.forEach(log => {
            const entry = createLogEntry(log.message, log.type, log.timestamp);
            logContainer.appendChild(entry);
        });
        
        // Apply current filter
        const activeFilter = document.querySelector('.filter-btn.active');
        if (activeFilter) {
            applyLogFilter(activeFilter.dataset.filter);
        }
    } catch (err) {
        console.error('Error loading activity log:', err);
    }
}

function createLogEntry(message, type, timestamp) {
    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.dataset.type = type;
    
    if (timestamp) {
        const timeSpan = document.createElement('span');
        timeSpan.style.color = 'var(--primary-blue)';
        timeSpan.style.marginRight = '10px';
        timeSpan.textContent = `[${timestamp}]`;
        entry.appendChild(timeSpan);
    }
    
    const messageText = document.createTextNode(message);
    entry.appendChild(messageText);
    
    return entry;
}

function setupLogFilters() {
    const filterBtns = document.querySelectorAll('.filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update active state
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Apply filter
            applyLogFilter(btn.dataset.filter);
        });
    });
}

function applyLogFilter(filter) {
    const logEntries = document.querySelectorAll('.log-entry');
    logEntries.forEach(entry => {
        if (filter === 'all') {
            entry.dataset.filtered = 'false';
        } else {
            entry.dataset.filtered = entry.dataset.type !== filter ? 'true' : 'false';
        }
    });
}

function setupCollapsibleSections() {
    // Initialize all sections as open
    const headers = document.querySelectorAll('.collapsible-header');
    headers.forEach(header => {
        header.classList.remove('collapsed');
    });
}

window.toggleSection = function(sectionId) {
    const content = document.getElementById(sectionId);
    const header = content.previousElementSibling;
    
    if (content.classList.contains('collapsed')) {
        content.classList.remove('collapsed');
        header.classList.remove('collapsed');
    } else {
        content.classList.add('collapsed');
        header.classList.add('collapsed');
    }
};

// Action Functions
async function performAction(endpoint, actionName, buttonElement, confirmMessage = null, body = null) {
    if (!SYSTEM_SECRET) {
        showNotification('System secret not configured', 'error');
        return;
    }
    
    // Confirm if needed
    if (confirmMessage) {
        if (!confirm(confirmMessage)) {
            return;
        }
    }
    
    // Ensure we have the button element
    if (buttonElement && buttonElement.tagName !== 'BUTTON') {
        buttonElement = buttonElement.closest('button');
    }
    
    const originalText = buttonElement ? buttonElement.innerHTML : '';
    if (buttonElement) {
        buttonElement.innerHTML = '<span class="processing-spinner">⚙️</span> Processing...';
        buttonElement.disabled = true;
    }
    
    const url = `${endpoint}?secret=${encodeURIComponent(SYSTEM_SECRET)}`;
    const options = {
        method: 'POST',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        body: body ? JSON.stringify(body) : null
    };
    
    let isBackgroundTask = false;
    
    try {
        const response = await fetch(url, options);
        const contentType = response.headers.get('content-type');
        
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response:', text);
            throw new Error(`Server returned non-JSON response. Status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Check for unauthorized first
        if (data.error === 'Unauthorized') {
            localStorage.removeItem('system_secret');
            SYSTEM_SECRET = null;
            showNotification('Invalid system secret', 'error');
            updateSecretUI();
        } else if (data.status === 'success') {
            const msg = data.message || `${actionName} completed`;
            showNotification(msg, 'success');
            await loadActivityLog();
            await loadSystemStatus();
        } else if (data.status === 'started' && data.task_id) {
            // Background task started
            isBackgroundTask = true;
            showNotification(`${actionName} started in background`, 'info');
            trackTask(data.task_id, actionName, buttonElement, originalText);
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    } catch (err) {
        const errMsg = `${actionName} failed: ${err.message}`;
        showNotification(errMsg, 'error');
        console.error('Full error:', err);
    } finally {
        // Only reset button if it's not a background task
        if (buttonElement && !isBackgroundTask) {
            buttonElement.innerHTML = originalText;
            buttonElement.disabled = false;
        }
    }
}

function trackTask(taskId, actionName, buttonElement, originalText) {
    activeTasks.add(taskId);
    updateRunningTasksPanel();
    
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/task_status?task_id=${encodeURIComponent(taskId)}`);
            const status = await response.json();
            
            console.log('Task status:', status);
            
            // Update button if provided
            if (buttonElement && status.progress !== undefined && status.total !== undefined) {
                const percentage = status.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;
                buttonElement.innerHTML = `⏳ ${percentage}% (${status.progress}/${status.total})`;
            }
            
            // Update running tasks panel
            updateTaskDisplay(taskId, actionName, status);
            
            if (status.status === 'completed') {
                clearInterval(pollInterval);
                activeTasks.delete(taskId);
                updateRunningTasksPanel();
                
                const msg = status.result?.message || `${actionName} completed successfully`;
                showNotification(msg, 'success');
                
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
                
                await loadActivityLog();
                await loadSystemStatus();
            } else if (status.status === 'failed') {
                clearInterval(pollInterval);
                activeTasks.delete(taskId);
                updateRunningTasksPanel();
                
                showNotification(`${actionName} failed: ${status.error}`, 'error');
                
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
            } else if (status.status !== 'running' && status.status !== 'pending') {
                // Unknown status
                clearInterval(pollInterval);
                activeTasks.delete(taskId);
                updateRunningTasksPanel();
                
                if (buttonElement) {
                    buttonElement.innerHTML = originalText;
                    buttonElement.disabled = false;
                }
            }
        } catch (err) {
            console.error('Error polling task status:', err);
            clearInterval(pollInterval);
            activeTasks.delete(taskId);
            updateRunningTasksPanel();
            
            showNotification(`Error checking ${actionName} progress`, 'error');
            
            if (buttonElement) {
                buttonElement.innerHTML = originalText;
                buttonElement.disabled = false;
            }
        }
    }, 1000);
}

function updateRunningTasksPanel() {
    const panel = document.getElementById('runningTasksPanel');
    const tasksList = document.getElementById('runningTasksList');
    
    if (activeTasks.size > 0) {
        panel.style.display = 'block';
    } else {
        panel.style.display = 'none';
        tasksList.innerHTML = '';
    }
}

function updateTaskDisplay(taskId, actionName, status) {
    const tasksList = document.getElementById('runningTasksList');
    let taskItem = document.getElementById(`task-${taskId}`);
    
    if (!taskItem) {
        taskItem = document.createElement('div');
        taskItem.className = 'task-item';
        taskItem.id = `task-${taskId}`;
        tasksList.appendChild(taskItem);
    }
    
    const percentage = status.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;
    
    taskItem.innerHTML = `
        <div class="task-header">
            <span class="task-name">${actionName}</span>
            <span class="task-status">${percentage}%</span>
        </div>
        <div class="task-progress-bar">
            <div class="task-progress-fill" style="width: ${percentage}%"></div>
        </div>
        <div class="task-details">${status.message || 'Processing...'}</div>
    `;
}

async function pollActiveTasks() {
    // This function is called periodically to keep tasks updated
    // The individual task polling intervals handle the actual updates
}

window.saveSystemSecret = async function() {
    const input = document.getElementById('secretInput');
    if (!input) return;
    
    const secret = input.value.trim();
    if (!secret) {
        showNotification('Please enter a secret', 'error');
        return;
    }
    
    input.disabled = true;
    
    try {
        const response = await fetch(`/api/system/validate_secret?secret=${encodeURIComponent(secret)}`, {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success && data.valid) {
            SYSTEM_SECRET = secret;
            localStorage.setItem('system_secret', secret);
            showNotification('Secret saved successfully', 'success');
            updateSecretUI();
            await loadSystemStatus();
            await loadActivityLog();
            
            // Start status interval if not already running
            if (!statusInterval) {
                statusInterval = setInterval(async () => {
                    await loadSystemStatus();
                    await loadActivityLog();
                    await pollActiveTasks();
                }, 5000);
            }
        } else {
            showNotification('Invalid system secret', 'error');
            input.value = '';
        }
    } catch (err) {
        console.error('Error validating secret:', err);
        showNotification('Error validating secret', 'error');
    } finally {
        input.disabled = false;
    }
};

window.clearSystemSecret = function(event) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    
    if (confirm('Are you sure you want to change the system secret?')) {
        SYSTEM_SECRET = null;
        localStorage.removeItem('system_secret');
        showNotification('Secret cleared', 'success');
        updateSecretUI();
        
        if (statusInterval) {
            clearInterval(statusInterval);
            statusInterval = null;
        }
    }
};

// Action handlers
window.actionScanImages = (e) => {
    e.preventDefault();
    performAction('/api/system/scan', 'Scan & Process', e.target);
};

window.actionReloadData = (e) => {
    e.preventDefault();
    performAction('/api/reload', 'Reload Data', e.target);
};

window.actionGenerateThumbnails = (e) => {
    e.preventDefault();
    performAction('/api/system/thumbnails', 'Generate Thumbnails', e.target);
};

window.actionGenerateHashes = (e) => {
    e.preventDefault();
    performAction('/api/similarity/generate-hashes', 'Generate Hashes', e.target);
};

window.actionOptimizeDatabase = (e) => {
    e.preventDefault();
    performAction('/api/system/reindex', 'Optimize Database', e.target, 
        'This will optimize the database (VACUUM and REINDEX). Continue?');
};

window.actionHealthCheck = (e) => {
    e.preventDefault();
    // For now, use default options. Could add modal like old panel
    performAction('/api/database_health_check', 'Health Check', e.target, null,
        { auto_fix: true, include_tag_deltas: true, include_thumbnails: false });
};

window.actionRebuildCategorized = (e) => {
    e.preventDefault();
    performAction('/api/system/rebuild_categorized', 'Rebuild Categorized', e.target,
        'This will refresh categorized tag data for all images. Continue?');
};

window.actionRecategorizeTags = (e) => {
    e.preventDefault();
    performAction('/api/system/recategorize', 'Recategorize Tags', e.target,
        'This will move general tags to correct categories. Continue?');
};

window.actionRecountTags = (e) => {
    e.preventDefault();
    performAction('/api/system/recount_tags', 'Recount Tags', e.target,
        'This will recount all tag usage statistics. Continue?');
};

window.actionBulkRetryTagging = (e) => {
    e.preventDefault();
    // Simplified version - could add modal for options
    performAction('/api/bulk_retry_tagging', 'Bulk Retry Tagging', e.target,
        'This will retry tagging for locally-tagged images. Continue?',
        { skip_local_fallback: true });
};

window.actionBulkRetagLocal = (e) => {
    e.preventDefault();
    performAction('/api/system/bulk_retag_local', 'Rescan with Local AI', e.target,
        'This will re-run local AI tagger on ALL images. This takes a while. Continue?');
};

window.actionApplyMergedSources = (e) => {
    e.preventDefault();
    performAction('/api/system/apply_merged_sources', 'Apply Merged Sources', e.target,
        'This will merge tags from multiple sources. Continue?');
};

window.actionCleanOrphans = (e) => {
    e.preventDefault();
    performAction('/api/system/clean_orphans', 'Clean Orphans', e.target,
        'This will remove database entries for deleted files. Continue?',
        { dry_run: false });
};

window.actionDeduplicate = (e) => {
    e.preventDefault();
    performAction('/api/system/deduplicate', 'Deduplicate', e.target,
        'This will find and remove duplicate images. Continue?',
        { dry_run: false });
};

window.actionRebuildDatabase = (e) => {
    e.preventDefault();
    performAction('/api/system/rebuild', 'Rebuild Database', e.target,
        'WARNING: This will delete and re-import all data from metadata files. This is IRREVERSIBLE. Are you absolutely sure?');
};

window.actionStartMonitor = (e) => {
    e.preventDefault();
    performAction('/api/system/monitor/start', 'Start Monitor', e.target);
};

window.actionStopMonitor = (e) => {
    e.preventDefault();
    performAction('/api/system/monitor/stop', 'Stop Monitor', e.target);
};

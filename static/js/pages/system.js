// System page JavaScript
import { showNotification } from '../utils/notifications.js';

// Functions from system-panel.js are available via window globals
// We'll access them after system-panel.js loads

let settingsData = {};
let settingsChanged = {};

// Tab switching
document.addEventListener('DOMContentLoaded', () => {
    initializeTabs();
    initializeSettings();
    initializeStatus();
    initializeActions();
    initializeLogs();
    
    // Initialize secret UI immediately if on actions tab
    setTimeout(() => {
        if (document.getElementById('actions-tab').classList.contains('active')) {
            if (window.updateSecretUI) {
                window.updateSecretUI();
            } else {
                // Wait for system-panel.js to load
                const checkInterval = setInterval(() => {
                    if (window.updateSecretUI) {
                        window.updateSecretUI();
                        clearInterval(checkInterval);
                    }
                }, 100);
                // Stop checking after 2 seconds
                setTimeout(() => clearInterval(checkInterval), 2000);
            }
        }
    }, 300);
});

function initializeTabs() {
    const tabs = document.querySelectorAll('.system-tab');
    const contents = document.querySelectorAll('.system-tab-content');
    
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;
            
            // Update active states
            tabs.forEach(t => t.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            document.getElementById(`${targetTab}-tab`).classList.add('active');
            
            // Load content if needed
            const secret = localStorage.getItem('system_secret');
            if (targetTab === 'status' && secret && window.loadSystemStatus) {
                window.loadSystemStatus();
            } else if (targetTab === 'logs' && secret && window.loadLogs) {
                window.loadLogs();
            } else if (targetTab === 'actions') {
                // Initialize secret UI when actions tab is shown
                if (window.updateSecretUI) {
                    window.updateSecretUI();
                }
            }
        });
    });
}

async function initializeSettings() {
    await loadSettings();
    setupSettingsSearch();
    setupSaveButton();
    setupReloadButton();
}

async function loadSettings() {
    try {
        const response = await fetch('/api/system/config');
        const data = await response.json();
        settingsData = data;
        renderSettings(data);
    } catch (err) {
        console.error('Error loading settings:', err);
        showNotification('Failed to load settings', 'error');
    }
}

function renderSettings(categorizedSettings) {
    const container = document.getElementById('settingsCategories');
    container.innerHTML = '';
    
    // Sort categories
    const categories = Object.keys(categorizedSettings).sort();
    
    categories.forEach(category => {
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'settings-category';
        categoryDiv.dataset.category = category;
        
        const header = document.createElement('div');
        header.className = 'settings-category-header';
        header.innerHTML = `<h3>${category}</h3>`;
        categoryDiv.appendChild(header);
        
        const itemsDiv = document.createElement('div');
        itemsDiv.className = 'settings-category-items';
        
        categorizedSettings[category].forEach(setting => {
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
        input.value = Array.isArray(setting.value) ? setting.value.join(', ') : (setting.value || '');
        input.placeholder = 'Comma-separated values';
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
        input.value = setting.value !== null && setting.value !== undefined ? setting.value : '';
        
        if (setting.min !== undefined) {
            input.min = setting.min;
        }
        if (setting.max !== undefined) {
            input.max = setting.max;
        }
        
        input.addEventListener('input', () => {
            let value = input.value;
            if (setting.type === 'int') {
                value = parseInt(value);
            } else if (setting.type === 'float') {
                value = parseFloat(value);
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
        
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        
        try {
            const secret = localStorage.getItem('system_secret');
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
            } else {
                showNotification(`Error: ${data.errors ? Object.values(data.errors).join(', ') : 'Failed to save'}`, 'error');
            }
        } catch (err) {
            console.error('Error saving settings:', err);
            showNotification('Failed to save settings', 'error');
        } finally {
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save All Changes';
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
    // Status will be loaded when tab is clicked via tab switching
    // Also load on initial page load if status tab is active
    setTimeout(() => {
        const secret = localStorage.getItem('system_secret');
        if (secret && window.loadSystemStatus && document.getElementById('status-tab').classList.contains('active')) {
            window.loadSystemStatus();
        }
    }, 100);
}

function initializeActions() {
    // Wait for system-panel.js to load, then initialize
    const initSecretUI = () => {
        if (window.validateStoredSecret && window.updateSecretUI) {
            window.validateStoredSecret().then(() => {
                window.updateSecretUI();
                const secret = localStorage.getItem('system_secret');
                if (secret && window.loadSystemStatus) {
                    window.loadSystemStatus();
                }
            });
            return true;
        }
        return false;
    };
    
    // Try immediately
    if (!initSecretUI()) {
        // If system-panel.js hasn't loaded yet, try again
        setTimeout(() => {
            if (!initSecretUI()) {
                // One more try
                setTimeout(initSecretUI, 200);
            }
        }, 100);
    }
    
    // Auto-refresh status
    setInterval(() => {
        const secret = localStorage.getItem('system_secret');
        if (secret && window.loadSystemStatus && document.getElementById('status-tab').classList.contains('active')) {
            window.loadSystemStatus();
        }
    }, 5000);
}

function initializeLogs() {
    // Logs will be loaded when tab is clicked
    setInterval(() => {
        const secret = localStorage.getItem('system_secret');
        if (secret && window.loadLogs && document.getElementById('logs-tab').classList.contains('active')) {
            window.loadLogs();
        }
    }, 5000);
}

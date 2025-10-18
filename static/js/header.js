class StatsTabs {
    constructor() {
        this.buttons = document.querySelectorAll('.stat-tab-button');
        this.panels = document.querySelectorAll('.stat-panel');
        this.panelsContainer = document.getElementById('statsPanelsContainer');
        this.currentOpenPanel = null;

        // NEW: Add toggle for image page
        this.headerContainer = document.querySelector('.header-container');
        this.tabsToggleButton = document.getElementById('tabs-toggle-button');

        this.init();
    }
    
    init() {
        this.buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleTabClick(button);
            });
        });

        // NEW: Click handler for the toggle button
        if (this.tabsToggleButton) {
            this.tabsToggleButton.addEventListener('click', () => {
                this.headerContainer.classList.toggle('tabs-expanded');
            });
        }
        
        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (this.currentOpenPanel && 
                !e.target.closest('.stats-panels-container') && 
                !e.target.closest('.stats-tabs-bar')) {
                this.closeCurrentPanel();
            }
        });
        
        // Prevent clicks inside panels from closing
        if (this.panelsContainer) {
            this.panelsContainer.addEventListener('click', (e) => {
                e.stopPropagation();
            });
        }
        
        // Restore last opened tab
        this.restoreLastTab();
    }
    
    handleTabClick(clickedButton) {
        const tabId = clickedButton.dataset.tab;
        const targetPanel = document.getElementById(tabId);
        
        if (!targetPanel) return;
        
        // If clicking the currently open tab, close it
        if (this.currentOpenPanel === targetPanel) {
            this.closeCurrentPanel();
            return;
        }
        
        // Close any currently open panel first
        if (this.currentOpenPanel) {
            this.closePanelWithAnimation(this.currentOpenPanel);
            // Deactivate previous button
            const previousButton = document.querySelector('.stat-tab-button.active');
            if (previousButton) {
                previousButton.classList.remove('active');
            }
        }
        
        // Open the new panel
        setTimeout(() => {
            clickedButton.classList.add('active');
            targetPanel.classList.add('active');
            this.currentOpenPanel = targetPanel;
            this.updatePanelsContainerState();
            this.saveLastTab(tabId);
        }, this.currentOpenPanel ? 150 : 0);
    }
    
    closeCurrentPanel() {
        if (!this.currentOpenPanel) return;
        
        this.closePanelWithAnimation(this.currentOpenPanel);
        
        // Deactivate button
        const activeButton = document.querySelector('.stat-tab-button.active');
        if (activeButton) {
            activeButton.classList.remove('active');
        }
        
        this.currentOpenPanel = null;
        this.updatePanelsContainerState();
        this.clearLastTab();
    }
    
    closePanelWithAnimation(panel) {
        panel.classList.add('closing');
        
        setTimeout(() => {
            panel.classList.remove('active', 'closing');
        }, 150);
    }
    
    updatePanelsContainerState() {
        if (this.panelsContainer) {
            if (this.currentOpenPanel) {
                this.panelsContainer.classList.add('has-active-panel');
            } else {
                this.panelsContainer.classList.remove('has-active-panel');
            }
        }
    }
    
    saveLastTab(tabId) {
        localStorage.setItem('lastOpenedTab', tabId);
    }
    
    clearLastTab() {
        localStorage.removeItem('lastOpenedTab');
    }
    
    restoreLastTab() {
        const lastTabId = localStorage.getItem('lastOpenedTab');
        if (!lastTabId) return;
        
        const button = document.querySelector(`[data-tab="${lastTabId}"]`);
        const panel = document.getElementById(lastTabId);
        
        if (button && panel) {
            button.classList.add('active');
            panel.classList.add('active');
            this.currentOpenPanel = panel;
            this.updatePanelsContainerState();
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.stats-tabs-bar')) {
        new StatsTabs();
    }
});
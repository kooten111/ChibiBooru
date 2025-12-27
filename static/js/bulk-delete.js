// bulk-delete.js - Mass delete functionality for image gallery
import { showSuccess, showError, showInfo } from './utils/notifications.js';

(function () {
    'use strict';

    let selectionMode = false;
    let selectedImages = new Set();

    const selectionToggle = document.getElementById('selection-toggle');
    const bulkActionsPanel = document.getElementById('bulkActionsPanel');
    const selectAllBtn = document.getElementById('select-all-btn');
    const downloadSelectedBtn = document.getElementById('download-selected-btn');
    const deleteSelectedBtn = document.getElementById('delete-selected-btn');
    const selectedCountSpan = document.getElementById('selected-count');

    // Check if we're on a search results page (has query parameter)
    const urlParams = new URLSearchParams(window.location.search);
    const hasQuery = urlParams.has('query');

    // Only enable bulk delete on search results pages
    if (!hasQuery || !selectionToggle) {
        return;
    }

    // Toggle selection mode
    function toggleSelectionMode() {
        selectionMode = !selectionMode;
        const checkboxes = document.querySelectorAll('.image-select-checkbox');
        const selectionIcon = selectionToggle.querySelector('.selection-icon');

        if (selectionMode) {
            // Enable selection mode - show checkboxes and action panel
            checkboxes.forEach(cb => {
                cb.style.display = 'block';
            });
            if (bulkActionsPanel) {
                bulkActionsPanel.style.display = 'flex';
            }
            selectionToggle.classList.add('active');
            if (selectionIcon) {
                selectionIcon.textContent = '☑';
            }
        } else {
            // Disable selection mode - hide checkboxes and reset
            checkboxes.forEach(cb => {
                cb.style.display = 'none';
                cb.checked = false;
            });
            if (bulkActionsPanel) {
                bulkActionsPanel.style.display = 'none';
            }
            selectionToggle.classList.remove('active');
            if (selectionIcon) {
                selectionIcon.textContent = '☐';
            }
            selectedImages.clear();
            updateSelectedCount();
        }
    }

    // Handle toggle button clicks
    if (selectionToggle) {
        selectionToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSelectionMode();
        });
    }

    // Update the selected count display
    function updateSelectedCount() {
        if (selectedCountSpan) {
            selectedCountSpan.textContent = selectedImages.size;
        }

        // Update button text
        if (selectAllBtn) {
            const allCheckboxes = document.querySelectorAll('.image-select-checkbox');
            const allSelected = allCheckboxes.length > 0 &&
                Array.from(allCheckboxes).every(cb => cb.checked);
            const btnText = selectAllBtn.querySelector('.btn-text');
            if (btnText) {
                btnText.textContent = allSelected ? 'Deselect All' : 'Select All';
            }
        }
    }

    // Handle checkbox changes
    document.addEventListener('change', function (e) {
        if (e.target.classList.contains('image-select-checkbox')) {
            const imagePath = e.target.dataset.imagePath;

            if (e.target.checked) {
                selectedImages.add(imagePath);
            } else {
                selectedImages.delete(imagePath);
            }

            updateSelectedCount();
        }
    });

    // Handle Select All button
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function () {
            const checkboxes = document.querySelectorAll('.image-select-checkbox');
            const allSelected = Array.from(checkboxes).every(cb => cb.checked);

            checkboxes.forEach(cb => {
                cb.checked = !allSelected;
                const imagePath = cb.dataset.imagePath;

                if (cb.checked) {
                    selectedImages.add(imagePath);
                } else {
                    selectedImages.delete(imagePath);
                }
            });

            updateSelectedCount();
        });
    }

    // Handle Download Selected button
    if (downloadSelectedBtn) {
        downloadSelectedBtn.addEventListener('click', async function () {
            if (selectedImages.size === 0) {
                showInfo('No images selected');
                return;
            }

            // Update button to show loading state
            const originalText = downloadSelectedBtn.innerHTML;
            downloadSelectedBtn.disabled = true;
            downloadSelectedBtn.innerHTML = '<span class="btn-icon">⏳</span><span class="btn-text">Preparing...</span>';

            try {
                const response = await fetch('/api/download_images_bulk', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        filepaths: Array.from(selectedImages)
                    })
                });

                if (response.ok) {
                    // Get the blob from the response
                    const blob = await response.blob();

                    // Create a download link
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `images_${Date.now()}.zip`;
                    document.body.appendChild(a);
                    a.click();

                    // Cleanup
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(a);
                } else {
                    const result = await response.json();
                    showError('Error downloading images: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error during bulk download:', error);
                showError('Network error occurred while downloading images');
            } finally {
                downloadSelectedBtn.disabled = false;
                downloadSelectedBtn.innerHTML = originalText;
            }
        });
    }

    // Handle Delete Selected button
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', async function () {
            if (selectedImages.size === 0) {
                showInfo('No images selected');
                return;
            }

            const confirmMessage = `Are you sure you want to delete ${selectedImages.size} image${selectedImages.size > 1 ? 's' : ''}? This action cannot be undone.`;

            if (!confirm(confirmMessage)) {
                return;
            }

            // Disable button during deletion
            deleteSelectedBtn.disabled = true;
            deleteSelectedBtn.textContent = 'Deleting...';

            try {
                const response = await fetch('/api/delete_images_bulk', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        filepaths: Array.from(selectedImages)
                    })
                });

                const result = await response.json();

                if (response.ok) {
                    // Remove deleted images from the page
                    selectedImages.forEach(imagePath => {
                        const thumbnail = document.querySelector(`.thumbnail[data-image-path="${imagePath}"]`);
                        if (thumbnail) {
                            thumbnail.remove();
                        }
                    });

                    // Clear selection
                    selectedImages.clear();
                    updateSelectedCount();

                    // Show success message
                    showSuccess(result.message || `Successfully deleted ${result.results.deleted} images`);

                    // If there are errors, show them
                    if (result.results.errors && result.results.errors.length > 0) {
                        console.error('Deletion errors:', result.results.errors);
                    }

                    // Reload the page to update the results count
                    window.location.reload();
                } else {
                    showError('Error deleting images: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error during bulk delete:', error);
                showError('Network error occurred while deleting images');
            } finally {
                deleteSelectedBtn.disabled = false;
                deleteSelectedBtn.innerHTML = 'Delete Selected (<span id="selected-count">0</span>)';
            }
        });
    }

    // Prevent checkbox clicks from triggering the image link
    document.addEventListener('click', function (e) {
        if (e.target.classList.contains('image-select-checkbox')) {
            e.stopPropagation();
        }
    }, true);

})();

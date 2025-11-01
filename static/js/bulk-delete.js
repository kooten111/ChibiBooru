// bulk-delete.js - Mass delete functionality for image gallery

(function() {
    'use strict';

    let selectionMode = false;
    let selectedImages = new Set();

    const enableSelectionBtn = document.getElementById('enable-selection-btn');
    const selectAllBtn = document.getElementById('select-all-btn');
    const deleteSelectedBtn = document.getElementById('delete-selected-btn');
    const selectedCountSpan = document.getElementById('selected-count');

    // Check if we're on a search results page (has query parameter)
    const urlParams = new URLSearchParams(window.location.search);
    const hasQuery = urlParams.has('query');

    // Only enable bulk delete on search results pages
    if (!hasQuery || !enableSelectionBtn) {
        return;
    }

    // Toggle selection mode
    function toggleSelectionMode() {
        selectionMode = !selectionMode;
        const checkboxes = document.querySelectorAll('.image-select-checkbox');

        if (selectionMode) {
            // Enable selection mode - show checkboxes and other buttons
            checkboxes.forEach(cb => {
                cb.style.display = 'block';
            });
            selectAllBtn.style.display = 'inline-block';
            deleteSelectedBtn.style.display = 'inline-block';
            enableSelectionBtn.textContent = 'Disable Selection';
            enableSelectionBtn.classList.remove('btn-secondary');
            enableSelectionBtn.classList.add('btn-primary');
        } else {
            // Disable selection mode - hide checkboxes and reset
            checkboxes.forEach(cb => {
                cb.style.display = 'none';
                cb.checked = false;
            });
            selectAllBtn.style.display = 'none';
            deleteSelectedBtn.style.display = 'none';
            enableSelectionBtn.textContent = 'Enable Selection';
            enableSelectionBtn.classList.remove('btn-primary');
            enableSelectionBtn.classList.add('btn-secondary');
            selectedImages.clear();
            updateSelectedCount();
        }
    }

    // Handle Enable/Disable Selection button
    if (enableSelectionBtn) {
        enableSelectionBtn.addEventListener('click', toggleSelectionMode);
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
            selectAllBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        }
    }

    // Handle checkbox changes
    document.addEventListener('change', function(e) {
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
        selectAllBtn.addEventListener('click', function() {
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

    // Handle Delete Selected button
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', async function() {
            if (selectedImages.size === 0) {
                alert('No images selected');
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
                    alert(result.message || `Successfully deleted ${result.results.deleted} images`);

                    // If there are errors, show them
                    if (result.results.errors && result.results.errors.length > 0) {
                        console.error('Deletion errors:', result.results.errors);
                    }

                    // Reload the page to update the results count
                    window.location.reload();
                } else {
                    alert('Error deleting images: ' + (result.error || 'Unknown error'));
                }
            } catch (error) {
                console.error('Error during bulk delete:', error);
                alert('Network error occurred while deleting images');
            } finally {
                deleteSelectedBtn.disabled = false;
                deleteSelectedBtn.innerHTML = 'Delete Selected (<span id="selected-count">0</span>)';
            }
        });
    }

    // Prevent checkbox clicks from triggering the image link
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('image-select-checkbox')) {
            e.stopPropagation();
        }
    }, true);

})();

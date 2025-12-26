/**
 * Favourites Module
 * Handles favourite button state and toggle functionality
 */

(function () {
    'use strict';

    const favouriteBtn = document.getElementById('favouriteBtn');
    if (!favouriteBtn) return;

    const filepath = favouriteBtn.dataset.filepath;
    const iconSpan = favouriteBtn.querySelector('.favourite-icon');
    const textSpan = favouriteBtn.querySelector('.favourite-text');

    // Icons for favourite states
    const ICON_FAVOURITE = '❤️';
    const ICON_NOT_FAVOURITE = '🤍';

    /**
     * Update button appearance based on favourite state
     */
    function updateButtonState(isFavourite) {
        if (isFavourite) {
            favouriteBtn.classList.add('is-favourite');
            if (iconSpan) iconSpan.textContent = ICON_FAVOURITE;
            if (textSpan) textSpan.textContent = 'Favourited';
        } else {
            favouriteBtn.classList.remove('is-favourite');
            if (iconSpan) iconSpan.textContent = ICON_NOT_FAVOURITE;
            if (textSpan) textSpan.textContent = 'Favourite';
        }
    }

    /**
     * Check initial favourite status on page load
     */
    async function checkFavouriteStatus() {
        try {
            const response = await fetch(`/api/favourites/status?filepath=${encodeURIComponent(filepath)}`);
            if (response.ok) {
                const data = await response.json();
                updateButtonState(data.is_favourite);
            }
        } catch (error) {
            console.error('Error checking favourite status:', error);
        }
    }

    /**
     * Toggle favourite status
     */
    async function toggleFavourite() {
        // Disable button during request
        favouriteBtn.disabled = true;

        try {
            const response = await fetch('/api/favourites/toggle', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ filepath: filepath }),
            });

            if (response.ok) {
                const data = await response.json();
                updateButtonState(data.is_favourite);

                // Optional: Show toast notification
                if (typeof showToast === 'function') {
                    showToast(data.message, 'success');
                }
            } else {
                const error = await response.json();
                console.error('Error toggling favourite:', error);
                if (typeof showToast === 'function') {
                    showToast(error.error || 'Failed to toggle favourite', 'error');
                }
            }
        } catch (error) {
            console.error('Error toggling favourite:', error);
            if (typeof showToast === 'function') {
                showToast('Failed to toggle favourite', 'error');
            }
        } finally {
            favouriteBtn.disabled = false;
        }
    }

    // Event listener for button click
    favouriteBtn.addEventListener('click', toggleFavourite);

    // Check initial status on page load
    checkFavouriteStatus();
})();

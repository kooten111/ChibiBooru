/**
 * Favourites Module
 * Handles favourite button state and toggle functionality
 */

(function () {
    'use strict';

    // Expose init function for client-side navigation
    // Expose init function for client-side navigation
    window.initFavourites = function () {
        favouriteBtn = document.getElementById('favouriteBtn');
        if (!favouriteBtn) return;

        iconSpan = favouriteBtn.querySelector('.favourite-icon');
        textSpan = favouriteBtn.querySelector('.favourite-text');

        // Remove existing listener to prevent duplicates if called multiple times
        favouriteBtn.removeEventListener('click', toggleFavourite);
        favouriteBtn.addEventListener('click', toggleFavourite);

        const filepath = favouriteBtn.dataset.filepath;

        checkFavouriteStatus(filepath);
    };

    let favouriteBtn;
    let iconSpan;
    let textSpan;
    // Icons for favourite states
    const ICON_FAVOURITE = '❤️';
    const ICON_NOT_FAVOURITE = '🤍';

    function updateButtonState(isFavourite) {
        // Re-query if null (safety)
        if (!favouriteBtn) favouriteBtn = document.getElementById('favouriteBtn');
        if (!favouriteBtn) return;
        iconSpan = favouriteBtn.querySelector('.favourite-icon');
        textSpan = favouriteBtn.querySelector('.favourite-text');

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

    async function checkFavouriteStatus(filepath) {
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

    async function toggleFavourite(e) {
        // Get the button from the event to ensure we have the right one
        const btn = e.currentTarget;
        const filepath = btn.dataset.filepath;

        // Disable button during request
        btn.disabled = true;

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
            btn.disabled = false;
        }
    }

    // Initialize on load
    window.initFavourites();

})();

// helpers.js - Shared utility functions

/**
 * Escapes HTML special characters to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} HTML-escaped text
 */
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Formats a number with k/M suffix for readability
 * @param {number} count - Number to format
 * @returns {string} Formatted number string
 */
export function formatCount(count) {
    if (count >= 1000000) return (count / 1000000).toFixed(1) + 'M';
    if (count >= 1000) return (count / 1000).toFixed(1) + 'k';
    return count.toString();
}

/**
 * Get icon for tag category
 * @param {string} category - Tag category name
 * @returns {string} Unicode icon for the category
 */
export function getCategoryIcon(category) {
    const icons = {
        character: '👤',
        copyright: '©️',
        artist: '🎨',
        species: '🐾',
        meta: '📋',
        general: '🏷️'
    };
    return icons[category] || '🏷️';
}

/**
 * Get CSS class for tag category
 * @param {string} category - Tag category name
 * @returns {string} CSS class name
 */
export function getCategoryClass(category) {
    return `tag-${category}`;
}

/**
 * Format tag count for display
 * @param {number} count - Tag count
 * @returns {string} Formatted count string
 */
export function formatTagCount(count) {
    return count.toLocaleString();
}

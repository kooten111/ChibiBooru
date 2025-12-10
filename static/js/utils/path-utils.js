// path-utils.js - Path handling utilities

/**
 * Encode image path for URL, preserving forward slashes
 * @param {string} path - Image path to encode
 * @returns {string} Encoded path
 */
export function encodeImagePath(path) {
    return encodeURIComponent(path).replace(/%2F/g, '/');
}

/**
 * Normalize image path by removing 'images/' prefix
 * @param {string} path - Image path to normalize
 * @returns {string} Normalized path
 */
export function normalizeImagePath(path) {
    return path.replace(/^images\//, '');
}

/**
 * Get full image URL from filepath
 * @param {string} filepath - Relative file path
 * @returns {string} Full URL to image
 */
export function getImageUrl(filepath) {
    return `/images/${encodeImagePath(filepath)}`;
}

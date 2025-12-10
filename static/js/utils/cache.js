// cache.js - Cache invalidation utilities

/**
 * Invalidate image-related cache
 * Clears cached image data to force reload
 */
export function invalidateImageCache() {
    // Clear any cached image data
    if (window.imageCache) {
        window.imageCache = {};
    }
    
    // Dispatch custom event for components that cache images
    window.dispatchEvent(new CustomEvent('image-cache-invalidated'));
}

/**
 * Invalidate tag-related cache
 * Clears cached tag data to force reload
 */
export function invalidateTagCache() {
    // Clear any cached tag data
    if (window.tagCache) {
        window.tagCache = {};
    }
    
    // Dispatch custom event for components that cache tags
    window.dispatchEvent(new CustomEvent('tag-cache-invalidated'));
}

/**
 * Invalidate all caches
 * Clears all cached data
 */
export function invalidateAllCaches() {
    invalidateImageCache();
    invalidateTagCache();
    
    // Dispatch global cache clear event
    window.dispatchEvent(new CustomEvent('all-caches-invalidated'));
}

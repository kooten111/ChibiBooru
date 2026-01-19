/**
 * Asynchronously loads FAISS/semantic similarity results and interleaves them
 * with tag-based results to prevent page blocking.
 */

(function() {
    'use strict';

    /**
     * URL-encode a path while preserving forward slashes
     * @param {string} path - Path to encode
     * @returns {string} Encoded path with slashes preserved
     */
    function encodePathForUrl(path) {
        if (!path) return '';
        return path.split('/').map(part => encodeURIComponent(part)).join('/');
    }

    /**
     * Normalize filepath for comparison (ensure consistent format)
     * @param {string} path - Filepath to normalize
     * @returns {string} Normalized filepath
     */
    function normalizePath(path) {
        if (!path) return '';
        // Remove leading/trailing slashes and ensure 'images/' prefix
        path = path.replace(/^\/+|\/+$/g, '');
        if (!path.startsWith('images/')) {
            path = `images/${path}`;
        }
        return path;
    }

    /**
     * Interleave tag and FAISS results, removing duplicates and current image
     * @param {Array} tagResults - Tag-based results
     * @param {Array} faissResults - FAISS/semantic results
     * @param {string} currentPath - Path of the current image to exclude
     * @param {number} limit - Maximum total results
     * @returns {Array} Interleaved results
     */
    function interleaveResults(tagResults, faissResults, currentPath, limit = 40) {
        const seen = new Set();
        const interleaved = [];
        const maxLength = Math.max(tagResults.length, faissResults.length);
        const currentPathNormalized = normalizePath(currentPath);
        
        // Interleave results, alternating between tag and FAISS
        for (let i = 0; i < maxLength && interleaved.length < limit; i++) {
            // Add FAISS result first (if available) to prioritize accurate results
            if (i < faissResults.length) {
                const faiss = faissResults[i];
                const faissPathNormalized = normalizePath(faiss.path);
                // Skip if duplicate or current image
                if (!seen.has(faissPathNormalized) && faissPathNormalized !== currentPathNormalized) {
                    seen.add(faissPathNormalized);
                    interleaved.push(faiss);
                    if (interleaved.length >= limit) break;
                }
            }
            
            // Then add tag result
            if (i < tagResults.length) {
                const tag = tagResults[i];
                const tagPathNormalized = normalizePath(tag.path);
                // Skip if duplicate or current image
                if (!seen.has(tagPathNormalized) && tagPathNormalized !== currentPathNormalized) {
                    seen.add(tagPathNormalized);
                    interleaved.push(tag);
                    if (interleaved.length >= limit) break;
                }
            }
        }
        
        return interleaved;
    }

    /**
     * Create a related image thumbnail element
     * @param {Object} image - Image data with path, thumb, primary_source
     * @returns {HTMLElement} Thumbnail anchor element
     */
    function createRelatedThumb(image) {
        const a = document.createElement('a');
        a.href = `/view/${encodePathForUrl(image.path)}`;
        a.className = 'related-thumb';
        
        const img = document.createElement('img');
        const thumbPath = image.thumb.startsWith('thumbnails/') || image.thumb.startsWith('images/') 
            ? image.thumb 
            : `images/${image.thumb}`;
        img.src = `/static/${encodePathForUrl(thumbPath)}`;
        img.alt = 'Related';
        a.appendChild(img);
        
        // Add source label
        const source = image.primary_source || 'unknown';
        const label = document.createElement('span');
        label.className = 'label similar';
        
        if (source === 'tag') {
            label.classList.add('similar-tag');
            label.textContent = 'Tag';
        } else if (source === 'semantic') {
            label.classList.add('similar-semantic');
            label.textContent = 'FAISS';
        } else if (source === 'visual') {
            label.classList.add('similar-visual');
            label.textContent = 'Visual';
        } else {
            label.textContent = 'Similar';
        }
        
        a.appendChild(label);
        return a;
    }

    /**
     * Update the related images display
     * @param {Array} results - Combined results to display
     */
    function updateRelatedImagesDisplay(results) {
        const container = document.getElementById('related-images-content');
        if (!container) return;
        
        const grid = container.querySelector('.related-grid-vertical');
        if (!grid) return;
        
        // Clear existing content
        grid.innerHTML = '';
        
        // Add all results
        results.forEach(image => {
            const thumb = createRelatedThumb(image);
            grid.appendChild(thumb);
        });
        
        // Update count in header
        const countElements = document.querySelectorAll('.related-images-vertical .text-muted-tiny');
        countElements.forEach(el => {
            el.textContent = `(${results.length} images)`;
        });
    }

    /**
     * Show loading indicator
     */
    function showLoadingIndicator() {
        const container = document.getElementById('related-images-content');
        if (!container) return;
        
        // Check if loading indicator already exists
        let loadingDiv = container.querySelector('.faiss-loading-indicator');
        if (loadingDiv) return;
        
        loadingDiv = document.createElement('div');
        loadingDiv.className = 'faiss-loading-indicator';
        loadingDiv.innerHTML = `
            <div class="faiss-loading-content">
                <div class="faiss-loading-spinner"></div>
                <span class="faiss-loading-text">Loading FAISS results...</span>
            </div>
        `;
        
        const grid = container.querySelector('.related-grid-vertical');
        if (grid && grid.parentNode) {
            grid.parentNode.insertBefore(loadingDiv, grid.nextSibling);
        } else {
            container.appendChild(loadingDiv);
        }
    }

    /**
     * Hide loading indicator
     */
    function hideLoadingIndicator() {
        const container = document.getElementById('related-images-content');
        if (!container) return;
        
        const loadingDiv = container.querySelector('.faiss-loading-indicator');
        if (loadingDiv) {
            loadingDiv.remove();
        }
    }

    /**
     * Load FAISS results asynchronously
     * @param {string} filepath - Path to the current image
     * @param {Array} tagResults - Existing tag-based results
     */
    async function loadFaissResults(filepath, tagResults) {
        // Show loading indicator
        showLoadingIndicator();
        
        try {
            // Clean filepath (remove images/ prefix if present)
            const cleanPath = filepath.startsWith('images/') ? filepath.substring(7) : filepath;
            const encodedPath = encodePathForUrl(cleanPath);
            
            // Fetch FAISS results
            const response = await fetch(`/api/similar-semantic/${encodedPath}?limit=40&exclude_family=true`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            const faissResults = data.similar || [];
            
            // Interleave tag and FAISS results, excluding current image
            const interleaved = interleaveResults(tagResults, faissResults, filepath, 40);
            
            // Update display
            updateRelatedImagesDisplay(interleaved);
            
        } catch (error) {
            console.error('Failed to load FAISS results:', error);
            // Keep tag results, just hide loading indicator
        } finally {
            hideLoadingIndicator();
        }
    }

    /**
     * Initialize related images loader
     */
    function initRelatedImagesLoader() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                initializeLoader();
            });
        } else {
            initializeLoader();
        }
    }

    /**
     * Initialize the loader
     */
    function initializeLoader() {
        const container = document.getElementById('related-images-content');
        if (!container) return;
        
        // Get current filepath from the page
        // Try data-filepath attribute first, then URL
        let filepath = null;
        
        // Try data-filepath on image view container
        const imageViewContainer = document.getElementById('imageViewContainer');
        if (imageViewContainer && imageViewContainer.dataset.filepath) {
            filepath = imageViewContainer.dataset.filepath;
        } else {
            // Fallback: extract from URL
            const pathMatch = window.location.pathname.match(/\/view\/(.+)$/);
            if (pathMatch) {
                filepath = decodeURIComponent(pathMatch[1]);
            }
        }
        
        if (!filepath) {
            console.warn('Could not determine filepath for FAISS loading');
            return;
        }
        
        // Normalize current filepath for comparison
        const currentPathNormalized = normalizePath(filepath);
        
        // Get existing tag results from the DOM, excluding current image
        const existingThumbs = container.querySelectorAll('.related-thumb');
        const tagResults = Array.from(existingThumbs)
            .map(thumb => {
                const link = thumb.getAttribute('href');
                const path = link ? decodeURIComponent(link.replace('/view/', '')) : '';
                const img = thumb.querySelector('img');
                const thumbSrc = img ? img.src.replace(/^.*\/static\//, '') : '';
                const label = thumb.querySelector('.label');
                const source = label && label.classList.contains('similar-tag') ? 'tag' : 'unknown';
                
                return {
                    path: path,
                    thumb: thumbSrc,
                    primary_source: source
                };
            })
            .filter(result => {
                // Filter out current image
                const resultPathNormalized = normalizePath(result.path);
                return resultPathNormalized !== currentPathNormalized;
            });
        
        // Only load FAISS if we have tag results
        if (tagResults.length > 0) {
            loadFaissResults(filepath, tagResults);
        }
    }

    // Initialize on page load
    initRelatedImagesLoader();

})();

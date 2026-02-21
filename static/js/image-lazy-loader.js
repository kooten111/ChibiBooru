/**
 * Lazy loader for image detail page - loads stats, deltas, pools, and similar images
 * asynchronously after the main image starts loading.
 * This improves page navigation time from ~500ms to ~50ms.
 */

(function () {
    'use strict';

    const currentFilepath = window.location.pathname.replace('/view/', '');

    /**
     * URL-encode a path while preserving forward slashes
     */
    function encodePathForUrl(path) {
        if (!path) return '';
        return path.split('/').map(part => encodeURIComponent(part)).join('/');
    }

    /**
     * Load and populate stats in the header
     */
    async function loadStats() {
        try {
            const response = await fetch(`/api/image/${encodePathForUrl(currentFilepath)}/stats`);
            if (!response.ok) return;
            
            const stats = await response.json();
            
            // Update header stats if they exist
            // Stats are typically shown in header.html, which is included in the template
            // This allows the header to update without blocking initial render
            if (window.updateHeaderStats && typeof window.updateHeaderStats === 'function') {
                window.updateHeaderStats(stats);
            }
        } catch (error) {
            console.warn('Failed to load stats:', error);
        }
    }

    /**
     * Load and populate tag deltas in the meta section
     */
    async function loadTagDeltas() {
        try {
            const response = await fetch(`/api/image/${encodePathForUrl(currentFilepath)}/deltas`);
            if (!response.ok) return;
            
            const tagDeltas = await response.json();
            
            // Only render if there are deltas
            if (!tagDeltas || (!tagDeltas.added?.length && !tagDeltas.removed?.length)) {
                return;
            }

            // Find the meta section
            const metaSection = document.querySelector('.tag-category.meta');
            if (!metaSection) return;

            // Create delta content
            let deltaHtml = `
                <div class="tag-category-subtitle mt-10" 
                     style="padding-top: 10px; border-top: 1px solid rgba(255, 165, 0, 0.2);">
                    Manual modifications
                </div>
            `;

            if (tagDeltas.added?.length) {
                tagDeltas.added.forEach(tag_info => {
                    deltaHtml += `
                        <div class="tag-item delta-added">
                            <a href="/?query=${encodeURIComponent(tag_info.name)}" class="link-primary">
                                +${tag_info.name}
                            </a>
                        </div>
                    `;
                });
            }

            if (tagDeltas.removed?.length) {
                tagDeltas.removed.forEach(tag_info => {
                    deltaHtml += `
                        <div class="tag-item delta-removed">
                            <a href="/?query=${encodeURIComponent(tag_info.name)}" class="link-danger">
                                -${tag_info.name}
                            </a>
                        </div>
                    `;
                });
            }

            // Append to meta section
            metaSection.insertAdjacentHTML('beforeend', deltaHtml);

        } catch (error) {
            console.warn('Failed to load tag deltas:', error);
        }
    }

    /**
     * Load and populate image pools
     */
    async function loadPools() {
        try {
            const response = await fetch(`/api/image/${encodePathForUrl(currentFilepath)}/pools`);
            if (!response.ok) return;
            
            const pools = await response.json();
            
            if (!pools || pools.length === 0) return;

            // Find the sidebar-left container
            const sidebarLeft = document.getElementById('sidebarLeft');
            if (!sidebarLeft) return;

            // Create pools section HTML
            const poolsHtml = `
                <div class="section-content" id="pools-content">
                    <div class="pool-management panel">
                        <button class="panel-header mobile-toggle collapsed" data-section="pools-panel-content">
                            <span class="section-icon">📁</span>
                            <span class="section-title">Pools</span>
                            <span class="text-muted-tiny">${pools.length} pool${pools.length !== 1 ? 's' : ''}</span>
                            <span class="section-arrow">▼</span>
                        </button>
                        <div class="panel-collapsible-content" id="pools-panel-content">
                            ${pools.map(pool => `
                                <div class="pool-item">
                                    <a href="/pool/${pool.id}" class="pool-link">
                                        <span class="pool-name">${pool.name}</span>
                                    </a>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;

            // Insert pools after tags section
            const tagsContent = document.getElementById('tags-content');
            if (tagsContent) {
                tagsContent.insertAdjacentHTML('afterend', poolsHtml);
                
                // Re-attach mobile toggle event listeners if needed
                if (window.attachMobileToggleListeners && typeof window.attachMobileToggleListeners === 'function') {
                    window.attachMobileToggleListeners();
                }
            }

        } catch (error) {
            console.warn('Failed to load pools:', error);
        }
    }

    /**
     * Load and populate similar images (both family and related)
     */
    async function loadSimilarImages() {
        try {
            const response = await fetch(`/api/image/${encodePathForUrl(currentFilepath)}/similar`);
            if (!response.ok) return;
            
            const data = await response.json();
            const { parent_child_images = [], similar_images = [] } = data;

            // Update family images data for family badge
            if (parent_child_images.length > 0) {
                let familyDataEl = document.getElementById('familyImagesData');
                if (!familyDataEl) {
                    // Create the element if it doesn't exist
                    familyDataEl = document.createElement('script');
                    familyDataEl.type = 'application/json';
                    familyDataEl.id = 'familyImagesData';
                    document.body.appendChild(familyDataEl);
                }
                familyDataEl.textContent = JSON.stringify(parent_child_images);
                
                // Trigger family badge initialization if it exists
                if (window.initializeFamilyBadge && typeof window.initializeFamilyBadge === 'function') {
                    window.initializeFamilyBadge();
                }
            }

            // Update related images data and populate the grid
            const relatedDataEl = document.getElementById('relatedImagesData');
            if (relatedDataEl) {
                relatedDataEl.textContent = JSON.stringify(similar_images);
            }

            // Update similar images count
            const countEls = [
                document.getElementById('similar-count'),
                document.getElementById('similar-count-desktop')
            ];
            countEls.forEach(el => {
                if (el) {
                    el.textContent = `(${similar_images.length} images)`;
                }
            });

            // Populate the related images grid
            const gridContainer = document.querySelector('.related-grid-vertical');
            if (gridContainer && similar_images.length > 0) {
                // Remove loading spinner
                gridContainer.innerHTML = '';
                
                // Get config for chips
                const config = getSimilarConfig();
                const showChips = config.showChips;

                // Add each similar image
                similar_images.forEach(img => {
                    const thumb = createRelatedThumb(img, showChips);
                    gridContainer.appendChild(thumb);
                });
            } else if (gridContainer && similar_images.length === 0) {
                gridContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">No similar images found</div>';
            }

            // Trigger related images initialization if it exists (for FAISS loading)
            if (window.initializeRelatedImages && typeof window.initializeRelatedImages === 'function') {
                window.initializeRelatedImages();
            }

        } catch (error) {
            console.warn('Failed to load similar images:', error);
            const gridContainer = document.querySelector('.related-grid-vertical');
            if (gridContainer) {
                gridContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">Failed to load similar images</div>';
            }
        }
    }

    /**
     * Get similar config from page
     */
    function getSimilarConfig() {
        const configEl = document.getElementById('similarConfig');
        if (!configEl) {
            return { sources: 'both', showChips: true };
        }
        try {
            return JSON.parse(configEl.textContent);
        } catch (e) {
            return { sources: 'both', showChips: true };
        }
    }

    /**
     * Create a related image thumbnail element
     */
    function createRelatedThumb(image, showChips = true) {
        const a = document.createElement('a');
        a.href = `/view/${encodePathForUrl(image.path)}`;
        a.className = 'related-thumb';

        const img = document.createElement('img');
        const thumbPath = image.thumb;
        if (thumbPath.startsWith('thumbnails/') || thumbPath.startsWith('images/')) {
            img.src = `/static/${encodePathForUrl(thumbPath)}`;
        } else {
            img.src = `/static/images/${encodePathForUrl(thumbPath)}`;
        }
        img.alt = 'Related';
        a.appendChild(img);

        if (showChips) {
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
        }

        return a;
    }

    /**
     * Initialize lazy loading
     */
    function init() {
        // Load all data in parallel after DOM is ready
        // These will complete while the user is viewing the main image
        Promise.all([
            loadStats(),
            loadTagDeltas(),
            loadPools(),
            loadSimilarImages()
        ]).catch(err => {
            console.error('Lazy loading error:', err);
        });
    }

    // Start lazy loading immediately
    // No need to wait for DOMContentLoaded since we're at the bottom of the page
    // and the main image has already started loading
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();

// Global instance for live filter access
let infiniteScrollInstance = null;

class InfiniteScroll {
    constructor() {
        this.gallery = document.querySelector('.gallery');
        this.loading = false;
        this.currentPage = 1;
        this.displayedPage = 1;
        this.hasMore = true;
        this.query = new URLSearchParams(window.location.search).get('query') || '';
        const bodyPerPage = parseInt(document.body.dataset.perPage, 10);
        this.perPage = parseInt(new URLSearchParams(window.location.search).get('per_page'), 10)
            || (Number.isFinite(bodyPerPage) && bodyPerPage > 0 ? bodyPerPage : 50);

        // Cache for prefetched pages
        this.pageCache = new Map();
        this.prefetchQueue = [];
        this.prefetchInProgress = false;

        this.PREFETCH_AHEAD = 3; // Number of pages to prefetch ahead

        // Determine scroll container - use .gallery-content if in gallery-page layout
        this.scrollContainer = document.querySelector('.gallery-content') || window;
        this.useWindowScroll = this.scrollContainer === window;

        // Live filter debounce
        this.liveFilterTimer = null;
        this.liveFilterDelay = 300; // ms

        this.init();
        this.initLiveFilter();
    }

    init() {
        this.scrollContainer.addEventListener('scroll', () => this.handleScroll());

        // Start prefetching immediately
        setTimeout(() => {
            this.startPrefetching();
            this.checkIfNeedMore();
        }, 500);
    }

    initLiveFilter() {
        // Listen for chip changes from autocomplete
        const chipWrapper = document.getElementById('chipInputWrapper');
        if (chipWrapper) {
            chipWrapper.addEventListener('chipsChanged', (e) => {
                this.handleLiveFilter(e.detail.query);
            });
        }
    }

    handleLiveFilter(newQuery) {
        // Skip live filtering for special queries that are server-side only
        // These include similarity searches which require special processing
        if (newQuery && (
            newQuery.startsWith('similar:') ||
            newQuery.includes(' similar:')
        )) {
            return;
        }

        // Debounce to avoid too many requests
        clearTimeout(this.liveFilterTimer);
        this.liveFilterTimer = setTimeout(() => {
            this.resetWithQuery(newQuery);
        }, this.liveFilterDelay);
    }

    async resetWithQuery(newQuery) {
        // Reset state
        this.query = newQuery;
        this.currentPage = 1;
        this.displayedPage = 1;
        this.hasMore = true;
        this.pageCache.clear();
        this.prefetchQueue = [];

        // Update URL without page reload
        const url = new URL(window.location);
        if (newQuery) {
            url.searchParams.set('query', newQuery);
        } else {
            url.searchParams.delete('query');
        }
        url.searchParams.set('per_page', this.perPage);
        url.searchParams.delete('page'); // Reset to page 1
        history.pushState({ query: newQuery }, '', url);

        // Show loading state
        this.gallery.classList.add('loading');
        this.showGalleryLoader();

        try {
            // Fetch first page
            const data = await this.fetchPage(1);

            // Clear gallery and add new images
            this.gallery.innerHTML = '';
            if (data.images && data.images.length > 0) {
                this.appendImages(data.images);
            } else {
                this.showEmptyState(newQuery);
            }

            this.hasMore = data.has_more;
            this.displayedPage = 1;

            // Update results info if it exists
            this.updateResultsInfo(data.total_results);

            // Start prefetching for next pages
            this.startPrefetching();

            // Check if we need more images to fill the viewport
            setTimeout(() => this.checkIfNeedMore(), 100);
        } catch (error) {
            console.error('Live filter error:', error);
            this.showError();
        } finally {
            this.gallery.classList.remove('loading');
            this.hideGalleryLoader();
        }
    }

    showGalleryLoader() {
        // Add skeleton placeholders
        if (this.gallery.children.length === 0) {
            const loader = document.createElement('div');
            loader.id = 'galleryLoader';
            loader.className = 'gallery-loader';
            loader.innerHTML = `
                <div class="loader-content">
                    <div class="loader-spinner"></div>
                    <span>Searching...</span>
                </div>
            `;
            this.gallery.parentElement.insertBefore(loader, this.gallery);
        }
    }

    hideGalleryLoader() {
        const loader = document.getElementById('galleryLoader');
        if (loader) loader.remove();
    }

    updateResultsInfo(total) {
        const resultsInfo = document.querySelector('.results-info');
        if (resultsInfo) {
            if (total > 0) {
                resultsInfo.textContent = `Found ${total} result${total !== 1 ? 's' : ''}`;
                resultsInfo.style.display = 'block';
            } else {
                resultsInfo.style.display = 'none';
            }
        }
    }

    showEmptyState(query) {
        const emptyDiv = document.createElement('div');
        emptyDiv.className = 'empty-results';
        emptyDiv.innerHTML = `
            <div class="empty-icon">🔍</div>
            <div class="empty-text">No images found${query ? ` for "${query}"` : ''}</div>
            <div class="empty-hint">Try different search terms</div>
        `;
        this.gallery.appendChild(emptyDiv);
    }

    handleScroll() {
        if (!this.hasMore) return;

        let scrollPosition, totalHeight;

        if (this.useWindowScroll) {
            scrollPosition = window.innerHeight + window.scrollY;
            totalHeight = document.documentElement.scrollHeight;
        } else {
            // For container-based scrolling
            scrollPosition = this.scrollContainer.scrollTop + this.scrollContainer.clientHeight;
            totalHeight = this.scrollContainer.scrollHeight;
        }

        // Display when 80% scrolled
        if (scrollPosition >= totalHeight * 0.8) {
            this.displayNextPage();
        }
    }

    checkIfNeedMore() {
        // If content doesn't fill the scroll container, display more
        let needsMore = false;

        if (this.useWindowScroll) {
            needsMore = document.documentElement.scrollHeight <= window.innerHeight;
        } else {
            needsMore = this.scrollContainer.scrollHeight <= this.scrollContainer.clientHeight;
        }

        if (needsMore && this.hasMore) {
            this.displayNextPage();
        }
    }

    startPrefetching() {
        // Queue up the next few pages for prefetching
        for (let i = 1; i <= this.PREFETCH_AHEAD; i++) {
            const pageToFetch = this.currentPage + i;
            if (!this.pageCache.has(pageToFetch)) {
                this.prefetchQueue.push(pageToFetch);
            }
        }

        this.processPrefetchQueue();
    }

    async processPrefetchQueue() {
        if (this.prefetchInProgress || this.prefetchQueue.length === 0) return;

        this.prefetchInProgress = true;

        while (this.prefetchQueue.length > 0) {
            const pageNum = this.prefetchQueue.shift();

            // Skip if already cached
            if (this.pageCache.has(pageNum)) continue;

            try {
                const data = await this.fetchPage(pageNum);
                this.pageCache.set(pageNum, data);

                const nextPage = pageNum + 1;
                if (data.has_more &&
                    nextPage <= this.displayedPage + this.PREFETCH_AHEAD &&
                    !this.pageCache.has(nextPage) &&
                    !this.prefetchQueue.includes(nextPage)) {
                    this.prefetchQueue.push(nextPage);
                }

            } catch (error) {
                console.error(`Error prefetching page ${pageNum}:`, error);
            }
        }

        this.prefetchInProgress = false;
    }

    async fetchPage(pageNum) {
        const params = new URLSearchParams({
            page: pageNum,
            per_page: this.perPage
        });

        if (this.query) {
            params.append('query', this.query);
        }

        const response = await fetch(`/api/images?${params}`);
        if (!response.ok) throw new Error('Network error');

        return await response.json();
    }

    async displayNextPage() {
        if (this.loading || !this.hasMore) return;

        const nextPage = this.displayedPage + 1;

        if (this.pageCache.has(nextPage)) {
            this.loading = true;
            const data = this.pageCache.get(nextPage);
            this.appendImages(data.images);
            this.displayedPage = nextPage;
            this.hasMore = data.has_more;
            this.loading = false;

            setTimeout(() => this.checkIfNeedMore(), 100);
            this.startPrefetching();
        } else {
            // Not cached yet, fetch it now with loading indicator
            this.loading = true;
            this.showLoader();

            try {
                const data = await this.fetchPage(nextPage);
                this.appendImages(data.images);
                this.displayedPage = nextPage;
                this.hasMore = data.has_more;

                // Check if we need to display more immediately
                setTimeout(() => this.checkIfNeedMore(), 100);

                // Continue prefetching
                this.startPrefetching();

            } catch (error) {
                console.error('Error loading page:', error);
                this.showError();
            } finally {
                this.loading = false;
                this.hideLoader();
            }
        }
    }

    appendImages(images) {
        const fragment = document.createDocumentFragment();

        images.forEach((img, index) => {
            const thumbnail = document.createElement('div');
            thumbnail.className = 'thumbnail skeleton';
            thumbnail.style.animationDelay = `${index * 0.02}s`;

            // URL-encode the path to handle non-ASCII characters (Japanese, etc.)
            const encodedPath = img.path.split('/').map(part => encodeURIComponent(part)).join('/');
            const encodedThumb = img.thumb.split('/').map(part => encodeURIComponent(part)).join('/');

            thumbnail.innerHTML = `
                <a href="/view/${encodedPath}">
                    <img src="/static/${encodedThumb}" alt="Image" loading="lazy" onload="this.closest('.thumbnail').classList.add('has-image')">
                </a>
            `;

            fragment.appendChild(thumbnail);

            // Setup masonry for new image
            const imgElement = thumbnail.querySelector('img');
            if (imgElement.complete) {
                thumbnail.classList.add('has-image');
                this.setupMasonryForImage(imgElement, thumbnail);
            } else {
                imgElement.addEventListener('load', () => {
                    this.setupMasonryForImage(imgElement, thumbnail);
                });
            }
        });

        this.gallery.appendChild(fragment);
    }

    setupMasonryForImage(img, container) {
        if (!img.naturalWidth || !img.naturalHeight) return;

        const aspectRatio = img.naturalWidth / img.naturalHeight;
        const rowHeight = 12;

        let colSpan = 1;
        if (aspectRatio > 2) {
            colSpan = 3;
            container.classList.add('ultra-wide');
        } else if (aspectRatio > 1.3) {
            colSpan = 2;
            container.classList.add('wide');
        } else if (aspectRatio < 0.6) {
            colSpan = 1;
            container.classList.add('ultra-tall');
        } else if (aspectRatio < 0.8) {
            colSpan = 1;
            container.classList.add('tall');
        } else {
            colSpan = 1;
            container.classList.add('square');
        }

        const containerWidth = container.offsetWidth || 300;
        const calculatedHeight = containerWidth / aspectRatio;
        const rowSpan = Math.round(calculatedHeight / rowHeight);

        container.style.gridRowEnd = `span ${Math.max(rowSpan, 10)}`;
        container.style.gridColumnEnd = `span ${colSpan}`;
    }

    showLoader() {
        if (document.getElementById('infiniteLoader')) return;

        const loader = document.createElement('div');
        loader.id = 'infiniteLoader';
        loader.style.cssText = `
            text-align: center;
            padding: 40px;
            color: #87ceeb;
            font-size: 1.1em;
            font-weight: 600;
        `;
        loader.innerHTML = `
            <div style="display: inline-block; animation: pulse 1.5s ease-in-out infinite;">
                Loading more images...
            </div>
        `;

        this.gallery.parentElement.appendChild(loader);
    }

    hideLoader() {
        const loader = document.getElementById('infiniteLoader');
        if (loader) loader.remove();
    }

    showError() {
        const error = document.createElement('div');
        error.style.cssText = `
            text-align: center;
            padding: 40px;
            color: #ff6b6b;
            font-size: 1.1em;
            font-weight: 600;
        `;
        error.textContent = 'Error loading more images. Please refresh the page.';

        this.gallery.parentElement.appendChild(error);

        setTimeout(() => error.remove(), 5000);
    }
}

// Add pulse animation and live filter styles
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    
    .gallery.loading {
        opacity: 0.6;
        pointer-events: none;
    }
    
    .gallery-loader {
        display: flex;
        justify-content: center;
        padding: 40px;
        color: var(--accent-primary, #87ceeb);
    }
    
    .gallery-loader .loader-content {
        display: flex;
        align-items: center;
        gap: 12px;
        font-weight: 600;
    }
    
    .gallery-loader .loader-spinner {
        width: 24px;
        height: 24px;
        border: 3px solid currentColor;
        border-top-color: transparent;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .empty-results {
        grid-column: 1 / -1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 80px 20px;
        color: var(--text-secondary, #888);
        text-align: center;
    }
    
    .empty-results .empty-icon {
        font-size: 4em;
        margin-bottom: 20px;
        opacity: 0.5;
    }
    
    .empty-results .empty-text {
        font-size: 1.3em;
        font-weight: 600;
        margin-bottom: 10px;
        color: var(--text-primary, #fff);
    }
    
    .empty-results .empty-hint {
        font-size: 0.95em;
        opacity: 0.7;
    }
`;
document.head.appendChild(style);

// Initialize infinite scroll when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on gallery pages (not image detail pages)
    if (document.querySelector('.gallery')) {
        infiniteScrollInstance = new InfiniteScroll();
    }
});
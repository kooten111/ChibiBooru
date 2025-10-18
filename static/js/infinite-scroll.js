class InfiniteScroll {
    constructor() {
        this.gallery = document.querySelector('.gallery');
        this.loading = false;
        this.currentPage = 1;
        this.displayedPage = 1;
        this.hasMore = true;
        this.query = new URLSearchParams(window.location.search).get('query') || '';
        this.perPage = parseInt(new URLSearchParams(window.location.search).get('per_page')) || 50;
        
        // Cache for prefetched pages
        this.pageCache = new Map();
        this.prefetchQueue = [];
        this.prefetchInProgress = false;
        
        this.PREFETCH_AHEAD = 3; // Number of pages to prefetch ahead
        
        this.init();
    }
    
    init() {
        window.addEventListener('scroll', () => this.handleScroll());
        
        // Start prefetching immediately
        setTimeout(() => {
            this.startPrefetching();
            this.checkIfNeedMore();
        }, 500);
    }
    
    handleScroll() {
        if (!this.hasMore) return;
        
        const scrollPosition = window.innerHeight + window.scrollY;
        const documentHeight = document.documentElement.scrollHeight;
        
        // Display when 80% scrolled
        if (scrollPosition >= documentHeight * 0.8) {
            this.displayNextPage();
        }
    }
    
    checkIfNeedMore() {
        // If page isn't tall enough to scroll, display more
        if (document.documentElement.scrollHeight <= window.innerHeight && this.hasMore) {
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
                
                // Update hasMore based on latest fetch
                if (!data.has_more) {
                    this.hasMore = false;
                }
                
                // Queue next page if we should keep prefetching
                const nextPage = pageNum + 1;
                if (data.has_more && 
                    nextPage <= this.displayedPage + this.PREFETCH_AHEAD && 
                    !this.pageCache.has(nextPage) &&
                    !this.prefetchQueue.includes(nextPage)) {
                    this.prefetchQueue.push(nextPage);
                }
                
            } catch (error) {
                console.error(`Error prefetching page ${pageNum}:`, error);
                // Don't stop prefetching on error, just skip this page
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
        
        // Check if page is already cached
        if (this.pageCache.has(nextPage)) {
            this.loading = true;
            const data = this.pageCache.get(nextPage);
            this.appendImages(data.images);
            this.displayedPage = nextPage;
            this.loading = false;
            
            // Check if we need to display more immediately
            setTimeout(() => this.checkIfNeedMore(), 100);
            
            // Continue prefetching
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
            thumbnail.className = 'thumbnail';
            thumbnail.style.animationDelay = `${index * 0.02}s`;
            
            thumbnail.innerHTML = `
                <a href="/image/${img.path}">
                    <img src="/static/${img.thumb}" alt="Image" loading="lazy">
                </a>
            `;
            
            fragment.appendChild(thumbnail);
            
            // Setup masonry for new image
            const imgElement = thumbnail.querySelector('img');
            if (imgElement.complete) {
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

// Add pulse animation
const style = document.createElement('style');
style.textContent = `
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
`;
document.head.appendChild(style);

// Initialize infinite scroll when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize on gallery pages (not image detail pages)
    if (document.querySelector('.gallery')) {
        new InfiniteScroll();
    }
});
// static/js/tags.js
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('tagSearchInput');
    const tagsContainer = document.getElementById('tagsListContainer');
    const categoryButtons = document.querySelectorAll('.category-filter-btn');
    const loadingIndicator = document.getElementById('loadingIndicator');

    // Configuration
    const INITIAL_BATCH_SIZE = 150;
    const LOAD_MORE_BATCH_SIZE = 100;
    const PRELOAD_BATCH_SIZE = 100; // Preload next batch in background

    let activeCategory = 'all';
    let currentOffset = 0;
    let totalTags = 0;
    let hasMore = true;
    let isLoading = false;
    let currentSearch = '';
    let preloadedBatch = null; // Cache for preloaded tags

    if (!searchInput) return;

    // Get URL parameters for initial category
    const urlParams = new URLSearchParams(window.location.search);
    const urlCategory = urlParams.get('category');
    if (urlCategory) {
        activeCategory = urlCategory;
        updateCategoryButtons();
    }

    // Create sentinel element for infinite scroll
    const sentinel = document.createElement('div');
    sentinel.className = 'scroll-sentinel';
    sentinel.style.height = '1px';
    tagsContainer.appendChild(sentinel);

    // Intersection Observer for lazy loading
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !isLoading && hasMore) {
                loadMoreTags();
            }
        });
    }, {
        rootMargin: '400px' // Start loading well before reaching the bottom
    });

    observer.observe(sentinel);

    // Fetch tags from API
    async function fetchTags(offset, limit, search = '', category = 'all') {
        const params = new URLSearchParams({
            offset: offset.toString(),
            limit: limit.toString(),
            search: search,
            category: category
        });

        const response = await fetch(`/api/tags/fetch?${params}`);
        if (!response.ok) {
            throw new Error('Failed to fetch tags');
        }

        return await response.json();
    }

    // Preload next batch in background
    async function preloadNextBatch() {
        if (!hasMore || preloadedBatch) return;

        try {
            const nextOffset = currentOffset;
            preloadedBatch = await fetchTags(
                nextOffset,
                PRELOAD_BATCH_SIZE,
                currentSearch,
                activeCategory
            );
        } catch (error) {
            console.error('Preload failed:', error);
            preloadedBatch = null;
        }
    }

    // Render tags in the container
    function renderTags(tags) {
        const fragment = document.createDocumentFragment();

        tags.forEach(tag => {
            const tagElement = document.createElement('a');
            tagElement.href = `/?query=${encodeURIComponent(tag.name)}`;
            tagElement.className = 'tag-browser-item';
            tagElement.dataset.tagName = tag.name;

            const nameSpan = document.createElement('span');
            nameSpan.className = 'tag-browser-name';
            nameSpan.textContent = tag.name;

            const categorySpan = document.createElement('span');
            categorySpan.className = `tag-browser-category ${tag.category}`;
            categorySpan.textContent = tag.category;

            const countSpan = document.createElement('span');
            countSpan.className = 'tag-browser-count';
            countSpan.textContent = tag.count;

            tagElement.appendChild(nameSpan);
            tagElement.appendChild(categorySpan);
            tagElement.appendChild(countSpan);

            fragment.appendChild(tagElement);
        });

        tagsContainer.insertBefore(fragment, sentinel);
    }

    // Load more tags (checks preloaded batch first)
    async function loadMoreTags() {
        if (isLoading || !hasMore) return;

        isLoading = true;
        loadingIndicator.style.display = 'block';

        try {
            let data;

            // Use preloaded batch if available
            if (preloadedBatch && preloadedBatch.offset === currentOffset) {
                data = preloadedBatch;
                preloadedBatch = null; // Clear cache
            } else {
                // Fetch fresh data
                const batchSize = currentOffset === 0 ? INITIAL_BATCH_SIZE : LOAD_MORE_BATCH_SIZE;
                data = await fetchTags(currentOffset, batchSize, currentSearch, activeCategory);
            }

            renderTags(data.tags);
            currentOffset += data.tags.length;
            totalTags = data.total;
            hasMore = data.hasMore;

            updateVisibleCount();

            // Preload next batch in background
            if (hasMore) {
                preloadNextBatch();
            }

            // Disconnect observer if no more tags
            if (!hasMore) {
                observer.disconnect();
            }

        } catch (error) {
            console.error('Failed to load tags:', error);
            loadingIndicator.textContent = 'Failed to load tags. Please refresh the page.';
        } finally {
            isLoading = false;
            loadingIndicator.style.display = 'none';
        }
    }

    // Reset and reload tags
    function resetAndReload() {
        // Clear container (keep sentinel)
        while (tagsContainer.firstChild && tagsContainer.firstChild !== sentinel) {
            tagsContainer.removeChild(tagsContainer.firstChild);
        }

        currentOffset = 0;
        hasMore = true;
        preloadedBatch = null;

        // Reconnect observer
        observer.disconnect();
        observer.observe(sentinel);

        // Load initial batch
        loadMoreTags();
    }

    // Update the visible tag count display
    function updateVisibleCount() {
        const countDisplay = document.getElementById('visibleTagCount');
        if (countDisplay) {
            const categoryText = activeCategory === 'all' ? '' : ` ${activeCategory}`;
            if (hasMore) {
                countDisplay.textContent = `Showing ${currentOffset} of ${totalTags}${categoryText} tags (scroll for more)`;
            } else {
                countDisplay.textContent = `Showing ${currentOffset}${categoryText} tags`;
            }
        }
    }

    // Update which category button is active
    function updateCategoryButtons() {
        categoryButtons.forEach(btn => {
            if (btn.dataset.category === activeCategory) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    // Set category filter
    function setCategory(category) {
        activeCategory = category;
        updateCategoryButtons();
        resetAndReload();

        // Update URL parameter
        const url = new URL(window.location);
        if (category === 'all') {
            url.searchParams.delete('category');
        } else {
            url.searchParams.set('category', category);
        }
        window.history.pushState({}, '', url);
    }

    // Handle search input
    function handleSearch() {
        currentSearch = searchInput.value.toLowerCase().trim();
        resetAndReload();
    }

    // Category button click handlers
    categoryButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            setCategory(btn.dataset.category);
        });
    });

    // Tag category badge click handlers (for clicking badges in tag items)
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('tag-browser-category')) {
            e.preventDefault();
            e.stopPropagation();
            const category = e.target.textContent.toLowerCase();
            setCategory(category);
        }
    });

    // Search input handler with debouncing
    let searchTimeout;
    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(handleSearch, 300); // 300ms debounce
    });

    // Initial load
    loadMoreTags();
});

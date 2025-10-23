// static/js/tags.js
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('tagSearchInput');
    const tagsContainer = document.getElementById('tagsListContainer');
    const categoryButtons = document.querySelectorAll('.category-filter-btn');

    // Lazy loading configuration
    const INITIAL_BATCH_SIZE = 100;
    const LOAD_MORE_BATCH_SIZE = 50;

    let allTags = Array.from(tagsContainer.getElementsByClassName('tag-browser-item'));
    let hiddenTags = [];
    let loadedCount = 0;
    let activeCategory = 'all';
    let isLoading = false;

    if (!searchInput) return;

    // Get URL parameters for initial category
    const urlParams = new URLSearchParams(window.location.search);
    const urlCategory = urlParams.get('category');
    if (urlCategory) {
        activeCategory = urlCategory;
        updateCategoryButtons();
    }

    // Initially hide all tags and store them
    hiddenTags = allTags.slice();
    allTags.forEach(tag => {
        tag.style.display = 'none';
        tag.dataset.loaded = 'false';
    });

    // Load initial batch of tags
    loadMoreTags(INITIAL_BATCH_SIZE);

    // Create a sentinel element for infinite scroll
    const sentinel = document.createElement('div');
    sentinel.className = 'scroll-sentinel';
    sentinel.style.height = '1px';
    tagsContainer.appendChild(sentinel);

    // Intersection Observer for lazy loading
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting && !isLoading) {
                loadMoreTags(LOAD_MORE_BATCH_SIZE);
            }
        });
    }, {
        rootMargin: '200px' // Start loading before reaching the bottom
    });

    observer.observe(sentinel);

    // Load more tags that match current filters
    function loadMoreTags(batchSize) {
        if (isLoading) return;

        isLoading = true;
        const query = searchInput.value.toLowerCase().trim();
        let loadedInBatch = 0;

        // Find tags that should be visible but aren't loaded yet
        for (let i = 0; i < allTags.length && loadedInBatch < batchSize; i++) {
            const tagElement = allTags[i];

            if (tagElement.dataset.loaded === 'true') continue;

            const tagName = tagElement.dataset.tagName.toLowerCase();
            const tagCategory = tagElement.querySelector('.tag-browser-category').textContent.toLowerCase();

            const matchesSearch = tagName.includes(query);
            const matchesCategory = activeCategory === 'all' || tagCategory === activeCategory;

            if (matchesSearch && matchesCategory) {
                tagElement.style.display = 'flex';
                tagElement.dataset.loaded = 'true';
                loadedInBatch++;
                loadedCount++;
            }
        }

        isLoading = false;
        updateVisibleCount();

        // If we loaded fewer tags than requested, we've reached the end
        if (loadedInBatch < batchSize) {
            observer.disconnect();
        }
    }

    // Reset lazy loading when filters change
    function resetLazyLoading() {
        // Mark all tags as not loaded
        allTags.forEach(tag => {
            tag.style.display = 'none';
            tag.dataset.loaded = 'false';
        });

        loadedCount = 0;

        // Reconnect observer
        observer.disconnect();
        observer.observe(sentinel);

        // Load initial batch with new filters
        loadMoreTags(INITIAL_BATCH_SIZE);
    }

    // Filter tags based on current search query and active category
    function filterTags() {
        resetLazyLoading();
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

    // Update the visible tag count display
    function updateVisibleCount() {
        const visibleTags = allTags.filter(tag => tag.dataset.loaded === 'true');
        const query = searchInput.value.toLowerCase().trim();

        // Count total tags that match current filters
        let totalMatching = 0;
        allTags.forEach(tagElement => {
            const tagName = tagElement.dataset.tagName.toLowerCase();
            const tagCategory = tagElement.querySelector('.tag-browser-category').textContent.toLowerCase();

            const matchesSearch = tagName.includes(query);
            const matchesCategory = activeCategory === 'all' || tagCategory === activeCategory;

            if (matchesSearch && matchesCategory) {
                totalMatching++;
            }
        });

        const countDisplay = document.getElementById('visibleTagCount');
        if (countDisplay) {
            const categoryText = activeCategory === 'all' ? '' : ` ${activeCategory}`;
            if (visibleTags.length < totalMatching) {
                countDisplay.textContent = `Showing ${visibleTags.length} of ${totalMatching}${categoryText} tags (scroll for more)`;
            } else {
                countDisplay.textContent = `Showing ${visibleTags.length}${categoryText} tags`;
            }
        }
    }

    // Set category filter
    function setCategory(category) {
        activeCategory = category;
        updateCategoryButtons();
        filterTags();

        // Update URL parameter
        const url = new URL(window.location);
        if (category === 'all') {
            url.searchParams.delete('category');
        } else {
            url.searchParams.set('category', category);
        }
        window.history.pushState({}, '', url);
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

    // Search input handler
    searchInput.addEventListener('input', filterTags);

    // Initial filter application
    filterTags();
});
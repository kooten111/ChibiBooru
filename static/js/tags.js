// static/js/tags.js
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('tagSearchInput');
    const tagsContainer = document.getElementById('tagsListContainer');
    const allTags = Array.from(tagsContainer.getElementsByClassName('tag-browser-item'));
    const categoryButtons = document.querySelectorAll('.category-filter-btn');

    let activeCategory = 'all';

    if (!searchInput) return;

    // Get URL parameters for initial category
    const urlParams = new URLSearchParams(window.location.search);
    const urlCategory = urlParams.get('category');
    if (urlCategory) {
        activeCategory = urlCategory;
        updateCategoryButtons();
    }

    // Filter tags based on current search query and active category
    function filterTags() {
        const query = searchInput.value.toLowerCase().trim();

        allTags.forEach(tagElement => {
            const tagName = tagElement.dataset.tagName.toLowerCase();
            const tagCategory = tagElement.querySelector('.tag-browser-category').textContent.toLowerCase();

            const matchesSearch = tagName.includes(query);
            const matchesCategory = activeCategory === 'all' || tagCategory === activeCategory;

            if (matchesSearch && matchesCategory) {
                tagElement.style.display = 'flex';
            } else {
                tagElement.style.display = 'none';
            }
        });

        updateVisibleCount();
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
        const visibleTags = allTags.filter(tag => tag.style.display !== 'none');
        const countDisplay = document.getElementById('visibleTagCount');
        if (countDisplay) {
            const categoryText = activeCategory === 'all' ? '' : ` ${activeCategory}`;
            countDisplay.textContent = `Showing ${visibleTags.length}${categoryText} tags`;
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
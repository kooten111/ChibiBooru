// static/js/tags.js
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('tagSearchInput');
    const tagsContainer = document.getElementById('tagsListContainer');
    const allTags = Array.from(tagsContainer.getElementsByClassName('tag-browser-item'));

    if (!searchInput) return;

    searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().trim();
        
        allTags.forEach(tagElement => {
            const tagName = tagElement.dataset.tagName.toLowerCase();
            if (tagName.includes(query)) {
                tagElement.style.display = 'flex';
            } else {
                tagElement.style.display = 'none';
            }
        });
    });
});
document.addEventListener('DOMContentLoaded', function() {
    const imageView = document.querySelector('.image-view');
    const body = document.body;

    if (imageView && body.classList.contains('image-page')) {
        imageView.addEventListener('click', function(event) {
            if (event.target.tagName === 'IMG') {
                body.classList.toggle('ui-hidden');
            }
        });
    }
});
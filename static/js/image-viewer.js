document.addEventListener('DOMContentLoaded', function() {
    const container = document.querySelector('.container');
    const imageView = document.querySelector('.image-view');

    if (container && imageView) {
        // When the image area is clicked...
        imageView.addEventListener('click', function(event) {
            // ...and the click is on the image itself...
            if (event.target.tagName === 'IMG') {
                // ...toggle the fullscreen class on the whole container.
                container.classList.toggle('image-fullscreen');
            }
        });
    }
});
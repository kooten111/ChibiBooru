// Preload related images for instant navigation
document.addEventListener('DOMContentLoaded', () => {
    // Get all related image links
    const relatedLinks = document.querySelectorAll('.related-thumb');
    
    relatedLinks.forEach(link => {
        const img = link.querySelector('img');
        if (!img) return;
        
        // Extract the image path from the link href
        const href = link.getAttribute('href');
        if (!href) return;
        
        // Extract filepath from URL (assumes format: /image/images/path/to/image.jpg)
        const match = href.match(/\/image\/(images\/.+)$/);
        if (!match) return;
        
        const imagePath = match[1];
        
        // Preload the full-size image
        const preloadLink = document.createElement('link');
        preloadLink.rel = 'prefetch';
        preloadLink.href = `/static/${imagePath}`;
        preloadLink.as = 'image';
        document.head.appendChild(preloadLink);
    });
    
    // Also preload thumbnails on hover for smoother experience
    relatedLinks.forEach(link => {
        link.addEventListener('mouseenter', function() {
            const href = this.getAttribute('href');
            if (!href) return;
            
            // Prefetch the HTML page as well for instant navigation
            const pagePrefetch = document.createElement('link');
            pagePrefetch.rel = 'prefetch';
            pagePrefetch.href = href;
            pagePrefetch.as = 'document';
            document.head.appendChild(pagePrefetch);
        }, { once: true }); // Only preload once per link
    });
    
    console.log(`Preloading ${relatedLinks.length} related images`);
});
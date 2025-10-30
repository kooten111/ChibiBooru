class ImageCarousel {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) return;
        
        this.track = this.container.querySelector('.carousel-track');
        this.prevBtn = this.container.querySelector('.carousel-nav.prev');
        this.nextBtn = this.container.querySelector('.carousel-nav.next');
        
        this.isDown = false;
        this.startX;
        this.scrollLeft;
        
        this.init();
    }
    
    init() {
        if (!this.track) return;
        
        // Navigation buttons
        if (this.prevBtn) {
            this.prevBtn.addEventListener('click', () => this.scroll(-1));
        }
        
        if (this.nextBtn) {
            this.nextBtn.addEventListener('click', () => this.scroll(1));
        }
        
        // Update button states on scroll
        this.track.addEventListener('scroll', () => this.updateButtons());
        
        // Drag to scroll events
        this.track.addEventListener('mousedown', (e) => this.handleMouseDown(e));
        this.track.addEventListener('mouseleave', () => this.handleMouseLeave());
        this.track.addEventListener('mouseup', () => this.handleMouseUp());
        this.track.addEventListener('mousemove', (e) => this.handleMouseMove(e));

        this.track.querySelectorAll('img').forEach(img => {
            img.addEventListener('dragstart', (e) => e.preventDefault());
        });

        this.updateButtons();

        document.addEventListener('keydown', (e) => this.handleKeyboard(e));
    }
    
    handleMouseDown(e) {
        this.isDown = true;
        this.track.classList.add('active');
        this.startX = e.pageX - this.track.offsetLeft;
        this.scrollLeft = this.track.scrollLeft;
        e.preventDefault(); 
    }

    handleMouseLeave() {
        this.isDown = false;
        this.track.classList.remove('active');
    }

    handleMouseUp() {
        this.isDown = false;
        this.track.classList.remove('active');
    }

    handleMouseMove(e) {
        if (!this.isDown) return;
        e.preventDefault();
        const x = e.pageX - this.track.offsetLeft;
        const walk = (x - this.startX) * 2;
        this.track.scrollLeft = this.scrollLeft - walk;
    }

    scroll(direction) {
        const scrollAmount = this.track.clientWidth * 0.8;
        this.track.scrollBy({
            left: direction * scrollAmount,
            behavior: 'smooth'
        });
    }
    
    updateButtons() {
        if (!this.track) return;
        
        const isAtStart = this.track.scrollLeft <= 0;
        const isAtEnd = this.track.scrollLeft + this.track.clientWidth >= this.track.scrollWidth - 1;
        
        if (this.prevBtn) {
            this.prevBtn.classList.toggle('disabled', isAtStart);
        }
        
        if (this.nextBtn) {
            this.nextBtn.classList.toggle('disabled', isAtEnd);
        }
    }
    
    handleKeyboard(e) {
        const rect = this.container.getBoundingClientRect();
        const isVisible = rect.top < window.innerHeight && rect.bottom > 0;
        
        if (!isVisible) return;
        
        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            this.scroll(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            this.scroll(1);
        }
    }
}

// Initialize carousel when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const carousel = new ImageCarousel('relatedCarousel');
    
    // Preload carousel images on hover
    const carouselItems = document.querySelectorAll('.carousel-item');
    carouselItems.forEach(item => {
        item.addEventListener('mouseenter', function() {
            const link = this.querySelector('a');
            if (!link) return;
            
            const href = link.getAttribute('href');
            if (!href) return;
            
            const prefetch = document.createElement('link');
            prefetch.rel = 'prefetch';
            prefetch.href = href;
            prefetch.as = 'document';
            document.head.appendChild(prefetch);
        }, { once: true });
    });
});
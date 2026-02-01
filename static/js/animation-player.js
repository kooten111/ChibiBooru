/**
 * Animation Player Component
 * Provides play/pause/seek controls for GIFs and zip-based animations
 */

class AnimationPlayer {
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            type: options.type || 'gif',      // 'gif', 'zip', 'webp'
            fps: options.fps || 24,
            autoplay: options.autoplay !== false,
            loop: options.loop !== false,
            md5: options.md5 || null,
            filepath: options.filepath || null,
            ...options
        };

        this.frames = [];
        this.currentFrame = 0;
        this.playing = false;
        this.fps = this.options.fps;
        this.animationInterval = null;
        this.loaded = false;
        this.canvas = null;
        this.ctx = null;
        this.frameImages = [];

        this.init();
    }

    async init() {
        // Create player structure
        this.createPlayerUI();

        // Load frames based on type
        if (this.options.type === 'zip') {
            await this.loadZipFrames();
        } else if (this.options.type === 'gif') {
            await this.loadGifFrames();
        }

        if (this.loaded && this.options.autoplay) {
            this.play();
        }
    }

    createPlayerUI() {
        // Add animation-container class to parent
        this.container.classList.add('animation-container');

        // Create canvas for rendering
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'animation-canvas';
        this.ctx = this.canvas.getContext('2d');

        // Find and hide the original image
        const originalImg = this.container.querySelector('img');
        if (originalImg) {
            originalImg.style.display = 'none';
            this.originalSrc = originalImg.src;
        }

        // Create controls overlay
        this.controls = document.createElement('div');
        this.controls.className = 'animation-controls';
        this.controls.innerHTML = `
            <div class="animation-progress-bar">
                <input type="range" class="animation-seek-bar" min="0" max="0" value="0">
            </div>
            <div class="animation-toolbar">
                <button class="animation-play-btn" title="Play/Pause (Space)">
                    <span class="play-icon">▶</span>
                    <span class="pause-icon" style="display:none">⏸</span>
                </button>
                <span class="animation-frame-info">0 / 0</span>
                <div class="animation-fps-control">
                    <label>FPS:</label>
                    <input type="range" class="animation-fps-slider" min="1" max="30" value="${this.fps}">
                    <span class="animation-fps-value">${this.fps}</span>
                </div>
                <button class="animation-prev-btn" title="Previous Frame (←)">⏮</button>
                <button class="animation-next-btn" title="Next Frame (→)">⏭</button>
            </div>
        `;

        // Insert elements
        this.container.insertBefore(this.canvas, this.container.firstChild);
        this.container.appendChild(this.controls);

        // Get references to controls
        this.seekBar = this.controls.querySelector('.animation-seek-bar');
        this.playBtn = this.controls.querySelector('.animation-play-btn');
        this.frameInfo = this.controls.querySelector('.animation-frame-info');
        this.fpsSlider = this.controls.querySelector('.animation-fps-slider');
        this.fpsValue = this.controls.querySelector('.animation-fps-value');
        this.prevBtn = this.controls.querySelector('.animation-prev-btn');
        this.nextBtn = this.controls.querySelector('.animation-next-btn');

        // Bind events
        this.bindEvents();
    }

    bindEvents() {
        // Play/Pause button
        this.playBtn.addEventListener('click', () => this.togglePlay());

        // Seek bar
        this.seekBar.addEventListener('input', (e) => {
            this.seekTo(parseInt(e.target.value));
        });

        // FPS slider
        this.fpsSlider.addEventListener('input', (e) => {
            this.setFps(parseInt(e.target.value));
        });

        // Previous/Next buttons
        this.prevBtn.addEventListener('click', () => this.prevFrame());
        this.nextBtn.addEventListener('click', () => this.nextFrame());

        // Keyboard controls
        document.addEventListener('keydown', (e) => {
            // Only respond if this container is visible
            if (!this.container.offsetParent) return;

            switch (e.key) {
                case ' ':
                    e.preventDefault();
                    this.togglePlay();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    this.prevFrame();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    this.nextFrame();
                    break;
            }
        });

        // Click on canvas to toggle play
        this.canvas.addEventListener('click', () => this.togglePlay());
    }

    async loadZipFrames() {
        if (!this.options.md5) {
            console.error('[AnimationPlayer] MD5 required for zip animations');
            return;
        }

        try {
            // Fetch frame URLs
            const response = await fetch(`/api/animation/frames/${this.options.md5}`);
            if (!response.ok) throw new Error('Failed to fetch frame URLs');

            const data = await response.json();
            const frameUrls = data.frame_urls || [];

            if (frameUrls.length === 0) {
                console.error('[AnimationPlayer] No frames found');
                return;
            }

            // Set canvas size
            if (data.width && data.height) {
                this.canvas.width = data.width;
                this.canvas.height = data.height;
            }

            // Set FPS from metadata
            if (data.default_fps) {
                this.fps = data.default_fps;
                this.fpsSlider.value = this.fps;
                this.fpsValue.textContent = this.fps;
            }

            // Preload all frames
            this.frameImages = await this.preloadImages(frameUrls);
            this.frames = frameUrls;
            this.loaded = true;

            // Update UI
            this.seekBar.max = this.frames.length - 1;
            this.updateUI();

            // Draw first frame
            this.drawFrame(0);

        } catch (error) {
            console.error('[AnimationPlayer] Error loading zip frames:', error);
        }
    }

    async loadGifFrames() {
        // For GIFs, we'll use a library like gifler or SuperGif
        // Or we can extract frames using canvas
        // For now, use a simple approach with the gifuct-js concept

        const img = this.container.querySelector('img');
        if (!img) return;

        try {
            // Fetch the GIF as array buffer
            const response = await fetch(this.originalSrc);
            const buffer = await response.arrayBuffer();

            // Parse GIF frames using a simple parser
            const frames = await this.parseGifFrames(buffer);

            if (frames.length === 0) {
                console.warn('[AnimationPlayer] Could not parse GIF frames, showing static image');
                img.style.display = '';
                this.controls.style.display = 'none';
                return;
            }

            // Set canvas size from first frame
            const firstFrame = frames[0];
            this.canvas.width = firstFrame.width;
            this.canvas.height = firstFrame.height;

            this.frameImages = frames.map(f => f.imageData);
            this.frameDelays = frames.map(f => f.delay);
            this.frames = this.frameImages;
            this.loaded = true;

            // Calculate average FPS from frame delays
            const avgDelay = this.frameDelays.reduce((a, b) => a + b, 0) / this.frameDelays.length;
            this.fps = Math.round(1000 / avgDelay);
            this.fpsSlider.value = Math.min(30, Math.max(1, this.fps));
            this.fpsValue.textContent = this.fps;

            // Update UI
            this.seekBar.max = this.frames.length - 1;
            this.updateUI();

            // Draw first frame
            this.drawFrame(0);

        } catch (error) {
            console.error('[AnimationPlayer] Error loading GIF frames:', error);
            // Fall back to showing the original image
            const img = this.container.querySelector('img');
            if (img) img.style.display = '';
            this.controls.style.display = 'none';
        }
    }

    async parseGifFrames(buffer) {
        // Simple GIF parser - extracts frames from GIF buffer
        // This is a simplified implementation. For production, consider using gifuct-js

        const frames = [];
        const gif = new Uint8Array(buffer);

        // Check GIF signature
        const signature = String.fromCharCode(...gif.slice(0, 6));
        if (signature !== 'GIF87a' && signature !== 'GIF89a') {
            throw new Error('Not a valid GIF file');
        }

        // Get logical screen descriptor
        const width = gif[6] | (gif[7] << 8);
        const height = gif[8] | (gif[9] << 8);
        const flags = gif[10];
        const hasGlobalColorTable = !!(flags & 0x80);
        const colorTableSize = 1 << ((flags & 0x07) + 1);

        // Create temporary canvas for rendering
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = width;
        tempCanvas.height = height;
        const tempCtx = tempCanvas.getContext('2d');

        // For now, just create a single frame from the image
        // Full GIF parsing is complex - recommend using gifuct-js library
        const img = new Image();
        img.src = this.originalSrc;
        await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = reject;
        });

        tempCtx.drawImage(img, 0, 0);
        const imageData = tempCtx.getImageData(0, 0, width, height);

        // For animated GIFs, we need to extract each frame
        // This simplified version just shows it as a single frame
        frames.push({
            imageData: imageData,
            width: width,
            height: height,
            delay: 100  // Default delay
        });

        return frames;
    }

    async preloadImages(urls) {
        const images = [];
        for (const url of urls) {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = reject;
                img.src = url;
            });
            images.push(img);
        }
        return images;
    }

    drawFrame(index) {
        if (!this.loaded || index < 0 || index >= this.frames.length) return;

        const frame = this.frameImages[index];

        if (frame instanceof ImageData) {
            // GIF frame (ImageData)
            this.ctx.putImageData(frame, 0, 0);
        } else if (frame instanceof HTMLImageElement) {
            // Zip frame (Image element)
            // Resize canvas if needed
            if (this.canvas.width !== frame.width || this.canvas.height !== frame.height) {
                this.canvas.width = frame.width;
                this.canvas.height = frame.height;
            }
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.ctx.drawImage(frame, 0, 0);
        }

        this.currentFrame = index;
        this.updateUI();
    }

    updateUI() {
        // Update frame info
        this.frameInfo.textContent = `${this.currentFrame + 1} / ${this.frames.length}`;

        // Update seek bar
        this.seekBar.value = this.currentFrame;

        // Update play/pause button
        const playIcon = this.playBtn.querySelector('.play-icon');
        const pauseIcon = this.playBtn.querySelector('.pause-icon');
        if (this.playing) {
            playIcon.style.display = 'none';
            pauseIcon.style.display = '';
        } else {
            playIcon.style.display = '';
            pauseIcon.style.display = 'none';
        }
    }

    play() {
        if (this.playing || !this.loaded) return;

        this.playing = true;
        this.updateUI();

        const frameDelay = 1000 / this.fps;

        this.animationInterval = setInterval(() => {
            let nextFrame = this.currentFrame + 1;
            if (nextFrame >= this.frames.length) {
                if (this.options.loop) {
                    nextFrame = 0;
                } else {
                    this.pause();
                    return;
                }
            }
            this.drawFrame(nextFrame);
        }, frameDelay);
    }

    pause() {
        if (!this.playing) return;

        this.playing = false;
        if (this.animationInterval) {
            clearInterval(this.animationInterval);
            this.animationInterval = null;
        }
        this.updateUI();
    }

    togglePlay() {
        if (this.playing) {
            this.pause();
        } else {
            this.play();
        }
    }

    seekTo(frame) {
        if (frame < 0 || frame >= this.frames.length) return;

        const wasPlaying = this.playing;
        if (wasPlaying) this.pause();

        this.drawFrame(frame);

        if (wasPlaying) this.play();
    }

    nextFrame() {
        const wasPlaying = this.playing;
        if (wasPlaying) this.pause();

        let next = this.currentFrame + 1;
        if (next >= this.frames.length) next = 0;
        this.drawFrame(next);
    }

    prevFrame() {
        const wasPlaying = this.playing;
        if (wasPlaying) this.pause();

        let prev = this.currentFrame - 1;
        if (prev < 0) prev = this.frames.length - 1;
        this.drawFrame(prev);
    }

    setFps(newFps) {
        this.fps = Math.max(1, Math.min(30, newFps));
        this.fpsValue.textContent = this.fps;

        // Restart animation if playing
        if (this.playing) {
            this.pause();
            this.play();
        }
    }

    destroy() {
        this.pause();
        if (this.controls) {
            this.controls.remove();
        }
        if (this.canvas) {
            this.canvas.remove();
        }
        // Show original image again
        const img = this.container.querySelector('img');
        if (img) img.style.display = '';
    }
}


/**
 * Initialize animation players for all animated content on the page
 */
function initAnimationPlayers() {
    // Find all animation containers
    const containers = document.querySelectorAll('[data-animation-type]');

    containers.forEach(container => {
        const type = container.dataset.animationType;
        const md5 = container.dataset.md5;
        const fps = parseInt(container.dataset.fps) || 24;
        const filepath = container.dataset.filepath;

        // Skip if already initialized
        if (container.animationPlayer) return;

        container.animationPlayer = new AnimationPlayer(container, {
            type,
            md5,
            fps,
            filepath,
            autoplay: true,
            loop: true
        });
    });
}


/**
 * Check if a file needs the custom animation player (zip animations only)
 * GIFs and other animated formats play natively in the browser
 */
function needsAnimationPlayer(filepath) {
    const ext = filepath.split('.').pop().toLowerCase();
    return ext === 'zip';
}


// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', initAnimationPlayers);

// Export for use in other scripts
window.AnimationPlayer = AnimationPlayer;
window.initAnimationPlayers = initAnimationPlayers;
window.needsAnimationPlayer = needsAnimationPlayer;

// static/js/global-uploader.js
import { showNotification } from './utils/notifications.js';

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('global-drop-zone');
    if (!dropZone) return;

    let dragCounter = 0;
    let dragTimeout = null;
    let uploadTimeout = null;
    const DRAG_DELAY = 300; // milliseconds to wait before showing drop zone
    const UPLOAD_DELAY = 1000; // milliseconds to wait before uploading (cancellable)

    window.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;

        // Only set timeout on first dragenter
        if (dragCounter === 1) {
            dragTimeout = setTimeout(() => {
                dropZone.classList.add('active');
            }, DRAG_DELAY);
        }
    });

    window.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            // Clear timeout if drag ends before delay completes
            if (dragTimeout) {
                clearTimeout(dragTimeout);
                dragTimeout = null;
            }
            dropZone.classList.remove('active');
        }
    });

    window.addEventListener('dragover', (e) => {
        e.preventDefault(); // This is crucial to allow a drop
    });

    window.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;

        // Clear timeout if drop happens before delay completes
        if (dragTimeout) {
            clearTimeout(dragTimeout);
            dragTimeout = null;
        }

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            // Show confirmation message
            const imageCount = Array.from(files).filter(f => f.type.startsWith('image/')).length;
            if (imageCount === 0) {
                dropZone.classList.remove('active');
                return;
            }

            dropZone.innerHTML = `<div>Upload ${imageCount} image(s)? <span style="font-size: 0.9em; opacity: 0.8;">(Cancelling...)</span></div>`;

            // Set upload timeout
            uploadTimeout = setTimeout(() => {
                dropZone.classList.remove('active');
                dropZone.innerHTML = '<div>Drop files anywhere to upload</div>';
                handleFileUpload(files);
            }, UPLOAD_DELAY);
        } else {
            dropZone.classList.remove('active');
        }
    });

    // Cancel upload if user clicks the drop zone during countdown
    dropZone.addEventListener('click', () => {
        if (uploadTimeout) {
            clearTimeout(uploadTimeout);
            uploadTimeout = null;
            dropZone.classList.remove('active');
            dropZone.innerHTML = '<div>Drop files anywhere to upload</div>';
            showNotification('Upload cancelled', 'info');
        }
    });

    function handleFileUpload(files) {
        const formData = new FormData();
        for (const file of files) {
            if (file.type.startsWith('image/')) {
                formData.append('file', file);
            }
        }

        const imageCount = formData.getAll('file').length;
        if (imageCount === 0) return;

        showNotification(`Uploading ${imageCount} image(s)...`, 'info');

        fetch('/upload', {
            method: 'POST',
            body: formData,
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                showNotification(data.message, 'success');
                // If the server sent a redirect URL, go there after a delay
                if (data.redirect_url) {
                    setTimeout(() => {
                        window.location.href = data.redirect_url;
                    }, 1500); // 1.5 second delay
                }
            } else {
                throw new Error(data.error || 'Unknown upload error');
            }
        })
        .catch(err => {
            showNotification(`Upload failed: ${err.message}`, 'error');
            console.error('Upload error:', err);
        });
    }

});
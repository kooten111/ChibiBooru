// static/js/global-uploader.js
import { showNotification } from './utils/notifications.js';

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('global-drop-zone');
    if (!dropZone) return;

    let dragCounter = 0;
    let dragTimeout = null;
    const DRAG_DELAY = 300; // milliseconds to wait before showing drop zone

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

        dropZone.classList.remove('active');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files);
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
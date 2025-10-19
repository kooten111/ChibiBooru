// static/js/global-uploader.js

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('global-drop-zone');
    if (!dropZone) return;

    let dragCounter = 0;

    window.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        dropZone.classList.add('active');
    });

    window.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter === 0) {
            dropZone.classList.remove('active');
        }
    });

    window.addEventListener('dragover', (e) => {
        e.preventDefault(); // This is crucial to allow a drop
    });

    window.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
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

        showUploadNotification(`Uploading ${imageCount} image(s)...`, 'info');

        fetch('/upload', {
            method: 'POST',
            body: formData,
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                showUploadNotification(data.message, 'success');
                // Reload after a short delay to see changes
                setTimeout(() => window.location.reload(), 1500);
            } else {
                throw new Error(data.error || 'Unknown upload error');
            }
        })
        .catch(err => {
            showUploadNotification(`Upload failed: ${err.message}`, 'error');
            console.error('Upload error:', err);
        });
    }

    function showUploadNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed; top: 100px; right: 30px; padding: 15px 25px;
            background: ${type === 'error' ? 'linear-gradient(135deg, #ff6b6b 0%, #c92a2a 100%)' : 
                         type === 'success' ? 'linear-gradient(135deg, #51cf66 0%, #37b24d 100%)' :
                         'linear-gradient(135deg, #4a9eff 0%, #357abd 100%)'};
            color: white; border-radius: 10px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
            z-index: 10002; font-weight: 600; max-width: 400px;
            animation: slideInRight 0.3s ease-out;
        `;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideOutRight 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 4000);
    }
});
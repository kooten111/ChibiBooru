// static/js/modal.js

function showConfirm(message, onConfirm, onCancel) {
    const overlay = document.createElement('div');
    overlay.className = 'custom-confirm-overlay';
    overlay.innerHTML = `
        <div class="custom-confirm-modal">
            <p>${message}</p>
            <div class="button-group">
                <button class="btn-cancel">Cancel</button>
                <button class="btn-confirm">Confirm</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(overlay);
    
    const modal = overlay.querySelector('.custom-confirm-modal');
    const btnConfirm = modal.querySelector('.btn-confirm');
    const btnCancel = modal.querySelector('.btn-cancel');
    
    btnConfirm.onclick = () => {
        overlay.remove();
        if (onConfirm) onConfirm();
    };
    
    btnCancel.onclick = () => {
        overlay.remove();
        if (onCancel) onCancel();
    };
    
    overlay.onclick = (e) => {
        if (e.target === overlay) {
            overlay.remove();
            if (onCancel) onCancel();
        }
    };
}

// Make available on window for ES modules
window.showConfirm = showConfirm;
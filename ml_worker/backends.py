"""
ML Backend Configuration - Strict Mode
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)

class Backend:
    """Available ML backends"""
    CUDA = "cuda"
    XPU = "xpu"
    MPS = "mps"
    CPU = "cpu"

def get_configured_backend():
    """Get the backend configured in environment variable"""
    return os.environ.get('ML_WORKER_BACKEND')

def setup_backend_environment(backend: str) -> None:
    """
    Set up environment variables for the selected backend.
    Must be called BEFORE importing torch.
    """
    if backend == Backend.CUDA:
        # CUDA environment variables
        if 'CUDA_VISIBLE_DEVICES' not in os.environ:
            os.environ['CUDA_VISIBLE_DEVICES'] = '0'

    elif backend == Backend.XPU:
        # Intel XPU environment variables
        if 'ONEAPI_DEVICE_SELECTOR' not in os.environ:
            os.environ['ONEAPI_DEVICE_SELECTOR'] = 'level_zero:gpu'
            
    logger.info(f"Environment configured for backend: {backend}")

def get_torch_device(backend: str) -> str:
    """
    Get the torch device string.
    Strictly enforces the requested backend or crashes.
    """
    import torch

    if backend == Backend.CUDA:
        if not torch.cuda.is_available():
            logger.error("Backend is CUDA but torch.cuda.is_available() is False!")
            sys.exit(1)
        return "cuda"
        
    elif backend == Backend.XPU:
        if not hasattr(torch, 'xpu') or not torch.xpu.is_available():
             # Try explicit import if not already done, though server.py should handle this
            try:
                import intel_extension_for_pytorch as ipex
                if torch.xpu.is_available():
                    return "xpu"
            except ImportError:
                pass
                
            logger.error("Backend is XPU but torch.xpu.is_available() is False!")
            sys.exit(1)
        return "xpu"
        
    elif backend == Backend.MPS:
        if not hasattr(torch.backends, 'mps') or not torch.backends.mps.is_available():
            logger.error("Backend is MPS but MPS is not available!")
            sys.exit(1)
        return "mps"
        
    elif backend == Backend.CPU:
        return "cpu"
        
    else:
        logger.error(f"Unknown backend type: {backend}")
        sys.exit(1)

def ensure_backend_ready() -> str:
    """
    Verify backend configuration.
    CRASHES if not configured or if dependencies are missing.
    No more auto-install fallback.
    """
    backend = get_configured_backend()
    
    if not backend:
        logger.error("ML_WORKER_BACKEND is not set in environment!")
        print("CRITICAL: ML_WORKER_BACKEND is not set. Please run setup_ml.py or start_booru.sh")
        sys.exit(1)
        
    setup_backend_environment(backend)
    
    return backend

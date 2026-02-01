"""
Model state and loading logic for ML worker
"""
import os
import sys
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Global state for models
tagger_session = None
tagger_metadata = None
upscaler_model = None
upscaler_device = None
similarity_model = None

def check_dependencies() -> bool:
    """
    Check that all required ML dependencies are installed.
    Returns True if all dependencies are available, False otherwise.
    """
    missing = []
    
    # Check onnxruntime
    try:
        import onnxruntime
        logger.info(f"onnxruntime: OK (version {onnxruntime.__version__})")
    except ImportError:
        missing.append("onnxruntime")
        logger.error("onnxruntime: MISSING")
    
    # Check torchvision
    try:
        import torchvision
        logger.info(f"torchvision: OK (version {torchvision.__version__})")
    except ImportError:
        missing.append("torchvision")
        logger.error("torchvision: MISSING")
    
    # Check torch (comes with torchvision but check explicitly)
    try:
        import torch
        logger.info(f"torch: OK (version {torch.__version__})")
    except ImportError:
        missing.append("torch")
        logger.error("torch: MISSING")
    
    # Check PIL
    try:
        from PIL import Image
        import PIL
        logger.info(f"Pillow: OK (version {PIL.__version__})")
    except ImportError:
        missing.append("Pillow")
        logger.error("Pillow: MISSING")
    
    # Check numpy
    try:
        import numpy
        logger.info(f"numpy: OK (version {numpy.__version__})")
    except ImportError:
        missing.append("numpy")
        logger.error("numpy: MISSING")
    
    if missing:
        logger.error("=" * 60)
        logger.error("FATAL: Missing required dependencies!")
        logger.error(f"Please install: {', '.join(missing)}")
        logger.error("Run: source ./venv/bin/activate && uv pip install -r requirements.txt")
        logger.error("=" * 60)
        return False
    
    logger.info("All ML dependencies verified.")
    return True


def get_onnx_providers() -> list:
    """Get the list of ONNX Runtime providers based on configured backend"""
    backend = os.environ.get('ML_WORKER_BACKEND', 'cpu')
    providers = []
    
    if backend == 'cuda':
        providers.append('CUDAExecutionProvider')
    elif backend == 'xpu':
        # OpenVINO is often used for XPU with ONNX
        providers.append('OpenVINOExecutionProvider')
    elif backend == 'mps':
        providers.append('CoreMLExecutionProvider')
    elif backend == 'cpu':
        providers.append('CPUExecutionProvider')
        
    return providers


def get_onnx_session_options():
    """
    Get ONNX Runtime SessionOptions configured for CPU parallelism.
    Uses intra_op_num_threads for parallel execution of operations within inference.
    """
    import onnxruntime as ort
    
    sess_options = ort.SessionOptions()
    
    # Get number of CPU cores, cap at 16 to avoid excessive threading overhead
    num_cores = min(os.cpu_count() or 4, 16)
    
    # intra_op_num_threads: parallelizes operations within a single inference run
    # (matrix ops, convolutions, etc.) - this is what we want for single-job multithreading
    sess_options.intra_op_num_threads = num_cores
    
    # inter_op_num_threads: parallelizes independent graph nodes
    # Set to 1 for single job inference (no parallel graphs)
    sess_options.inter_op_num_threads = 1
    
    logger.info(f"ONNX Session configured with {num_cores} intra-op threads")
    
    return sess_options

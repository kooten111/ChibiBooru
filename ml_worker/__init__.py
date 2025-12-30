"""
ML Worker Package

Provides isolated subprocess execution for ML frameworks (PyTorch, ONNXRuntime)
to reduce memory footprint of the main application.

The ML worker runs as a separate process that:
- Loads ML frameworks only when needed
- Auto-terminates after idle timeout (default: 5 minutes)
- Communicates via Unix domain socket
- Handles CUDA/XPU/MPS/CPU backend detection

Usage:
    from ml_worker.client import MLWorkerClient

    client = MLWorkerClient()
    result = client.tag_image(image_path, model_path, threshold=0.35)
"""

__version__ = "1.0.0"

from ml_worker.client import MLWorkerClient

__all__ = ['MLWorkerClient']

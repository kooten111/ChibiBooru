"""
GPU Detection Utility for RealESRGAN Upscaler
Detects GPU hardware and manages PyTorch backend installation
"""

import subprocess
import platform
import sys
import os
from typing import Dict, Optional, Tuple

# Cache GPU info to avoid repeated detection
_gpu_info_cache: Optional[Dict] = None


def run_command(cmd: str, capture: bool = True) -> Tuple[int, str, str]:
    """Run shell command and return output"""
    if capture:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    else:
        return subprocess.run(cmd, shell=True).returncode, "", ""


def detect_gpu_hardware() -> Dict:
    """
    Detect GPU hardware without requiring PyTorch.
    Returns dict with vendor, device type, and recommended PyTorch variant.
    """
    global _gpu_info_cache
    
    if _gpu_info_cache is not None:
        return _gpu_info_cache
    
    gpu_info = {
        'vendor': 'CPU',
        'has_gpu': False,
        'device': 'cpu',
        'name': 'CPU',
        'recommended_pytorch': 'cpu',
        'memory_gb': None
    }

    # Try lspci (Linux)
    if platform.system() == "Linux":
        code, stdout, _ = run_command("lspci | grep -i 'vga\\|3d\\|display'")
        if code == 0 and stdout:
            gpu_text = stdout.lower()

            if 'nvidia' in gpu_text or 'geforce' in gpu_text or 'rtx' in gpu_text or 'gtx' in gpu_text:
                gpu_info['vendor'] = 'Nvidia'
                gpu_info['has_gpu'] = True
                gpu_info['device'] = 'cuda'
                gpu_info['recommended_pytorch'] = 'cuda'
                # Extract GPU name
                for line in stdout.strip().split('\n'):
                    if 'nvidia' in line.lower():
                        gpu_info['name'] = line.split(':')[-1].strip() if ':' in line else 'Nvidia GPU'
                        break
            elif 'amd' in gpu_text or 'radeon' in gpu_text:
                gpu_info['vendor'] = 'AMD'
                gpu_info['has_gpu'] = True
                gpu_info['device'] = 'cuda'  # ROCm uses cuda device in PyTorch
                gpu_info['recommended_pytorch'] = 'rocm'
                for line in stdout.strip().split('\n'):
                    if 'amd' in line.lower() or 'radeon' in line.lower():
                        gpu_info['name'] = line.split(':')[-1].strip() if ':' in line else 'AMD GPU'
                        break
            elif 'intel' in gpu_text and ('arc' in gpu_text or 'xe' in gpu_text):
                gpu_info['vendor'] = 'Intel'
                gpu_info['has_gpu'] = True
                gpu_info['device'] = 'xpu'
                gpu_info['recommended_pytorch'] = 'xpu'
                for line in stdout.strip().split('\n'):
                    if 'intel' in line.lower():
                        gpu_info['name'] = line.split(':')[-1].strip() if ':' in line else 'Intel GPU'
                        break

    # Try nvidia-smi as fallback for Nvidia
    if not gpu_info['has_gpu']:
        code, stdout, _ = run_command("nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null")
        if code == 0 and stdout.strip():
            gpu_info['vendor'] = 'Nvidia'
            gpu_info['has_gpu'] = True
            gpu_info['device'] = 'cuda'
            gpu_info['recommended_pytorch'] = 'cuda'
            gpu_info['name'] = stdout.strip()

    # Try rocm-smi for AMD
    if not gpu_info['has_gpu']:
        code, stdout, _ = run_command("rocm-smi --showproductname 2>/dev/null")
        if code == 0 and stdout:
            gpu_info['vendor'] = 'AMD'
            gpu_info['has_gpu'] = True
            gpu_info['device'] = 'cuda'
            gpu_info['recommended_pytorch'] = 'rocm'
            gpu_info['name'] = 'AMD GPU (ROCm)'

    _gpu_info_cache = gpu_info
    return gpu_info


def get_pytorch_device() -> str:
    """
    Get the appropriate PyTorch device string.
    Returns 'cuda', 'xpu', or 'cpu'.
    """
    try:
        import torch
        
        # Check for Intel XPU first
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            return 'xpu'
        
        # Check for CUDA (works for both Nvidia and AMD ROCm)
        if torch.cuda.is_available():
            return 'cuda'
        
        return 'cpu'
    except ImportError:
        # PyTorch not installed, use hardware detection
        gpu_info = detect_gpu_hardware()
        return gpu_info['device']


def check_upscaler_dependencies() -> Dict:
    """
    Check if all upscaler dependencies are installed and working.
    Now only requires PyTorch - we use our own RRDBNet implementation.
    """
    result = {
        'ready': False,
        'pytorch_installed': False,
        'pytorch_version': None,
        'gpu_available': False,
        'gpu_info': None,
        'device': 'cpu',
        'missing': []
    }
    
    # Check PyTorch - this is all we need now
    try:
        import torch
        result['pytorch_installed'] = True
        result['pytorch_version'] = torch.__version__
        
        # Check GPU availability
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            result['gpu_available'] = True
            result['device'] = 'xpu'
        elif torch.cuda.is_available():
            result['gpu_available'] = True
            result['device'] = 'cuda'
            result['gpu_info'] = {
                'name': torch.cuda.get_device_name(0),
                'memory_gb': torch.cuda.get_device_properties(0).total_memory / 1024**3
            }
        
        # PyTorch is all we need - our RRDBNet is standalone
        result['ready'] = True
        
    except ImportError:
        result['missing'].append('torch')
    
    return result


def get_pytorch_install_command(variant: str = 'auto') -> str:
    """
    Get the pip install command for PyTorch based on GPU type.
    """
    if variant == 'auto':
        gpu_info = detect_gpu_hardware()
        variant = gpu_info['recommended_pytorch']
    
    if variant == 'cuda':
        return "pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
    elif variant == 'rocm':
        return "pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.2"
    elif variant == 'xpu':
        return "pip install torch torchvision intel-extension-for-pytorch"
    else:
        return "pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"


def install_upscaler_dependencies(variant: str = 'auto') -> Dict:
    """
    Install upscaler dependencies (PyTorch only - we use standalone RRDBNet).
    This should be run from within the venv.
    Returns dict with success status and messages.
    """
    result = {
        'success': False,
        'messages': [],
        'errors': []
    }
    
    # Get GPU info
    gpu_info = detect_gpu_hardware()
    if variant == 'auto':
        variant = gpu_info['recommended_pytorch']
    
    result['messages'].append(f"Detected GPU: {gpu_info['vendor']} - {gpu_info['name']}")
    result['messages'].append(f"Installing PyTorch with {variant.upper()} support...")
    
    # Install PyTorch
    pytorch_cmd = get_pytorch_install_command(variant)
    code, stdout, stderr = run_command(pytorch_cmd, capture=False)
    
    if code != 0:
        result['errors'].append(f"PyTorch installation failed: {stderr}")
        return result
    
    result['messages'].append("PyTorch installed successfully")
    
    # Install basic dependencies (numpy/Pillow likely already installed)
    result['messages'].append("Installing image processing dependencies...")
    
    packages = ["numpy", "Pillow"]
    code, _, stderr = run_command(f"pip install {' '.join(packages)}", capture=False)
    
    if code != 0:
        result['errors'].append(f"Dependency installation failed: {stderr}")
        return result
    
    # Verify installation
    deps = check_upscaler_dependencies()
    if deps['ready']:
        result['success'] = True
        result['messages'].append("All dependencies installed successfully!")
        result['messages'].append("Model will be downloaded on first upscale.")
    else:
        result['errors'].append(f"Missing dependencies after install: {deps['missing']}")
    
    return result

"""
ML Backend Detection and Installation

Detects available GPU hardware (NVIDIA CUDA, Intel XPU, Apple MPS) and
automatically installs the appropriate PyTorch variant on first run.
"""

import os
import sys
import platform
import subprocess
import logging
from typing import List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class Backend:
    """Available ML backends"""
    CUDA = "cuda"
    XPU = "xpu"
    MPS = "mps"
    CPU = "cpu"


def _run_command(cmd: List[str], capture_output: bool = True) -> Tuple[bool, str]:
    """
    Run a command and return success status and output.

    Args:
        cmd: Command and arguments as list
        capture_output: Whether to capture output

    Returns:
        Tuple of (success, output)
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False, ""


def detect_nvidia_gpu() -> bool:
    """
    Detect if NVIDIA GPU is available.

    Returns:
        True if NVIDIA GPU detected
    """
    success, output = _run_command(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'])
    if success and output.strip():
        logger.info(f"Detected NVIDIA GPU: {output.strip()}")
        return True
    return False


def detect_intel_gpu() -> bool:
    """
    Detect if Intel GPU is available.

    Returns:
        True if Intel GPU detected
    """
    # Check for Intel GPU via multiple methods

    # Method 1: Check for XPU via sycl-ls (Intel oneAPI)
    success, output = _run_command(['sycl-ls'])
    if success and 'gpu' in output.lower() and 'intel' in output.lower():
        logger.info("Detected Intel GPU via sycl-ls")
        return True

    # Method 2: Check lspci on Linux
    if platform.system() == 'Linux':
        success, output = _run_command(['lspci'])
        if success and 'intel' in output.lower() and 'vga' in output.lower():
            logger.info("Detected Intel GPU via lspci")
            return True

    return False


def detect_apple_silicon() -> bool:
    """
    Detect if running on Apple Silicon (M1/M2/M3).

    Returns:
        True if Apple Silicon detected
    """
    if platform.system() == 'Darwin':
        # Check if processor is ARM
        processor = platform.processor().lower()
        machine = platform.machine().lower()

        if 'arm' in processor or 'arm64' in machine:
            logger.info(f"Detected Apple Silicon: {processor} / {machine}")
            return True

    return False


def detect_available_backends() -> List[str]:
    """
    Detect all available ML backends on the system.

    Returns:
        List of available backend names, in order of preference
    """
    available = []

    # Check NVIDIA CUDA (highest priority)
    if detect_nvidia_gpu():
        available.append(Backend.CUDA)

    # Check Intel XPU
    if detect_intel_gpu():
        available.append(Backend.XPU)

    # Check Apple Silicon MPS
    if detect_apple_silicon():
        available.append(Backend.MPS)

    # CPU is always available as fallback
    available.append(Backend.CPU)

    return available


def check_torch_installed() -> bool:
    """
    Check if PyTorch is already installed.

    Returns:
        True if torch can be imported
    """
    try:
        import torch
        logger.info(f"PyTorch {torch.__version__} already installed")
        return True
    except ImportError:
        return False


def get_torch_install_command(backend: str) -> List[str]:
    """
    Get the pip install command for a specific backend.

    Args:
        backend: Backend name (cuda/xpu/mps/cpu)

    Returns:
        List of command arguments for subprocess
    """
    commands = {
        Backend.CUDA: [
            sys.executable, '-m', 'pip', 'install',
            'torch', 'torchvision',
            '--index-url', 'https://download.pytorch.org/whl/cu121'
        ],
        Backend.XPU: [
            sys.executable, '-m', 'pip', 'install',
            'torch', 'torchvision',
            '--index-url', 'https://pytorch-extension.intel.com/release-whl/stable/xpu/us/'
        ],
        Backend.MPS: [
            sys.executable, '-m', 'pip', 'install',
            'torch', 'torchvision'
        ],
        Backend.CPU: [
            sys.executable, '-m', 'pip', 'install',
            'torch', 'torchvision',
            '--index-url', 'https://download.pytorch.org/whl/cpu'
        ]
    }

    return commands.get(backend, commands[Backend.CPU])


def install_pytorch(backend: str) -> bool:
    """
    Install PyTorch for the specified backend.

    Args:
        backend: Backend to install for

    Returns:
        True if installation successful
    """
    logger.info(f"Installing PyTorch for backend: {backend}")

    cmd = get_torch_install_command(backend)

    print(f"\nInstalling PyTorch for {backend}...")
    print(f"Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)
        if result.returncode == 0:
            logger.info("PyTorch installation successful")
            return True
    except subprocess.CalledProcessError as e:
        logger.error(f"PyTorch installation failed: {e}")
        return False

    return False


def prompt_backend_selection(available_backends: List[str]) -> Optional[str]:
    """
    Prompt user to select a backend from available options.

    Args:
        available_backends: List of available backend names

    Returns:
        Selected backend name, or None if cancelled
    """
    print("\n" + "="*60)
    print("ML Worker Backend Selection")
    print("="*60)
    print("\nDetected Hardware:")

    for i, backend in enumerate(available_backends, 1):
        desc = {
            Backend.CUDA: "NVIDIA GPU (CUDA) - Best performance",
            Backend.XPU: "Intel GPU (XPU) - Good performance",
            Backend.MPS: "Apple Silicon (MPS) - Good performance",
            Backend.CPU: "CPU Only - Slower, but works everywhere"
        }
        recommended = " (Recommended)" if i == 1 else ""
        print(f"  [{i}] {desc.get(backend, backend)}{recommended}")

    print("\nSelect backend to install (1-{}, or 'q' to quit): ".format(len(available_backends)), end='')

    while True:
        try:
            choice = input().strip().lower()

            if choice == 'q':
                return None

            idx = int(choice) - 1
            if 0 <= idx < len(available_backends):
                selected = available_backends[idx]
                print(f"\nSelected: {selected}")
                return selected
            else:
                print(f"Invalid choice. Enter 1-{len(available_backends)} or 'q': ", end='')
        except ValueError:
            print(f"Invalid input. Enter 1-{len(available_backends)} or 'q': ", end='')


def save_backend_to_config(backend: str) -> bool:
    """
    Save the selected backend to config.

    Args:
        backend: Backend to save

    Returns:
        True if saved successfully
    """
    try:
        # Try to update .env file
        env_path = Path('.env')

        if env_path.exists():
            # Read existing .env
            with open(env_path, 'r') as f:
                lines = f.readlines()

            # Update or add ML_WORKER_BACKEND
            found = False
            for i, line in enumerate(lines):
                if line.startswith('ML_WORKER_BACKEND='):
                    lines[i] = f'ML_WORKER_BACKEND={backend}\n'
                    found = True
                    break

            if not found:
                lines.append(f'\nML_WORKER_BACKEND={backend}\n')

            # Write back
            with open(env_path, 'w') as f:
                f.writelines(lines)
        else:
            # Create new .env file
            with open(env_path, 'w') as f:
                f.write(f'ML_WORKER_BACKEND={backend}\n')

        logger.info(f"Saved backend '{backend}' to .env")
        return True

    except Exception as e:
        logger.error(f"Failed to save backend to config: {e}")
        return False


def setup_backend_environment(backend: str) -> None:
    """
    Set up environment variables for the selected backend.
    Must be called BEFORE importing torch.

    Args:
        backend: Backend to configure
    """
    if backend == Backend.CUDA:
        # CUDA environment variables
        if 'CUDA_VISIBLE_DEVICES' not in os.environ:
            os.environ['CUDA_VISIBLE_DEVICES'] = '0'  # Use first GPU by default

    elif backend == Backend.XPU:
        # Intel XPU environment variables
        if 'ONEAPI_DEVICE_SELECTOR' not in os.environ:
            os.environ['ONEAPI_DEVICE_SELECTOR'] = 'level_zero:gpu'

    # No special env vars needed for MPS or CPU
    logger.info(f"Environment configured for backend: {backend}")


def get_torch_device(backend: str) -> str:
    """
    Get the torch device string for the specified backend.

    Args:
        backend: Backend name

    Returns:
        Torch device string (e.g., "cuda", "xpu", "cpu")
    """
    # This function is called AFTER torch is imported
    try:
        import torch

        if backend == Backend.CUDA and torch.cuda.is_available():
            return "cuda"
        elif backend == Backend.XPU:
            # Intel XPU uses "xpu" device
            return "xpu"
        elif backend == Backend.MPS and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"
        else:
            return "cpu"
    except ImportError:
        return "cpu"


def ensure_backend_ready(backend: Optional[str] = None) -> str:
    """
    Ensure a backend is ready to use. Install PyTorch if needed.

    Args:
        backend: Preferred backend, or None to auto-detect

    Returns:
        The backend that was set up

    Raises:
        RuntimeError: If backend setup fails
    """
    # Check if torch already installed
    if check_torch_installed():
        if backend:
            setup_backend_environment(backend)
            return backend
        else:
            # Auto-detect and return first available
            available = detect_available_backends()
            if available:
                setup_backend_environment(available[0])
                return available[0]
            return Backend.CPU

    # Torch not installed - need to install
    available_backends = detect_available_backends()

    if backend is None:
        # Interactive selection
        backend = prompt_backend_selection(available_backends)
        if backend is None:
            raise RuntimeError("Backend selection cancelled")

    if backend not in available_backends:
        logger.warning(f"Requested backend '{backend}' not available. Using CPU.")
        backend = Backend.CPU

    # Install PyTorch
    if not install_pytorch(backend):
        raise RuntimeError(f"Failed to install PyTorch for backend: {backend}")

    # Save to config
    save_backend_to_config(backend)

    # Set up environment
    setup_backend_environment(backend)

    return backend

#!/usr/bin/env python3
"""
ML Backend Setup Script for ChibiBooru

This script handles the installation of PyTorch and related packages
for the correct backend (XPU, CUDA, or CPU).

Run this script after installing base requirements:
    python setup_ml.py

The script will:
1. Detect available hardware
2. Prompt for backend selection (or use ML_WORKER_BACKEND from .env)
3. Install the correct PyTorch version
4. Save the backend choice to .env
"""

import os
import sys
import subprocess
import shutil

def run_command(command, check=True):
    """Run a shell command"""
    print(f"  $ {command}")
    try:
        result = subprocess.run(command, shell=True, check=check, 
                                capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        if e.stderr:
            print(e.stderr)
        return False

def get_installer():
    """Get installer command: prefer uv pip when available, else python -m pip"""
    if shutil.which("uv"):
        return "uv pip"
    return f"{sys.executable} -m pip"

def detect_hardware():
    """Detect available GPU hardware"""
    print("\n🔍 Detecting hardware...")
    hardware = []
    
    # Check for NVIDIA GPU
    try:
        result = subprocess.run("nvidia-smi", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            hardware.append("cuda")
            print("  ✓ NVIDIA GPU detected (CUDA)")
    except Exception:
        pass
    
    # Check for Intel GPU
    try:
        result = subprocess.run("lspci | grep -i 'vga\\|3d\\|display' | grep -i intel", 
                               shell=True, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            # Check for discrete Intel GPU (Arc)
            if "arc" in result.stdout.lower() or any(x in result.stdout.lower() 
                for x in ['a310', 'a380', 'a580', 'a750', 'a770', 'b570', 'b580']):
                hardware.append("xpu")
                print("  ✓ Intel Arc GPU detected (XPU)")
            else:
                print("  ⚠ Intel integrated graphics detected (XPU may work)")
                hardware.append("xpu")
    except Exception:
        pass
    
    # CPU is always available
    hardware.append("cpu")
    print("  ✓ CPU always available")
    
    return hardware

def get_current_backend():
    """Read current backend from .env file"""
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('ML_WORKER_BACKEND='):
                    return line.split('=', 1)[1].strip()
    return None

def save_backend(backend):
    """Save backend choice to .env file"""
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    lines = []
    found = False
    
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('ML_WORKER_BACKEND='):
                    lines.append(f'ML_WORKER_BACKEND={backend}\n')
                    found = True
                else:
                    lines.append(line)
    
    if not found:
        lines.append(f'ML_WORKER_BACKEND={backend}\n')
    
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print(f"  ✓ Saved ML_WORKER_BACKEND={backend} to .env")

def uninstall_torch():
    """Uninstall existing PyTorch packages"""
    print("\n🗑️  Removing existing PyTorch installation...")
    installer = get_installer()
    # Ignore errors if not installed
    subprocess.run(f"{installer} uninstall -y torch torchvision torchaudio intel-extension-for-pytorch 2>/dev/null",
                   shell=True, capture_output=True)
    return True

def install_torch(backend):
    """Install PyTorch for the specified backend"""
    installer = get_installer()
    
    print(f"\n📦 Installing PyTorch for {backend.upper()}...")
    
    if backend == "xpu":
        # Intel XPU requires PyTorch nightly
        print("  Using PyTorch nightly for Intel XPU support")
        cmd = f"{installer} install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/xpu"
        
    elif backend == "cuda":
        # CUDA uses stable PyTorch with CUDA support
        print("  Using PyTorch stable with CUDA 12.4")
        cmd = f"{installer} install torch torchvision --index-url https://download.pytorch.org/whl/cu124"
        
    elif backend == "cpu":
        # CPU-only version
        print("  Using PyTorch stable (CPU only)")
        cmd = f"{installer} install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
        
    else:
        print(f"  ❌ Unknown backend: {backend}")
        return False
    
    return run_command(cmd)

def verify_installation(backend):
    """Verify the PyTorch installation works"""
    print(f"\n✅ Verifying {backend.upper()} installation...")
    
    verify_script = f"""
import torch
print(f"  PyTorch version: {{torch.__version__}}")

if "{backend}" == "xpu":
    if hasattr(torch, 'xpu') and torch.xpu.is_available():
        print(f"  XPU available: True")
        print(f"  XPU device: {{torch.xpu.get_device_name(0)}}")
    else:
        print("  ❌ XPU not available!")
        exit(1)
elif "{backend}" == "cuda":
    if torch.cuda.is_available():
        print(f"  CUDA available: True")
        print(f"  CUDA device: {{torch.cuda.get_device_name(0)}}")
    else:
        print("  ❌ CUDA not available!")
        exit(1)
else:
    print("  CPU mode - no GPU acceleration")

print("  ✓ Installation verified!")
"""
    
    result = subprocess.run([sys.executable, "-c", verify_script], 
                           capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    return result.returncode == 0

def main():
    print("=" * 60)
    print("  ChibiBooru ML Backend Setup")
    print("=" * 60)
    
    # Check if running in venv
    if sys.prefix == sys.base_prefix:
        print("\n⚠️  Warning: Not running in a virtual environment!")
        print("   Activate venv first: source venv/bin/activate")
    
    # Detect hardware
    available = detect_hardware()
    
    # Check for existing backend in .env
    current = get_current_backend()
    if current:
        print(f"\n📋 Current backend in .env: {current.upper()}")
    
    # Check for non-interactive mode (use .env value or auto-detect)
    if os.environ.get('NON_INTERACTIVE') == '1':
        if current:
            backend = current
            print(f"  Using existing backend: {backend}")
        else:
            # Auto-select best available
            for pref in ['xpu', 'cuda', 'cpu']:
                if pref in available:
                    backend = pref
                    break
            print(f"  Auto-selected backend: {backend}")
    else:
        # Interactive mode
        print("\n🎯 Select ML backend:")
        print("   1) Intel XPU (Arc A/B-Series GPUs) - Recommended for Intel")
        print("   2) NVIDIA CUDA")
        print("   3) CPU Only (no GPU acceleration)")
        
        default = current or (available[0] if available else 'cpu')
        choice = input(f"\n   Enter choice [1-3] (default: {default}): ").strip()
        
        if choice == "1":
            backend = "xpu"
        elif choice == "2":
            backend = "cuda"
        elif choice == "3":
            backend = "cpu"
        elif choice == "":
            backend = default
        else:
            print("   Invalid choice. Using CPU.")
            backend = "cpu"
    
    print(f"\n🎯 Selected backend: {backend.upper()}")
    
    # Uninstall existing torch
    uninstall_torch()
    
    # Install torch for backend
    if not install_torch(backend):
        print("\n❌ Installation failed!")
        return 1
    
    # Save to .env
    save_backend(backend)
    
    # Verify installation
    if not verify_installation(backend):
        print("\n⚠️  Verification failed, but installation may still work.")
        print("   Try restarting the application.")
    
    print("\n" + "=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print(f"\n  Backend: {backend.upper()}")
    print("  You can now start the application with: ./start_booru.sh")
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

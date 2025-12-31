import os
import sys
import subprocess
import shutil
from pathlib import Path

# Constants
BASE_DIR = Path(__file__).parent.absolute()
ENV_FILE = BASE_DIR / ".env"

def run_command(command, shell=True):
    try:
        print(f"Running: {command}")
        subprocess.check_call(command, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        sys.exit(1)

def get_env_variable(var_name):
    if not ENV_FILE.exists():
        return None
    
    with open(ENV_FILE, 'r') as f:
        for line in f:
            if line.strip().startswith(f"{var_name}="):
                return line.strip().split('=', 1)[1]
    return None

def set_env_variable(var_name, value):
    lines = []
    if ENV_FILE.exists():
        with open(ENV_FILE, 'r') as f:
            lines = f.readlines()
    
    new_lines = []
    found = False
    for line in lines:
        if line.strip().startswith(f"{var_name}="):
            new_lines.append(f"{var_name}={value}\n")
            found = True
        else:
            new_lines.append(line)
    
    if not found:
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        new_lines.append(f"{var_name}={value}\n")
    
    with open(ENV_FILE, 'w') as f:
        f.writelines(new_lines)

def detect_hardware():
    print("Detecting hardware...")
    
    if sys.platform == "darwin":
        import platform
        if platform.machine() == "arm64":
            print("Found Apple Silicon.")
            return "mps"
    
    # Simple lspci check for Linux
    try:
        lspci_out = subprocess.check_output("lspci", shell=True).decode().lower()
        if "nvidia" in lspci_out:
            print("Found NVIDIA GPU.")
            return "cuda"
        if "intel" in lspci_out and ("vga" in lspci_out or "display" in lspci_out or "3d" in lspci_out):
            print("Found Intel GPU.")
            return "xpu"
    except Exception as e:
        pass
    
    return "cpu"

def install_torch(mode):
    print(f"\nInstalling PyTorch for mode: {mode.upper()}...")
    
    # Common uninstall to ensure clean slate
    print("Uninstalling existing PyTorch packages...")
    subprocess.call([sys.executable, "-m", "pip", "uninstall", "-y", "torch", "torchvision", "intel-extension-for-pytorch", "torchaudio"])

    if mode == "xpu":
        print("Installing PyTorch Nightly for Intel XPU...")
        run_command(f"{sys.executable} -m pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/xpu")
    
    elif mode == "cuda":
        print("Installing PyTorch Stable for CUDA...")
        run_command(f"{sys.executable} -m pip install torch torchvision")
        
    elif mode == "mps":
        print("Installing PyTorch for Apple Silicon...")
        run_command(f"{sys.executable} -m pip install torch torchvision")

    elif mode == "cpu":
        print("Installing PyTorch for CPU...")
        run_command(f"{sys.executable} -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu")
    
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)

def main():
    print("=== ML Backend Setup ===")
    
    # Check if backend is already configured
    current_backend = get_env_variable("ML_WORKER_BACKEND")
    
    if current_backend:
        print(f"Backend already configured in .env: {current_backend}")
        # Verify if torch is installed and matches
        try:
            import torch
            print(f"PyTorch {torch.__version__} is installed.")
            # Basic sanity check
            if current_backend == "xpu":
                # For modern PyTorch Nightly with XPU, it's often built-in.
                # Only import ipex if we suspect we are on an older version or specific setup.
                # But safer to check torch.xpu availability.
                if hasattr(torch, 'xpu') and torch.xpu.is_available():
                    print("XPU is available via torch.xpu.")
                else:
                    # Fallback check for extension
                    try:
                        import intel_extension_for_pytorch
                        print("Intel Extension for PyTorch is installed.")
                    except ImportError:
                        print("WARNING: XPU selected but torch.xpu not available and ipex not found. Proceeding tentatively.")
                        
            elif current_backend == "cuda":
                if not torch.cuda.is_available():
                    print("WARNING: CUDA backend selected but torch.cuda.is_available() is False.")
            
            # If we get here, assume it's good enough to maintain current state
            # unless user forces reinstall (could add a flag later)
            print("Setup appears complete.")
            return
        except ImportError as e:
            print(f"Check failed: {e}")
            print("PyTorch or backend extension not installed/working. Reinstalling...")
            install_torch(current_backend)
            return

    else:
        print("No backend configured.")
        detected = detect_hardware()
        print(f"\nDetected best match: {detected.upper()}")
        
        print("\nPlease select your ML backend:")
        print(f"1) Intel XPU (Arc A-Series / B-Series){' (Detected)' if detected == 'xpu' else ''}")
        print(f"2) NVIDIA CUDA{' (Detected)' if detected == 'cuda' else ''}")
        # Note: OpenVINO is automatically used if XPU is selected (via ipex or onnx provider)
        print(f"3) Apple Silicon (MPS){' (Detected)' if detected == 'mps' else ''}")
        print("4) CPU Only (Not Recommended)")
        
        while True:
            choice = input(f"Enter choice [1-4] (default matches detection): ").strip()
            
            if choice == "1":
                mode = "xpu"
                break
            elif choice == "2":
                mode = "cuda"
                break
            elif choice == "3":
                mode = "mps"
                break
            elif choice == "4":
                mode = "cpu"
                break
            elif choice == "":
                mode = detected
                break
            else:
                print("Invalid choice. Try again.")
        
        print(f"\nSelected backend: {mode}")
        set_env_variable("ML_WORKER_BACKEND", mode)
        install_torch(mode)

    print("\n=== ML Setup Complete ===")

if __name__ == "__main__":
    main()

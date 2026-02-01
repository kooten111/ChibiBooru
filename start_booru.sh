#!/bin/bash
# Start the Booru application with uvicorn and standalone monitor process

cd "$(dirname "$0")"

# Optional: force venv rebuild (e.g. ./start_booru.sh --rebuild-venv)
for arg in "$@"; do
    if [ "$arg" = "--rebuild-venv" ]; then
        if [ -d "venv" ]; then
            echo "Removing existing venv (--rebuild-venv)..."
            rm -rf venv
        fi
        break
    fi
done

# Python 3.10–3.12 required (onnxruntime and dependencies)
check_python_version() {
    python${1:-} -c '
import sys
v = sys.version_info
ok = (3, 10) <= (v.major, v.minor) <= (3, 12)
sys.exit(0 if ok else 1)
' 2>/dev/null
}

# If we will create a new venv, ensure python3 is in range before creating
if [ ! -d "venv" ]; then
    if ! check_python_version 3; then
        echo "ChibiBooru requires Python 3.10–3.12. Current: $(python3 --version 2>&1)."
        echo "To use a supported version with pyenv: pyenv install 3.12.2 && pyenv local 3.12.2, then run ./start_booru.sh again."
        exit 1
    fi
    echo "Creating virtual environment..."
    if command -v uv >/dev/null 2>&1; then
        uv venv venv --python python3
    else
        python3 -m venv venv
    fi
fi

# Activate virtual environment
source venv/bin/activate

# Ensure activated Python is in range (catches existing venv created with wrong version)
if ! check_python_version; then
    echo "ChibiBooru requires Python 3.10–3.12. Current: $(python --version 2>&1)."
    echo "Recreate the venv with a supported Python, e.g. with pyenv: pyenv install 3.12.2 && pyenv local 3.12.2, then run ./start_booru.sh --rebuild-venv."
    exit 1
fi

# Prefer uv when available (faster installs)
USE_UV=false
if command -v uv >/dev/null 2>&1; then
    USE_UV=true
fi

# Setup flags: run wizard and/or install+ML setup when .env or torch is missing
NEEDS_ENV=false
NEEDS_TORCH=false
[ ! -f ".env" ] && NEEDS_ENV=true
if ! python -c "import torch" 2>/dev/null; then
    NEEDS_TORCH=true
fi

# Install base dependencies only when torch is missing (venv assumed correct otherwise)
if [ "$NEEDS_TORCH" = true ]; then
    echo "Running initial setup (torch missing)..."
    if [ "$USE_UV" = true ]; then
        if ! uv pip install -r requirements.txt; then
            echo ""
            echo "Dependency installation failed. Fix the error above (e.g. use Python 3.10–3.12 if onnxruntime fails) and run ./start_booru.sh again."
            exit 1
        fi
    else
        pip install --upgrade pip -q
        if ! pip install -r requirements.txt; then
            echo ""
            echo "Dependency installation failed. Fix the error above (e.g. use Python 3.10–3.12 if onnxruntime fails) and run ./start_booru.sh again."
            exit 1
        fi
    fi
fi

# Populate .env (secrets, directories, optional models) when .env is missing
if [ "$NEEDS_ENV" = true ]; then
    python setup_wizard.py
fi

# ML backend selection and torch install when torch is missing
if [ "$NEEDS_TORCH" = true ]; then
    if [ "$NEEDS_ENV" = true ]; then
        python setup_ml.py
    else
        NON_INTERACTIVE=1 python setup_ml.py
    fi
fi

# Load environment variables from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Get host and port from environment or use defaults
HOST=${FLASK_HOST:-0.0.0.0}
PORT=${FLASK_PORT:-5000}
WORKERS=${UVICORN_WORKERS:-1}

echo "=========================================="
echo "Starting ChibiBooru"
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    # Avoid double cleanup
    if [ -z "$MONITOR_PID" ]; then
        return
    fi
    
    local pid=$MONITOR_PID
    MONITOR_PID=""  # Clear immediately to prevent double cleanup
    
    if kill -0 $pid 2>/dev/null; then
        echo "Stopping monitor..."
        kill $pid 2>/dev/null
        
        # Wait with timeout (max 5 seconds)
        local count=0
        while kill -0 $pid 2>/dev/null && [ $count -lt 50 ]; do
            sleep 0.1
            count=$((count + 1))
        done
        
        # Force kill if still running
        if kill -0 $pid 2>/dev/null; then
            echo "Force killing monitor..."
            kill -9 $pid 2>/dev/null
        fi
        
        echo "✓ Monitor stopped"
    fi
}

# Start monitor in background (standalone process)
echo "Starting monitor service..."
python monitor_runner.py &
MONITOR_PID=$!
echo "✓ Monitor started (PID: $MONITOR_PID)"

# Trap to ensure monitor is killed when script exits
# Use only INT and TERM (not EXIT) to avoid double cleanup on Ctrl+C
trap 'cleanup; exit 0' INT TERM

# Give monitor a moment to initialize
sleep 2

# Start uvicorn web server in foreground
echo "Starting web server on $HOST:$PORT with $WORKERS workers..."
echo "=========================================="
uvicorn app:create_app --factory --host $HOST --port $PORT --workers $WORKERS

# Note: cleanup happens automatically via trap


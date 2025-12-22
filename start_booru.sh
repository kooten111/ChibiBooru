#!/bin/bash
# Start the Booru application with uvicorn and standalone monitor process

cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Load environment variables from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Get host and port from environment or use defaults
HOST=${FLASK_HOST:-0.0.0.0}
PORT=${FLASK_PORT:-5000}
WORKERS=${UVICORN_WORKERS:-4}

echo "=========================================="
echo "Starting ChibiBooru"
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    if [ -n "$MONITOR_PID" ] && kill -0 $MONITOR_PID 2>/dev/null; then
        echo "Stopping monitor..."
        kill $MONITOR_PID 2>/dev/null
        wait $MONITOR_PID 2>/dev/null
        echo "✓ Monitor stopped"
    fi
}

# Start monitor in background (standalone process)
echo "Starting monitor service..."
python monitor_runner.py &
MONITOR_PID=$!
echo "✓ Monitor started (PID: $MONITOR_PID)"

# Trap to ensure monitor is killed when script exits
# This handles Ctrl+C, script termination, or any exit
trap cleanup INT TERM EXIT

# Give monitor a moment to initialize
sleep 2

# Start uvicorn web server in foreground
echo "Starting web server on $HOST:$PORT with $WORKERS workers..."
echo "=========================================="
uvicorn app:create_app --factory --host $HOST --port $PORT --workers $WORKERS

# Note: cleanup happens automatically via trap


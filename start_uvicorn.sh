#!/bin/bash
# Start the Booru application with uvicorn

# Activate virtual environment
source venv/bin/activate

# Load environment variables from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Get host and port from environment or use defaults
HOST=${FLASK_HOST:-0.0.0.0}
PORT=${FLASK_PORT:-5000}

# Start uvicorn with hot reload
# Exclude temporary file directories from reload monitoring to prevent crashes
echo "Starting Booru with uvicorn on $HOST:$PORT"
uvicorn app:create_app --factory --host $HOST --port $PORT --reload --reload-exclude 'ingest/*' --reload-exclude 'storage/*'

# Alternative without reload (for production):
# uvicorn app:create_app --factory --host $HOST --port $PORT --workers 4

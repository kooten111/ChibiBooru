"""
ML Worker Server

Subprocess that handles ML framework operations in isolation from the main application.
Auto-terminates after idle timeout to save memory.

Run as: python -m ml_worker.server
"""

import os
import os
import sys

# Monkeypatch os.exit if it doesn't exist (Python 3) to fix broken libraries
# specifically intel_extension_for_pytorch v2.8 which calls os.exit(127) on version mismatch
if not hasattr(os, 'exit'):
    def _fake_exit(code):
        raise ImportError(f"Library attempted to exit with code {code} (compatibility check failed)")
    os.exit = _fake_exit

import socket
import signal
import time
import threading
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ml_worker.protocol import (
    Message, Request, Response, RequestType, validate_request
)
from ml_worker.backends import ensure_backend_ready
from ml_worker import models
from ml_worker.jobs import handle_get_job_status
from ml_worker.handlers import (
    handle_extract_animation,
    handle_generate_thumbnail,
    handle_tag_image,
    handle_tag_video,
    handle_upscale_image,
    handle_compute_similarity,
    handle_train_rating_model,
    handle_infer_ratings,
    handle_health_check,
    handle_rebuild_cache
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [ML Worker] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# Global state
_last_request_time = time.time()
_shutdown_requested = False
_idle_timeout = 300  # 5 minute default (matches env var default)
_socket_path = '/tmp/chibibooru_ml_worker.sock'


def update_activity():
    """Update the last activity timestamp"""
    global _last_request_time
    _last_request_time = time.time()


def get_idle_time() -> float:
    """Get current idle time in seconds"""
    return time.time() - _last_request_time


def should_shutdown() -> bool:
    """Check if worker should shutdown due to inactivity"""
    from ml_worker.jobs import get_active_jobs_count
    
    # 1. Check idle timeout
    is_idle = get_idle_time() > _idle_timeout
    
    # 2. Check for active jobs
    # If any job is running or pending, do NOT shutdown
    has_active_jobs = get_active_jobs_count() > 0
    
    if has_active_jobs:
        # Effectively reset idle timer if working
        update_activity()
        return False
        
    # 3. Check for active client connections
    # Each client handler runs in a separate thread.
    # MainThread + IdleMonitor thread = 2 threads minimum.
    # If active_count > 2, we have clients connected.
    active_threads = threading.active_count()
    if active_threads > 2:
        # Update activity to keep alive
        # update_activity() # Optional, but good practice
        return False

    return is_idle


from services import similarity_service
class LocalSemanticBackend(similarity_service.SemanticBackend):
    """
    Local backend for when running INSIDE the worker process.
    Calls the handler functions directly instead of going through IPC.
    """
    def is_available(self) -> bool:
        return True
        
    def get_embedding(self, image_path: str, model_path: str) -> Optional[np.ndarray]:
        try:
            # Call handler directly
            result = handle_compute_similarity({
                'image_path': image_path,
                'model_path': model_path
            })
            embedding = result['embedding']
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            logger.error(f"Local backend embedding failed: {e}")
            return None
            
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        # This isn't actually used by the worker usually (worker computes embeddings, not searches)
        # But if it were, we'd need a search handler or access the DB directly.
        # Since the worker HAS access to the DB code (it imports services), it technically could.
        # But usually search happens in main process.
        # We'll leave this empty or implementing partial if needed.
        logger.warning("LocalSemanticBackend.search_similar called inside worker - not implemented/needed usually")
        return []


def handle_request(request: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
    """
    Handle a request message.

    Args:
        request: Request message dict
        progress_callback: Optional function(current, total, message)

    Returns:
        Response message dict
    """
    update_activity()

    request_id = request.get('id', 'unknown')
    request_type = request.get('type')
    request_data = request.get('data', {})

    logger.info(f"Handling request {request_id}: {request_type}")

    result = None
    try:
        if request_type == RequestType.TAG_IMAGE.value:
            result = handle_tag_image(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.UPSCALE_IMAGE.value:
            # Pass progress callback to upscaler
            result = handle_upscale_image(request_data, progress_callback=progress_callback)
            return Response.success(request_id, result)

        elif request_type == RequestType.COMPUTE_SIMILARITY.value:
            result = handle_compute_similarity(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.HEALTH_CHECK.value:
            result = handle_health_check(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.TRAIN_RATING_MODEL.value:
            result = handle_train_rating_model(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.INFER_RATINGS.value:
            result = handle_infer_ratings(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.GET_JOB_STATUS.value:
            result = handle_get_job_status(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.REBUILD_CACHE.value:
            result = handle_rebuild_cache(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.EXTRACT_ANIMATION.value:
            result = handle_extract_animation(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.TAG_VIDEO.value:
            result = handle_tag_video(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.GENERATE_THUMBNAIL.value:
            result = handle_generate_thumbnail(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.SHUTDOWN.value:
            logger.info("Shutdown requested")
            global _shutdown_requested
            _shutdown_requested = True
            return Response.success(request_id, {"message": "Shutting down"})

        else:
            return Response.error(request_id, f"Unknown request type: {request_type}")

    except Exception as e:
        logger.error(f"Error handling request {request_id}: {e}", exc_info=True)
        return Response.from_exception(request_id, e)
    finally:
        # Reset idle timer after any request completes (success or failure)
        update_activity()


def handle_client(client_socket: socket.socket):
    """Handle a client connection"""
    try:
        while True:
            # Receive request
            try:
                request = Message.recv_message(client_socket, timeout=1.0)
            except socket.timeout:
                continue
            except ConnectionError:
                break

            if not validate_request(request):
                logger.warning(f"Invalid request received: {request}")
                response = Response.error("unknown", "Invalid request format")
                Message.send_message(client_socket, response)
            else:
                # Define progress callback
                def send_progress(current, total, message=""):
                    try:
                        resp = Response.progress(request.get('id'), current, total, message)
                        Message.send_message(client_socket, resp)
                    except Exception as e:
                        logger.warning(f"Failed to send progress update: {e}")

                response = handle_request(request, progress_callback=send_progress)
                # Send response
                Message.send_message(client_socket, response)

            # Check if shutdown requested
            if _shutdown_requested:
                break

    except Exception as e:
        logger.error(f"Error in client handler: {e}", exc_info=True)
    finally:
        try:
            client_socket.close()
        except:
            pass


def idle_monitor():
    """Background thread that monitors idle time and triggers shutdown"""
    global _shutdown_requested
    
    while not _shutdown_requested:
        time.sleep(30)  # Check every 30 seconds

        if should_shutdown():
            logger.info(f"Idle timeout reached ({_idle_timeout}s). Shutting down.")
            _shutdown_requested = True
            break


def cleanup_socket():
    """Remove socket file if it exists"""
    if os.path.exists(_socket_path):
        try:
            os.unlink(_socket_path)
            logger.info(f"Removed existing socket: {_socket_path}")
        except OSError as e:
            logger.warning(f"Failed to remove socket: {e}")


def run_server():
    """Main server loop"""
    global _idle_timeout, _socket_path

    # Check all dependencies are installed FIRST
    logger.info("Checking ML dependencies...")
    if not models.check_dependencies():
        logger.error("ML Worker cannot start due to missing dependencies.")
        return 1

    # Get config from environment
    _idle_timeout = int(os.environ.get('ML_WORKER_IDLE_TIMEOUT', 300))
    _socket_path = os.environ.get('ML_WORKER_SOCKET', '/tmp/chibibooru_ml_worker.sock')
    # Ensure backend is ready (strict mode)
    try:
        backend = ensure_backend_ready()
        logger.info(f"Backend strictly configured: {backend}")
        
        # Inject LocalSemanticBackend so worker uses itself for embeddings/search
        similarity_service.set_semantic_backend(LocalSemanticBackend())
        logger.info("Injected LocalSemanticBackend for worker process")
        
    except Exception as e:
        logger.error(f"Failed to set up backend: {e}")
        return 1

    # Clean up old socket
    cleanup_socket()

    # Create Unix domain socket
    server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server_socket.bind(_socket_path)
    server_socket.listen(5)
    server_socket.settimeout(1.0)  # Allow checking shutdown flag

    logger.info("Server listening for connections")

    # Start idle monitor thread
    monitor_thread = threading.Thread(target=idle_monitor, daemon=True)
    monitor_thread.start()

    # Main server loop
    try:
        while not _shutdown_requested:
            try:
                client_socket, _ = server_socket.accept()
                logger.info("Client connected")

                # Handle client in a thread
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket,),
                    daemon=True
                )
                client_thread.start()

            except socket.timeout:
                continue
            except Exception as e:
                if not _shutdown_requested:
                    logger.error(f"Error accepting connection: {e}")
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        logger.info("Shutting down server")
        server_socket.close()
        cleanup_socket()

    logger.info("Server stopped")
    return 0


if __name__ == '__main__':
    sys.exit(run_server())
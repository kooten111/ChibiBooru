"""
ML Worker Client

Client API for communicating with the ML worker subprocess.
Handles process spawning, connection management, and request routing.
"""

import os
import sys
import socket
import subprocess
import time
import uuid
import logging
import threading
import atexit
import signal
from pathlib import Path
from typing import Dict, Any, Optional, List

from ml_worker.protocol import Message, Request, Response, RequestType, ResponseStatus

logger = logging.getLogger(__name__)


class MLWorkerError(Exception):
    """Base exception for ML worker errors"""
    pass


class MLWorkerConnectionError(MLWorkerError):
    """Worker connection failed"""
    pass


class MLWorkerTimeoutError(MLWorkerError):
    """Worker request timed out"""
    pass


class MLWorkerClient:
    """
    Client for communicating with ML worker subprocess.

    Automatically spawns worker if not running and handles connection pooling.
    """

    def __init__(self, socket_path: Optional[str] = None,
                 timeout: float = 300.0,
                 max_retries: int = 3):
        """
        Initialize ML worker client.

        Args:
            socket_path: Path to Unix domain socket (default from env)
            timeout: Request timeout in seconds
            max_retries: Max connection retry attempts
        """
        self.socket_path = socket_path or os.environ.get(
            'ML_WORKER_SOCKET',
            '/tmp/chibibooru_ml_worker.sock'
        )
        self.timeout = timeout
        self.max_retries = max_retries

        self._worker_process: Optional[subprocess.Popen] = None
        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        
        # Register cleanup handlers
        atexit.register(self._cleanup_worker)
        
        logger.info(f"ML Worker Client initialized (socket: {self.socket_path})")
    
    def _cleanup_worker(self):
        """Terminate the ML worker process"""
        if self._worker_process:
            try:
                self._worker_process.terminate()
                self._worker_process.wait(timeout=5)
                logger.info("ML worker terminated cleanly")
            except subprocess.TimeoutExpired:
                self._worker_process.kill()
                logger.warning("ML worker killed (didn't respond to terminate)")
            except Exception as e:
                logger.error(f"Error cleaning up ML worker: {e}")
            finally:
                self._worker_process = None

    def _is_worker_running(self) -> bool:
        """Check if worker process is running"""
        # Check if socket exists and responds
        if not os.path.exists(self.socket_path):
            return False

        try:
            # Try to connect
            test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            test_sock.settimeout(1.0)
            test_sock.connect(self.socket_path)
            test_sock.close()
            return True
        except (socket.error, socket.timeout, ConnectionRefusedError):
            return False

    def _spawn_worker(self) -> bool:
        """
        Spawn the ML worker process.

        Returns:
            True if worker spawned successfully
        """
        logger.info("Spawning ML worker process...")

        # Get Python executable
        python_exe = sys.executable

        # Get worker module path
        worker_module = 'ml_worker.server'

        # Set environment variables for worker
        env = os.environ.copy()

        # Start worker process
        try:
            self._worker_process = subprocess.Popen(
                [python_exe, '-m', worker_module],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL
            )

            # Wait for socket to appear (up to 10 seconds)
            for i in range(100):
                if os.path.exists(self.socket_path):
                    # Socket exists, try to connect
                    if self._is_worker_running():
                        logger.info(f"ML worker spawned successfully (PID: {self._worker_process.pid})")
                        return True
                time.sleep(0.1)

            # Timeout waiting for socket
            logger.error("ML worker failed to start (timeout waiting for socket)")
            if self._worker_process:
                self._worker_process.terminate()
                self._worker_process = None
            return False

        except Exception as e:
            logger.error(f"Failed to spawn ML worker: {e}")
            return False

    def _connect(self) -> socket.socket:
        """
        Connect to the ML worker.

        Returns:
            Connected socket

        Raises:
            MLWorkerConnectionError: If connection fails
        """
        # Check if worker is running
        if not self._is_worker_running():
            logger.info("ML worker not running, spawning...")
            if not self._spawn_worker():
                raise MLWorkerConnectionError("Failed to spawn ML worker")

        # Connect to socket
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect(self.socket_path)
            return sock
        except Exception as e:
            raise MLWorkerConnectionError(f"Failed to connect to ML worker: {e}")

    def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a request to the worker and receive response.

        Args:
            request: Request message dict

        Returns:
            Response data

        Raises:
            MLWorkerError: If request fails
        """
        for attempt in range(self.max_retries):
            try:
                with self._lock:
                    # Connect (or reconnect)
                    sock = self._connect()

                    try:
                        # Send request
                        Message.send_message(sock, request)

                        # Receive response
                        response = Message.recv_message(sock, timeout=self.timeout)

                        # Check response status
                        if response['status'] == ResponseStatus.SUCCESS.value:
                            return response['data']
                        else:
                            error_msg = response.get('error', 'Unknown error')
                            traceback_str = response.get('traceback')
                            if traceback_str:
                                logger.error(f"Worker error traceback:\n{traceback_str}")
                            raise MLWorkerError(f"Worker error: {error_msg}")

                    finally:
                        sock.close()

            except socket.timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    raise MLWorkerTimeoutError(f"Request timed out after {self.timeout}s")

            except (ConnectionError, BrokenPipeError, MLWorkerConnectionError) as e:
                logger.warning(f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}")
                # Worker might have crashed, try to respawn
                if attempt < self.max_retries - 1:
                    time.sleep(0.5)  # Brief delay before retry
                    continue
                else:
                    raise MLWorkerConnectionError(f"Connection failed after {self.max_retries} attempts")

        raise MLWorkerError("Max retries exceeded")

    def tag_image(self, image_path: str, model_path: str,
                  threshold: float = 0.35,
                  character_threshold: float = 0.85,
                  metadata_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Tag an image using the local tagger model.

        Args:
            image_path: Path to image file
            model_path: Path to ONNX model file
            threshold: Confidence threshold for general tags
            character_threshold: Confidence threshold for character tags
            metadata_path: Optional path to metadata JSON

        Returns:
            Dict with:
                - tags: Dict[category, List[str]] - Tags by category
                - all_predictions: List[dict] - All predictions with confidence
                - tagger_name: str - Name of tagger model

        Raises:
            MLWorkerError: If tagging fails
        """
        request_id = str(uuid.uuid4())

        request_data = {
            "image_path": image_path,
            "model_path": model_path,
            "threshold": threshold,
            "character_threshold": character_threshold
        }

        if metadata_path:
            request_data["metadata_path"] = metadata_path

        request = Request.tag_image(
            request_id,
            image_path,
            model_path,
            threshold,
            character_threshold
        )

        return self._send_request(request)

    def upscale_image(self, image_path: str, output_path: str,
                     model_name: str = 'RealESRGAN_x4plus_anime',
                     device: str = 'auto') -> Dict[str, Any]:
        """
        Upscale an image using RealESRGAN.

        Args:
            image_path: Path to input image
            output_path: Path to save upscaled image
            model_name: Name of upscaler model
            device: Device to use ('cuda', 'xpu', 'cpu', or 'auto')

        Returns:
            Dict with:
                - success: bool
                - output_path: str
                - original_size: Tuple[int, int]
                - upscaled_size: Tuple[int, int]

        Raises:
            MLWorkerError: If upscaling fails
        """
        request_id = str(uuid.uuid4())

        request = Request.upscale_image(
            request_id,
            image_path,
            model_name,
            output_path,
            device
        )

        return self._send_request(request)

    def compute_similarity(self, image_path: str,
                          model_path: str) -> Dict[str, Any]:
        """
        Compute semantic similarity embedding for an image.

        Args:
            image_path: Path to image file
            model_path: Path to similarity model

        Returns:
            Dict with:
                - embedding: List[float] - Feature vector

        Raises:
            MLWorkerError: If computation fails
        """
        request_id = str(uuid.uuid4())

        request = Request.compute_similarity(
            request_id,
            image_path,
            model_path
        )

        return self._send_request(request)

    def health_check(self) -> Dict[str, Any]:
        """
        Check worker health status.

        Returns:
            Dict with worker status information

        Raises:
            MLWorkerError: If health check fails
        """
        request_id = str(uuid.uuid4())
        request = Request.health_check(request_id)

        return self._send_request(request)

    def shutdown(self) -> bool:
        """
        Request worker shutdown.

        Returns:
            True if shutdown requested successfully
        """
        try:
            request_id = str(uuid.uuid4())
            request = Request.shutdown(request_id)
            self._send_request(request)
            return True
        except Exception as e:
            logger.warning(f"Failed to send shutdown request: {e}")
            return False

    def train_rating_model(self, timeout: float = 600.0) -> Dict[str, Any]:
        """
        Train rating inference model via ML Worker.

        Args:
            timeout: Request timeout in seconds (default 600s for training)

        Returns:
            Dict with training statistics

        Raises:
            MLWorkerError: If training fails
        """
        request_id = str(uuid.uuid4())
        request = Request.train_rating_model(request_id)

        # Temporarily increase timeout for this request
        old_timeout = self.timeout
        try:
            self.timeout = timeout
            return self._send_request(request)
        finally:
            self.timeout = old_timeout

    def infer_ratings(self, image_ids: List[int] = None, timeout: float = 600.0) -> Dict[str, Any]:
        """
        Run rating inference via ML Worker.

        Args:
            image_ids: List of image IDs to infer (None = all unrated)
            timeout: Request timeout in seconds (default 600s)

        Returns:
            Dict with inference statistics

        Raises:
            MLWorkerError: If inference fails
        """
        request_id = str(uuid.uuid4())
        request = Request.infer_ratings(request_id, image_ids)

        # Temporarily increase timeout for this request
        old_timeout = self.timeout
        try:
            self.timeout = timeout
            return self._send_request(request)
        finally:
            self.timeout = old_timeout

    def train_character_model(self, timeout: float = 600.0) -> Dict[str, Any]:
        """
        Train character inference model via ML Worker.

        Args:
            timeout: Request timeout in seconds (default 600s for training)

        Returns:
            Dict with training statistics

        Raises:
            MLWorkerError: If training fails
        """
        request_id = str(uuid.uuid4())
        request = Request.train_character_model(request_id)

        # Temporarily increase timeout for this request
        old_timeout = self.timeout
        try:
            self.timeout = timeout
            return self._send_request(request)
        finally:
            self.timeout = old_timeout

    def infer_characters(self, image_ids: List[int] = None, timeout: float = 600.0) -> Dict[str, Any]:
        """
        Run character inference via ML Worker.

        Args:
            image_ids: List of image IDs to infer (None = all untagged)
            timeout: Request timeout in seconds (default 600s)

        Returns:
            Dict with inference statistics

        Raises:
            MLWorkerError: If inference fails
        """
        request_id = str(uuid.uuid4())
        request = Request.infer_characters(request_id, image_ids)

        # Temporarily increase timeout for this request
        old_timeout = self.timeout
        try:
            self.timeout = timeout
            return self._send_request(request)
        finally:
            self.timeout = old_timeout

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a long-running job.

        Args:
            job_id: Job identifier

        Returns:
            Dict with job status information

        Raises:
            MLWorkerError: If status check fails
        """
        request_id = str(uuid.uuid4())
        request = Request.get_job_status(request_id, job_id)
        return self._send_request(request)

    def __del__(self):
        """Cleanup on deletion"""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        pass


# Global client instance (lazy initialization)
_global_client: Optional[MLWorkerClient] = None
_client_lock = threading.Lock()


def get_ml_worker_client() -> MLWorkerClient:
    """
    Get or create global ML worker client instance.

    Returns:
        MLWorkerClient instance
    """
    global _global_client

    if _global_client is None:
        with _client_lock:
            if _global_client is None:
                _global_client = MLWorkerClient()

    return _global_client

"""
ML Worker Communication Protocol

Defines JSON-based message format for IPC between client and worker server.
Messages are sent over Unix domain socket with length prefixing.
"""

import json
import struct
import socket
import traceback
from typing import Dict, Any, Optional
from enum import Enum


class RequestType(str, Enum):
    """Supported request types"""
    TAG_IMAGE = "tag_image"
    UPSCALE_IMAGE = "upscale_image"
    COMPUTE_SIMILARITY = "compute_similarity"
    HEALTH_CHECK = "health_check"
    SHUTDOWN = "shutdown"
    TRAIN_RATING_MODEL = "train_rating_model"
    INFER_RATINGS = "infer_ratings"
    GET_JOB_STATUS = "get_job_status"
    REBUILD_CACHE = "rebuild_cache"
    EXTRACT_ANIMATION = "extract_animation"
    TAG_VIDEO = "tag_video"
    GENERATE_THUMBNAIL = "generate_thumbnail"


class ResponseStatus(str, Enum):
    """Response status codes"""
    SUCCESS = "success"
    ERROR = "error"
    PROGRESS = "progress"


class Message:
    """Base message class for requests and responses"""

    @staticmethod
    def encode_message(msg_dict: Dict[str, Any]) -> bytes:
        """
        Encode a message dict to bytes with length prefix.

        Format: [4-byte length][JSON data]
        """
        json_bytes = json.dumps(msg_dict).encode('utf-8')
        length = len(json_bytes)
        return struct.pack('!I', length) + json_bytes

    @staticmethod
    def decode_message(data: bytes) -> Dict[str, Any]:
        """Decode a message from bytes"""
        return json.loads(data.decode('utf-8'))

    @staticmethod
    def send_message(sock: socket.socket, msg_dict: Dict[str, Any]) -> None:
        """Send a message over a socket"""
        encoded = Message.encode_message(msg_dict)
        sock.sendall(encoded)

    @staticmethod
    def recv_message(sock: socket.socket, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Receive a message from a socket.

        Args:
            sock: Socket to receive from
            timeout: Optional timeout in seconds

        Returns:
            Decoded message dict

        Raises:
            ConnectionError: If connection closed
            socket.timeout: If timeout exceeded
        """
        if timeout is not None:
            sock.settimeout(timeout)

        # Read 4-byte length prefix
        length_data = b''
        while len(length_data) < 4:
            chunk = sock.recv(4 - len(length_data))
            if not chunk:
                raise ConnectionError("Connection closed while reading length")
            length_data += chunk

        length = struct.unpack('!I', length_data)[0]

        # Read message data
        msg_data = b''
        while len(msg_data) < length:
            chunk = sock.recv(length - len(msg_data))
            if not chunk:
                raise ConnectionError("Connection closed while reading message")
            msg_data += chunk

        return Message.decode_message(msg_data)


class Request:
    """Request message builder"""

    @staticmethod
    def create(request_type: RequestType, request_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a request message.

        Args:
            request_type: Type of request
            request_id: Unique request identifier
            data: Request-specific data

        Returns:
            Request message dict
        """
        return {
            "type": request_type.value,
            "id": request_id,
            "data": data
        }

    @staticmethod
    def tag_image(request_id: str, image_path: str, model_path: str,
                  threshold: float = 0.35, character_threshold: float = 0.85,
                  storage_threshold: float = 0.50) -> Dict[str, Any]:
        """Create a tag_image request"""
        return Request.create(
            RequestType.TAG_IMAGE,
            request_id,
            {
                "image_path": image_path,
                "model_path": model_path,
                "threshold": threshold,
                "character_threshold": character_threshold,
                "storage_threshold": storage_threshold
            }
        )

    @staticmethod
    def upscale_image(request_id: str, image_path: str, model_name: str,
                     output_path: str, device: str = "auto") -> Dict[str, Any]:
        """Create an upscale_image request"""
        return Request.create(
            RequestType.UPSCALE_IMAGE,
            request_id,
            {
                "image_path": image_path,
                "model_name": model_name,
                "output_path": output_path,
                "device": device
            }
        )

    @staticmethod
    def compute_similarity(request_id: str, image_path: str,
                          model_path: str) -> Dict[str, Any]:
        """Create a compute_similarity request"""
        return Request.create(
            RequestType.COMPUTE_SIMILARITY,
            request_id,
            {
                "image_path": image_path,
                "model_path": model_path
            }
        )

    @staticmethod
    def health_check(request_id: str) -> Dict[str, Any]:
        """Create a health_check request"""
        return Request.create(
            RequestType.HEALTH_CHECK,
            request_id,
            {}
        )

    @staticmethod
    def shutdown(request_id: str) -> Dict[str, Any]:
        """Create a shutdown request"""
        return Request.create(
            RequestType.SHUTDOWN,
            request_id,
            {}
        )

    @staticmethod
    def train_rating_model(request_id: str) -> Dict[str, Any]:
        """Create a train_rating_model request"""
        return Request.create(
            RequestType.TRAIN_RATING_MODEL,
            request_id,
            {"job_id": request_id}
        )

    @staticmethod
    def infer_ratings(request_id: str, image_ids: list = None) -> Dict[str, Any]:
        """Create an infer_ratings request"""
        return Request.create(
            RequestType.INFER_RATINGS,
            request_id,
            {
                "image_ids": image_ids if image_ids is not None else [],
                "job_id": request_id
            }
        )

    @staticmethod
    def get_job_status(request_id: str, job_id: str) -> Dict[str, Any]:
        """Create a get_job_status request"""
        return Request.create(
            RequestType.GET_JOB_STATUS,
            request_id,
            {
                "job_id": job_id
            }
        )

    @staticmethod
    def rebuild_cache(request_id: str, similarity_type: str = 'blended') -> Dict[str, Any]:
        """Create a rebuild_cache request"""
        return Request.create(
            RequestType.REBUILD_CACHE,
            request_id,
            {
                "similarity_type": similarity_type
            }
        )

    @staticmethod
    def extract_animation(request_id: str, zip_path: str, output_dir: str) -> Dict[str, Any]:
        """Create an extract_animation request"""
        return Request.create(
            RequestType.EXTRACT_ANIMATION,
            request_id,
            {
                "zip_path": zip_path,
                "output_dir": output_dir
            }
        )

    @staticmethod
    def tag_video(request_id: str, video_path: str, num_frames: int = 5,
                  model_path: str = None, threshold: float = 0.35,
                  character_threshold: float = 0.85, metadata_path: str = None,
                  storage_threshold: float = 0.50) -> Dict[str, Any]:
        """Create a tag_video request"""
        return Request.create(
            RequestType.TAG_VIDEO,
            request_id,
            {
                "video_path": video_path,
                "num_frames": num_frames,
                "model_path": model_path,
                "threshold": threshold,
                "character_threshold": character_threshold,
                "metadata_path": metadata_path,
                "storage_threshold": storage_threshold
            }
        )

    @staticmethod
    def generate_thumbnail(request_id: str, filepath: str, output_path: str, size: int = 512, quality: int = 85) -> Dict[str, Any]:
        """Create a generate_thumbnail request"""
        return Request.create(
            RequestType.GENERATE_THUMBNAIL,
            request_id,
            {
                "filepath": filepath,
                "output_path": output_path,
                "size": size,
                "quality": quality
            }
        )


class Response:
    """Response message builder"""

    @staticmethod
    def create(request_id: str, status: ResponseStatus,
               data: Optional[Dict[str, Any]] = None,
               error: Optional[str] = None,
               traceback_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a response message.

        Args:
            request_id: Request ID this is responding to
            status: Response status
            data: Response data (for success)
            error: Error message (for error)
            traceback_str: Stack trace (for error)

        Returns:
            Response message dict
        """
        return {
            "id": request_id,
            "status": status.value,
            "data": data if data is not None else {},
            "error": error,
            "traceback": traceback_str
        }

    @staticmethod
    def success(request_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a success response"""
        return Response.create(request_id, ResponseStatus.SUCCESS, data=data)

    @staticmethod
    def error(request_id: str, error_msg: str,
              include_traceback: bool = True) -> Dict[str, Any]:
        """Create an error response"""
        tb = traceback.format_exc() if include_traceback else None
        return Response.create(
            request_id,
            ResponseStatus.ERROR,
            error=error_msg,
            traceback_str=tb
        )

    @staticmethod
    def from_exception(request_id: str, exc: Exception) -> Dict[str, Any]:
        """Create an error response from an exception"""
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        return Response.error(request_id, error_msg, include_traceback=True)

    @staticmethod
    def progress(request_id: str, current: int, total: int, message: str = "") -> Dict[str, Any]:
        """Create a progress response"""
        return Response.create(
            request_id,
            ResponseStatus.PROGRESS,
            data={
                "current": current,
                "total": total,
                "percentage": (current / total * 100) if total > 0 else 0,
                "message": message
            }
        )


def validate_request(msg: Dict[str, Any]) -> bool:
    """
    Validate that a message is a properly formatted request.

    Args:
        msg: Message dict to validate

    Returns:
        True if valid, False otherwise
    """
    required_fields = ['type', 'id', 'data']
    if not all(field in msg for field in required_fields):
        return False

    if msg['type'] not in [rt.value for rt in RequestType]:
        return False

    if not isinstance(msg['data'], dict):
        return False

    return True


def validate_response(msg: Dict[str, Any]) -> bool:
    """
    Validate that a message is a properly formatted response.

    Args:
        msg: Message dict to validate

    Returns:
        True if valid, False otherwise
    """
    required_fields = ['id', 'status', 'data']
    if not all(field in msg for field in required_fields):
        return False

    if msg['status'] not in [rs.value for rs in ResponseStatus]:
        return False

    return True

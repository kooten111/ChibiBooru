"""
ML Worker Server

Subprocess that handles ML framework operations in isolation from the main application.
Auto-terminates after idle timeout to save memory.

Run as: python -m ml_worker.server
"""

import os
import sys
import json
import socket
import signal
import time
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ml_worker.protocol import (
    Message, Request, Response, RequestType, ResponseStatus,
    validate_request
)
from ml_worker.backends import ensure_backend_ready, setup_backend_environment, get_torch_device

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
_idle_timeout = 300  # 5 minutes default
_socket_path = '/tmp/chibibooru_ml_worker.sock'

# ML models (lazy loaded)
_tagger_session = None
_tagger_metadata = None
_upscaler_model = None
_upscaler_device = None
_similarity_model = None


def update_activity():
    """Update the last activity timestamp"""
    global _last_request_time
    _last_request_time = time.time()


def get_idle_time() -> float:
    """Get current idle time in seconds"""
    return time.time() - _last_request_time


def should_shutdown() -> bool:
    """Check if worker should shutdown due to inactivity"""
    return get_idle_time() > _idle_timeout


def handle_tag_image(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tag_image request.

    Args:
        request_data: {image_path, model_path, threshold, character_threshold}

    Returns:
        Dict with tags and predictions
    """
    global _tagger_session, _tagger_metadata

    image_path = request_data['image_path']
    model_path = request_data['model_path']
    metadata_path = request_data.get('metadata_path', model_path.replace('.onnx', '_metadata.json'))
    threshold = request_data.get('threshold', 0.35)
    character_threshold = request_data.get('character_threshold', 0.85)

    logger.info(f"Tagging image: {os.path.basename(image_path)}")

    # Lazy load ONNX and torch
    import onnxruntime as ort
    import torchvision.transforms as transforms
    from PIL import Image
    import numpy as np

    # Load model if not already loaded
    if _tagger_session is None:
        logger.info(f"Loading tagger model from {model_path}")

        with open(metadata_path, 'r') as f:
            _tagger_metadata = json.load(f)

        providers = ['CPUExecutionProvider']
        _tagger_session = ort.InferenceSession(model_path, providers=providers)

        dataset_info = _tagger_metadata['dataset_info']
        logger.info(f"Tagger model loaded. Found {dataset_info['total_tags']} tags.")

    # Preprocess image
    image_size = _tagger_metadata.get('model_info', {}).get('img_size', 512)

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    with Image.open(image_path) as img:
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        width, height = img.size
        aspect_ratio = width / height

        if aspect_ratio > 1:
            new_width = image_size
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = image_size
            new_width = int(new_height * aspect_ratio)

        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        pad_color = (124, 116, 104)
        new_image = Image.new('RGB', (image_size, image_size), pad_color)
        new_image.paste(img, ((image_size - new_width) // 2, (image_size - new_height) // 2))

        img_numpy = transform(new_image).unsqueeze(0).numpy()

    # Run inference
    input_name = _tagger_session.get_inputs()[0].name
    raw_outputs = _tagger_session.run(None, {input_name: img_numpy})

    # Use refined predictions if available
    logits = raw_outputs[1] if len(raw_outputs) > 1 else raw_outputs[0]
    probs = 1.0 / (1.0 + np.exp(-logits))

    # Extract tags
    dataset_info = _tagger_metadata['dataset_info']
    tag_mapping = dataset_info['tag_mapping']
    idx_to_tag = tag_mapping['idx_to_tag']
    tag_to_category = tag_mapping['tag_to_category']

    storage_threshold = 0.10
    display_threshold = threshold

    all_predictions = []
    tags_by_category = {
        "general": [], "character": [], "copyright": [],
        "artist": [], "meta": [], "species": []
    }

    indices = np.where(probs[0] >= storage_threshold)[0]

    for idx in indices:
        idx_str = str(idx)
        tag_name = idx_to_tag.get(idx_str)
        if not tag_name:
            continue

        # Skip rating tags
        if tag_name.startswith('rating:') or tag_name.startswith('rating_'):
            continue

        category = tag_to_category.get(tag_name, "general")
        confidence = float(probs[0][idx])

        all_predictions.append({
            'tag_name': tag_name,
            'category': category,
            'confidence': confidence
        })

        if confidence >= display_threshold:
            if category in tags_by_category:
                tags_by_category[category].append(tag_name)
            else:
                tags_by_category["general"].append(tag_name)

    return {
        "tags": tags_by_category,
        "all_predictions": all_predictions,
        "tagger_name": _tagger_metadata.get('model_info', {}).get('name', 'Unknown')
    }


def handle_upscale_image(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle upscale_image request.

    Args:
        request_data: {image_path, model_name, output_path, device}

    Returns:
        Dict with success status and output path
    """
    global _upscaler_model, _upscaler_device

    image_path = request_data['image_path']
    model_name = request_data.get('model_name', 'RealESRGAN_x4plus_anime')
    output_path = request_data['output_path']
    device = request_data.get('device', 'auto')

    logger.info(f"Upscaling image: {os.path.basename(image_path)}")

    # Lazy load torch and dependencies
    import torch
    from PIL import Image
    import numpy as np

    # Import RRDBNet architecture
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.rrdbnet_arch import RRDBNet

    # Model configs
    MODEL_CONFIGS = {
        'RealESRGAN_x4plus': {'num_block': 23, 'num_feat': 64, 'num_grow_ch': 32},
        'RealESRGAN_x4plus_anime': {'num_block': 6, 'num_feat': 64, 'num_grow_ch': 32}
    }

    # Determine device
    if device == 'auto':
        backend = os.environ.get('ML_WORKER_BACKEND', 'cpu')
        device = get_torch_device(backend)

    _upscaler_device = device

    # Load model if not already loaded
    if _upscaler_model is None:
        logger.info(f"Loading upscaler model: {model_name} on {device}")

        model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS['RealESRGAN_x4plus'])
        model_dir = Path('./models/Upscaler')
        model_path = model_dir / f"{model_name}.pth"

        if not model_path.exists():
            raise FileNotFoundError(f"Upscaler model not found: {model_path}")

        _upscaler_model = RRDBNet(
            num_in_ch=3, num_out_ch=3,
            num_feat=model_config['num_feat'],
            num_block=model_config['num_block'],
            num_grow_ch=model_config['num_grow_ch'],
            scale=4
        )

        loadnet = torch.load(str(model_path), map_location=torch.device('cpu'), weights_only=True)

        if 'params_ema' in loadnet:
            keyname = 'params_ema'
        elif 'params' in loadnet:
            keyname = 'params'
        else:
            keyname = None

        if keyname:
            _upscaler_model.load_state_dict(loadnet[keyname], strict=True)
        else:
            _upscaler_model.load_state_dict(loadnet, strict=True)

        _upscaler_model.eval()
        _upscaler_model = _upscaler_model.to(device)

        if device != 'cpu':
            _upscaler_model = _upscaler_model.half()

        logger.info(f"Upscaler model loaded on {device}")

    # Load and preprocess image
    img = Image.open(image_path).convert('RGB')
    original_size = img.size

    img_np = np.array(img).astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(np.transpose(img_np, (2, 0, 1))).float().unsqueeze(0)
    img_tensor = img_tensor.to(_upscaler_device)

    if _upscaler_device != 'cpu':
        img_tensor = img_tensor.half()

    logger.info(f"Upscaler input tensor device: {img_tensor.device}")


    # Upscale
    with torch.no_grad():
        output = _upscaler_model(img_tensor)

    output = output.squeeze(0).cpu().float().numpy()
    output = np.transpose(output, (1, 2, 0))
    output = np.clip(output * 255.0, 0, 255).astype(np.uint8)

    # Save result
    output_img = Image.fromarray(output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    output_img.save(output_path)

    upscaled_size = output_img.size

    logger.info(f"Upscaling complete: {original_size} -> {upscaled_size}")

    return {
        "success": True,
        "output_path": output_path,
        "original_size": original_size,
        "upscaled_size": upscaled_size
    }


def handle_compute_similarity(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle compute_similarity request.

    Args:
        request_data: {image_path, model_path}

    Returns:
        Dict with embedding vector
    """
    global _similarity_model

    image_path = request_data['image_path']
    model_path = request_data['model_path']

    logger.info(f"Computing similarity for: {os.path.basename(image_path)}")

    # Lazy load ONNX
    import onnxruntime as ort
    from PIL import Image
    import numpy as np

    # Load model if not already loaded
    if _similarity_model is None:
        logger.info(f"Loading similarity model from {model_path}")
        providers = ['CPUExecutionProvider']
        _similarity_model = ort.InferenceSession(model_path, providers=providers)
        logger.info("Similarity model loaded")

    # Preprocess image (standard 224x224 for most models)
    img = Image.open(image_path).convert('RGB')
    img = img.resize((224, 224), Image.Resampling.LANCZOS)

    img_np = np.array(img).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    img_np = (img_np - mean) / std
    img_np = np.transpose(img_np, (2, 0, 1))
    img_np = np.expand_dims(img_np, axis=0)

    # Run inference
    input_name = _similarity_model.get_inputs()[0].name
    outputs = _similarity_model.run(None, {input_name: img_np})
    embedding = outputs[0][0]

    return {
        "embedding": embedding.tolist()
    }


def handle_health_check(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle health check request"""
    return {
        "status": "ok",
        "idle_time": get_idle_time(),
        "models_loaded": {
            "tagger": _tagger_session is not None,
            "upscaler": _upscaler_model is not None,
            "similarity": _similarity_model is not None
        }
    }


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a request message.

    Args:
        request: Request message dict

    Returns:
        Response message dict
    """
    update_activity()

    request_id = request.get('id', 'unknown')
    request_type = request.get('type')
    request_data = request.get('data', {})

    logger.info(f"Handling request {request_id}: {request_type}")

    try:
        if request_type == RequestType.TAG_IMAGE.value:
            result = handle_tag_image(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.UPSCALE_IMAGE.value:
            result = handle_upscale_image(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.COMPUTE_SIMILARITY.value:
            result = handle_compute_similarity(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.HEALTH_CHECK.value:
            result = handle_health_check(request_data)
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
            else:
                response = handle_request(request)

            # Send response
            Message.send_message(client_socket, response)

            # Check if shutdown requested
            if _shutdown_requested:
                break

    except Exception as e:
        logger.error(f"Error in client handler: {e}", exc_info=True)
    finally:
        client_socket.close()


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


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}. Shutting down gracefully.")
    global _shutdown_requested
    _shutdown_requested = True


def run_server():
    """Main server loop"""
    global _idle_timeout, _socket_path

    # Get config from environment
    _idle_timeout = int(os.environ.get('ML_WORKER_IDLE_TIMEOUT', 300))
    _socket_path = os.environ.get('ML_WORKER_SOCKET', '/tmp/chibibooru_ml_worker.sock')
    backend = os.environ.get('ML_WORKER_BACKEND', 'auto')

    logger.info("="*60)
    logger.info("ML Worker Server Starting")
    logger.info("="*60)
    logger.info(f"Socket path: {_socket_path}")
    logger.info(f"Idle timeout: {_idle_timeout}s")
    logger.info(f"Backend: {backend}")

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Ensure backend is ready (sets environment variables)
    try:
        if backend == 'auto':
            # Resolve auto to specific backend
            from ml_worker.backends import detect_available_backends
            available = detect_available_backends()
            if available:
                backend = available[0]
                logger.info(f"Auto-detected best backend: {backend}")
            else:
                backend = 'cpu'
                logger.warning("No backends detected, falling back to CPU")

        setup_backend_environment(backend)
        logger.info(f"Backend environment configured: {backend}")
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

    finally:
        logger.info("Shutting down server")
        server_socket.close()
        cleanup_socket()

    logger.info("Server stopped")
    return 0


if __name__ == '__main__':
    sys.exit(run_server())

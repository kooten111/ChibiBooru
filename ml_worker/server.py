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


def check_dependencies() -> bool:
    """
    Check that all required ML dependencies are installed.
    Returns True if all dependencies are available, False otherwise.
    """
    missing = []
    
    # Check onnxruntime
    try:
        import onnxruntime
        logger.info(f"onnxruntime: OK (version {onnxruntime.__version__})")
    except ImportError:
        missing.append("onnxruntime")
        logger.error("onnxruntime: MISSING")
    
    # Check torchvision
    try:
        import torchvision
        logger.info(f"torchvision: OK (version {torchvision.__version__})")
    except ImportError:
        missing.append("torchvision")
        logger.error("torchvision: MISSING")
    
    # Check torch (comes with torchvision but check explicitly)
    try:
        import torch
        logger.info(f"torch: OK (version {torch.__version__})")
    except ImportError:
        missing.append("torch")
        logger.error("torch: MISSING")
    
    # Check PIL
    try:
        from PIL import Image
        import PIL
        logger.info(f"Pillow: OK (version {PIL.__version__})")
    except ImportError:
        missing.append("Pillow")
        logger.error("Pillow: MISSING")
    
    # Check numpy
    try:
        import numpy
        logger.info(f"numpy: OK (version {numpy.__version__})")
    except ImportError:
        missing.append("numpy")
        logger.error("numpy: MISSING")
    
    if missing:
        logger.error("=" * 60)
        logger.error("FATAL: Missing required dependencies!")
        logger.error(f"Please install: {', '.join(missing)}")
        logger.error("Run: source ./venv/bin/activate && pip install -r requirements.txt")
        logger.error("=" * 60)
        return False
    
    logger.info("All ML dependencies verified.")
    return True

# Global state
_last_request_time = time.time()
_shutdown_requested = False
_idle_timeout = 60  # 1 minute default
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


def get_onnx_providers() -> list:
    """Get the list of ONNX Runtime providers based on configured backend"""
    backend = os.environ.get('ML_WORKER_BACKEND', 'cpu')
    providers = []
    
    if backend == 'cuda':
        providers.append('CUDAExecutionProvider')
    elif backend == 'xpu':
        # OpenVINO is often used for XPU with ONNX
        providers.append('OpenVINOExecutionProvider')
    elif backend == 'mps':
        providers.append('CoreMLExecutionProvider')
    elif backend == 'cpu':
        providers.append('CPUExecutionProvider')
        
    return providers


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
    metadata_path = request_data.get('metadata_path')
    if not metadata_path:
        # Try common metadata file naming conventions
        model_dir = os.path.dirname(model_path)
        for name in ['metadata.json', 'model_metadata.json', os.path.basename(model_path).replace('.onnx', '_metadata.json')]:
            candidate = os.path.join(model_dir, name)
            if os.path.exists(candidate):
                metadata_path = candidate
                break
        if not metadata_path:
            metadata_path = model_path.replace('.onnx', '_metadata.json')  # Fallback
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
            
        # Dynamic providers based on backend
        providers = get_onnx_providers()
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


def tiled_inference(model, img, tile_size=512, tile_pad=32, scale=4, device='cpu'):
    """
    Run inference using seamless tiling.
    img: Tensor (1, C, H, W)
    """
    import math
    import torch
    
    batch, channel, height, width = img.shape
    output_height = height * scale
    output_width = width * scale
    output_shape = (batch, channel, output_height, output_width)

    # Initialize output tensor
    output = torch.zeros(output_shape, device=device)

    # Number of tiles
    tiles_x = math.ceil(width / tile_size)
    tiles_y = math.ceil(height / tile_size)

    logger.info(f"Tiling: {tiles_x}x{tiles_y} tiles (Input tile: {tile_size}px, Pad: {tile_pad}px)")

    for y in range(tiles_y):
        for x in range(tiles_x):
            # 1. Determine Input Crop Coordinates (Input Space)
            # Core crop (without padding)
            ofs_x = x * tile_size
            ofs_y = y * tile_size
            
            # Input Pad limits (don't go out of bounds)
            input_start_x = max(ofs_x - tile_pad, 0)
            input_end_x = min(ofs_x + tile_size + tile_pad, width)
            input_start_y = max(ofs_y - tile_pad, 0)
            input_end_y = min(ofs_y + tile_size + tile_pad, height)

            # Input padding offsets (how much we actually padded relative to the core crop)
            pad_left = ofs_x - input_start_x
            pad_top = ofs_y - input_start_y
            
            # Crop Input
            input_tile = img[:, :, input_start_y:input_end_y, input_start_x:input_end_x]

            # 2. Run Inference
            with torch.no_grad():
                try:
                    output_tile = model(input_tile)
                except RuntimeError as e:
                    logger.error(f"Error processing tile ({x},{y}): {e}")
                    raise e

            # 3. Determine Output Crop Coordinates (Output Space)
            # The output tensor includes the padding, so we need to crop the VALID center area.
            
            # Corresponding valid output area in the final image
            output_start_x = ofs_x * scale
            output_end_x = min(ofs_x + tile_size, width) * scale
            output_start_y = ofs_y * scale
            output_end_y = min(ofs_y + tile_size, height) * scale

            # Crop offsets within the output_tile
            # We skip the 'pad_left * scale' pixels that correspond to the left padding
            tile_crop_start_x = pad_left * scale
            tile_crop_end_x = tile_crop_start_x + (output_end_x - output_start_x)
            
            tile_crop_start_y = pad_top * scale
            tile_crop_end_y = tile_crop_start_y + (output_end_y - output_start_y)

            # Place into final output
            output[:, :, output_start_y:output_end_y, output_start_x:output_end_x] = \
                output_tile[:, :, tile_crop_start_y:tile_crop_end_y, tile_crop_start_x:tile_crop_end_x]

    return output


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

    # Determine device strict mode
    # Backend environment is already setup by startup
    backend = os.environ.get('ML_WORKER_BACKEND')
    if not backend:
        logger.error("ML_WORKER_BACKEND not set")
        raise RuntimeError("ML_WORKER_BACKEND not set")
        
    # Import IPEX if available (not required with PyTorch nightly XPU)
    if backend == 'xpu':
        try:
            import intel_extension_for_pytorch as ipex
            logger.info("Intel Extension for PyTorch imported for Upscaler")
        except ImportError:
            # IPEX not required with PyTorch nightly - XPU support is built-in
            logger.info("IPEX not installed, using built-in XPU support")
            
    device = get_torch_device(backend)
    
    # CRITICAL: Strict Check - Fail immediately if device is CPU but backend is not
    if backend != 'cpu' and device == 'cpu':
        logger.error(f"CRITICAL FAILURE: Backend is configured as '{backend}' but torch detected device as '{device}'.")
        raise RuntimeError(f"Strict Mode Violation: Refusing to run on CPU when {backend} is requested.")
        
    _upscaler_device = device

    # Load model if not already loaded
    if _upscaler_model is None:
        logger.info(f"Loading upscaler model: {model_name} on {device}")

        model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS['RealESRGAN_x4plus'])
        model_dir = Path('./models/Upscaler')
        model_path = model_dir / f"{model_name}.pth"

        if not model_path.exists():
            # Try fallback to non-anime if anime requested but missing, or vice versa?
            # User likely has 4plus but requested anime.
            if 'anime' in model_name:
                alt_model = 'RealESRGAN_x4plus'
                alt_path = model_dir / f"{alt_model}.pth"
                if alt_path.exists():
                    logger.warning(f"Model {model_name} not found. Falling back to {alt_model}")
                    model_path = alt_path
                    model_config = MODEL_CONFIGS[alt_model]
                else:
                    raise FileNotFoundError(f"Upscaler model not found: {model_path}")
            else:
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

        logger.info(f"Upscaler model loaded on {device}")

    # Load and preprocess image
    img = Image.open(image_path).convert('RGB')
    original_size = img.size

    img_np = np.array(img).astype(np.float32) / 255.0
    img_tensor = torch.from_numpy(np.transpose(img_np, (2, 0, 1))).float().unsqueeze(0)
    img_tensor = img_tensor.to(_upscaler_device)

    logger.info(f"Upscaler input tensor device: {img_tensor.device}")

    # Upscale
    # FINAL SAFETY CHECK
    if _upscaler_device != 'cpu' and img_tensor.device.type == 'cpu':
         raise RuntimeError(f"FATAL: Input tensor is on CPU despite requested device {_upscaler_device}! Aborting to prevent CPU fallback.")

    # Attempt to clear memory before upscaling - REMOVED to match standalone speed
    # import gc
    # gc.collect()
    # if backend == 'xpu' and hasattr(torch, 'xpu'):
    #    torch.xpu.empty_cache()
    # elif backend == 'cuda' and torch.cuda.is_available():
    #    torch.cuda.empty_cache()
    # elif backend == 'mps':
    #    if hasattr(torch.mps, 'empty_cache'):
    #        torch.mps.empty_cache()

    # Use tiled inference matching reference implementation
    try:
        output = tiled_inference(_upscaler_model, img_tensor, tile_size=400, tile_pad=32, device=_upscaler_device)
    except RuntimeError as e:
        logger.error(f"Inference failed: {e}")
        raise e

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
        providers = get_onnx_providers()
        _similarity_model = ort.InferenceSession(model_path, providers=providers)
        logger.info("Similarity model loaded")

    # Preprocess image - model expects 448x448 in NHWC format (TensorFlow-style)
    # Handle videos by extracting a frame
    if image_path.lower().endswith(('.mp4', '.webm', '.gif', '.mov', '.avi')):
        import cv2
        cap = cv2.VideoCapture(image_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Get middle frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise ValueError(f"Could not extract frame from video: {image_path}")
        # Convert BGR to RGB
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame)
    else:
        img = Image.open(image_path).convert('RGB')
    
    # Resize with aspect ratio preservation and padding (matching similarity_service.py)
    target_size = 448
    w, h = img.size
    ratio = min(target_size/w, target_size/h)
    new_w, new_h = int(w*ratio), int(h*ratio)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    # Paste on gray background
    new_img = Image.new('RGB', (target_size, target_size), (124, 116, 104))
    new_img.paste(img, ((target_size-new_w)//2, (target_size-new_h)//2))

    # Convert to numpy - NHWC format (no transpose needed)
    img_np = np.array(new_img).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img_np = (img_np - mean) / std
    # Model expects NHWC: (1, 448, 448, 3) - no transpose needed
    img_np = np.expand_dims(img_np, axis=0).astype(np.float32)

    # Run inference
    input_name = _similarity_model.get_inputs()[0].name
    outputs = _similarity_model.run(None, {input_name: img_np})
    
    # Find the 1024-d embedding output (not the 9083-d classification)
    # Model outputs: predictions_sigmoid (9083), globalavgpooling (1024,1,1), predictions_norm (1024)
    embedding = None
    for out in outputs:
        # Look for exactly 1024 dimensions (the embedding vector)
        flat = out.flatten() if len(out.shape) > 2 else out[0] if len(out.shape) == 2 else out
        if hasattr(flat, '__len__') and len(flat) == 1024:
            embedding = flat.astype(np.float32)
            break
    
    if embedding is None:
        # Log output shapes for debugging
        logger.error(f"Could not find 1024-d embedding. Output shapes: {[o.shape for o in outputs]}")
        raise ValueError(f"Model did not produce valid 1024-d embedding")

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


def handle_train_rating_model(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle train_rating_model request.
    
    Returns:
        Dict with training statistics
    """
    logger.info("Training rating model...")
    
    # Import rating service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import rating_service
    
    # Run training
    stats = rating_service.train_model()
    
    logger.info(f"Rating model training complete: {stats}")
    return stats


def handle_infer_ratings(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle infer_ratings request.
    
    Args:
        request_data: {image_ids: list | None}
    
    Returns:
        Dict with inference statistics
    """
    image_ids = request_data.get('image_ids', [])
    
    logger.info(f"Running rating inference (image_ids: {len(image_ids) if image_ids else 'all unrated'})")
    
    # Import rating service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import rating_service
    
    # Run inference
    if image_ids:
        # Infer specific images
        stats = {
            'processed': 0,
            'rated': 0,
            'skipped_low_confidence': 0,
            'by_rating': {r: 0 for r in rating_service.RATINGS}
        }
        
        for image_id in image_ids:
            result = rating_service.infer_rating_for_image(image_id)
            stats['processed'] += 1
            if result['rated']:
                stats['rated'] += 1
                stats['by_rating'][result['rating']] += 1
            else:
                stats['skipped_low_confidence'] += 1
    else:
        # Infer all unrated
        stats = rating_service.infer_all_unrated_images()
    
    logger.info(f"Rating inference complete: {stats}")
    return stats


def handle_train_character_model(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle train_character_model request.
    
    Returns:
        Dict with training statistics
    """
    logger.info("Training character model...")
    
    # Import character service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import character_service
    
    # Run training
    stats = character_service.train_model()
    
    logger.info(f"Character model training complete: {stats}")
    return stats


def handle_infer_characters(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle infer_characters request.
    
    Args:
        request_data: {image_ids: list | None}
    
    Returns:
        Dict with inference statistics
    """
    image_ids = request_data.get('image_ids', [])
    
    logger.info(f"Running character inference (image_ids: {len(image_ids) if image_ids else 'all untagged'})")
    
    # Import character service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import character_service
    
    # Run inference
    if image_ids:
        # Infer specific images
        stats = {
            'processed': 0,
            'tagged': 0,
            'skipped': 0,
            'characters_added': 0
        }
        
        for image_id in image_ids:
            result = character_service.infer_character_for_image(image_id)
            stats['processed'] += 1
            if result.get('characters_added', 0) > 0:
                stats['tagged'] += 1
                stats['characters_added'] += result['characters_added']
            else:
                stats['skipped'] += 1
    else:
        # Infer all untagged
        stats = character_service.infer_all_untagged_images()
    
    logger.info(f"Character inference complete: {stats}")
    return stats


# Job status tracking (simple in-memory store)
_job_store = {}


def handle_get_job_status(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle get_job_status request.
    
    Args:
        request_data: {job_id: str}
    
    Returns:
        Dict with job status
    """
    job_id = request_data.get('job_id')
    
    if not job_id:
        raise ValueError("job_id is required")
    
    job = _job_store.get(job_id)
    
    if not job:
        return {
            "found": False,
            "job_id": job_id
        }
    
    return {
        "found": True,
        "job_id": job_id,
        **job
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

        elif request_type == RequestType.TRAIN_RATING_MODEL.value:
            result = handle_train_rating_model(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.INFER_RATINGS.value:
            result = handle_infer_ratings(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.TRAIN_CHARACTER_MODEL.value:
            result = handle_train_character_model(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.INFER_CHARACTERS.value:
            result = handle_infer_characters(request_data)
            return Response.success(request_id, result)

        elif request_type == RequestType.GET_JOB_STATUS.value:
            result = handle_get_job_status(request_data)
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

    # Check all dependencies are installed FIRST
    logger.info("Checking ML dependencies...")
    if not check_dependencies():
        logger.error("ML Worker cannot start due to missing dependencies.")
        return 1

    # Get config from environment
    _idle_timeout = int(os.environ.get('ML_WORKER_IDLE_TIMEOUT', 300))
    _socket_path = os.environ.get('ML_WORKER_SOCKET', '/tmp/chibibooru_ml_worker.sock')
    # Ensure backend is ready (strict mode)
    try:
        backend = ensure_backend_ready()
        logger.info(f"Backend strictly configured: {backend}")
    except Exception as e:
        logger.error(f"Failed to set up backend: {e}")
        # Build might fail if ensure_backend_ready crashes process directly
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
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
import zipfile
import threading
import subprocess
import tempfile
import shutil
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ml_worker.protocol import (
    Message, Request, Response, RequestType, ResponseStatus,
    validate_request
)
from ml_worker.backends import ensure_backend_ready, setup_backend_environment, get_torch_device
from services import similarity_service

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
_idle_timeout = 300  # 5 minute default (matches env var default)
_socket_path = '/tmp/chibibooru_ml_worker.sock'

# ML models (lazy loaded)
_tagger_session = None
_tagger_metadata = None
_upscaler_model = None
_upscaler_device = None
_similarity_model = None

# Constants for animation extraction
FRAME_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')

def natural_sort_key(s: str) -> List:
    """Sort key for natural sorting."""
    import re
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

def is_valid_frame(filename: str) -> bool:
    """Check if a filename is a valid image frame."""
    if filename.startswith('.') or filename.startswith('__'):
        return False
    return filename.lower().endswith(FRAME_EXTENSIONS)

def handle_extract_animation(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle extract_animation request.
    
    Args:
        request_data: {zip_path, output_dir}
        
    Returns:
        Dict with animation metadata
    """
    zip_filepath = request_data['zip_path']
    extract_dir = request_data['output_dir']
    
    logger.info(f"Extracting zip animation: {os.path.basename(zip_filepath)}")
    
    try:
        from PIL import Image
        
        with zipfile.ZipFile(zip_filepath, 'r') as zf:
            # Get list of image files in the zip
            all_files = zf.namelist()
            
            # Filter to only image files
            image_files = [f for f in all_files if is_valid_frame(os.path.basename(f))]
            
            if not image_files:
                raise ValueError(f"No valid image files found in {zip_filepath}")
            
            # Sort files naturally
            image_files = sorted(image_files, key=natural_sort_key)
            
            # Create extraction directory
            os.makedirs(extract_dir, exist_ok=True)
            
            # Extract and rename files for consistent ordering
            frames = []
            first_frame_path = None
            width, height = None, None
            
            for i, img_file in enumerate(image_files):
                # Get extension from original file
                ext = os.path.splitext(img_file)[1].lower()
                # Create numbered filename for consistent ordering
                frame_filename = f"frame_{i:05d}{ext}"
                frame_path = os.path.join(extract_dir, frame_filename)
                
                # Extract the file
                with zf.open(img_file) as src:
                    with open(frame_path, 'wb') as dst:
                        dst.write(src.read())
                
                frames.append(frame_filename)
                
                # Get dimensions from first frame
                if i == 0:
                    first_frame_path = frame_path
                    try:
                        with Image.open(frame_path) as img:
                            width, height = img.size
                    except Exception as e:
                        logger.warning(f"Error reading first frame dimensions: {e}")
            
            # Save metadata
            metadata = {
                "frame_count": len(frames),
                "frames": frames,
                "width": width,
                "height": height,
                "default_fps": 10,
                "original_files": image_files
            }
            
            metadata_path = os.path.join(extract_dir, "animation.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Extracted {len(frames)} frames")
            
            return {
                "extract_dir": extract_dir,
                "first_frame": first_frame_path,
                **metadata
            }
            
    except Exception as e:
        logger.error(f"Error extracting zip animation: {e}")
        raise

def handle_tag_video(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tag_video request.
    Extracts frames using ffmpeg and tags them using internal tagger.
    """
    video_filepath = request_data['video_path']
    num_frames = request_data.get('num_frames', 5)
    
    # Reuse params for tagging
    model_path = request_data['model_path']
    threshold = request_data.get('threshold', 0.35)
    
    logger.info(f"Tagging video: {os.path.basename(video_filepath)} ({num_frames} frames)")
    
    # Check ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')
    
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError("ffmpeg/ffprobe not found in worker environment")
        
    try:
        # Get duration
        duration_cmd = [
            ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_filepath
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
        duration = float(duration_result.stdout.strip())

        # Extract frames
        frame_times = [duration * (i + 1) / (num_frames + 1) for i in range(num_frames)]
        
        all_tags_with_scores = {}
        
        for i, timestamp in enumerate(frame_times):
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                temp_frame_path = temp_frame.name
            
            try:
                subprocess.run([
                    ffmpeg_path, '-ss', str(timestamp), '-i', video_filepath,
                    '-vframes', '1', '-strict', 'unofficial', '-y', temp_frame_path
                ], check=True, capture_output=True)
                
                # Tag using internal handler function directly
                # We need to construct a request payload for handle_tag_image
                tag_request = {
                    "image_path": temp_frame_path,
                    "model_path": model_path,
                    "threshold": threshold,
                    "storage_threshold": request_data.get('storage_threshold', 0.50),
                    "character_threshold": request_data.get('character_threshold', 0.85),
                    "metadata_path": request_data.get('metadata_path')
                }
                
                result = handle_tag_image(tag_request)
                
                # Merge logic
                all_predictions = result.get('all_predictions', [])
                for pred in all_predictions:
                    confidence = pred['confidence']
                    
                    # Apply threshold BEFORE merging - use the same threshold as images
                    if confidence < threshold:
                        continue
                    
                    tag_name = pred['tag_name']
                    category = pred['category']
                    
                    if tag_name.startswith('rating:') or tag_name.startswith('rating_'):
                        continue
                    
                    key = (tag_name, category)
                    
                    if key in all_tags_with_scores:
                        all_tags_with_scores[key]['count'] += 1
                        all_tags_with_scores[key]['max_prob'] = max(all_tags_with_scores[key]['max_prob'], confidence)
                    else:
                        all_tags_with_scores[key] = {'count': 1, 'max_prob': confidence}
                        
            except Exception as e:
                logger.warning(f"Error tagging frame {i+1}: {e}")
                continue
            finally:
                if os.path.exists(temp_frame_path):
                    os.unlink(temp_frame_path)
                    
        # Final merge
        if not all_tags_with_scores:
            logger.warning("No tags found in any frame")
            return {"tags": {}, "tagger_name": "unknown"}
            
        tags_by_category = {"general": [], "character": [], "copyright": [], "artist": [], "meta": [], "species": []}

        for (tag_name, category), scores in all_tags_with_scores.items():
            if scores['count'] >= 2 or scores['max_prob'] >= 0.8:
                if category in tags_by_category:
                    tags_by_category[category].append(tag_name)
                else:
                    tags_by_category["general"].append(tag_name)
                    
        return {
            "tags": tags_by_category,
            "tagger_name": _tagger_metadata.get('model_info', {}).get('name', 'Unknown') + " (video)" if _tagger_metadata else "video"
        }
        
    except Exception as e:
        logger.error(f"Error tagging video: {e}")
        raise

def handle_generate_thumbnail(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle generate_thumbnail request.
    Generates thumbnail for image, video, or zip animation.
    """
    filepath = request_data['filepath']
    output_path = request_data['output_path']
    size = request_data.get('size', 512)
    
    logger.info(f"Generating thumbnail for: {os.path.basename(filepath)}")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    try:
        from PIL import Image
        
        # Handle Zip Animation
        if filepath.lower().endswith('.zip'):
            with zipfile.ZipFile(filepath, 'r') as zf:
                all_files = zf.namelist()
                image_files = [f for f in all_files if is_valid_frame(os.path.basename(f))]
                
                if not image_files:
                    raise ValueError(f"No valid images in zip: {filepath}")
                
                image_files = sorted(image_files, key=natural_sort_key)
                first_frame = image_files[0]
                
                with zf.open(first_frame) as src:
                    with Image.open(src) as img:
                        if img.mode in ('RGBA', 'LA', 'P'):
                            background = Image.new('RGB', img.size, (255, 255, 255))
                            if img.mode == 'P': img = img.convert('RGBA')
                            background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                            img = background
                        img.thumbnail((size, size), Image.Resampling.LANCZOS)
                        img.save(output_path, 'WEBP', quality=85, method=6)
                        
        # Handle Video
        elif filepath.lower().endswith(('.mp4', '.webm')):
            ffmpeg_path = shutil.which('ffmpeg')
            if not ffmpeg_path:
                raise RuntimeError("ffmpeg not found")
                
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                temp_frame_path = temp_frame.name
            
            try:
                subprocess.run([
                    ffmpeg_path, '-ss', '0.1', '-i', filepath, '-vframes', '1',
                    '-strict', 'unofficial', '-y', temp_frame_path
                ], check=True, capture_output=True)
                
                with Image.open(temp_frame_path) as img:
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                    img.save(output_path, 'WEBP', quality=85, method=6)
            finally:
                if os.path.exists(temp_frame_path):
                    os.unlink(temp_frame_path)
                    
        # Handle Regular Image
        else:
            with Image.open(filepath) as img:
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P': img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                    img = background
                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                img.save(output_path, 'WEBP', quality=85, method=6)
                
        return {"success": True, "output_path": output_path}
        
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        raise


def update_activity():
    """Update the last activity timestamp"""
    global _last_request_time
    _last_request_time = time.time()


def get_idle_time() -> float:
    """Get current idle time in seconds"""
    return time.time() - _last_request_time


def should_shutdown() -> bool:
    """Check if worker should shutdown due to inactivity"""
    # 1. Check idle timeout
    is_idle = get_idle_time() > _idle_timeout
    
    # 2. Check for active jobs
    # If any job is running or pending, do NOT shutdown
    has_active_jobs = any(
        job['status'] in ('running', 'pending') 
        for job in _job_store.values()
    )
    
    if has_active_jobs:
        # Effectively reset idle timer if working
        update_activity()
        return False
        
    return is_idle


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

    storage_threshold = request_data.get('storage_threshold', 0.50)
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


import uuid
import traceback

class JobRunner(threading.Thread):
    def __init__(self, job_id: str, target, args=(), kwargs=None):
        super().__init__()
        self.job_id = job_id
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = True
        
    def run(self):
        try:
            _job_store[self.job_id]['status'] = 'running'
            
            def progress_callback(percent, message):
                _job_store[self.job_id]['progress'] = percent
                _job_store[self.job_id]['message'] = message
            
            # Inject progress_callback if target accepts it
            result = self.target(progress_callback=progress_callback, *self.args, **self.kwargs)
            
            _job_store[self.job_id]['status'] = 'completed'
            _job_store[self.job_id]['progress'] = 100
            _job_store[self.job_id]['result'] = result
            
        except Exception as e:
            logger.error(f"Job {self.job_id} failed: {e}")
            logger.error(traceback.format_exc())
            _job_store[self.job_id]['status'] = 'failed'
            _job_store[self.job_id]['error'] = str(e)

def start_job(target, *args, **kwargs) -> str:
    """Start a background job and return its ID"""
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {
        'status': 'pending',
        'progress': 0,
        'message': 'Starting...',
        'created_at': time.time()
    }
    
    runner = JobRunner(job_id, target, args, kwargs)
    runner.start()
    
    return job_id


def handle_train_rating_model(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle train_rating_model request.
    
    Returns:
        Dict with job info (job_id, status)
    """
    logger.info("Starting rating model training background job...")
    
    # Import rating service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import rating_service
    
    job_id = start_job(rating_service.train_model)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Training started in background"
    }


def handle_infer_ratings(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle infer_ratings request.
    
    Args:
        request_data: {image_ids: list | None}
    
    Returns:
        Dict with job info (job_id, status)
    """
    image_ids = request_data.get('image_ids', [])
    
    logger.info(f"Starting rating inference background job (image_ids: {len(image_ids) if image_ids else 'all unrated'})")
    
    # Import rating service
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import rating_service
    
    # Define wrapper for infer_specific which doesn't support callback yet
    # Or just support callback for infer_all which is the main long-running task
    
    if image_ids:
        # Wrapper for specific images
        def _run_specific(progress_callback=None):
            if progress_callback:
                progress_callback(0, "Processing specific images...")
                
            stats = {
                'processed': 0,
                'rated': 0,
                'skipped_low_confidence': 0,
                'by_rating': {r: 0 for r in rating_service.RATINGS}
            }
            
            total = len(image_ids)
            for i, image_id in enumerate(image_ids):
                result = rating_service.infer_rating_for_image(image_id)
                stats['processed'] += 1
                if result['rated']:
                    stats['rated'] += 1
                    stats['by_rating'][result['rating']] += 1
                else:
                    stats['skipped_low_confidence'] += 1
                
                if progress_callback and (i + 1) % 10 == 0:
                     progress_callback(int((i+1)/total * 100), f"Processed {i+1}/{total}")
                     
            return stats
            
        job_id = start_job(_run_specific)
    else:
        # Infer all unrated supports callback natively now
        job_id = start_job(rating_service.infer_all_unrated_images)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Inference started in background"
    }


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
        try:
            # Call handler directly
            result = handle_search_similar({
                'query_embedding': query_embedding,
                'limit': limit
            })
            return result.get('results', [])
        except Exception as e:
            logger.error(f"Local backend search failed: {e}")
            return []


def handle_rebuild_cache(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle rebuild_cache request.
    Restarts the cache build process in a background thread.
    """
    similarity_type = request_data.get('similarity_type', 'blended')
    logger.info(f"Starting similarity cache rebuild ({similarity_type})...")
    
    # Import here to avoid circular dependencies
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from services import similarity_cache
    
    def _run_rebuild(progress_callback=None):
        logger.info(f"Rebuilding cache ({similarity_type})...")
        
        def adapter(current, total):
            if progress_callback:
                pct = int(current / total * 100) if total > 0 else 0
                progress_callback(pct, f"Processed {current}/{total} images")
            
        stats = similarity_cache.rebuild_cache_full(
            similarity_type=similarity_type,
            progress_callback=adapter
        )
        
        logger.info(f"Rebuild complete. Stats: {stats}")
        return stats
        
    job_id = start_job(_run_rebuild)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Cache rebuild started"
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
        
        # Inject LocalSemanticBackend so worker uses itself for embeddings/search
        # instead of trying to connect to its own socket
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from services import similarity_service
        similarity_service.set_semantic_backend(LocalSemanticBackend())
        logger.info("Injected LocalSemanticBackend for worker process")
        
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
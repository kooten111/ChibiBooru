"""
Upscaler Service for ChibiBooru
Uses RealESRGAN for AI-powered image upscaling with lazy model loading
Standalone implementation - no basicsr/realesrgan dependency
"""

import os
import asyncio
import logging
import urllib.request
from pathlib import Path
from typing import Dict, Optional
from PIL import Image
import numpy as np

import config
from utils.gpu_detection import check_upscaler_dependencies, get_pytorch_device

logger = logging.getLogger(__name__)

# Lazy-loaded upscaler instance
_model = None
_device = None

# Model download URLs
MODEL_URLS = {
    'RealESRGAN_x4plus': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
    'RealESRGAN_x4plus_anime': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth'
}

# Model configurations (num_block varies by model)
MODEL_CONFIGS = {
    'RealESRGAN_x4plus': {'num_block': 23, 'num_feat': 64, 'num_grow_ch': 32},
    'RealESRGAN_x4plus_anime': {'num_block': 6, 'num_feat': 64, 'num_grow_ch': 32}
}

# Model storage directory
MODELS_DIR = './models/Upscaler'


def get_upscaled_path(filepath: str) -> str:
    """
    Get the path where the upscaled version would be stored.
    Mirrors the original path structure under the upscaled directory.
    """
    # Normalize the filepath
    if filepath.startswith('images/'):
        relative_path = filepath
    elif filepath.startswith('./static/images/'):
        relative_path = filepath.replace('./static/', '')
    elif filepath.startswith('/static/images/'):
        relative_path = filepath.replace('/static/', '')
    else:
        relative_path = f"images/{filepath}"
    
    # Create upscaled path
    upscaled_path = os.path.join(config.UPSCALED_IMAGES_DIR, relative_path)
    return upscaled_path


def check_upscale_exists(filepath: str) -> bool:
    """Check if an upscaled version exists for the given image."""
    upscaled_path = get_upscaled_path(filepath)
    return os.path.exists(upscaled_path)


def get_upscale_url(filepath: str) -> Optional[str]:
    """Get the URL for the upscaled version if it exists."""
    if not check_upscale_exists(filepath):
        return None
    
    upscaled_path = get_upscaled_path(filepath)
    if upscaled_path.startswith('./static/'):
        return upscaled_path.replace('./static/', '/static/')
    elif upscaled_path.startswith('static/'):
        return '/' + upscaled_path
    return upscaled_path


def _download_model(model_name: str) -> str:
    """Download the model weights if not present."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    model_path = os.path.join(MODELS_DIR, f"{model_name}.pth")
    
    if os.path.exists(model_path):
        logger.info(f"Model already exists: {model_path}")
        return model_path
    
    url = MODEL_URLS.get(model_name)
    if not url:
        raise ValueError(f"Unknown model: {model_name}")
    
    logger.info(f"Downloading {model_name} from {url}...")
    
    # Download with progress
    def progress_hook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        if count % 100 == 0:
            logger.info(f"Download progress: {percent}%")
    
    urllib.request.urlretrieve(url, model_path, progress_hook)
    
    logger.info(f"Model downloaded to: {model_path}")
    return model_path


def _load_model():
    """Load the RRDBNet model (lazy loading)."""
    global _model, _device
    
    if _model is not None:
        return _model
    
    import torch
    from utils.rrdbnet_arch import RRDBNet
    
    device = get_pytorch_device()
    _device = device
    
    model_name = config.UPSCALER_MODEL
    model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS['RealESRGAN_x4plus'])
    
    logger.info(f"Loading {model_name} on {device}...")
    
    # Download model if needed
    model_path = _download_model(model_name)
    
    # Create model
    _model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=model_config['num_feat'],
        num_block=model_config['num_block'],
        num_grow_ch=model_config['num_grow_ch'],
        scale=4
    )
    
    # Load weights
    loadnet = torch.load(model_path, map_location=torch.device('cpu'), weights_only=True)
    
    # Handle different checkpoint formats
    if 'params_ema' in loadnet:
        keyname = 'params_ema'
    elif 'params' in loadnet:
        keyname = 'params'
    else:
        keyname = None
    
    if keyname:
        _model.load_state_dict(loadnet[keyname], strict=True)
    else:
        _model.load_state_dict(loadnet, strict=True)
    
    _model.eval()
    _model = _model.to(device)
    
    # Use half precision on GPU
    if device != 'cpu':
        _model = _model.half()
    
    logger.info(f"Model loaded successfully on {device}")
    return _model


def _tile_process(img_tensor, model, tile_size=512, tile_pad=10, scale=4):
    """Process image in tiles to avoid VRAM issues."""
    import torch
    
    batch, channel, height, width = img_tensor.shape
    output_height = height * scale
    output_width = width * scale
    output_shape = (batch, channel, output_height, output_width)
    
    # Create output tensor
    output = img_tensor.new_zeros(output_shape)
    
    # Calculate number of tiles
    tiles_x = (width + tile_size - 1) // tile_size
    tiles_y = (height + tile_size - 1) // tile_size
    
    for y in range(tiles_y):
        for x in range(tiles_x):
            # Calculate tile boundaries
            x_start = x * tile_size
            y_start = y * tile_size
            x_end = min(x_start + tile_size, width)
            y_end = min(y_start + tile_size, height)
            
            # Add padding
            x_start_pad = max(x_start - tile_pad, 0)
            y_start_pad = max(y_start - tile_pad, 0)
            x_end_pad = min(x_end + tile_pad, width)
            y_end_pad = min(y_end + tile_pad, height)
            
            # Extract tile with padding
            tile = img_tensor[:, :, y_start_pad:y_end_pad, x_start_pad:x_end_pad]
            
            # Process tile
            with torch.no_grad():
                tile_output = model(tile)
            
            # Calculate output boundaries
            out_x_start = x_start * scale
            out_y_start = y_start * scale
            out_x_end = x_end * scale
            out_y_end = y_end * scale
            
            # Calculate tile output boundaries (remove padding)
            tile_out_x_start = (x_start - x_start_pad) * scale
            tile_out_y_start = (y_start - y_start_pad) * scale
            tile_out_x_end = tile_out_x_start + (x_end - x_start) * scale
            tile_out_y_end = tile_out_y_start + (y_end - y_start) * scale
            
            # Place tile in output
            output[:, :, out_y_start:out_y_end, out_x_start:out_x_end] = \
                tile_output[:, :, tile_out_y_start:tile_out_y_end, tile_out_x_start:tile_out_x_end]
    
    return output


async def upscale_image(filepath: str, force: bool = False) -> Dict:
    """Upscale an image using RealESRGAN."""
    import time
    import torch
    
    result = {
        'success': False,
        'filepath': filepath,
        'upscaled_path': None,
        'upscaled_url': None,
        'original_size': None,
        'upscaled_size': None,
        'processing_time': 0,
        'error': None
    }
    
    if not config.UPSCALER_ENABLED:
        result['error'] = 'Upscaler is disabled. Enable it in config.'
        return result
    
    # Check if already upscaled
    upscaled_path = get_upscaled_path(filepath)
    if not force and os.path.exists(upscaled_path):
        result['success'] = True
        result['upscaled_path'] = upscaled_path
        result['upscaled_url'] = get_upscale_url(filepath)
        result['error'] = 'Already upscaled'
        return result
    
    # Find the original image
    if os.path.exists(filepath):
        source_path = filepath
    elif os.path.exists(f"./static/{filepath}"):
        source_path = f"./static/{filepath}"
    elif os.path.exists(f"./static/images/{filepath}"):
        source_path = f"./static/images/{filepath}"
    else:
        result['error'] = f"Original image not found: {filepath}"
        return result
    
    start_time = time.time()
    
    try:
        # Load the model (lazy loading)
        model = _load_model()
        device = _device
        
        # Load image
        img = Image.open(source_path).convert('RGB')
        result['original_size'] = img.size
        
        # Convert to tensor
        img_np = np.array(img).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(np.transpose(img_np, (2, 0, 1))).float()
        img_tensor = img_tensor.unsqueeze(0).to(device)
        
        # Use half precision on GPU
        if device != 'cpu':
            img_tensor = img_tensor.half()
        
        # Run upscaling in thread pool
        loop = asyncio.get_event_loop()
        
        def do_upscale():
            # Use tiling for large images
            if img.size[0] > config.UPSCALER_TILE_SIZE or img.size[1] > config.UPSCALER_TILE_SIZE:
                return _tile_process(img_tensor, model, config.UPSCALER_TILE_SIZE, 10, config.UPSCALER_SCALE)
            else:
                with torch.no_grad():
                    return model(img_tensor)
        
        output_tensor = await loop.run_in_executor(None, do_upscale)
        
        # Convert back to image
        output = output_tensor.squeeze().float().cpu().clamp_(0, 1).numpy()
        output = np.transpose(output, (1, 2, 0))
        output = (output * 255.0).round().astype(np.uint8)
        
        upscaled_img = Image.fromarray(output)
        result['upscaled_size'] = upscaled_img.size
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(upscaled_path), exist_ok=True)
        
        # Save with high quality
        upscaled_img.save(upscaled_path, quality=95)
        
        result['success'] = True
        result['upscaled_path'] = upscaled_path
        result['upscaled_url'] = get_upscale_url(filepath)
        result['processing_time'] = time.time() - start_time
        
        logger.info(f"Upscaled {filepath}: {result['original_size']} -> {result['upscaled_size']} in {result['processing_time']:.2f}s")
        
    except Exception as e:
        result['error'] = str(e)
        result['processing_time'] = time.time() - start_time
        logger.error(f"Upscale failed for {filepath}: {e}")
    
    return result


async def delete_upscaled_image(filepath: str) -> Dict:
    """Delete the upscaled version of an image."""
    result = {
        'success': False,
        'filepath': filepath,
        'deleted_path': None,
        'error': None
    }
    
    upscaled_path = get_upscaled_path(filepath)
    
    if not os.path.exists(upscaled_path):
        result['error'] = 'No upscaled version exists'
        return result
    
    try:
        os.remove(upscaled_path)
        result['success'] = True
        result['deleted_path'] = upscaled_path
        
        # Clean up empty directories
        parent_dir = os.path.dirname(upscaled_path)
        while parent_dir and parent_dir != config.UPSCALED_IMAGES_DIR:
            try:
                if not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    parent_dir = os.path.dirname(parent_dir)
                else:
                    break
            except OSError:
                break
        
        logger.info(f"Deleted upscaled image: {upscaled_path}")
        
    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Failed to delete upscaled image {upscaled_path}: {e}")
    
    return result


def get_upscaler_status() -> Dict:
    """Get current upscaler status."""
    ready = False
    pytorch_ok = False
    model_exists = False
    
    try:
        import torch
        pytorch_ok = True
    except ImportError:
        pass
    
    if pytorch_ok:
        model_name = config.UPSCALER_MODEL
        model_path = os.path.join(MODELS_DIR, f"{model_name}.pth")
        model_exists = os.path.exists(model_path)
        ready = True  # PyTorch is enough, model will auto-download
    
    return {
        'enabled': config.UPSCALER_ENABLED,
        'ready': ready if config.UPSCALER_ENABLED else False,
        'model': config.UPSCALER_MODEL,
        'model_downloaded': model_exists,
        'scale': config.UPSCALER_SCALE,
        'tile_size': config.UPSCALER_TILE_SIZE,
        'pytorch_installed': pytorch_ok,
        'model_loaded': _model is not None,
        'device': _device or 'unknown'
    }

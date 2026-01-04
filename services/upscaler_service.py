"""
Upscaler Service for ChibiBooru
Uses RealESRGAN for AI-powered image upscaling via ML Worker subprocess
The ML Worker handles model loading/unloading for memory efficiency
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional
import time

import config

logger = logging.getLogger(__name__)


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
    
    from urllib.parse import quote
    
    upscaled_path = get_upscaled_path(filepath)
    
    # We need to preserve the slashes but encode the path components
    # Especially for files with spaces, parentheses, etc.
    parts = upscaled_path.split('/')
    encoded_parts = [quote(part) for part in parts]
    encoded_path = '/'.join(encoded_parts)
    
    if encoded_path.startswith('./static/'):
        return encoded_path.replace('./static/', '/static/')
    elif encoded_path.startswith('static/'):
        return '/' + encoded_path
    return encoded_path


async def upscale_image(filepath: str, force: bool = False) -> Dict:
    """
    Upscale an image using RealESRGAN via ML Worker.
    
    The ML Worker subprocess handles the actual upscaling, ensuring:
    - Memory isolation from main process
    - Model is loaded/unloaded as needed
    - Auto-terminates after idle timeout
    """
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
        # Use ML Worker for upscaling
        from ml_worker.client import get_ml_worker_client
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(upscaled_path), exist_ok=True)
        
        # Send upscale request to ML Worker
        loop = asyncio.get_event_loop()
        
        def do_upscale():
            client = get_ml_worker_client()
            return client.upscale_image(
                image_path=os.path.abspath(source_path),
                output_path=os.path.abspath(upscaled_path),
                model_name=config.UPSCALER_MODEL,
                device='auto'
            )
        
        worker_result = await loop.run_in_executor(None, do_upscale)
        
        result['success'] = worker_result.get('success', False)
        result['upscaled_path'] = upscaled_path
        result['upscaled_url'] = get_upscale_url(filepath)
        result['original_size'] = worker_result.get('original_size')
        result['upscaled_size'] = worker_result.get('upscaled_size')
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
    model_exists = False
    worker_status = None
    
    # Check if model file exists
    model_name = config.UPSCALER_MODEL
    model_path = os.path.join('./models/Upscaler', f"{model_name}.pth")
    model_exists = os.path.exists(model_path)
    
    # Try to get ML Worker status
    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        if client._is_worker_running():
            worker_status = client.health_check()
    except Exception as e:
        logger.debug(f"Could not get ML worker status: {e}")
    
    models_loaded = {}
    if worker_status:
        models_loaded = worker_status.get('models_loaded', {})
    
    return {
        'enabled': config.UPSCALER_ENABLED,
        'ready': config.UPSCALER_ENABLED and model_exists,
        'model': config.UPSCALER_MODEL,
        'model_downloaded': model_exists,
        'scale': config.UPSCALER_SCALE,
        'tile_size': config.UPSCALER_TILE_SIZE,
        'using_ml_worker': True,
        'worker_running': worker_status is not None,
        'model_loaded': models_loaded.get('upscaler', False)
    }

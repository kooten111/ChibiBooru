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
import hashlib

import config

logger = logging.getLogger(__name__)


def _normalize_relative_path(filepath: str) -> str:
    """Normalize a filepath to a relative path under images/."""
    if filepath.startswith('images/'):
        return filepath
    elif filepath.startswith('./static/images/'):
        return filepath.replace('./static/', '')
    elif filepath.startswith('/static/images/'):
        return filepath.replace('/static/', '')
    else:
        return f"images/{filepath}"


def _find_upscaled_file(filepath: str) -> Optional[str]:
    """
    Find an existing upscaled file for the given image, regardless of extension.
    Returns the actual path on disk if found, or None.
    """
    relative_path = _normalize_relative_path(filepath)
    base_path = os.path.join(config.UPSCALED_IMAGES_DIR, relative_path)
    stem = os.path.splitext(base_path)[0]

    # Fast path: check the configured format first
    preferred = f"{stem}.{config.UPSCALER_OUTPUT_FORMAT}"
    if os.path.exists(preferred):
        return preferred

    # Check other common formats (handles files saved before a format change)
    for ext in ('png', 'webp', 'jpg', 'jpeg'):
        candidate = f"{stem}.{ext}"
        if candidate != preferred and os.path.exists(candidate):
            return candidate

    return None


def get_upscaled_path(filepath: str) -> str:
    """
    Get the target path where a new upscaled version should be saved.
    Uses the configured output format extension.
    """
    relative_path = _normalize_relative_path(filepath)
    base_path = os.path.join(config.UPSCALED_IMAGES_DIR, relative_path)
    stem = os.path.splitext(base_path)[0]
    return f"{stem}.{config.UPSCALER_OUTPUT_FORMAT}"


def check_upscale_exists(filepath: str) -> bool:
    """Check if an upscaled version exists for the given image (any format)."""
    return _find_upscaled_file(filepath) is not None


def get_upscale_url(filepath: str) -> Optional[str]:
    """Get the URL for the upscaled version if it exists (any format)."""
    actual_path = _find_upscaled_file(filepath)
    if actual_path is None:
        return None
    
    from urllib.parse import quote
    
    # We need to preserve the slashes but encode the path components
    # Especially for files with spaces, parentheses, etc.
    parts = actual_path.split('/')
    encoded_parts = [quote(part) for part in parts]
    encoded_path = '/'.join(encoded_parts)
    
    # Remove ./static/ prefix and use /upscaled/ route
    if encoded_path.startswith('./static/upscaled/'):
        return encoded_path.replace('./static/upscaled/', '/upscaled/')
    elif encoded_path.startswith('static/upscaled/'):
        return '/' + encoded_path.replace('static/', '')
    elif encoded_path.startswith('./static/'):
        return encoded_path.replace('./static/', '/static/')
    elif encoded_path.startswith('static/'):
        return '/' + encoded_path
    return encoded_path


def get_upscale_etag(filepath: str) -> str:
    """
    Generate an ETag for cache invalidation based on upscale status.
    Changes whenever upscale is added/removed.
    """
    actual_path = _find_upscaled_file(filepath)
    
    if actual_path:
        # Include modification time in ETag if upscale exists
        try:
            mtime = os.path.getmtime(actual_path)
            etag_string = f"{filepath}-upscaled-{mtime}"
        except OSError:
            etag_string = f"{filepath}-upscaled"
    else:
        # Simple ETag for original image
        etag_string = f"{filepath}-original"
    
    # Generate a short hash
    etag_hash = hashlib.md5(etag_string.encode()).hexdigest()
    return f'"{etag_hash}"'


# Progress tracking
# Key: filepath, Value: {status, percentage, message, updated_at}
active_upscales: Dict[str, Dict] = {}

def get_upscale_progress(filepath: str) -> Optional[Dict]:
    """Get progress of an active upscale job."""
    return active_upscales.get(filepath)


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
    
    if not config.is_upscalable(filepath):
        result['error'] = 'Animated images and videos cannot be upscaled.'
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
    
    # Import ML Worker client and exceptions
    try:
        from ml_worker.client import get_ml_worker_client, MLWorkerConnectionError, MLWorkerError
    except ImportError as e:
        result['error'] = "ML Worker module not available. Please ensure the ML Worker is properly installed."
        result['processing_time'] = time.time() - start_time
        logger.error(f"ML Worker import failed: {e}")
        return result
    
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(upscaled_path), exist_ok=True)
        
        # Init progress
        active_upscales[filepath] = {
            'status': 'starting',
            'percentage': 0,
            'message': 'Initializing...',
            'updated_at': time.time()
        }
        
        # Send upscale request to ML Worker
        loop = asyncio.get_event_loop()
        
        def do_upscale():
            client = get_ml_worker_client()
            
            def progress_callback(current, total, message):
                # Update global progress dict
                if total > 0:
                    percent = (current / total) * 100
                    active_upscales[filepath] = {
                        'status': 'processing',
                        'percentage': percent,
                        'message': message,
                        'current': current,
                        'total': total,
                        'updated_at': time.time()
                    }
            
            return client.upscale_image(
                image_path=os.path.abspath(source_path),
                output_path=os.path.abspath(upscaled_path),
                model_name=config.UPSCALER_MODEL,
                device='auto',
                tile_size=config.UPSCALER_TILE_SIZE,
                tile_pad=config.UPSCALER_TILE_PAD,
                min_tile_size=config.UPSCALER_MIN_TILE_SIZE,
                allow_cpu_fallback=config.UPSCALER_ALLOW_CPU_FALLBACK,
                output_format=config.UPSCALER_OUTPUT_FORMAT,
                output_quality=config.UPSCALER_OUTPUT_QUALITY,
                progress_callback=progress_callback
            )
        
        worker_result = await loop.run_in_executor(None, do_upscale)
        
        result['success'] = worker_result.get('success', False)
        result['upscaled_path'] = upscaled_path
        result['upscaled_url'] = get_upscale_url(filepath)
        result['original_size'] = worker_result.get('original_size')
        result['upscaled_size'] = worker_result.get('upscaled_size')
        
        # Get file size
        try:
             result['upscaled_filesize'] = os.path.getsize(upscaled_path)
        except OSError:
             result['upscaled_filesize'] = 0

        result['processing_time'] = time.time() - start_time
        
        logger.info(f"Upscaled {filepath}: {result['original_size']} -> {result['upscaled_size']} in {result['processing_time']:.2f}s")
        
        # Update database with new dimensions
        try:
            from repositories.data_access import update_image_upscale_info
            # Normalize filepath for DB lookup (remove ./static/images/ prefix if present)
            db_path = filepath
            if db_path.startswith('./static/images/'):
                db_path = db_path.replace('./static/images/', '')
            elif db_path.startswith('static/images/'):
                 db_path = db_path.replace('static/images/', '')
            
            if result['upscaled_size']:
                update_image_upscale_info(db_path, result['upscaled_size'][0], result['upscaled_size'][1])
        except Exception as e:
             logger.error(f"Failed to update database with upscale info for {filepath}: {e}")
        
        # Mark as completed in progress dict
        active_upscales[filepath] = {
            'status': 'completed',
            'percentage': 100,
            'message': 'Upscale complete',
            'updated_at': time.time()
        }
        
    except MLWorkerConnectionError as e:
        # ML Worker connection failed
        result['error'] = "ML Worker is not available. The ML Worker process may not be running. Please check the server logs and try again."
        result['processing_time'] = time.time() - start_time
        logger.error(f"Upscale failed for {filepath}: ML Worker connection error: {e}", exc_info=True)
        # Mark as failed in progress dict
        active_upscales[filepath] = {
            'status': 'failed',
            'percentage': 0,
            'message': result['error'],
            'updated_at': time.time()
        }
    except MLWorkerError as e:
        # Other ML Worker errors
        result['error'] = f"ML Worker error: {str(e)}"
        result['processing_time'] = time.time() - start_time
        logger.error(f"Upscale failed for {filepath}: ML Worker error: {e}", exc_info=True)
        # Mark as failed in progress dict
        active_upscales[filepath] = {
            'status': 'failed',
            'percentage': 0,
            'message': result['error'],
            'updated_at': time.time()
        }
    except Exception as e:
        # Generic error handling
        error_msg = str(e)
        result['error'] = error_msg
        result['processing_time'] = time.time() - start_time
        logger.error(f"Upscale failed for {filepath}: {e}", exc_info=True)
        # Mark as failed in progress dict
        active_upscales[filepath] = {
            'status': 'failed',
            'percentage': 0,
            'message': error_msg,
            'updated_at': time.time()
        }
    finally:
        # Delay cleanup so frontend can poll final status
        async def cleanup_progress():
            await asyncio.sleep(3)  # Give frontend time to poll final state
            if filepath in active_upscales:
                del active_upscales[filepath]
        
        # Schedule cleanup task
        asyncio.create_task(cleanup_progress())
    
    return result


def delete_upscaled_image(filepath: str) -> Dict:
    """Delete the upscaled version of an image (any format)."""
    result = {
        'success': False,
        'filepath': filepath,
        'deleted_path': None,
        'error': None
    }
    
    actual_path = _find_upscaled_file(filepath)
    
    if actual_path is None:
        result['error'] = 'No upscaled version exists'
        return result
    
    try:
        upscaled_path = actual_path
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
        
        # Clear database info
        try:
            from repositories.data_access import update_image_upscale_info
            # Normalize filepath for DB lookup
            db_path = filepath
            if db_path.startswith('./static/images/'):
                db_path = db_path.replace('./static/images/', '')
            elif db_path.startswith('static/images/'):
                 db_path = db_path.replace('static/images/', '')

            update_image_upscale_info(db_path, None, None)
        except Exception as e:
             logger.error(f"Failed to clear database upscale info for {filepath}: {e}")
        
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

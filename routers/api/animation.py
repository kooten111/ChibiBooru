# routers/api/animation.py
"""
API endpoints for animation playback.
Serves frames from zip animations and provides animation metadata.
"""

from quart import request, jsonify, send_file, Response
from . import api_blueprint
from services import zip_animation_service
from database import models
from utils import api_handler
import os


@api_blueprint.route('/animation/metadata/<path:filepath>')
@api_handler()
async def get_animation_metadata(filepath):
    """
    Get metadata for an animation file.
    
    Returns:
        JSON with frame_count, width, height, default_fps, etc.
    """
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    # Look up the image in the database to get its MD5
    image_data = models.get_image_by_filepath(filepath)
    if not image_data:
        raise ValueError(f"Image not found: {filepath}")
    
    md5 = image_data.get('md5')
    if not md5:
        raise ValueError(f"No MD5 found for image: {filepath}")
    
    # Check if this is a zip animation
    if not filepath.lower().endswith('.zip'):
        # For regular images/GIFs, return basic info
        # GIF frame info will be extracted client-side
        return {
            "type": "native",  # GIF, WebP, etc - handled by browser/JS
            "filepath": filepath,
            "is_animated": filepath.lower().endswith(('.gif', '.webp', '.apng'))
        }
    
    # Get zip animation metadata
    metadata = zip_animation_service.get_animation_metadata(md5)
    if not metadata:
        raise ValueError(f"Animation metadata not found for: {filepath}")
    
    return {
        "type": "zip",
        "filepath": filepath,
        "md5": md5,
        "frame_count": metadata.get("frame_count", 0),
        "frames": metadata.get("frames", []),
        "width": metadata.get("width"),
        "height": metadata.get("height"),
        "default_fps": metadata.get("default_fps", 10),
        "is_animated": True
    }


@api_blueprint.route('/animation/frame/<md5>/<int:frame_index>')
async def get_animation_frame(md5, frame_index):
    """
    Get a specific frame from a zip animation.
    
    Args:
        md5: MD5 hash of the original zip file
        frame_index: Zero-based frame index
    
    Returns:
        The frame image file
    """
    frame_path = zip_animation_service.get_frame_path(md5, frame_index)
    
    if not frame_path or not os.path.exists(frame_path):
        return Response("Frame not found", status=404)
    
    # Determine content type from extension
    ext = os.path.splitext(frame_path)[1].lower()
    content_types = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp'
    }
    content_type = content_types.get(ext, 'application/octet-stream')
    
    return await send_file(
        frame_path,
        mimetype=content_type,
        cache_timeout=86400  # Cache for 24 hours
    )


@api_blueprint.route('/animation/frames/<md5>')
@api_handler()
async def get_all_frame_urls(md5):
    """
    Get URLs for all frames of a zip animation.
    Useful for preloading all frames client-side.
    
    Args:
        md5: MD5 hash of the original zip file
    
    Returns:
        JSON with list of frame URLs
    """
    metadata = zip_animation_service.get_animation_metadata(md5)
    if not metadata:
        raise ValueError(f"Animation not found for MD5: {md5}")
    
    frames = metadata.get("frames", [])
    frame_urls = [f"/api/animation/frame/{md5}/{i}" for i in range(len(frames))]
    
    return {
        "md5": md5,
        "frame_count": len(frames),
        "frame_urls": frame_urls,
        "width": metadata.get("width"),
        "height": metadata.get("height"),
        "default_fps": metadata.get("default_fps", 10)
    }

# services/zip_animation_service.py
"""
Service for handling zip file animations.
Zip files containing image sequences are extracted and served as frame-by-frame animations.
"""

import os
import zipfile
import tempfile
import shutil
import json
from PIL import Image
from typing import Optional, List, Dict, Tuple
import config

# Directory to store extracted animation frames
ANIMATION_FRAMES_DIR = "./static/animations"

# Supported image extensions for animation frames
FRAME_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')


def ensure_animations_dir():
    """Ensure the animations directory exists."""
    os.makedirs(ANIMATION_FRAMES_DIR, exist_ok=True)


def get_animation_dir(md5: str) -> str:
    """Get the directory path for a specific animation's frames."""
    from utils.file_utils import get_hash_bucket
    bucket = get_hash_bucket(md5)
    return os.path.join(ANIMATION_FRAMES_DIR, bucket, md5)


def is_valid_frame(filename: str) -> bool:
    """Check if a filename is a valid image frame."""
    # Skip hidden files and system files
    if filename.startswith('.') or filename.startswith('__'):
        return False
    return filename.lower().endswith(FRAME_EXTENSIONS)


def extract_zip_animation(zip_filepath: str, md5: str) -> Optional[Dict]:
    """
    Extract images from a zip file for animation playback using ML Worker.
    
    Args:
        zip_filepath: Path to the zip file
        md5: MD5 hash of the zip file (used for storage directory)
    
    Returns:
        Dictionary with animation metadata, or None if extraction fails
    """
    ensure_animations_dir()
    
    try:
        # Get target directory
        extract_dir = get_animation_dir(md5)
        
        # Use ML Worker for extraction
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        
        # This call blocks until the worker finishes extraction
        # Since this runs in a thread pool (via ingest_service or similar), it's safe.
        result = client.extract_animation(
            zip_path=os.path.abspath(zip_filepath),
            output_dir=os.path.abspath(extract_dir)
        )
        
        if result:
            print(f"[ZipAnimation] Extracted {result.get('frame_count')} frames via ML Worker")
            
        return result
            
    except Exception as e:
        print(f"[ZipAnimation] Error extracting {zip_filepath} via ML Worker: {e}")
        import traceback
        traceback.print_exc()
        return None


def natural_sort_key(s: str) -> List:
    """
    Sort key for natural sorting (handles numeric sequences).
    Example: frame_1, frame_2, frame_10 instead of frame_1, frame_10, frame_2
    """
    import re
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def get_animation_metadata(md5: str) -> Optional[Dict]:
    """
    Get metadata for an extracted animation.
    
    Args:
        md5: MD5 hash of the original zip file
    
    Returns:
        Animation metadata dictionary, or None if not found
    """
    extract_dir = get_animation_dir(md5)
    metadata_path = os.path.join(extract_dir, "animation.json")
    
    if not os.path.exists(metadata_path):
        return None
    
    try:
        with open(metadata_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ZipAnimation] Error reading metadata for {md5}: {e}")
        return None


def get_frame_path(md5: str, frame_index: int) -> Optional[str]:
    """
    Get the file path for a specific frame.
    
    Args:
        md5: MD5 hash of the original zip file
        frame_index: Zero-based frame index
    
    Returns:
        Path to the frame file, or None if not found
    """
    metadata = get_animation_metadata(md5)
    if not metadata:
        return None
    
    frames = metadata.get("frames", [])
    if frame_index < 0 or frame_index >= len(frames):
        return None
    
    extract_dir = get_animation_dir(md5)
    return os.path.join(extract_dir, frames[frame_index])


def get_frame_url(md5: str, frame_index: int) -> Optional[str]:
    """
    Get the URL path for a specific frame (for use in templates/API).
    
    Args:
        md5: MD5 hash of the original zip file
        frame_index: Zero-based frame index
    
    Returns:
        URL path for the frame, or None if not found
    """
    metadata = get_animation_metadata(md5)
    if not metadata:
        return None
    
    frames = metadata.get("frames", [])
    if frame_index < 0 or frame_index >= len(frames):
        return None
    
    from utils.file_utils import get_hash_bucket
    bucket = get_hash_bucket(md5)
    return f"/static/animations/{bucket}/{md5}/{frames[frame_index]}"


def create_thumbnail_from_animation(md5: str, thumb_dir: str = "./static/thumbnails") -> Optional[str]:
    """
    Create a thumbnail from the first frame of an animation.
    
    Args:
        md5: MD5 hash of the original zip file
        thumb_dir: Directory to save thumbnails
    
    Returns:
        Path to the created thumbnail, or None if failed
    """
    from utils.file_utils import get_hash_bucket
    
    first_frame = get_frame_path(md5, 0)
    if not first_frame or not os.path.exists(first_frame):
        return None
    
    try:
        # Create bucketed thumbnail path
        bucket = get_hash_bucket(md5)
        thumb_path = os.path.join(thumb_dir, bucket, f"{md5}.webp")
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # Create thumbnail
        with Image.open(first_frame) as img:
            # Convert if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                img = background
            
            # Resize
            thumb_size = config.THUMB_SIZE
            img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
            img.save(thumb_path, 'WEBP', quality=85, method=6)
        
        return thumb_path
        
    except Exception as e:
        print(f"[ZipAnimation] Error creating thumbnail for {md5}: {e}")
        return None


def delete_animation_frames(md5: str) -> bool:
    """
    Delete extracted frames for an animation.
    
    Args:
        md5: MD5 hash of the original zip file
    
    Returns:
        True if deleted successfully, False otherwise
    """
    extract_dir = get_animation_dir(md5)
    
    if not os.path.exists(extract_dir):
        return True
    
    try:
        shutil.rmtree(extract_dir)
        print(f"[ZipAnimation] Deleted frames for {md5}")
        return True
    except Exception as e:
        print(f"[ZipAnimation] Error deleting frames for {md5}: {e}")
        return False


def tag_animation_with_first_frame(md5: str) -> Optional[Dict]:
    """
    Tag an animation by analyzing its first frame with the local tagger.
    
    Args:
        md5: MD5 hash of the original zip file
    
    Returns:
        Tag result dictionary, or None if failed
    """
    first_frame = get_frame_path(md5, 0)
    if not first_frame or not os.path.exists(first_frame):
        return None
    
    from services.processing_service import tag_with_local_tagger
    return tag_with_local_tagger(first_frame)

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
    Extract images from a zip file for animation playback.
    
    Args:
        zip_filepath: Path to the zip file
        md5: MD5 hash of the zip file (used for storage directory)
    
    Returns:
        Dictionary with animation metadata, or None if extraction fails
    """
    ensure_animations_dir()
    
    try:
        with zipfile.ZipFile(zip_filepath, 'r') as zf:
            # Get list of image files in the zip
            all_files = zf.namelist()
            
            # Filter to only image files
            image_files = [f for f in all_files if is_valid_frame(os.path.basename(f))]
            
            if not image_files:
                print(f"[ZipAnimation] No valid image files found in {zip_filepath}")
                return None
            
            # Sort files naturally (handling numeric sequences)
            image_files = sorted(image_files, key=natural_sort_key)
            
            # Create extraction directory
            extract_dir = get_animation_dir(md5)
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
                        print(f"[ZipAnimation] Error reading first frame dimensions: {e}")
            
            # Save metadata
            metadata = {
                "frame_count": len(frames),
                "frames": frames,
                "width": width,
                "height": height,
                "default_fps": 10,  # Default playback speed
                "original_files": image_files
            }
            
            metadata_path = os.path.join(extract_dir, "animation.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"[ZipAnimation] Extracted {len(frames)} frames from {os.path.basename(zip_filepath)}")
            
            return {
                "extract_dir": extract_dir,
                "first_frame": first_frame_path,
                **metadata
            }
            
    except zipfile.BadZipFile:
        print(f"[ZipAnimation] Invalid zip file: {zip_filepath}")
        return None
    except Exception as e:
        print(f"[ZipAnimation] Error extracting {zip_filepath}: {e}")
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

"""
Perceptual Hashing Module

Provides hash computation functions for visual similarity detection.
Supports images, videos, and zip animations.
"""
import os
from typing import Optional
from PIL import Image, UnidentifiedImageError
import imagehash
import config
from services import zip_animation_service
from database import models


def _log(message: str, level: str = "info"):
    """Centralized logging helper."""
    try:
        from services import monitor_service
        monitor_service.add_log(f"[Similarity] {message}", level)
    except Exception:
        print(f"[Similarity] {message}")


# ============================================================================
# Hash Computation
# ============================================================================

def compute_phash(image_path: str, hash_size: int = None) -> Optional[str]:
    """
    Compute perceptual hash for an image.
    
    Args:
        image_path: Path to the image file
        hash_size: Size of the hash (8 = 64-bit hash, 16 = 256-bit). Defaults to config.PHASH_SIZE.
    
    Returns:
        Hex string representation of the hash, or None on error
    """
    if hash_size is None:
        hash_size = config.PHASH_SIZE
    try:
        # Allow partial loading of truncated images (e.g., incomplete downloads)
        from PIL import ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (handles RGBA, P mode, etc.)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if 'A' in img.mode:
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            phash = imagehash.phash(img, hash_size=hash_size)
            return str(phash)
    except UnidentifiedImageError:
        _log(f"Cannot identify image: {image_path}", "warning")
        return None
    except OSError as e:
        # Catch truncated/corrupted image errors specifically
        if "truncated" in str(e).lower() or "image file is truncated" in str(e).lower():
            _log(f"Corrupted/incomplete image file (truncated): {os.path.basename(image_path)}", "error")
        else:
            _log(f"OS error reading image {os.path.basename(image_path)}: {e}", "error")
        return None
    except Exception as e:
        _log(f"Error computing hash for {image_path}: {e}", "error")
        return None


def compute_colorhash(image_path: str, binbits: int = 3) -> Optional[str]:
    """
    Compute color hash for an image (captures color distribution).
    
    Args:
        image_path: Path to the image file
        binbits: Bits per channel (3 = 8x8x8 bins)
    
    Returns:
        Hex string representation of the hash, or None on error
    """
    try:
        # Allow partial loading of truncated images
        from PIL import ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            chash = imagehash.colorhash(img, binbits=binbits)
            return str(chash)
    except UnidentifiedImageError:
        _log(f"Cannot identify image for colorhash: {image_path}", "warning")
        return None
    except OSError as e:
        # Catch truncated/corrupted image errors specifically
        if "truncated" in str(e).lower():
            _log(f"Corrupted/incomplete image file (truncated): {os.path.basename(image_path)}", "error")
        else:
            _log(f"OS error reading image for colorhash {os.path.basename(image_path)}: {e}", "error")
        return None
    except Exception as e:
        _log(f"Error computing colorhash for {image_path}: {e}", "error")
        return None


def compute_colorhash_for_video(video_path: str) -> Optional[str]:
    """Compute color hash from the first frame of a video."""
    from utils.video_utils import extract_first_frame
    
    frame = extract_first_frame(video_path)
    if frame is None:
        return None
    
    try:
        if frame.mode != 'RGB':
            frame = frame.convert('RGB')
        return str(imagehash.colorhash(frame))
    except Exception as e:
        _log(f"Error computing colorhash for video: {e}", "error")
        return None


def compute_phash_for_video(video_path: str, hash_size: int = None) -> Optional[str]:
    """Compute perceptual hash from the first frame of a video."""
    if hash_size is None:
        hash_size = config.PHASH_SIZE
    from utils.video_utils import extract_first_frame
    
    frame = extract_first_frame(video_path)
    if frame is None:
        return None
    
    try:
        if frame.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', frame.size, (255, 255, 255))
            if frame.mode == 'P':
                frame = frame.convert('RGBA')
            if 'A' in frame.mode:
                background.paste(frame, mask=frame.split()[-1])
            else:
                background.paste(frame)
            frame = background
        elif frame.mode != 'RGB':
            frame = frame.convert('RGB')
        
        return str(imagehash.phash(frame, hash_size=hash_size))
    except Exception as e:
        _log(f"Error computing phash for video: {e}", "error")
        return None


def compute_phash_for_zip_animation(md5: str) -> Optional[str]:
    """Compute perceptual hash from the first frame of a zip animation."""
    try:
        first_frame = zip_animation_service.get_frame_path(md5, 0)
        if first_frame and os.path.exists(first_frame):
            return compute_phash(first_frame)
        return None
    except Exception as e:
        _log(f"Error hashing zip animation: {e}", "error")
        return None


def compute_phash_for_file(filepath: str, md5: str = None) -> Optional[str]:
    """Compute perceptual hash for any supported file type."""
    if filepath.lower().endswith(config.SUPPORTED_VIDEO_EXTENSIONS):
        return compute_phash_for_video(filepath)
    elif filepath.lower().endswith(config.SUPPORTED_ZIP_EXTENSIONS):
        if md5:
            return compute_phash_for_zip_animation(md5)
        return None
    else:
        return compute_phash(filepath)


def compute_colorhash_for_file(filepath: str) -> Optional[str]:
    """Compute color hash for any supported file type."""
    if filepath.lower().endswith(config.SUPPORTED_VIDEO_EXTENSIONS):
        return compute_colorhash_for_video(filepath)
    elif filepath.lower().endswith(config.SUPPORTED_ZIP_EXTENSIONS):
        image_data = models.get_image_details(filepath)
        if image_data and image_data.get('md5'):
            md5 = image_data['md5']
            first_frame_path = zip_animation_service.get_frame_path(md5, 0)
            if first_frame_path and os.path.exists(first_frame_path):
                try:
                    img = Image.open(first_frame_path)
                    return str(imagehash.colorhash(img))
                except (OSError, IOError, UnidentifiedImageError) as e:
                    _log(f"Error computing colorhash for zip: {e}", "error")
                    return None
        return None
    else:
        return compute_colorhash(filepath)


# ============================================================================
# Hash Comparison
# ============================================================================

def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two hex hash strings.
    
    Lower distance = more similar. Max distance = PHASH_SIZE² (config-dependent).
    """
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return int(h1 - h2)
    except Exception:
        return config.PHASH_BITS


def hash_similarity_score(hash1: str, hash2: str, max_distance: int = None) -> float:
    """
    Convert Hamming distance to a similarity score (0.0 to 1.0).
    
    Returns:
        1.0 = identical, 0.0 = completely different
    """
    if max_distance is None:
        max_distance = config.PHASH_BITS
    distance = hamming_distance(hash1, hash2)
    return float(max(0.0, 1.0 - (distance / max_distance)))

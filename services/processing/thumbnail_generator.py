"""
Thumbnail generation for images, videos, and zip animations.
"""

import os
import subprocess
import tempfile
import shutil
from PIL import Image
import config

# Load from config
THUMB_DIR = config.THUMB_DIR
THUMB_SIZE = config.THUMB_SIZE
THUMB_QUALITY = config.THUMB_QUALITY

# ML Worker client - always import (no fallback to local loading)
try:
    from ml_worker.client import get_ml_worker_client
    ML_WORKER_AVAILABLE = True
except ImportError:
    ML_WORKER_AVAILABLE = False


def ensure_thumbnail(filepath, image_dir="./static/images", md5=None):
    """
    Create a thumbnail for an image, video, or zip animation.
    Handles both bucketed and legacy flat paths.
    
    Args:
        filepath: Path to the media file
        image_dir: Base image directory
        md5: Optional MD5 hash (required for zip animations)
    """
    # Get just the filename
    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]

    # Use bucketed structure for thumbnails
    # Try to extract bucket from input filepath first to support collision buckets
    from utils.file_utils import extract_bucket_from_path, get_hash_bucket
    
    path_bucket = extract_bucket_from_path(filepath)
    bucket = path_bucket if path_bucket else get_hash_bucket(filename)
    
    thumb_path = os.path.join(THUMB_DIR, bucket, base_name + '.webp')

    if not os.path.exists(thumb_path):
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # Try using ML Worker first
        if ML_WORKER_AVAILABLE:
            try:
                client = get_ml_worker_client()
                
                # Use ML Worker for all types (zip, video, image)
                # It handles logic internally
                print(f"[Thumbnail] Generating via ML Worker: {filename}")
                result = client.generate_thumbnail(
                    filepath=os.path.abspath(filepath),
                    output_path=os.path.abspath(thumb_path),
                    size=THUMB_SIZE,
                    quality=THUMB_QUALITY
                )
                
                if result and result.get('success'):
                    return
            except Exception as e:
                print(f"[Thumbnail] ML Worker generation failed: {e}. Falling back to local.")
                # Fall through to local logic

        try:
            # Check if this is a zip animation
            if filepath.lower().endswith('.zip'):
                if md5:
                    from services import zip_animation_service
                    # Get the first frame from the extracted animation
                    first_frame = zip_animation_service.get_frame_path(md5, 0)
                    if first_frame and os.path.exists(first_frame):
                        # Create thumbnail from first frame
                        with Image.open(first_frame) as img:
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P': img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                                img = background
                            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                            img.save(thumb_path, 'WEBP', quality=THUMB_QUALITY, method=6)
                        print(f"[Thumbnail] Created thumbnail for zip animation: {os.path.basename(filepath)}")
                    else:
                        print(f"[Thumbnail] ERROR: Could not find first frame for zip animation: {os.path.basename(filepath)}")
                else:
                    print(f"[Thumbnail] ERROR: MD5 required for zip animation thumbnail: {os.path.basename(filepath)}")
            # Check if this is a video file
            elif filepath.lower().endswith(('.mp4', '.webm')):
                # Extract first frame from video using ffmpeg
                # Check if ffmpeg is available
                ffmpeg_path = shutil.which('ffmpeg')
                if not ffmpeg_path:
                    print(f"[Thumbnail] ERROR: ffmpeg not found. Cannot create thumbnail for video: {os.path.basename(filepath)}")
                    print(f"[Thumbnail] Install ffmpeg to enable video thumbnail generation.")
                    return  # Skip thumbnail creation for this video

                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                    temp_frame_path = temp_frame.name
                try:
                    # Extract frame at 0.1 seconds (works for short videos too)
                    subprocess.run([
                        ffmpeg_path, '-ss', '0.1', '-i', filepath, '-vframes', '1',
                        '-strict', 'unofficial', '-y', temp_frame_path
                    ], check=True, capture_output=True)
                    # Now process the extracted frame as an image
                    with Image.open(temp_frame_path) as img:
                        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                        img.save(thumb_path, 'WEBP', quality=THUMB_QUALITY, method=6)
                finally:
                    if os.path.exists(temp_frame_path):
                        os.unlink(temp_frame_path)
            else:
                # Regular image processing
                with Image.open(filepath) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P': img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                        img = background
                    img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                    img.save(thumb_path, 'WEBP', quality=THUMB_QUALITY, method=6)
        except Exception as e:
            print(f"Thumbnail error for {filepath}: {e}")

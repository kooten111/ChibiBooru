"""
Thumbnail generation handler
"""
import os
import shutil
import logging
import zipfile
import subprocess
import tempfile
from typing import Dict, Any

from ml_worker.utils import is_valid_frame, natural_sort_key

logger = logging.getLogger(__name__)

def handle_generate_thumbnail(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle generate_thumbnail request.
    Generates thumbnail for image, video, or zip animation.
    """
    filepath = request_data['filepath']
    output_path = request_data['output_path']
    size = request_data.get('size', 512)
    quality = request_data.get('quality', 85)

    if not os.path.exists(filepath):
        logger.warning(f"Source file not found: {filepath}")
        raise FileNotFoundError(f"No such file or directory: {filepath}")

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
                
                try:
                    with zf.open(first_frame) as src:
                        with Image.open(src) as img:
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P': img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                                img = background
                            img.thumbnail((size, size), Image.Resampling.LANCZOS)
                            img.save(output_path, 'WEBP', quality=quality, method=6)
                except OSError as e:
                    # Handle truncated images in zip
                    if 'truncated' in str(e).lower() or 'corrupted' in str(e).lower():
                        logger.warning(f"Image in zip is truncated, attempting recovery: {first_frame}")
                        from PIL import ImageFile
                        ImageFile.LOAD_TRUNCATED_IMAGES = True
                        try:
                            with zf.open(first_frame) as src:
                                with Image.open(src) as img:
                                    if img.mode in ('RGBA', 'LA', 'P'):
                                        background = Image.new('RGB', img.size, (255, 255, 255))
                                        if img.mode == 'P': img = img.convert('RGBA')
                                        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                                        img = background
                                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                                    img.save(output_path, 'WEBP', quality=quality, method=6)
                        finally:
                            ImageFile.LOAD_TRUNCATED_IMAGES = False
                        
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
                
                try:
                    with Image.open(temp_frame_path) as img:
                        img.thumbnail((size, size), Image.Resampling.LANCZOS)
                        img.save(output_path, 'WEBP', quality=quality, method=6)
                except OSError as e:
                    # Handle truncated frame images
                    if 'truncated' in str(e).lower() or 'corrupted' in str(e).lower():
                        logger.warning(f"Extracted frame is truncated, attempting recovery: {temp_frame_path}")
                        from PIL import ImageFile
                        ImageFile.LOAD_TRUNCATED_IMAGES = True
                        try:
                            with Image.open(temp_frame_path) as img:
                                img.thumbnail((size, size), Image.Resampling.LANCZOS)
                                img.save(output_path, 'WEBP', quality=quality, method=6)
                        finally:
                            ImageFile.LOAD_TRUNCATED_IMAGES = False
            finally:
                if os.path.exists(temp_frame_path):
                    os.unlink(temp_frame_path)
                    
        # Handle Regular Image
        else:
            try:
                with Image.open(filepath) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P': img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                        img = background
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                    img.save(output_path, 'WEBP', quality=quality, method=6)
            except OSError as e:
                # Handle truncated images
                if 'truncated' in str(e).lower() or 'corrupted' in str(e).lower():
                    logger.warning(f"Image file is truncated, attempting recovery: {filepath}")
                    from PIL import ImageFile
                    ImageFile.LOAD_TRUNCATED_IMAGES = True
                    try:
                        with Image.open(filepath) as img:
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P': img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                                img = background
                            img.thumbnail((size, size), Image.Resampling.LANCZOS)
                            img.save(output_path, 'WEBP', quality=quality, method=6)
                    finally:
                        ImageFile.LOAD_TRUNCATED_IMAGES = False
                
        return {"success": True, "output_path": output_path}
        
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}")
        raise

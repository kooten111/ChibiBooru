"""
Animation extraction handler
"""
import os
import json
import logging
import zipfile
from typing import Dict, Any

from ml_worker.utils import is_valid_frame, natural_sort_key

logger = logging.getLogger(__name__)

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
                "default_fps": 24,
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

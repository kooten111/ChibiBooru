"""
Video Utilities

Provides helper functions for video processing, primarily frame extraction.
"""
import os
import subprocess
import tempfile
from typing import Optional
from PIL import Image


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False


def extract_first_frame(video_path: str) -> Optional[Image.Image]:
    """
    Extract the first frame from a video file as a PIL Image.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        PIL Image of the first frame, or None on error
    """
    if not is_ffmpeg_available():
        print("[VideoUtils] ffmpeg not found, cannot extract video frame")
        return None
    
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vframes', '1', '-f', 'image2',
            tmp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            img = Image.open(tmp_path)
            # Load image into memory before closing file
            img.load()
            os.unlink(tmp_path)
            return img
        
        return None
    except Exception as e:
        print(f"[VideoUtils] Error extracting video frame: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return None

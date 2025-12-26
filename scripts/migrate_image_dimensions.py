#!/usr/bin/env python3
"""
Migration script to populate image_width and image_height for existing images.

This script:
1. Queries all images with NULL dimensions
2. Opens each file with PIL (or ffprobe for videos) to get dimensions
3. Updates the database in batches

Usage:
    python scripts/migrate_image_dimensions.py
"""

import os
import sys
import shutil

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection
from PIL import Image
from tqdm import tqdm
import config


def get_video_dimensions(filepath):
    """Get video dimensions using ffprobe."""
    import subprocess
    ffprobe_path = shutil.which('ffprobe')
    if not ffprobe_path:
        return None, None
    
    try:
        result = subprocess.run([
            ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
            filepath
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(',')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
    except Exception as e:
        print(f"  ffprobe error: {e}")
    
    return None, None


def get_zip_animation_dimensions(md5):
    """Get dimensions from the first frame of a zip animation."""
    try:
        from services import zip_animation_service
        first_frame = zip_animation_service.get_frame_path(md5, 0)
        if first_frame and os.path.exists(first_frame):
            with Image.open(first_frame) as img:
                return img.width, img.height
    except Exception as e:
        print(f"  Zip animation error: {e}")
    return None, None


def get_image_dimensions(filepath):
    """Get image dimensions using PIL."""
    try:
        with Image.open(filepath) as img:
            return img.width, img.height
    except Exception as e:
        print(f"  PIL error: {e}")
    return None, None


def migrate_dimensions(batch_size=100):
    """Main migration function."""
    print("Image Dimensions Migration")
    print("=" * 50)
    
    # Get count of images needing migration
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM images 
            WHERE image_width IS NULL OR image_height IS NULL
        """)
        total_count = cursor.fetchone()[0]
        
        if total_count == 0:
            print("✅ All images already have dimensions populated!")
            return
        
        print(f"Found {total_count} images needing dimension migration")
        
        # Get all images needing migration
        cursor.execute("""
            SELECT id, filepath, md5 FROM images 
            WHERE image_width IS NULL OR image_height IS NULL
        """)
        images = cursor.fetchall()
    
    updated = 0
    errors = 0
    
    for img in tqdm(images, desc="Migrating dimensions"):
        image_id = img['id']
        filepath = img['filepath']
        md5 = img['md5']
        
        # Build full path
        full_path = os.path.join(config.IMAGE_DIRECTORY, filepath)
        
        if not os.path.exists(full_path):
            errors += 1
            continue
        
        width, height = None, None
        
        # Determine file type and get dimensions
        if filepath.lower().endswith('.zip'):
            width, height = get_zip_animation_dimensions(md5)
        elif filepath.lower().endswith(('.mp4', '.webm')):
            width, height = get_video_dimensions(full_path)
        else:
            width, height = get_image_dimensions(full_path)
        
        if width and height:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE images 
                    SET image_width = ?, image_height = ?
                    WHERE id = ?
                """, (width, height, image_id))
                conn.commit()
            updated += 1
        else:
            errors += 1
    
    print()
    print(f"✅ Migration complete!")
    print(f"   Updated: {updated}")
    print(f"   Errors:  {errors}")


if __name__ == "__main__":
    migrate_dimensions()

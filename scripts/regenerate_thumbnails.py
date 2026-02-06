#!/usr/bin/env python3
"""
Multithreaded Thumbnail Regeneration Script

This script regenerates thumbnails for all images in the database.
It uses THUMB_SIZE from config to determine the target size.

Features:
- Multithreaded thumbnail generation
- Progress bar with tqdm
- Skips non-existent source files
- Optional: regenerate all thumbnails or only outdated ones

Usage:
    # Regenerate thumbnails with wrong dimensions
    python scripts/regenerate_thumbnails.py

    # Force regenerate ALL thumbnails
    python scripts/regenerate_thumbnails.py --all

    # Use specific number of threads
    python scripts/regenerate_thumbnails.py --threads 8

    # Dry run (show what would be regenerated)
    python scripts/regenerate_thumbnails.py --dry-run
"""

import os
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from PIL import Image
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database.core import get_db_connection
from utils.file_utils import extract_bucket_from_path, get_hash_bucket


# Global stats
stats_lock = Lock()
stats = {
    'regenerated': 0,
    'skipped_correct_size': 0,
    'skipped_no_source': 0,
    'skipped_no_thumb': 0,
    'errors': 0,
}


def get_thumbnail_path(filepath: str) -> str:
    """Get the thumbnail path for an image filepath."""
    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]
    
    # Extract bucket from source path or compute from filename
    path_bucket = extract_bucket_from_path(filepath)
    bucket = path_bucket if path_bucket else get_hash_bucket(filename)
    
    return os.path.join(config.THUMB_DIR, bucket, base_name + '.webp')


def check_thumbnail_size(thumb_path: str, target_size: int) -> bool:
    """
    Check if a thumbnail's max dimension matches the target size.
    Returns True if the thumbnail is the correct size.
    """
    try:
        with Image.open(thumb_path) as img:
            width, height = img.size
            max_dim = max(width, height)
            # Allow for some tolerance (within 5% or 10px)
            tolerance = max(10, target_size * 0.05)
            return abs(max_dim - target_size) <= tolerance
    except Exception:
        return False


def regenerate_thumbnail(
    filepath: str, 
    image_dir: str,
    target_size: int,
    quality: int,
    dry_run: bool = False
) -> dict:
    """
    Regenerate a single thumbnail.
    
    Returns a dict with status info.
    """
    result = {
        'filepath': filepath,
        'status': 'unknown',
        'error': None,
    }
    
    # Get full path to source image
    if not os.path.isabs(filepath):
        source_path = os.path.join(image_dir, filepath)
    else:
        source_path = filepath
    
    # Normalize path
    source_path = os.path.abspath(source_path)
    
    # Check if source exists
    if not os.path.exists(source_path):
        result['status'] = 'no_source'
        return result
    
    # Get thumbnail path
    thumb_path = get_thumbnail_path(source_path)
    
    # In dry-run mode, just check what would be done
    if dry_run:
        if not os.path.exists(thumb_path):
            result['status'] = 'would_create'
        elif not check_thumbnail_size(thumb_path, target_size):
            result['status'] = 'would_regenerate'
        else:
            result['status'] = 'correct_size'
        return result
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # Handle different file types
        ext = os.path.splitext(source_path)[1].lower()
        
        if ext == '.zip':
            # For zip animations, try to get first frame
            try:
                # Get MD5 from database for zip
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT md5 FROM images WHERE filepath = ?", (filepath,))
                    row = cur.fetchone()
                    if row:
                        from services import zip_animation_service
                        first_frame = zip_animation_service.get_frame_path(row['md5'], 0)
                        if first_frame and os.path.exists(first_frame):
                            _create_thumbnail_from_image(first_frame, thumb_path, target_size, quality)
                            result['status'] = 'regenerated'
                            return result
            except Exception as e:
                result['status'] = 'error'
                result['error'] = f'Zip animation error: {e}'
                return result
                
            result['status'] = 'error'
            result['error'] = 'Could not extract frame from zip'
            return result
            
        elif ext in ('.mp4', '.webm'):
            # For videos, extract frame using ffmpeg
            try:
                import subprocess
                import tempfile
                import shutil
                
                ffmpeg_path = shutil.which('ffmpeg')
                if not ffmpeg_path:
                    result['status'] = 'error'
                    result['error'] = 'ffmpeg not found'
                    return result
                
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                    temp_frame_path = temp_frame.name
                
                try:
                    subprocess.run([
                        ffmpeg_path, '-ss', '0.1', '-i', source_path, '-vframes', '1',
                        '-strict', 'unofficial', '-y', temp_frame_path
                    ], check=True, capture_output=True)
                    
                    _create_thumbnail_from_image(temp_frame_path, thumb_path, target_size, quality)
                    result['status'] = 'regenerated'
                finally:
                    if os.path.exists(temp_frame_path):
                        os.unlink(temp_frame_path)
                        
            except subprocess.CalledProcessError as e:
                result['status'] = 'error'
                result['error'] = f'ffmpeg error: {e}'
                return result
            except Exception as e:
                result['status'] = 'error'
                result['error'] = str(e)
                return result
        else:
            # Regular image
            _create_thumbnail_from_image(source_path, thumb_path, target_size, quality)
            result['status'] = 'regenerated'
            
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)
    
    return result


def _create_thumbnail_from_image(source_path: str, thumb_path: str, target_size: int, quality: int):
    """Create a thumbnail from an image file."""
    with Image.open(source_path) as img:
        # Handle transparency
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = background
        
        # Resize maintaining aspect ratio
        img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
        
        # Save as WebP
        img.save(thumb_path, 'WEBP', quality=quality, method=6)


def get_all_image_filepaths() -> list:
    """Get all image filepaths from the database."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filepath FROM images ORDER BY id")
        return [row['filepath'] for row in cur.fetchall()]


def filter_images_needing_regeneration(
    filepaths: list, 
    target_size: int,
    regenerate_all: bool = False,
    image_dir: str = "./static/images"
) -> list:
    """Filter images that need thumbnail regeneration."""
    needs_regeneration = []
    
    for filepath in tqdm(filepaths, desc="Scanning thumbnails"):
        # Get full path to source image
        if not os.path.isabs(filepath):
            source_path = os.path.join(image_dir, filepath)
        else:
            source_path = filepath
        source_path = os.path.abspath(source_path)
        
        # Skip if source doesn't exist
        if not os.path.exists(source_path):
            continue
        
        thumb_path = get_thumbnail_path(source_path)
        
        # If regenerating all, include all images with existing sources
        if regenerate_all:
            needs_regeneration.append(filepath)
            continue
        
        # Check if thumbnail exists
        if not os.path.exists(thumb_path):
            # No thumbnail - might need to generate
            needs_regeneration.append(filepath)
            continue
        
        # Check if thumbnail size is wrong
        if not check_thumbnail_size(thumb_path, target_size):
            needs_regeneration.append(filepath)
    
    return needs_regeneration


def main():
    parser = argparse.ArgumentParser(
        description='Regenerate thumbnails at the current THUMB_SIZE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/regenerate_thumbnails.py            # Regenerate wrong-sized thumbnails
  python scripts/regenerate_thumbnails.py --all      # Regenerate ALL thumbnails  
  python scripts/regenerate_thumbnails.py --threads 8  # Use 8 threads
  python scripts/regenerate_thumbnails.py --dry-run  # Preview what would be done
        """
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Regenerate ALL thumbnails, not just wrong-sized ones'
    )
    parser.add_argument(
        '--threads', '-t',
        type=int,
        default=config.MAX_WORKERS,
        help=f'Number of threads to use (default: {config.MAX_WORKERS})'
    )
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Show what would be regenerated without making changes'
    )
    parser.add_argument(
        '--image-dir',
        type=str,
        default=config.IMAGE_DIRECTORY,
        help=f'Image directory (default: {config.IMAGE_DIRECTORY})'
    )
    
    args = parser.parse_args()
    
    # Display current configuration
    print(f"\n{'='*60}")
    print(f"Thumbnail Regeneration Script")
    print(f"{'='*60}")
    print(f"Target Size: {config.THUMB_SIZE}px (max dimension)")
    print(f"Quality: {config.THUMB_QUALITY}")
    print(f"Output Dir: {config.THUMB_DIR}")
    print(f"Threads: {args.threads}")
    print(f"Mode: {'Regenerate ALL' if args.all else 'Only wrong-sized'}")
    if args.dry_run:
        print(f"DRY RUN - No changes will be made")
    print(f"{'='*60}\n")
    
    # Get all image filepaths
    print("Fetching image list from database...")
    all_filepaths = get_all_image_filepaths()
    print(f"Found {len(all_filepaths)} images in database")
    
    # Filter to ones needing regeneration
    print("\nScanning for thumbnails that need regeneration...")
    to_regenerate = filter_images_needing_regeneration(
        all_filepaths,
        config.THUMB_SIZE,
        regenerate_all=args.all,
        image_dir=args.image_dir
    )
    
    if not to_regenerate:
        print("\n✓ All thumbnails are already the correct size!")
        return 0
    
    print(f"\nFound {len(to_regenerate)} thumbnails to {'regenerate' if not args.dry_run else 'check'}")
    
    if args.dry_run:
        # In dry-run, just show what would be done
        print("\nDry run results:")
        would_create = 0
        would_regenerate = 0
        correct = 0
        
        for filepath in tqdm(to_regenerate, desc="Checking"):
            result = regenerate_thumbnail(
                filepath,
                args.image_dir,
                config.THUMB_SIZE,
                config.THUMB_QUALITY,
                dry_run=True
            )
            if result['status'] == 'would_create':
                would_create += 1
            elif result['status'] == 'would_regenerate':
                would_regenerate += 1
            elif result['status'] == 'correct_size':
                correct += 1
        
        print(f"\n  Would create new: {would_create}")
        print(f"  Would regenerate: {would_regenerate}")
        print(f"  Already correct: {correct}")
        return 0
    
    # Regenerate thumbnails with thread pool
    print(f"\nRegenerating thumbnails using {args.threads} threads...")
    
    regenerated = 0
    errors = 0
    
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(
                regenerate_thumbnail,
                filepath,
                args.image_dir,
                config.THUMB_SIZE,
                config.THUMB_QUALITY,
                False
            ): filepath
            for filepath in to_regenerate
        }
        
        with tqdm(total=len(futures), desc="Regenerating") as pbar:
            for future in as_completed(futures):
                result = future.result()
                
                if result['status'] == 'regenerated':
                    regenerated += 1
                elif result['status'] == 'error':
                    errors += 1
                    if result['error']:
                        tqdm.write(f"Error: {result['filepath']}: {result['error']}")
                
                pbar.update(1)
    
    # Print summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"  Regenerated: {regenerated}")
    print(f"  Errors: {errors}")
    print(f"{'='*60}\n")
    
    if errors > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

# utils/deduplication.py
"""
MD5-based deduplication utility.
Prevents duplicate images from being processed or downloaded.
"""

import os
import json
import hashlib
from pathlib import Path

METADATA_DIR = "./metadata"
STATIC_IMAGES = "./static/images"


def get_md5(filepath):
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def build_md5_index():
    """
    Build a mapping of MD5 -> filepath from all existing metadata files.
    Returns dict: {md5: relative_path}
    """
    md5_index = {}
    
    if not os.path.isdir(METADATA_DIR):
        return md5_index
    
    for metadata_file in Path(METADATA_DIR).glob("*.json"):
        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            
            md5 = metadata.get("md5")
            relative_path = metadata.get("relative_path")
            
            if md5 and relative_path:
                md5_index[md5] = relative_path
        
        except Exception as e:
            print(f"Warning: Could not read {metadata_file}: {e}")
            continue
    
    return md5_index


def is_duplicate(filepath, md5_index=None):
    """
    Check if a file's MD5 already exists in the collection.
    
    Args:
        filepath: Path to the image file (can be full or relative)
        md5_index: Optional pre-built MD5 index (for batch operations)
    
    Returns:
        tuple: (is_duplicate: bool, existing_path: str or None, md5: str)
    """
    # Build index if not provided
    if md5_index is None:
        md5_index = build_md5_index()
    
    # Ensure we have the full path
    if not filepath.startswith(STATIC_IMAGES):
        full_path = os.path.join(STATIC_IMAGES, filepath)
    else:
        full_path = filepath
    
    # Calculate MD5 of the new file
    try:
        new_md5 = get_md5(full_path)
    except FileNotFoundError:
        print(f"File not found: {full_path}")
        return False, None, None
    except Exception as e:
        print(f"Error calculating MD5 for {full_path}: {e}")
        return False, None, None
    
    # Check if this MD5 exists
    if new_md5 in md5_index:
        return True, md5_index[new_md5], new_md5
    
    return False, None, new_md5


def remove_duplicate(filepath):
    """
    Remove a duplicate image file and its thumbnail.
    Does NOT remove metadata (since it's shared by MD5).
    
    Args:
        filepath: Path to the duplicate image file
    
    Returns:
        bool: True if successfully removed
    """
    # Remove image
    full_path = os.path.join(STATIC_IMAGES, filepath) if not filepath.startswith(STATIC_IMAGES) else filepath
    
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
            print(f"Removed duplicate image: {filepath}")
        
        # Remove thumbnail
        rel_path = os.path.relpath(full_path, STATIC_IMAGES)
        thumb_path = os.path.join("./static/thumbnails", os.path.splitext(rel_path)[0] + '.webp')
        
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
            print(f"Removed thumbnail: {thumb_path}")
        
        return True
    
    except Exception as e:
        print(f"Error removing duplicate {filepath}: {e}")
        return False


def scan_and_remove_duplicates(dry_run=True):
    """
    Scan all images and remove duplicates based on MD5.
    Keeps the first occurrence (by metadata file order).
    
    Args:
        dry_run: If True, only report duplicates without removing them
    
    Returns:
        dict: Statistics about duplicates found/removed
    """
    print("Building MD5 index from metadata...")
    md5_index = build_md5_index()
    
    print(f"Scanning images in {STATIC_IMAGES}...")
    
    duplicates_found = []
    images_scanned = 0
    
    for root, _, files in os.walk(STATIC_IMAGES):
        for file in files:
            if not file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                continue
            
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, STATIC_IMAGES)
            
            images_scanned += 1
            
            # Check for duplicate
            is_dup, existing_path, md5 = is_duplicate(full_path, md5_index)
            
            if is_dup and existing_path != rel_path:
                duplicates_found.append({
                    'duplicate': rel_path,
                    'original': existing_path,
                    'md5': md5
                })
                
                if not dry_run:
                    remove_duplicate(rel_path)
    
    # Print report
    print(f"\n{'='*60}")
    print(f"Scan complete: {images_scanned} images scanned")
    print(f"Duplicates found: {len(duplicates_found)}")
    
    if duplicates_found:
        print(f"\n{'DRY RUN - ' if dry_run else ''}Duplicate images:")
        for dup in duplicates_found:
            print(f"  {dup['duplicate']}")
            print(f"    → matches {dup['original']} (MD5: {dup['md5'][:8]}...)")
    
    if dry_run and duplicates_found:
        print(f"\nRun with dry_run=False to actually remove duplicates")
    
    print(f"{'='*60}\n")
    
    return {
        'scanned': images_scanned,
        'duplicates_found': len(duplicates_found),
        'duplicates': duplicates_found,
        'removed': 0 if dry_run else len(duplicates_found)
    }


if __name__ == "__main__":
    # Run as standalone script
    import sys
    
    dry_run = "--remove" not in sys.argv
    
    print("MD5 Deduplication Tool")
    print("="*60)
    
    if dry_run:
        print("Running in DRY RUN mode (no files will be deleted)")
        print("Use --remove flag to actually delete duplicates")
    else:
        print("WARNING: This will DELETE duplicate files!")
        response = input("Continue? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            sys.exit(0)
    
    print()
    results = scan_and_remove_duplicates(dry_run=dry_run)
#!/usr/bin/env python3
"""
Migration script to move existing images from flat directory structure
to hash-based bucketed structure.

This script:
1. Scans all images in static/images/
2. Moves each file to a bucketed subdirectory based on filename hash
3. Updates the database filepath entries
4. Migrates thumbnails to bucketed structure as well

Usage:
    python migrate_to_bucketed_structure.py [--dry-run] [--limit N]

Options:
    --dry-run   Show what would be done without actually moving files
    --limit N   Only process first N images (for testing)
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from database import get_db_connection
from utils.file_utils import get_hash_bucket, ensure_bucket_dir


def is_bucket_dir(dirname):
    """Check if a directory name looks like a hash bucket (3 hex chars)."""
    return len(dirname) == 3 and all(c in '0123456789abcdef' for c in dirname.lower())


def get_all_flat_files(base_dir="./static/images"):
    """
    Get all files that are NOT in bucketed subdirectories.

    This includes:
    - Files directly in the root images directory
    - Files in custom subdirectories (like "Senip", "artwork", etc.)

    Excludes:
    - Files already in bucket directories (abc, 123, etc.)

    Returns:
        List of tuples (full_path, filename, source_subdir)
        where source_subdir is None for root files, or the subdir name
    """
    flat_files = []

    # Get files in root directory
    for item in os.listdir(base_dir):
        full_path = os.path.join(base_dir, item)
        if os.path.isfile(full_path):
            flat_files.append((full_path, item, None))

    # Check subdirectories
    for item in os.listdir(base_dir):
        full_path = os.path.join(base_dir, item)
        if os.path.isdir(full_path):
            # Skip if it's a bucket directory
            if is_bucket_dir(item):
                continue

            # It's a custom subdirectory - process files in it
            subdir_name = item
            for subfile in os.listdir(full_path):
                subfile_path = os.path.join(full_path, subfile)
                if os.path.isfile(subfile_path):
                    flat_files.append((subfile_path, subfile, subdir_name))

    return flat_files


def migrate_file(filepath, filename, dry_run=False):
    """
    Move a file to its bucketed location.

    Args:
        filepath: Full path to the file
        filename: Just the filename
        dry_run: If True, don't actually move files

    Returns:
        Tuple of (old_rel_path, new_rel_path, success)
    """
    # Get bucket and create directory
    bucket = get_hash_bucket(filename)
    bucket_dir = os.path.join(config.IMAGE_DIRECTORY, bucket)

    # Old and new paths (relative to static/)
    old_rel_path = f"images/{filename}"
    new_rel_path = f"images/{bucket}/{filename}"

    dest_path = os.path.join(config.IMAGE_DIRECTORY, bucket, filename)

    if os.path.exists(dest_path):
        print(f"  ⚠ Destination already exists: {new_rel_path}")
        return (old_rel_path, new_rel_path, False)

    if dry_run:
        print(f"  [DRY RUN] Would move: {filename} → {bucket}/")
        return (old_rel_path, new_rel_path, True)

    try:
        # Create bucket directory
        os.makedirs(bucket_dir, exist_ok=True)

        # Move the file
        shutil.move(filepath, dest_path)
        print(f"  ✓ Moved: {filename} → {bucket}/")
        return (old_rel_path, new_rel_path, True)
    except Exception as e:
        print(f"  ✗ Error moving {filename}: {e}")
        return (old_rel_path, new_rel_path, False)


def migrate_thumbnail(filename, dry_run=False):
    """
    Move thumbnail to bucketed structure if it exists.

    Args:
        filename: Original image filename
        dry_run: If True, don't actually move files
    """
    # Get thumbnail filename
    base_name = os.path.splitext(filename)[0]
    thumb_filename = base_name + '.webp'

    # Check if flat thumbnail exists
    flat_thumb = os.path.join(config.THUMB_DIR, thumb_filename)
    if not os.path.exists(flat_thumb):
        return False

    # Get bucket and create directory
    bucket = get_hash_bucket(filename)
    bucket_dir = os.path.join(config.THUMB_DIR, bucket)
    dest_path = os.path.join(bucket_dir, thumb_filename)

    if os.path.exists(dest_path):
        return False

    if dry_run:
        print(f"    [DRY RUN] Would move thumbnail: {thumb_filename} → thumbnails/{bucket}/")
        return True

    try:
        os.makedirs(bucket_dir, exist_ok=True)
        shutil.move(flat_thumb, dest_path)
        print(f"    ✓ Moved thumbnail: {thumb_filename} → {bucket}/")
        return True
    except Exception as e:
        print(f"    ✗ Error moving thumbnail {thumb_filename}: {e}")
        return False


def update_database_path(old_path, new_path, dry_run=False):
    """
    Update filepath in database.

    Args:
        old_path: Old relative path (e.g., "images/file.jpg")
        new_path: New relative path (e.g., "images/abc/file.jpg")
        dry_run: If True, don't actually update database

    Returns:
        Boolean indicating success
    """
    # Database stores paths without "images/" prefix
    old_db_path = old_path.replace("images/", "", 1)
    new_db_path = new_path.replace("images/", "", 1)

    if dry_run:
        return True

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Check if new_db_path already exists (database already updated)
            cursor.execute("SELECT filepath FROM images WHERE filepath = ?", (new_db_path,))
            if cursor.fetchone():
                print(f"    ✓ Database already has bucketed path: {new_db_path}")
                return True

            # Update filepath in images table
            cursor.execute("""
                UPDATE images
                SET filepath = ?
                WHERE filepath = ?
            """, (new_db_path, old_db_path))

            # Update FTS table
            cursor.execute("""
                UPDATE images_fts
                SET filepath = ?
                WHERE filepath = ?
            """, (new_db_path, old_db_path))

            conn.commit()

            if cursor.rowcount > 0:
                print(f"    ✓ Updated database: {old_db_path} → {new_db_path}")
                return True
            else:
                print(f"    ⚠ No flat database entry found - may already be migrated")
                return True  # Consider this a success, file is moved
    except Exception as e:
        print(f"    ✗ Error updating database for {old_db_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Migrate images to hash-based bucketed directory structure'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, default=None,
                        help='Only process first N images (for testing)')
    args = parser.parse_args()

    print("=" * 70)
    print("Image Bucketing Migration Script")
    print("=" * 70)
    print(f"Source: {config.IMAGE_DIRECTORY}")
    print(f"Bucket size: 3 hex chars (4096 buckets)")

    if args.dry_run:
        print("\n⚠ DRY RUN MODE - No changes will be made\n")
    else:
        print("\n⚠ WARNING: This will move files and update database!")
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    print("\nScanning for images in flat structure...")
    flat_files = get_all_flat_files(config.IMAGE_DIRECTORY)

    if not flat_files:
        print("✓ No images found in flat structure. All images already bucketed!")
        return

    print(f"Found {len(flat_files)} images to migrate")

    if args.limit:
        flat_files = flat_files[:args.limit]
        print(f"Limiting to first {args.limit} images (--limit)")

    print("\nStarting migration...")
    print("-" * 70)

    success_count = 0
    error_count = 0
    skipped_count = 0
    subdirs_found = set()

    for i, (filepath, filename, source_subdir) in enumerate(flat_files, 1):
        if source_subdir:
            print(f"\n[{i}/{len(flat_files)}] Processing: {source_subdir}/{filename}")
            subdirs_found.add(source_subdir)
        else:
            print(f"\n[{i}/{len(flat_files)}] Processing: {filename}")

        # Migrate the image file
        old_path, new_path, success = migrate_file(filepath, filename, args.dry_run)

        if not success:
            skipped_count += 1
            continue

        # Update database
        if update_database_path(old_path, new_path, args.dry_run):
            success_count += 1

            # Migrate thumbnail if it exists
            migrate_thumbnail(filename, args.dry_run)
        else:
            error_count += 1

    # Clean up empty subdirectories
    if subdirs_found and not args.dry_run:
        print("\n" + "-" * 70)
        print("Cleaning up empty subdirectories...")
        for subdir in subdirs_found:
            subdir_path = os.path.join(config.IMAGE_DIRECTORY, subdir)
            if os.path.exists(subdir_path) and os.path.isdir(subdir_path):
                try:
                    # Check if empty
                    if not os.listdir(subdir_path):
                        os.rmdir(subdir_path)
                        print(f"  ✓ Removed empty directory: {subdir}/")
                    else:
                        print(f"  ⚠ Directory not empty (skipped): {subdir}/")
                except Exception as e:
                    print(f"  ✗ Error removing {subdir}/: {e}")

    print("\n" + "=" * 70)
    print("Migration Complete")
    print("=" * 70)
    print(f"Successfully migrated: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Total: {len(flat_files)}")

    if subdirs_found:
        print(f"\nCustom subdirectories processed: {', '.join(sorted(subdirs_found))}")

    if args.dry_run:
        print("\n⚠ This was a DRY RUN - no changes were made")
        print("Run without --dry-run to perform actual migration")


if __name__ == '__main__':
    main()

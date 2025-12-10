#!/usr/bin/env python3
"""
Reprocess all existing Pixiv images to add local tagger complementary tags.

This script finds all images that:
1. Have Pixiv as a source
2. Don't have local_tagger as a source (or need to update local tagger results)

Then it runs the local tagger on them and merges the results.
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from repositories.data_access import get_db_connection
from services import processing_service as processing
from utils.tag_extraction import extract_tags_from_source, merge_tag_sources, deduplicate_categorized_tags


def get_pixiv_images_needing_reprocessing():
    """Get all Pixiv images that need local tagger complement."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find images that have Pixiv as a source but no local_tagger source
        cur.execute("""
            SELECT DISTINCT i.id, i.filepath, i.md5, i.active_source
            FROM images i
            JOIN image_sources isrc ON i.id = isrc.image_id
            JOIN sources s ON isrc.source_id = s.id
            WHERE s.name = 'pixiv'
            AND i.id NOT IN (
                SELECT image_id
                FROM image_sources isrc2
                JOIN sources s2 ON isrc2.source_id = s2.id
                WHERE s2.name = 'local_tagger'
            )
            ORDER BY i.id
        """)

        return cur.fetchall()


def reprocess_pixiv_image(image_row, dry_run=False):
    """Reprocess a single Pixiv image with local tagger complement."""
    image_id = image_row['id']
    filepath = image_row['filepath']
    md5 = image_row['md5']
    active_source = image_row['active_source']

    print(f"\n[{image_id}] Processing: {filepath}")
    print(f"  Current active source: {active_source}")

    # Construct full filepath
    full_path = os.path.join("static/images", filepath)
    if not os.path.exists(full_path):
        print(f"  ⚠️  WARNING: File not found on disk: {full_path}")
        return False

    if dry_run:
        print(f"  ✓ Would reprocess this image (dry run)")
        return True

    try:
        # Get existing raw metadata
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT data FROM raw_metadata WHERE image_id = ?", (image_id,))
            result = cur.fetchone()

            if not result:
                print(f"  ⚠️  WARNING: No raw metadata found")
                return False

            import json
            raw_metadata = json.loads(result['data'])
            all_results = raw_metadata.get('sources', {})

            if 'pixiv' not in all_results:
                print(f"  ⚠️  WARNING: Pixiv source not found in raw metadata")
                return False

        # Run local tagger
        print(f"  🤖 Running local tagger...")
        local_tagger_result = processing.tag_with_local_tagger(full_path)

        if not local_tagger_result:
            print(f"  ❌ Local tagger failed")
            return False

        # Add local tagger results to all_results
        all_results[local_tagger_result['source']] = local_tagger_result['data']
        tag_count = len([t for v in local_tagger_result['data']['tags'].values() for t in v])
        pred_count = len(local_tagger_result['data'].get('all_predictions', []))
        print(f"  ✓ Local tagger: {tag_count} display tags, {pred_count} stored predictions")

        # Extract and merge tags
        pixiv_tags = extract_tags_from_source(all_results['pixiv'], 'pixiv')
        local_tagger_tags = extract_tags_from_source(all_results['local_tagger'], 'local_tagger')

        # Merge all categories except artist (Pixiv artist is usually accurate)
        merged_tags = merge_tag_sources(
            pixiv_tags,
            local_tagger_tags,
            merge_categories=['character', 'copyright', 'species', 'meta', 'general']
        )

        # Deduplicate tags across categories
        merged_tags = deduplicate_categorized_tags(merged_tags)

        # Convert to the format expected by update function
        categorized_tags = {
            'character': merged_tags['tags_character'].split(),
            'copyright': merged_tags['tags_copyright'].split(),
            'artist': merged_tags['tags_artist'].split(),
            'species': merged_tags['tags_species'].split(),
            'meta': merged_tags['tags_meta'].split(),
            'general': merged_tags['tags_general'].split()
        }

        # Extract rating
        from utils.tag_extraction import extract_rating_from_source
        rating, rating_source = extract_rating_from_source(all_results['pixiv'], 'pixiv')

        # Update database
        with get_db_connection() as conn:
            cur = conn.cursor()

            # Update image record with new tags
            cur.execute("""
                UPDATE images
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?
                WHERE id = ?
            """, (
                ' '.join(categorized_tags['character']),
                ' '.join(categorized_tags['copyright']),
                ' '.join(categorized_tags['artist']),
                ' '.join(categorized_tags['species']),
                ' '.join(categorized_tags['meta']),
                ' '.join(categorized_tags['general']),
                image_id
            ))

            # Add local_tagger as a source
            cur.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", ('local_tagger',))
            cur.execute("SELECT id FROM sources WHERE name = ?", ('local_tagger',))
            local_tagger_source_id = cur.fetchone()['id']

            cur.execute("""
                INSERT OR IGNORE INTO image_sources (image_id, source_id)
                VALUES (?, ?)
            """, (image_id, local_tagger_source_id))

            # Update or insert raw metadata
            import json
            raw_metadata['sources'] = all_results
            raw_metadata['local_tagger_lookup'] = True

            cur.execute("""
                INSERT OR REPLACE INTO raw_metadata (image_id, data)
                VALUES (?, ?)
            """, (image_id, json.dumps(raw_metadata)))

            # Re-link tags (this is complex, so we'll use a simplified approach)
            # Delete existing tag links from 'original' source
            cur.execute("DELETE FROM image_tags WHERE image_id = ? AND source = 'original'", (image_id,))

            # Add all tags back
            for category, tags in categorized_tags.items():
                for tag in tags:
                    if not tag:  # Skip empty strings
                        continue

                    # Insert or get tag
                    cur.execute("""
                        INSERT OR IGNORE INTO tags (name, category)
                        VALUES (?, ?)
                    """, (tag, category))

                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag,))
                    tag_id = cur.fetchone()['id']

                    # Link to image
                    cur.execute("""
                        INSERT OR IGNORE INTO image_tags (image_id, tag_id, source)
                        VALUES (?, ?, 'original')
                    """, (image_id, tag_id))

            conn.commit()

        print(f"  ✅ Successfully reprocessed")
        return True

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Reprocess Pixiv images with local tagger')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--limit', type=int, help='Limit number of images to process')
    args = parser.parse_args()

    print("=" * 80)
    print("Pixiv Image Reprocessing Script")
    print("=" * 80)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    # Check if local tagger is available
    if not config.ENABLE_LOCAL_TAGGER:
        print("❌ ERROR: Local tagger is disabled in config")
        sys.exit(1)

    # Load local tagger
    print("Loading local tagger...")
    processing.load_local_tagger()

    # Check if it loaded successfully by checking if the session exists
    if processing.local_tagger_session is None:
        print("❌ ERROR: Failed to load local tagger")
        sys.exit(1)
    print("✓ Local tagger loaded\n")

    # Get images to process
    print("Finding Pixiv images without local tagger complement...")
    images = get_pixiv_images_needing_reprocessing()

    if not images:
        print("✅ No images need reprocessing!")
        return

    total = len(images)
    if args.limit:
        images = images[:args.limit]
        print(f"Found {total} images, processing first {len(images)} (limited)")
    else:
        print(f"Found {total} images to process")

    # Process each image
    success_count = 0
    fail_count = 0

    for i, image_row in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}]", end=' ')
        if reprocess_pixiv_image(image_row, dry_run=args.dry_run):
            success_count += 1
        else:
            fail_count += 1

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total processed: {len(images)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")

    if args.dry_run:
        print("\nℹ️  This was a dry run. Re-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Migration script to backfill ratings for existing images from their raw metadata.

This script extracts ratings from danbooru/e621 source data stored in raw_metadata
and applies them as rating tags to the images.
"""

import json
import sys
import os

# Add parent directory to path to import from project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


def backfill_ratings():
    """
    Backfill ratings for all images that have rating data in their raw_metadata.
    """
    rating_map = {
        'g': 'rating:general',
        's': 'rating:sensitive',
        'q': 'rating:questionable',
        'e': 'rating:explicit'
    }

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get all images with their raw metadata
        cur.execute("""
            SELECT i.id, i.active_source, rm.data
            FROM images i
            JOIN raw_metadata rm ON rm.image_id = i.id
        """)

        rows = cur.fetchall()
        total = len(rows)
        processed = 0
        ratings_applied = 0

        print(f"Found {total} images to check...")

        for row in rows:
            image_id = row['id']
            active_source = row['active_source']

            try:
                metadata = json.loads(row['data'])
            except json.JSONDecodeError:
                print(f"Warning: Could not parse metadata for image {image_id}")
                processed += 1
                continue

            # Look for rating in the sources
            sources_data = metadata.get('sources', {})

            rating = None
            rating_source = None

            # Check if the active source has rating data
            if active_source in sources_data:
                source_data = sources_data[active_source]
                if 'rating' in source_data:
                    rating_char = source_data.get('rating', '').lower()
                    rating = rating_map.get(rating_char)

                    # Determine source trust level
                    if active_source in ['danbooru', 'e621']:
                        rating_source = 'original'
                    elif active_source in ['local_tagger', 'camie_tagger']:
                        rating_source = 'ai_inference'
                    else:
                        rating_source = 'original'

            # If we found a rating, apply it
            if rating and rating_source:
                # Check if the image already has a rating tag
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM image_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE it.image_id = ?
                      AND t.name IN ('rating:general', 'rating:sensitive', 'rating:questionable', 'rating:explicit')
                """, (image_id,))

                has_rating = cur.fetchone()['count'] > 0

                if not has_rating:
                    # Insert or update the rating tag
                    cur.execute("""
                        INSERT INTO tags (name, category) VALUES (?, 'rating')
                        ON CONFLICT(name) DO UPDATE SET category = 'rating'
                    """, (rating,))

                    cur.execute("SELECT id FROM tags WHERE name = ?", (rating,))
                    tag_id = cur.fetchone()['id']

                    # Insert the image_tag with the appropriate source
                    cur.execute("""
                        INSERT OR IGNORE INTO image_tags (image_id, tag_id, source)
                        VALUES (?, ?, ?)
                    """, (image_id, tag_id, rating_source))

                    ratings_applied += 1

                    if ratings_applied % 100 == 0:
                        print(f"Progress: {processed}/{total} checked, {ratings_applied} ratings applied")
                        conn.commit()

            processed += 1

        # Final commit
        conn.commit()

        print(f"\nMigration complete!")
        print(f"Total images checked: {total}")
        print(f"Ratings applied: {ratings_applied}")
        print(f"Images already rated or no rating data: {total - ratings_applied}")


if __name__ == '__main__':
    print("Starting ratings backfill migration...")
    print("This will extract ratings from danbooru/e621 metadata and apply them as tags.")
    print()

    try:
        backfill_ratings()
    except Exception as e:
        print(f"\nError during migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

#!/usr/bin/env python3
"""
Backfill rating-source tags for existing rated images.
"""

import sqlite3
from database import get_db_connection

def backfill_rating_sources():
    """Add rating-source tags to all images that have ratings."""
    
    rating_tags = [
        'rating:general',
        'rating:sensitive',
        'rating:questionable',
        'rating:explicit'
    ]
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get all images with ratings and their sources
        placeholders = ','.join('?' * len(rating_tags))
        cur.execute(f"""
            SELECT it.image_id, it.source
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name IN ({placeholders})
        """, rating_tags)
        
        rated_images = cur.fetchall()
        print(f"Found {len(rated_images)} rated images")
        
        # Add rating-source tags
        added = 0
        for row in rated_images:
            image_id = row['image_id']
            source = row['source']
            
            # Create source tag name
            source_tag_name = f'rating-source:{source.replace("_", "-")}'
            
            # Ensure tag exists
            cur.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (source_tag_name, 'meta')
            )
            
            # Get tag ID
            cur.execute("SELECT id FROM tags WHERE name = ?", (source_tag_name,))
            tag_id = cur.fetchone()['id']
            
            # Add to image_tags (ignore if already exists)
            cur.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)",
                (image_id, tag_id, source)
            )
            
            if cur.rowcount > 0:
                added += 1
        
        conn.commit()
        
        print(f"Added {added} rating-source tags")
        
        # Show summary
        cur.execute("""
            SELECT t.name, COUNT(*) as count
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name LIKE 'rating-source:%'
            GROUP BY t.name
            ORDER BY t.name
        """)
        
        print("\nRating source distribution:")
        for row in cur.fetchall():
            print(f"  {row['name']}: {row['count']}")

if __name__ == "__main__":
    backfill_rating_sources()

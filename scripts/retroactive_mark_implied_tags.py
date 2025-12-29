#!/usr/bin/env python3
"""
Script to retroactively identify and mark tags that were added by implication rules.

Logic:
1. For each image, get the original tags from raw_metadata
2. Get current tags from image_tags table
3. Get manually added tags from tag_deltas
4. Tags that are current but NOT in (original + manually added) are potentially from implications
5. For those tags, check if there's an active implication rule that would have added them
6. If so, update the source to 'implication'
"""

import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


def get_original_tags_from_metadata(metadata_json: str) -> set:
    """Extract all original tags from raw_metadata JSON.
    
    Handles different source formats:
    - Danbooru: tag_string, tag_string_general, tag_string_copyright, etc.
    - e621: tags dict with category keys ('general', 'copyright', etc.)
    """
    if not metadata_json:
        return set()
    
    try:
        metadata = json.loads(metadata_json)
        all_tags = set()
        
        sources = metadata.get('sources', {})
        for source_name, source_data in sources.items():
            
            # Handle Danbooru format: tag_string_* fields
            if source_name == 'danbooru':
                # All tags in one string
                tag_string = source_data.get('tag_string', '')
                if tag_string:
                    all_tags.update(tag_string.split())
                
                # Also check category-specific strings (these overlap with tag_string but are good to include)
                for key in ['tag_string_general', 'tag_string_character', 'tag_string_copyright', 
                           'tag_string_artist', 'tag_string_meta']:
                    cat_tags = source_data.get(key, '')
                    if cat_tags:
                        all_tags.update(cat_tags.split())
            
            # Handle e621 format: tags dict
            elif source_name == 'e621':
                tags = source_data.get('tags', {})
                if isinstance(tags, dict):
                    for category, tag_list in tags.items():
                        if isinstance(tag_list, list):
                            all_tags.update(tag_list)
                        elif isinstance(tag_list, str):
                            all_tags.update(tag_list.split())
            
            # Generic fallback for other sources
            else:
                # Try tag_string first (like danbooru)
                tag_string = source_data.get('tag_string', '')
                if tag_string and isinstance(tag_string, str):
                    all_tags.update(tag_string.split())
                
                # Then try tags dict (like e621)
                tags = source_data.get('tags', {})
                if isinstance(tags, dict):
                    for category, tag_list in tags.items():
                        if isinstance(tag_list, list):
                            all_tags.update(tag_list)
                        elif isinstance(tag_list, str):
                            all_tags.update(tag_list.split())
                elif isinstance(tags, list):
                    all_tags.update(tags)
                elif isinstance(tags, str):
                    all_tags.update(tags.split())
        
        return all_tags
    except (json.JSONDecodeError, AttributeError, TypeError):
        return set()


def get_current_tags(conn, image_id: int) -> set:
    """Get all current tags for an image from image_tags."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.name 
        FROM image_tags it
        JOIN tags t ON it.tag_id = t.id
        WHERE it.image_id = ?
    """, (image_id,))
    return {row['name'] for row in cursor.fetchall()}


def get_manually_added_tags(conn, image_md5: str) -> set:
    """Get tags that were manually added via deltas."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tag_name 
        FROM tag_deltas
        WHERE image_md5 = ? AND operation = 'add'
    """, (image_md5,))
    return {row['tag_name'] for row in cursor.fetchall()}


def get_active_implications(conn) -> dict:
    """Get all active implications as a dict: source_tag -> set(implied_tags)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t_source.name as source_tag, t_implied.name as implied_tag
        FROM tag_implications ti
        JOIN tags t_source ON ti.source_tag_id = t_source.id
        JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
        WHERE ti.status = 'active'
    """)
    
    implications = {}
    for row in cursor.fetchall():
        source = row['source_tag']
        implied = row['implied_tag']
        if source not in implications:
            implications[source] = set()
        implications[source].add(implied)
    
    return implications


def compute_implied_tags(current_tags: set, implications: dict) -> set:
    """Compute which tags would be implied given current tags and implications."""
    implied = set()
    
    for tag in current_tags:
        if tag in implications:
            implied.update(implications[tag])
    
    return implied


def mark_tag_as_implied(conn, image_id: int, tag_name: str) -> bool:
    """Update a tag's source to 'implication' for a specific image."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE image_tags
        SET source = 'implication'
        WHERE image_id = ?
          AND tag_id = (SELECT id FROM tags WHERE name = ?)
          AND source != 'user'  -- Don't override user-added tags
    """, (image_id, tag_name))
    return cursor.rowcount > 0


def main():
    print("=" * 60)
    print("Retroactive Implied Tags Identification")
    print("=" * 60)
    
    with get_db_connection() as conn:
        # Get all active implications
        implications = get_active_implications(conn)
        print(f"\nLoaded {len(implications)} source tags with active implications")
        
        # Get all image_tags that could potentially be implied
        # Only check images that have tags matching implication source tags
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT i.id, i.md5, rm.data, i.filepath
            FROM images i
            JOIN raw_metadata rm ON i.id = rm.image_id
            JOIN image_tags it ON i.id = it.image_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name IN (
                SELECT t_source.name
                FROM tag_implications ti
                JOIN tags t_source ON ti.source_tag_id = t_source.id
                WHERE ti.status = 'active'
            )
        """)
        
        images = cursor.fetchall()
        print(f"Found {len(images)} images with tags that have active implications")
        
        total_marked = 0
        images_updated = 0
        
        for row in images:
            image_id = row['id']
            image_md5 = row['md5']
            metadata_json = row['data']
            filepath = row['filepath']
            
            # Get original tags from raw metadata
            original_tags = get_original_tags_from_metadata(metadata_json)
            
            # Get current tags
            current_tags = get_current_tags(conn, image_id)
            
            # Get manually added tags
            manually_added = get_manually_added_tags(conn, image_md5)
            
            # Tags that were added after import (not original, not manually added)
            added_tags = current_tags - original_tags - manually_added
            
            if not added_tags:
                continue
            
            # Which of these added tags would be implied by the implication rules?
            would_be_implied = compute_implied_tags(current_tags, implications)
            
            # Tags that were added and match implication rules are likely from implications
            likely_implied = added_tags & would_be_implied
            
            if likely_implied:
                image_marked = 0
                for tag in likely_implied:
                    if mark_tag_as_implied(conn, image_id, tag):
                        image_marked += 1
                        total_marked += 1
                
                if image_marked > 0:
                    images_updated += 1
                    if images_updated <= 10:  # Show first 10 examples
                        print(f"\n  Image: {filepath}")
                        print(f"    Marked as implied: {', '.join(sorted(likely_implied))}")
        
        conn.commit()
        
        print(f"\n" + "=" * 60)
        print(f"Summary:")
        print(f"  Images updated: {images_updated}")
        print(f"  Tags marked as implied: {total_marked}")
        print("=" * 60)


if __name__ == '__main__':
    main()

"""
Tag Repository Module

This module handles all tag-related database operations including:
- Tag counting and retrieval
- Tag categorization
- Tag implications
- Tag updates for images

Extracted from models.py to improve code organization.
"""

import json
import threading
from tqdm import tqdm
from database import get_db_connection


# ============================================================================
# TAG COUNTING AND RETRIEVAL
# ============================================================================

def get_tag_counts():
    """Get tag counts from the in-memory cache."""
    # Import inside function to avoid circular import
    from core import cache_manager
    with cache_manager.data_lock:
        return cache_manager.tag_counts


def reload_tag_counts():
    """Reload just the tag counts without reloading all image data."""
    # Import inside function to avoid circular import
    from core import cache_manager
    with cache_manager.data_lock:
        with get_db_connection() as conn:
            tag_counts_query = "SELECT name, COUNT(DISTINCT image_id) FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
            cache_manager.tag_counts = {row['name']: row['COUNT(DISTINCT image_id)'] for row in conn.execute(tag_counts_query).fetchall()}


def get_all_tags_sorted():
    """Get all tags with their counts, sorted alphabetically by name."""
    with get_db_connection() as conn:
        query = """
        SELECT t.name, t.category, COUNT(it.image_id) as count
        FROM tags t
        LEFT JOIN image_tags it ON t.id = it.tag_id
        GROUP BY t.id
        ORDER BY t.name ASC
        """
        return [dict(row) for row in conn.execute(query).fetchall()]


# ============================================================================
# TAG NORMALIZATION
# ============================================================================

def normalize_tag_name(tag_name):
    """
    Normalize tag names, specifically converting rating tags from underscore
    to colon format.

    Examples:
        rating_explicit -> rating:explicit
        rating_general -> rating:general

    Args:
        tag_name: The tag name to normalize

    Returns:
        Normalized tag name
    """
    # Define rating tag mappings
    rating_mappings = {
        'rating_explicit': 'rating:explicit',
        'rating_general': 'rating:general',
        'rating_questionable': 'rating:questionable',
        'rating_sensitive': 'rating:sensitive'
    }

    return rating_mappings.get(tag_name, tag_name)


def get_tag_category(tag_name):
    """
    Determine the correct category for a tag based on its name.

    Args:
        tag_name: The tag name

    Returns:
        The category string ('meta', 'general', etc.) or None
    """
    # Rating tags always go to meta
    if tag_name.startswith('rating:'):
        return 'meta'

    return None  # Let caller decide default


# ============================================================================
# TAG CATEGORIZATION
# ============================================================================

def recategorize_misplaced_tags():
    """
    Check all general tags and move them to correct categories if they exist
    as categorized tags elsewhere in the database.
    Also normalizes rating tags from underscore to colon format and moves them to meta.
    """
    print("Recategorizing misplaced tags...")

    # Build lookup from all known categorized tags
    known_categorized = {
        'artist': set(),
        'copyright': set(),
        'character': set(),
        'species': set(),
        'meta': set()
    }

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Build lookup from existing categorized tags
        for category in known_categorized.keys():
            cur.execute("SELECT DISTINCT name FROM tags WHERE category = ?", (category,))
            known_categorized[category].update(row['name'] for row in cur.fetchall())

        # Handle rating tag normalization first
        rating_mappings = {
            'rating_explicit': 'rating:explicit',
            'rating_general': 'rating:general',
            'rating_questionable': 'rating:questionable',
            'rating_sensitive': 'rating:sensitive'
        }

        rating_changes = 0
        for old_name, new_name in rating_mappings.items():
            # Check if the old tag exists in ANY category
            cur.execute("SELECT id, category FROM tags WHERE name = ?", (old_name,))
            old_tag = cur.fetchone()

            if not old_tag:
                continue

            old_tag_id = old_tag['id']

            # Check if the new tag already exists
            cur.execute("SELECT id FROM tags WHERE name = ?", (new_name,))
            new_tag = cur.fetchone()

            if new_tag:
                new_tag_id = new_tag['id']
                # Migrate all image associations from old to new tag
                cur.execute("""
                    SELECT image_id, source
                    FROM image_tags
                    WHERE tag_id = ?
                """, (old_tag_id,))
                old_associations = cur.fetchall()

                for assoc in old_associations:
                    image_id = assoc['image_id']
                    source = assoc['source']

                    # Check if image already has the new tag
                    cur.execute("""
                        SELECT 1 FROM image_tags
                        WHERE image_id = ? AND tag_id = ?
                    """, (image_id, new_tag_id))

                    if not cur.fetchone():
                        # Update the tag_id to point to the new tag
                        cur.execute("""
                            UPDATE image_tags
                            SET tag_id = ?
                            WHERE image_id = ? AND tag_id = ?
                        """, (new_tag_id, image_id, old_tag_id))
                    else:
                        # Image already has the new tag, just remove the old association
                        cur.execute("""
                            DELETE FROM image_tags
                            WHERE image_id = ? AND tag_id = ?
                        """, (image_id, old_tag_id))

                # Delete the old tag
                cur.execute("DELETE FROM tags WHERE id = ?", (old_tag_id,))
                rating_changes += 1
            else:
                # New tag doesn't exist, just rename and recategorize
                cur.execute("""
                    UPDATE tags
                    SET name = ?, category = 'meta'
                    WHERE id = ?
                """, (new_name, old_tag_id))
                rating_changes += 1

        if rating_changes > 0:
            print(f"Normalized {rating_changes} rating tags")

        # Find all general tags that should be recategorized
        cur.execute("SELECT DISTINCT name FROM tags WHERE category = 'general'")
        general_tags = [row['name'] for row in cur.fetchall()]

        changes = 0
        for tag_name in tqdm(general_tags, desc="Checking tags"):
            for category, tag_set in known_categorized.items():
                if tag_name in tag_set:
                    # Found a match - update this tag's category
                    cur.execute("UPDATE tags SET category = ? WHERE name = ? AND category = 'general'",
                               (category, tag_name))
                    changes += 1
                    break

        conn.commit()

    total_changes = changes + rating_changes
    print(f"Recategorized {total_changes} tags ({changes} regular, {rating_changes} ratings)")
    return total_changes


def rebuild_categorized_tags_from_relations():
    """
    Back-fills the categorized tag columns in the 'images' table based on
    the existing data in the 'image_tags' and 'tags' tables.
    This is a data migration step.
    """
    print("Rebuilding categorized tag columns...")
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all images
        cursor.execute("SELECT id FROM images")
        images = cursor.fetchall()

        updated_count = 0
        for image_row in tqdm(images, desc="Updating Images"):
            image_id = image_row['id']

            # Fetch all tags for this image, grouped by category
            query = """
            SELECT category, COALESCE(GROUP_CONCAT(name, ' '), '') as tags
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE it.image_id = ?
            GROUP BY t.category
            """
            cursor.execute(query, (image_id,))

            categorized_tags = {row['category']: row['tags'] for row in cursor.fetchall()}

            # Update the images table
            update_query = """
            UPDATE images SET
                tags_character = ?,
                tags_copyright = ?,
                tags_artist = ?,
                tags_species = ?,
                tags_meta = ?,
                tags_general = ?
            WHERE id = ?
            """
            cursor.execute(update_query, (
                categorized_tags.get('character'),
                categorized_tags.get('copyright'),
                categorized_tags.get('artist'),
                categorized_tags.get('species'),
                categorized_tags.get('meta'),
                categorized_tags.get('general'),
                image_id
            ))
            updated_count += 1

        conn.commit()

    print(f"Successfully updated categorized tags for {updated_count} images.")
    return updated_count


# ============================================================================
# TAG IMPLICATIONS
# ============================================================================

def add_implication(source_tag_name, implied_tag_name):
    """Create an implication from a source tag to an implied tag."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get tag IDs
        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag_name,))
        source_id = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag_name,))
        implied_id = cursor.fetchone()

        if source_id and implied_id:
            cursor.execute("INSERT OR IGNORE INTO tag_implications (source_tag_id, implied_tag_id) VALUES (?, ?)",
                           (source_id['id'], implied_id['id']))
            conn.commit()
            return True
        return False


def get_implications_for_tag(tag_name):
    """Get all tags implied by a given source tag."""
    with get_db_connection() as conn:
        query = """
        SELECT t_implied.name
        FROM tags t_source
        JOIN tag_implications ti ON t_source.id = ti.source_tag_id
        JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
        WHERE t_source.name = ?
        """
        return [row['name'] for row in conn.execute(query, (tag_name,)).fetchall()]


def apply_implications_for_image(image_id):
    """Apply all tag implications for a given image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get all current tags for the image
        cursor.execute("SELECT t.name FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = ?", (image_id,))
        current_tags = {row['name'] for row in cursor.fetchall()}

        tags_to_add = set()

        # Use a loop to handle chained implications (A->B, B->C)
        newly_added_tags_this_iteration = set(current_tags)
        while newly_added_tags_this_iteration:
            tags_to_check = newly_added_tags_this_iteration
            newly_added_tags_this_iteration = set()

            for tag_name in tags_to_check:
                implied_tags = get_implications_for_tag(tag_name)
                for implied_tag in implied_tags:
                    if implied_tag not in current_tags and implied_tag not in tags_to_add:
                        tags_to_add.add(implied_tag)
                        newly_added_tags_this_iteration.add(implied_tag)

        # Add the new tags to the database
        for tag_name in tags_to_add:
            cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, 'general'))
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cursor.fetchone()['id']
            cursor.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

        conn.commit()
        return len(tags_to_add) > 0


# ============================================================================
# TAG UPDATE FUNCTIONS
# ============================================================================

def update_image_tags(filepath, new_tags_str):
    """Update the tags for a specific image (legacy uncategorized format)."""
    from repositories.delta_tracker import compute_tag_deltas, record_tag_delta

    new_tags = set(tag.strip() for tag in new_tags_str.lower().split())

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT id, md5 FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            if not result:
                return False
            image_id = result['id']
            image_md5 = result['md5']

            # Compute deltas before making changes (treats all as general tags)
            categorized_tags = {'tags_general': new_tags_str}
            deltas = compute_tag_deltas(filepath, categorized_tags)

            # Record each delta
            for tag_name, tag_category, operation in deltas:
                record_tag_delta(image_md5, tag_name, tag_category, operation)

            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))

            for tag_name in new_tags:
                if not tag_name: continue

                # Normalize tag name (e.g., rating_explicit -> rating:explicit)
                normalized_tag_name = normalize_tag_name(tag_name)

                # Determine correct category
                category = get_tag_category(normalized_tag_name) or 'general'

                cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (normalized_tag_name, category))

                cursor.execute("SELECT id FROM tags WHERE name = ?", (normalized_tag_name,))
                tag_id_result = cursor.fetchone()
                if not tag_id_result:
                    print(f"Failed to get or create tag_id for: {normalized_tag_name}")
                    continue
                tag_id = tag_id_result['id']

                cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

            conn.commit()
            return True
    except Exception as e:
        print(f"Database error updating tags for {filepath}: {e}")
        conn.rollback()
        return False


def update_image_tags_categorized(filepath, categorized_tags):
    """Update image tags by category in the database."""
    # Import delta tracking from the repository
    from repositories.delta_tracker import compute_tag_deltas, record_tag_delta

    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    elif filepath.startswith('static/images/'):
        filepath = filepath[14:]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get image_id and MD5
            cursor.execute("SELECT id, md5 FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            if not result:
                print(f"Image not found: {filepath}")
                return False

            image_id = result['id']
            image_md5 = result['md5']

            # Compute deltas before making changes
            deltas = compute_tag_deltas(filepath, categorized_tags)
            print(f"Computed {len(deltas)} tag deltas for {filepath}")

            # Record each delta in the tag_deltas table
            for tag_name, tag_category, operation in deltas:
                record_tag_delta(image_md5, tag_name, tag_category, operation)

            # Update the categorized tag columns in images table
            cursor.execute("""
                UPDATE images
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?
                WHERE id = ?
            """, (
                categorized_tags.get('tags_character', ''),
                categorized_tags.get('tags_copyright', ''),
                categorized_tags.get('tags_artist', ''),
                categorized_tags.get('tags_species', ''),
                categorized_tags.get('tags_meta', ''),
                categorized_tags.get('tags_general', ''),
                image_id
            ))

            # Delete old image_tags entries
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))

            # Insert new tags for each category
            for category_key, tags_str in categorized_tags.items():
                if not tags_str or not tags_str.strip():
                    continue

                # Remove 'tags_' prefix from category name
                category_name = category_key.replace('tags_', '')

                tags = [t.strip() for t in tags_str.split() if t.strip()]
                for tag_name in tags:
                    # Normalize tag name (e.g., rating_explicit -> rating:explicit)
                    normalized_tag_name = normalize_tag_name(tag_name)

                    # Determine correct category (rating tags override category_name)
                    final_category = get_tag_category(normalized_tag_name) or category_name

                    # Get or create tag with proper category
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (normalized_tag_name,))
                    tag_row = cursor.fetchone()

                    if tag_row:
                        tag_id = tag_row['id']
                        # Update category if it's wrong (e.g., rating tag in general)
                        cursor.execute("UPDATE tags SET category = ? WHERE id = ? AND category != ?",
                                       (final_category, tag_id, final_category))
                    else:
                        # Create new tag with proper category
                        cursor.execute("INSERT INTO tags (name, category) VALUES (?, ?)",
                                       (normalized_tag_name, final_category))
                        tag_id = cursor.lastrowid

                    # Insert image-tag relationship
                    cursor.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                                   (image_id, tag_id))

            conn.commit()
            return True

    except Exception as e:
        print(f"Error updating tags for {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return False

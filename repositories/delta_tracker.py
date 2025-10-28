"""
Delta Tracker - Tag modification tracking across database rebuilds.

Extracted from models.py as part of refactoring effort to split monolithic
data access layer into focused, maintainable modules.

This module tracks manual tag modifications (additions/removals) that users make
and preserves them across database rebuilds. The delta tracking system ensures
that manual changes aren't lost when refreshing metadata from external sources.

Key Features:
- Records tag additions and removals per image (by MD5)
- Automatically cancels out opposite operations (add+remove = no change)
- Applies deltas after database rebuilds to restore manual changes
- Provides delta history for individual images
"""

from database import get_db_connection


def record_tag_delta(image_md5, tag_name, tag_category, operation):
    """
    Record a tag change (add/remove) in the delta tracking table.
    This preserves manual modifications across database rebuilds.

    Args:
        image_md5 (str): MD5 hash of the image
        tag_name (str): Name of the tag
        tag_category (str): Category of the tag (character, copyright, artist, species, meta, general)
        operation (str): 'add' or 'remove'

    Returns:
        bool: True if successful, False otherwise

    Note:
        Automatically detects and cancels out opposite operations.
        For example, if a tag was added, then removed, both deltas are deleted.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Check if there's an opposite operation that would cancel this out
            opposite_op = 'remove' if operation == 'add' else 'add'
            cursor.execute("""
                SELECT COUNT(*) as count FROM tag_deltas
                WHERE image_md5 = ? AND tag_name = ? AND operation = ?
            """, (image_md5, tag_name, opposite_op))

            has_opposite = cursor.fetchone()['count'] > 0

            if has_opposite:
                # Cancel out: remove the opposite operation and don't insert this one
                cursor.execute("""
                    DELETE FROM tag_deltas
                    WHERE image_md5 = ? AND tag_name = ? AND operation = ?
                """, (image_md5, tag_name, opposite_op))
                print(f"Cancelled out: {operation} tag '{tag_name}' with existing {opposite_op}")
            else:
                # No opposite to cancel, insert or update the delta
                cursor.execute("""
                    INSERT OR REPLACE INTO tag_deltas
                    (image_md5, tag_name, tag_category, operation, timestamp)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (image_md5, tag_name, tag_category, operation))
                print(f"Recorded delta: {operation} tag '{tag_name}' for MD5 {image_md5}")

            conn.commit()
            return True

    except Exception as e:
        print(f"Error recording tag delta: {e}")
        import traceback
        traceback.print_exc()
        return False


def compute_tag_deltas(filepath, new_categorized_tags):
    """
    Compare new tags against CURRENT tags (before this edit) to find what changed.
    This computes the incremental delta for THIS specific edit.

    Args:
        filepath (str): Image filepath
        new_categorized_tags (dict): Dict of categorized tags after user edit
            Format: {'tags_character': 'tag1 tag2', 'tags_general': 'tag3', ...}

    Returns:
        list: List of tuples: (tag_name, tag_category, operation)
            operation is either 'add' or 'remove'

    Example:
        >>> compute_tag_deltas('image.png', {'tags_general': 'new_tag'})
        [('new_tag', 'general', 'add')]
    """
    deltas = []

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get image MD5 and CURRENT tags (before this edit)
            cursor.execute("""
                SELECT i.md5,
                       i.tags_character, i.tags_copyright, i.tags_artist,
                       i.tags_species, i.tags_meta, i.tags_general
                FROM images i
                WHERE i.filepath = ?
            """, (filepath,))

            result = cursor.fetchone()
            if not result:
                print(f"Image not found: {filepath}")
                return deltas

            md5 = result['md5']

            # Get OLD tags (current state BEFORE this edit)
            old_tags = {}
            for category in ['character', 'copyright', 'artist', 'species', 'meta', 'general']:
                category_key = f'tags_{category}'
                old_tags_str = result[category_key] or ''
                old_tags[category] = set(tag.strip() for tag in old_tags_str.split() if tag.strip())

            # Get NEW tags (from this edit)
            new_tags = {}
            for category_key, tags_str in new_categorized_tags.items():
                category_name = category_key.replace('tags_', '')
                if not tags_str or not tags_str.strip():
                    new_tags[category_name] = set()
                else:
                    new_tags[category_name] = set(tag.strip() for tag in tags_str.split() if tag.strip())

            # Find what changed in THIS edit only
            all_categories = set(list(old_tags.keys()) + list(new_tags.keys()))

            for category in all_categories:
                old_set = old_tags.get(category, set())
                new_set = new_tags.get(category, set())

                # Tags added in this edit
                added = new_set - old_set
                for tag_name in added:
                    deltas.append((tag_name, category, 'add'))

                # Tags removed in this edit
                removed = old_set - new_set
                for tag_name in removed:
                    deltas.append((tag_name, category, 'remove'))

            return deltas

    except Exception as e:
        print(f"Error computing tag deltas: {e}")
        import traceback
        traceback.print_exc()
        return deltas


def apply_tag_deltas():
    """
    Apply all recorded tag deltas after a database rebuild.
    This should be called at the end of repopulate_from_database().

    Returns:
        bool: True if successful, False otherwise

    Process:
        1. Fetch all deltas from tag_deltas table
        2. For each delta, find the image by MD5
        3. Get or create the tag
        4. Apply the operation (add or remove)
        5. Rebuild categorized tags

    Note:
        This function depends on rebuild_categorized_tags_from_relations
        from models.py to update the denormalized tag columns.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all deltas grouped by image
            cursor.execute("""
                SELECT image_md5, tag_name, tag_category, operation
                FROM tag_deltas
                ORDER BY image_md5, timestamp
            """)

            deltas = cursor.fetchall()
            delta_count = len(deltas)

            if delta_count == 0:
                print("No tag deltas to apply.")
                return True

            print(f"Applying {delta_count} tag deltas...")
            applied = 0

            for delta in deltas:
                md5 = delta['image_md5']
                tag_name = delta['tag_name']
                tag_category = delta['tag_category']
                operation = delta['operation']

                # Get image_id from MD5
                cursor.execute("SELECT id FROM images WHERE md5 = ?", (md5,))
                img_result = cursor.fetchone()

                if not img_result:
                    print(f"Warning: Image with MD5 {md5} not found, skipping delta for tag '{tag_name}'")
                    continue

                image_id = img_result['id']

                # Get or create the tag
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_result = cursor.fetchone()

                if tag_result:
                    tag_id = tag_result['id']
                    # Update category if needed
                    if tag_category:
                        cursor.execute("UPDATE tags SET category = ? WHERE id = ?", (tag_category, tag_id))
                else:
                    # Create new tag
                    cursor.execute(
                        "INSERT INTO tags (name, category) VALUES (?, ?)",
                        (tag_name, tag_category or 'general')
                    )
                    tag_id = cursor.lastrowid

                if operation == 'add':
                    # Add tag to image
                    cursor.execute(
                        "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                        (image_id, tag_id)
                    )
                    applied += 1

                elif operation == 'remove':
                    # Remove tag from image
                    cursor.execute(
                        "DELETE FROM image_tags WHERE image_id = ? AND tag_id = ?",
                        (image_id, tag_id)
                    )
                    applied += 1

            conn.commit()
            print(f"Successfully applied {applied} tag deltas.")

            # Rebuild categorized tags after applying deltas
            # Import here to avoid circular dependency
            from models import rebuild_categorized_tags_from_relations
            rebuild_categorized_tags_from_relations()

            return True

    except Exception as e:
        print(f"Error applying tag deltas: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_image_deltas(filepath):
    """
    Get all tag deltas for a specific image.
    Returns a dict with 'added' and 'removed' tag lists.

    Args:
        filepath (str): Image filepath

    Returns:
        dict: Dictionary with 'added' and 'removed' keys
            - added: list of dicts with 'name' and 'category'
            - removed: list of dicts with 'name' and 'category'

    Example:
        >>> get_image_deltas('image.png')
        {'added': [{'name': 'new_tag', 'category': 'general'}], 'removed': []}

    Note:
        Processes deltas in order and computes net changes.
        If a tag is added then removed, it won't appear in either list.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get MD5 for the image
            cursor.execute("SELECT md5 FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()

            if not result:
                return {'added': [], 'removed': []}

            md5 = result['md5']

            # Get deltas
            cursor.execute("""
                SELECT tag_name, tag_category, operation
                FROM tag_deltas
                WHERE image_md5 = ?
                ORDER BY timestamp
            """, (md5,))

            deltas = cursor.fetchall()

            # Track net changes: process all deltas in order
            # and calculate what the final state is
            tag_states = {}  # tag_name -> (operation, category)

            for delta in deltas:
                tag_name = delta['tag_name']
                tag_category = delta['tag_category']
                operation = delta['operation']

                if operation == 'add':
                    # Adding a tag
                    tag_states[tag_name] = ('add', tag_category)
                elif operation == 'remove':
                    # Removing a tag
                    if tag_name in tag_states and tag_states[tag_name][0] == 'add':
                        # If we previously added this tag, cancel it out
                        del tag_states[tag_name]
                    else:
                        # Otherwise mark it as removed
                        tag_states[tag_name] = ('remove', tag_category)

            # Convert net changes to lists
            added = []
            removed = []

            for tag_name, (operation, tag_category) in tag_states.items():
                tag_info = {
                    'name': tag_name,
                    'category': tag_category
                }
                if operation == 'add':
                    added.append(tag_info)
                else:
                    removed.append(tag_info)

            return {'added': added, 'removed': removed}

    except Exception as e:
        print(f"Error getting image deltas: {e}")
        return {'added': [], 'removed': []}

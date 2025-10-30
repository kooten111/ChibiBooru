"""
Data Access Layer Module

This module contains pure database query functions with no business logic.
Functions here perform simple CRUD operations and data retrieval.

Extracted from models.py to improve code organization and separation of concerns.
"""

import json
from database import get_db_connection
from functools import lru_cache

# ============================================================================
# STATISTICS QUERIES
# ============================================================================

def get_image_count():
    """Get total count of images in the database."""
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(id) FROM images").fetchone()[0]


def get_avg_tags_per_image():
    """Calculate average number of tags per image."""
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT AVG(tag_count) FROM (SELECT COUNT(tag_id) as tag_count FROM image_tags GROUP BY image_id)"
        ).fetchone()
        return round(result[0], 1) if result and result[0] is not None else 0


def get_source_breakdown():
    """Get count of images per source."""
    query = """
    SELECT s.name, COUNT(ims.image_id)
    FROM sources s
    JOIN image_sources ims ON s.id = ims.source_id
    GROUP BY s.name
    """
    with get_db_connection() as conn:
        return {row['name']: row['COUNT(ims.image_id)'] for row in conn.execute(query).fetchall()}


def get_category_counts():
    """Get count of tags per category."""
    query = "SELECT category, COUNT(id) FROM tags WHERE category IS NOT NULL GROUP BY category"
    with get_db_connection() as conn:
        return {row['category']: row['COUNT(id)'] for row in conn.execute(query).fetchall()}


def get_saucenao_lookup_count():
    """Get count of images that have been looked up on SauceNAO."""
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(id) FROM images WHERE saucenao_lookup = 1").fetchone()[0]


# ============================================================================
# IMAGE QUERIES
# ============================================================================

def md5_exists(md5):
    """Check if an MD5 hash already exists in the images table."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM images WHERE md5 = ?", (md5,))
        return cursor.fetchone() is not None


def get_all_images_with_tags():
    """Get all images with their concatenated tags."""
    with get_db_connection() as conn:
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        GROUP BY i.id
        """
        return [dict(row) for row in conn.execute(query).fetchall()]


def get_all_filepaths():
    """Returns a set of all filepaths in the database."""
    with get_db_connection() as conn:
        return {row['filepath'] for row in conn.execute("SELECT filepath FROM images").fetchall()}

@lru_cache(maxsize=10000)
def get_image_details(filepath):
    """Get detailed information about a specific image including all tags and metadata."""
    with get_db_connection() as conn:
        query = """
        SELECT
            i.*,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id) as all_tags,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'character') as tags_character,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'copyright') as tags_copyright,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'artist') as tags_artist,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'species') as tags_species,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'meta') as tags_meta,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'general') as tags_general,
            rm.data as raw_metadata
        FROM images i
        LEFT JOIN raw_metadata rm ON i.id = rm.image_id
        WHERE i.filepath = ?
        """
        details = conn.execute(query, (filepath,)).fetchone()
        if not details:
            return None

        details_dict = dict(details)
        if details_dict.get('raw_metadata'):
            details_dict['raw_metadata'] = json.loads(details_dict['raw_metadata'])

        # If no active_source set but we have metadata, determine it
        if not details_dict.get('active_source') and details_dict.get('raw_metadata'):
            metadata = details_dict['raw_metadata']
            sources = metadata.get('sources', {})
            if 'danbooru' in sources:
                details_dict['active_source'] = 'danbooru'
            elif 'e621' in sources:
                details_dict['active_source'] = 'e621'
            elif sources:
                details_dict['active_source'] = list(sources.keys())[0]

        return details_dict


def delete_image(filepath):
    """Delete an image and all its related data from the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM images WHERE filepath = ?", (filepath,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Database error deleting {filepath}: {e}")
        return False


# ============================================================================
# RELATIONSHIP QUERIES
# ============================================================================

def get_related_images(post_id, parent_id, post_id_to_md5_mapping):
    """
    Find parent and child images using optimized database queries.

    Uses indexed columns (parent_id, has_children) instead of scanning
    all raw_metadata JSON blobs, providing near-instant lookups.
    """
    related = []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Find parent using direct indexed lookup
        if parent_id:
            # First try: Use the parent_id column directly (fastest)
            # This works if parent_id was populated during repopulation
            parent = cursor.execute(
                "SELECT filepath FROM images WHERE post_id = ?",
                (parent_id,)
            ).fetchone()

            # Second try: Use the mapping (fallback for cross-source relationships)
            if not parent and parent_id in post_id_to_md5_mapping:
                parent_md5 = post_id_to_md5_mapping[parent_id]
                parent = cursor.execute(
                    "SELECT filepath FROM images WHERE md5 = ?",
                    (parent_md5,)
                ).fetchone()

            if parent:
                related.append({
                    "path": f"images/{parent['filepath']}",
                    "type": "parent"
                })

        # Find children using indexed parent_id column (MUCH faster than JSON scanning)
        if post_id:
            # Direct lookup using indexed parent_id column
            children = cursor.execute(
                "SELECT filepath FROM images WHERE parent_id = ?",
                (post_id,)
            ).fetchall()

            for child in children:
                related.append({
                    "path": f"images/{child['filepath']}",
                    "type": "child"
                })

            # Fallback: Check for cross-source relationships using MD5 mapping
            # This handles cases where parent_id might be from a different source
            current_md5 = post_id_to_md5_mapping.get(post_id)
            if current_md5:
                # Only scan metadata for images that have has_children flag or parent_id set
                # This dramatically reduces the search space
                cursor.execute("""
                    SELECT i.filepath, rm.data
                    FROM images i
                    JOIN raw_metadata rm ON i.id = rm.image_id
                    WHERE (i.parent_id IS NOT NULL OR i.has_children = 1)
                    AND rm.data IS NOT NULL
                    AND i.filepath NOT IN (
                        SELECT filepath FROM images WHERE parent_id = ?
                    )
                """, (post_id,))

                existing_children = {img['path'] for img in related}

                for row in cursor.fetchall():
                    try:
                        metadata = json.loads(row['data'])
                        # Check parent_id from ALL sources
                        for source, data in metadata.get('sources', {}).items():
                            if source == 'danbooru':
                                check_parent = data.get('parent_id')
                            elif source == 'e621':
                                check_parent = data.get('relationships', {}).get('parent_id')
                            else:
                                check_parent = data.get('parent_id')

                            # If this image's parent matches our MD5, it's our child
                            if check_parent and check_parent in post_id_to_md5_mapping:
                                if post_id_to_md5_mapping[check_parent] == current_md5:
                                    child_path = f"images/{row['filepath']}"
                                    if child_path not in existing_children:
                                        related.append({
                                            "path": child_path,
                                            "type": "child"
                                        })
                                        existing_children.add(child_path)
                                    break  # Don't add same child twice
                    except:
                        continue

    return related


def search_images_by_relationship(relationship_type):
    """
    Search for images by relationship type.
    relationship_type: 'parent', 'child', or 'any'
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        matching_filepaths = set()

        # Get all images with raw metadata
        cursor.execute("SELECT i.id, i.filepath, rm.data FROM images i LEFT JOIN raw_metadata rm ON i.id = rm.image_id WHERE rm.data IS NOT NULL")

        for row in cursor.fetchall():
            try:
                metadata = json.loads(row['data'])
                image_id = row['id']
                filepath = row['filepath']

                has_parent = False
                has_child = False

                # Extract all post_ids and parent_ids for this image
                post_ids = set()
                parent_ids = set()

                for source, data in metadata.get('sources', {}).items():
                    if source == 'danbooru':
                        pid = data.get('id')
                        ppid = data.get('parent_id')
                    elif source == 'e621':
                        pid = data.get('id')
                        ppid = data.get('relationships', {}).get('parent_id')
                    else:
                        pid = data.get('id')
                        ppid = data.get('parent_id')

                    if pid:
                        post_ids.add(pid)
                    if ppid:
                        parent_ids.add(ppid)

                # Check if has parent
                if parent_ids:
                    has_parent = True

                # Check if has children (are we a parent to anyone?)
                if post_ids and relationship_type in ['child', 'any']:
                    # Quick check: see if any other image references us as parent
                    cursor2 = conn.cursor()
                    cursor2.execute("SELECT rm2.data FROM raw_metadata rm2 WHERE rm2.image_id != ?", (image_id,))
                    for other_row in cursor2.fetchall():
                        try:
                            other_metadata = json.loads(other_row['data'])
                            for other_source, other_data in other_metadata.get('sources', {}).items():
                                if other_source == 'danbooru':
                                    other_parent = other_data.get('parent_id')
                                elif other_source == 'e621':
                                    other_parent = other_data.get('relationships', {}).get('parent_id')
                                else:
                                    other_parent = other_data.get('parent_id')

                                if other_parent and other_parent in post_ids:
                                    has_child = True
                                    break
                            if has_child:
                                break
                        except:
                            continue

                # Add to results based on type
                if relationship_type == 'parent' and has_parent:
                    matching_filepaths.add(filepath)
                elif relationship_type == 'child' and has_child:
                    matching_filepaths.add(filepath)
                elif relationship_type == 'any' and (has_parent or has_child):
                    matching_filepaths.add(filepath)

            except:
                continue

        # Get full image data with tags
        if matching_filepaths:
            placeholders = ','.join('?' for _ in matching_filepaths)
            query = f"""
            SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            WHERE i.filepath IN ({placeholders})
            GROUP BY i.id
            """
            return [dict(row) for row in conn.execute(query, list(matching_filepaths)).fetchall()]

        return []


# ============================================================================
# SEARCH QUERIES
# ============================================================================

def search_images_by_tags(tags_list):
    """Search for images that have ALL specified tags (AND logic)."""
    with get_db_connection() as conn:
        base_query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        JOIN image_tags it ON i.id = it.image_id
        JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT it_inner.image_id
            FROM image_tags it_inner
            JOIN tags t_inner ON it_inner.tag_id = t_inner.id
            WHERE t_inner.name IN ({placeholders})
            GROUP BY it_inner.image_id
            HAVING COUNT(DISTINCT t_inner.name) = ?
        )
        GROUP BY i.id
        """
        placeholders = ','.join('?' for _ in tags_list)
        query = base_query.format(placeholders=placeholders)
        params = tags_list + [len(tags_list)]
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def search_images_by_source(source_name):
    """Search for images from a specific source."""
    with get_db_connection() as conn:
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT ims.image_id
            FROM image_sources ims
            JOIN sources s ON ims.source_id = s.id
            WHERE s.name = ?
        )
        GROUP BY i.id
        """
        return [dict(row) for row in conn.execute(query, (source_name,)).fetchall()]


def search_images_by_multiple_sources(source_names):
    """
    Search for images that have ALL specified sources (AND logic).
    Returns images only if they exist in every source in source_names list.
    """
    with get_db_connection() as conn:
        # Build a query that requires the image to have ALL sources
        # Using HAVING COUNT(DISTINCT s.name) = number_of_sources ensures AND logic
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT ims.image_id
            FROM image_sources ims
            JOIN sources s ON ims.source_id = s.id
            WHERE s.name IN ({placeholders})
            GROUP BY ims.image_id
            HAVING COUNT(DISTINCT s.name) = ?
        )
        GROUP BY i.id
        """
        placeholders = ','.join('?' for _ in source_names)
        query = query.format(placeholders=placeholders)
        params = source_names + [len(source_names)]
        return [dict(row) for row in conn.execute(query, params).fetchall()]


# ============================================================================
# IMAGE INSERTION
# ============================================================================

def add_image_with_metadata(image_info, source_names, categorized_tags, raw_metadata_dict):
    """
    Adds a new image and all its metadata to the database in a single transaction.
    Returns True on success, False on failure (including duplicate MD5 race condition).
    """
    import sqlite3

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 1. Insert the image record
            cursor.execute("""
                INSERT INTO images (filepath, md5, post_id, parent_id, has_children, saucenao_lookup)
                VALUES (:filepath, :md5, :post_id, :parent_id, :has_children, :saucenao_lookup)
            """, image_info)
            image_id = cursor.lastrowid

            # 2. Link sources
            for name in source_names:
                cursor.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (name,))
                cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
                source_id = cursor.fetchone()['id']
                cursor.execute("INSERT INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_id))

            # 3. Insert and link tags
            for category, tags_list in categorized_tags.items():
                for tag_name in tags_list:
                    if not tag_name: continue
                    cursor.execute("""
    INSERT INTO tags (name, category) VALUES (?, ?)
    ON CONFLICT(name) DO UPDATE SET category = excluded.category
""", (tag_name, category))
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cursor.fetchone()['id']
                    cursor.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

            # 4. Insert raw metadata
            cursor.execute(
                "INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)",
                (image_id, json.dumps(raw_metadata_dict))
            )
            # 5. Populate categorized tag columns in images table
            tag_columns = {
                'character': 'tags_character',
                'copyright': 'tags_copyright',
                'artist': 'tags_artist',
                'species': 'tags_species',
                'meta': 'tags_meta',
                'general': 'tags_general'
            }

            update_values = {}
            for category, tags_list in categorized_tags.items():
                col_name = tag_columns.get(category)
                if col_name:
                    update_values[col_name] = ' '.join(tags_list) if tags_list else None

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
                update_values.get('tags_character'),
                update_values.get('tags_copyright'),
                update_values.get('tags_artist'),
                update_values.get('tags_species'),
                update_values.get('tags_meta'),
                update_values.get('tags_general'),
                image_id
            ))

            conn.commit()
            return True
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: images.md5" in str(e):
            print(f"Race condition: MD5 {image_info['md5']} was inserted by another process. Treating as duplicate.")
            return False
        else:
            print(f"Database integrity error adding image {image_info['filepath']}: {e}")
            return False
    except Exception as e:
        print(f"Database error adding image {image_info['filepath']}: {e}")
        return False

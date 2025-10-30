"""
Cache Manager Module

This module manages the in-memory caches for ChibiBooru:
- tag_counts: Dictionary mapping tag names to their usage counts
- image_data: List of all images with their tags
- post_id_to_md5: Cross-source mapping of post IDs to MD5 hashes
- data_lock: Thread-safe access to cache data

Extracted from models.py to improve code organization.
"""

import json
import threading
from database import get_db_connection

# ============================================================================
# GLOBAL CACHE VARIABLES
# ============================================================================

# In-memory caches
tag_counts = {}
image_data = []
post_id_to_md5 = {}
data_lock = threading.Lock()


# ============================================================================
# CACHE LOADING FUNCTIONS
# ============================================================================

def load_data_from_db():
    """Load or reload data from the database into the in-memory caches."""
    global tag_counts, image_data, post_id_to_md5
    print("Loading data from database...")

    # Invalidate similarity caches when reloading data
    from events.cache_events import trigger_cache_invalidation
    trigger_cache_invalidation()

    with data_lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images';")
            if cursor.fetchone() is None:
                print("Warning: Database tables not found. Skipping data load.")
                tag_counts = {}
                image_data = []
                post_id_to_md5 = {}
                return False

            tag_counts_query = "SELECT name, COUNT(image_id) FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
            tag_counts.clear()
            tag_counts.update({row['name']: row['COUNT(image_id)'] for row in conn.execute(tag_counts_query).fetchall()})

            image_data_query = """
            SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            GROUP BY i.id
            """
            image_data.clear()
            image_data.extend([dict(row) for row in conn.execute(image_data_query).fetchall()])

            # Build post_id → MD5 mapping for ALL sources
            print("Building cross-source post_id index...")
            post_id_to_md5.clear()  # Clear existing mapping
            cursor.execute("""
                SELECT i.md5, rm.data
                FROM images i
                JOIN raw_metadata rm ON i.id = rm.image_id
                WHERE rm.data IS NOT NULL
            """)
            for row in cursor.fetchall():
                try:
                    metadata = json.loads(row['data'])
                    md5 = row['md5']
                    for source, data in metadata.get('sources', {}).items():
                        if source in ['danbooru', 'e621', 'gelbooru', 'yandere']:
                            post_id = data.get('id')
                            if post_id:
                                post_id_to_md5[post_id] = md5
                except:
                    continue

    print(f"Loaded {len(image_data)} images, {len(tag_counts)} unique tags, {len(post_id_to_md5)} cross-source post_ids.")
    return True


def reload_single_image(filepath):
    """Reload a single image's data in the in-memory cache without full reload."""
    global image_data
    with data_lock:
        with get_db_connection() as conn:
            query = """
            SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            WHERE i.filepath = ?
            GROUP BY i.id
            """
            result = conn.execute(query, (filepath,)).fetchone()

            if result:
                new_entry = dict(result)
                # Remove old entry if exists
                image_data[:] = [img for img in image_data if img['filepath'] != filepath]
                # Add new entry
                image_data.append(new_entry)


def remove_image_from_cache(filepath):
    """Remove a single image from the in-memory cache."""
    global image_data
    with data_lock:
        image_data[:] = [img for img in image_data if img['filepath'] != filepath]


# ============================================================================
# CACHE ACCESS FUNCTIONS
# ============================================================================

def get_image_data():
    """Get all image data from the in-memory cache."""
    with data_lock:
        return image_data


def get_tag_counts():
    """Get tag counts from the in-memory cache."""
    with data_lock:
        return tag_counts


def reload_tag_counts():
    """Reload just the tag counts without reloading all image data."""
    global tag_counts
    with data_lock:
        with get_db_connection() as conn:
            tag_counts_query = "SELECT name, COUNT(image_id) FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
            tag_counts.clear()
            tag_counts.update({row['name']: row['COUNT(image_id)'] for row in conn.execute(tag_counts_query).fetchall()})

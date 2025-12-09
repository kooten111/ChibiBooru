"""
Cache Manager Module

Manages the in-memory caches for ChibiBooru:
- tag_counts: Dictionary mapping tag names to their usage counts
- image_data: List of all images with their tags
- post_id_to_md5: Cross-source mapping of post IDs to MD5 hashes
- data_lock: Thread-safe access to cache data

Optimized with:
- Async loading support to prevent UI blocking
- Batched JSON parsing
- Progress tracking
"""

import json
import threading
import concurrent.futures
from database import get_db_connection

tag_counts = {}
image_data = []
post_id_to_md5 = {}
data_lock = threading.RLock()  # Changed to RLock to allow reentrant locking
_loading_in_progress = False
_load_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cache_loader")


def _load_data_from_db_impl():
    """Internal implementation of database loading with optimizations."""
    global tag_counts, image_data, post_id_to_md5, _loading_in_progress

    print("Loading data from database...")

    # Invalidate similarity caches when reloading data
    from events.cache_events import trigger_cache_invalidation
    trigger_cache_invalidation()

    # Create temporary storage to minimize lock time
    temp_tag_counts = {}
    temp_image_data = []
    temp_post_id_to_md5 = {}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images';")
        if cursor.fetchone() is None:
            print("Warning: Database tables not found. Skipping data load.")
            with data_lock:
                tag_counts.clear()
                image_data.clear()
                post_id_to_md5.clear()
                _loading_in_progress = False
            return False

        # Load tag counts
        tag_counts_query = "SELECT name, COUNT(DISTINCT image_id) as count FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
        for row in conn.execute(tag_counts_query).fetchall():
            temp_tag_counts[row['name']] = row['count']

        # Load image data
        image_data_query = """
        SELECT i.filepath, COALESCE(GROUP_CONCAT(t.name, ' '), '') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        GROUP BY i.id
        """
        temp_image_data = [dict(row) for row in conn.execute(image_data_query).fetchall()]

        # Build cross-source post_id index with batched JSON parsing
        print("Building cross-source post_id index...")
        cursor.execute("""
            SELECT i.md5, rm.data
            FROM images i
            JOIN raw_metadata rm ON i.id = rm.image_id
            WHERE rm.data IS NOT NULL
        """)

        # Batch process JSON parsing to show progress and reduce memory pressure
        BATCH_SIZE = 1000
        rows = cursor.fetchall()
        total_rows = len(rows)

        for i in range(0, total_rows, BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            for row in batch:
                try:
                    metadata = json.loads(row['data'])
                    md5 = row['md5']
                    for source, data in metadata.get('sources', {}).items():
                        if source in ['danbooru', 'e621', 'gelbooru', 'yandere']:
                            post_id = data.get('id')
                            if post_id:
                                temp_post_id_to_md5[post_id] = md5
                except:
                    continue

            if i + BATCH_SIZE < total_rows:
                print(f"  Processed {i + BATCH_SIZE}/{total_rows} metadata entries...")

    # Update global caches atomically with minimal lock time
    with data_lock:
        tag_counts.clear()
        tag_counts.update(temp_tag_counts)
        image_data.clear()
        image_data.extend(temp_image_data)
        post_id_to_md5.clear()
        post_id_to_md5.update(temp_post_id_to_md5)
        _loading_in_progress = False

    print(f"Loaded {len(image_data)} images, {len(tag_counts)} unique tags, {len(post_id_to_md5)} cross-source post_ids.")
    return True


def load_data_from_db():
    """Load or reload data from the database into the in-memory caches (synchronous)."""
    global _loading_in_progress

    with data_lock:
        if _loading_in_progress:
            print("Cache load already in progress, skipping...")
            return False
        _loading_in_progress = True

    try:
        return _load_data_from_db_impl()
    except Exception as e:
        print(f"Error loading cache: {e}")
        with data_lock:
            _loading_in_progress = False
        return False


def load_data_from_db_async():
    """Load data asynchronously in background thread to avoid blocking the main thread.

    Returns a Future object that can be waited on if needed.
    """
    global _loading_in_progress

    with data_lock:
        if _loading_in_progress:
            print("Cache load already in progress, skipping async request...")
            return None
        _loading_in_progress = True

    # Submit to executor
    future = _load_executor.submit(_load_data_from_db_impl)

    def on_error(fut):
        try:
            fut.result()
        except Exception as e:
            print(f"Async cache load failed: {e}")
            with data_lock:
                global _loading_in_progress
                _loading_in_progress = False

    future.add_done_callback(on_error)
    return future


def is_loading():
    """Check if cache is currently being loaded."""
    with data_lock:
        return _loading_in_progress


def reload_single_image(filepath):
    """Reload a single image's data in the in-memory cache without full reload."""
    global image_data
    with data_lock:
        with get_db_connection() as conn:
            query = """
            SELECT i.filepath, COALESCE(GROUP_CONCAT(t.name, ' '), '') as tags
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
            tag_counts_query = "SELECT name, COUNT(DISTINCT image_id) FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
            tag_counts.clear()
            tag_counts.update({row['name']: row['COUNT(DISTINCT image_id)'] for row in conn.execute(tag_counts_query).fetchall()})

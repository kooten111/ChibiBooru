"""
Cache Manager Module

Manages the in-memory caches for ChibiBooru:
- tag_counts: Dictionary mapping tag IDs to their usage counts
- image_data: List of all images with their tag IDs (stored as int32 arrays)
- post_id_to_md5: Cross-source mapping of post IDs to MD5 hashes
- data_lock: Thread-safe access to cache data

Memory optimizations:
- Tag IDs used as keys instead of tag names (~200-500 MB savings)
- Int32 arrays for tag storage (4 bytes per tag vs 50+ bytes)
- Async loading support to prevent UI blocking
- Batched JSON parsing with progress tracking
"""

import json
import sys
import threading
import concurrent.futures
import logging
from array import array
from typing import Optional
from tqdm import tqdm
from database import get_db_connection
import config

logger = logging.getLogger('chibibooru.CacheManager')

tag_counts = {}
image_data = []
post_id_to_md5 = {}
data_lock = threading.RLock()  # Use RLock to allow reentrant locking
_loading_in_progress = False
_load_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cache_loader")


def _load_data_from_db_impl(verbose=True):
    """Internal implementation of database loading with optimizations."""
    global tag_counts, image_data, post_id_to_md5, _loading_in_progress

    logger.debug("Loading data from database...")

    # Reload tag ID cache (ensure fresh mappings before loading IDs)
    from core.tag_id_cache import reload_tag_id_cache
    reload_tag_id_cache()

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
            logger.warning("Database tables not found. Skipping data load.")
            with data_lock:
                tag_counts.clear()
                image_data.clear()
                post_id_to_md5.clear()
                _loading_in_progress = False
            return False

        # Load tag counts using tag IDs as keys for memory efficiency
        tag_counts_query = "SELECT id, COUNT(DISTINCT image_id) as count FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY id"
        for row in conn.execute(tag_counts_query).fetchall():
            temp_tag_counts[row['id']] = row['count']

        # Load image data using tag IDs
        image_data_query = """
        SELECT i.filepath,
               COALESCE(GROUP_CONCAT(t.id, ','), '') as tag_ids
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        GROUP BY i.id
        """
        for row in conn.execute(image_data_query).fetchall():
            row_dict = dict(row)
            # Parse comma-separated IDs into compact int32 array
            if row_dict['tag_ids']:
                ids = [int(id_str) for id_str in row_dict['tag_ids'].split(',')]
                row_dict['tag_ids'] = array('i', ids)  # 4 bytes per ID
            else:
                row_dict['tag_ids'] = array('i')  # Empty array
            temp_image_data.append(row_dict)

        # Build cross-source post_id index with tqdm progress
        cursor.execute("""
            SELECT i.md5, rm.data
            FROM images i
            JOIN raw_metadata rm ON i.id = rm.image_id
            WHERE rm.data IS NOT NULL
        """)

        rows = cursor.fetchall()
        parse_errors = 0
        
        # Only show progress bar if verbose=True
        disable_tqdm = not verbose
        
        for row in tqdm(rows, desc="Building post_id index", unit="entries", leave=False, disable=disable_tqdm):
            try:
                metadata = json.loads(row['data'])
                md5 = sys.intern(row['md5'])  # Intern MD5 strings for memory efficiency
                for source, data in metadata.get('sources', {}).items():
                    if source in ['danbooru', 'e621', 'gelbooru', 'yandere']:
                        post_id = data.get('id')
                        if post_id:
                            temp_post_id_to_md5[post_id] = md5
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                parse_errors += 1
                if parse_errors <= 5:  # Log first 5 errors in detail
                    logger.error(f"Error parsing metadata for md5={row['md5']}: {e}")
                continue
        
        if parse_errors > 5:
            logger.warning(f"Suppressed {parse_errors - 5} additional metadata parse errors")

    # Update global caches atomically with minimal lock time
    with data_lock:
        tag_counts.clear()
        tag_counts.update(temp_tag_counts)
        image_data.clear()
        image_data.extend(temp_image_data)
        post_id_to_md5.clear()
        post_id_to_md5.update(temp_post_id_to_md5)
        _loading_in_progress = False

    logger.info(f"Loaded {len(image_data)} images, {len(tag_counts)} unique tags, {len(post_id_to_md5)} cross-source post_ids.")
    return True


def load_data_from_db(verbose=True):
    """Load or reload data from the database into the in-memory caches (synchronous)."""
    global _loading_in_progress

    with data_lock:
        if _loading_in_progress:
            logger.debug("Cache load already in progress, skipping...")
            return False
        _loading_in_progress = True

    try:
        return _load_data_from_db_impl(verbose=verbose)
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
        with data_lock:
            _loading_in_progress = False
        return False


def load_data_from_db_async(verbose=False):
    """Load data asynchronously in background thread to avoid blocking the main thread.

    Returns a Future object that can be waited on if needed.
    """
    global _loading_in_progress

    with data_lock:
        if _loading_in_progress:
            logger.debug("Cache load already in progress, skipping async request...")
            return None
        _loading_in_progress = True

    # Submit to executor
    future = _load_executor.submit(_load_data_from_db_impl, verbose=verbose)

    def on_error(fut):
        try:
            fut.result()
        except Exception as e:
            logger.error(f"Async cache load failed: {e}")
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
            # Load image data using tag IDs
            query = """
            SELECT i.filepath,
                   COALESCE(GROUP_CONCAT(t.id, ','), '') as tag_ids
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            WHERE i.filepath = ?
            GROUP BY i.id
            """
            result = conn.execute(query, (filepath,)).fetchone()

            if result:
                new_entry = dict(result)
                # Parse comma-separated IDs into array
                if new_entry['tag_ids']:
                    ids = [int(id_str) for id_str in new_entry['tag_ids'].split(',')]
                    new_entry['tag_ids'] = array('i', ids)
                else:
                    new_entry['tag_ids'] = array('i')
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
            tag_counts_query = "SELECT id, COUNT(DISTINCT image_id) as count FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY id"
            tag_counts.clear()
            tag_counts.update({row['id']: row['count'] for row in conn.execute(tag_counts_query).fetchall()})


# ============================================================================
# Tag ID Cache Helper Functions (Memory Optimization - Phase 3)
# ============================================================================

def get_image_tags_as_string(image_data_entry: dict) -> str:
    """
    Get tags as space-separated string from image_data entry.

    Args:
        image_data_entry: Dict from image_data cache

    Returns:
        Space-separated tag names string
    """
    from core.tag_id_cache import get_tag_id_cache
    tag_ids = image_data_entry.get('tag_ids', array('i'))
    cache = get_tag_id_cache()
    return cache.get_string_from_ids(tag_ids)


def get_image_tags_as_set(image_data_entry: dict) -> set:
    """
    Get tags as set for fast set operations.

    Returns:
        Set of tag names (for compatibility with existing code)
    """
    tags_string = get_image_tags_as_string(image_data_entry)
    return set(tags_string.split()) if tags_string else set()


def get_image_tags_as_ids(image_data_entry: dict) -> array:
    """
    Get tags as array of IDs.

    Args:
        image_data_entry: Dict from image_data cache

    Returns:
        array of int32 tag IDs
    """
    return image_data_entry.get('tag_ids', array('i'))


def get_image_tag_count(image_data_entry: dict) -> int:
    """
    Get number of tags for an image.

    Args:
        image_data_entry: Dict from image_data cache

    Returns:
        Number of tags
    """
    tag_ids = image_data_entry.get('tag_ids', array('i'))
    return len(tag_ids)


# ============================================================================
# Cache Invalidation Helpers
# ============================================================================

def invalidate_image_cache(filepath: str = None):
    """
    Invalidate image-related caches.
    
    Args:
        filepath: If provided, invalidate only for this image.
                  If None, invalidate all image caches.
    """
    from repositories.data_access import get_image_details
    
    if filepath:
        reload_single_image(filepath)
    reload_tag_counts()
    get_image_details.cache_clear()


def invalidate_tag_cache():
    """Invalidate tag-related caches."""
    # Reload tag ID cache (new tags may have been added)
    from core.tag_id_cache import reload_tag_id_cache
    reload_tag_id_cache()
    reload_tag_counts()


def invalidate_all_caches():
    """Invalidate all application caches."""
    from repositories.data_access import get_image_details
    
    load_data_from_db()
    get_image_details.cache_clear()

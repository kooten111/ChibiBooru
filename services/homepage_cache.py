"""
Homepage Hot Cache

Pre-assembles randomized homepage image sets in the background so the
gallery route can serve them instantly without any per-request DB/IO work.

Architecture:
  - A background daemon thread maintains a buffer of ready-to-serve pages.
  - Each page is a random sample of IMAGES_PER_PAGE images, fully formatted
    with path, thumbnail path, and tag strings.
  - The home() route pops a page from the buffer (instant).
  - The background thread refills the buffer automatically.
  - On cache invalidation (image add/delete), the buffer is flushed and
    the underlying image list is refreshed.
"""

import random
import threading
import time
from collections import deque

import config
from database import models
from core.cache_manager import get_image_tags_as_string
from utils import get_thumbnail_path

# Buffer size: how many pre-assembled pages to keep ready
_BUFFER_SIZE = 3

# Internal state
_buffer = deque(maxlen=_BUFFER_SIZE)
_all_images = None          # Cached result of get_all_images_with_tags()
_all_images_lock = threading.Lock()
_buffer_event = threading.Event()  # Signals the producer to wake up
_started = False
_start_lock = threading.Lock()


def _refresh_image_list():
    """Fetch the full image list from the database."""
    global _all_images
    with _all_images_lock:
        _all_images = models.get_all_images_with_tags()
    return _all_images


def _build_page(images_list):
    """Build one ready-to-serve homepage from a list of all images."""
    page_size = config.IMAGES_PER_PAGE
    count = min(page_size, len(images_list))
    if count == 0:
        return [], 0

    sample = random.sample(images_list, count)
    page = [
        {
            "path": f"images/{img['filepath']}",
            "thumb": get_thumbnail_path(f"images/{img['filepath']}"),
            "tags": get_image_tags_as_string(img),
        }
        for img in sample
    ]
    return page, len(images_list)


def _producer_loop():
    """Background thread that keeps the buffer full."""
    global _all_images

    while True:
        # Wait until buffer needs filling (or we're signaled to wake)
        _buffer_event.wait(timeout=5.0)
        _buffer_event.clear()

        try:
            # Ensure we have an image list
            if _all_images is None:
                _refresh_image_list()

            # Fill buffer up to capacity
            while len(_buffer) < _BUFFER_SIZE and _all_images:
                page, total = _build_page(_all_images)
                _buffer.append((page, total))

        except Exception as e:
            print(f"[HomepageCache] Producer error: {e}")
            time.sleep(1.0)  # Back off on error


def _ensure_started():
    """Start the background producer thread on first access."""
    global _started
    if _started:
        return
    with _start_lock:
        if _started:
            return
        t = threading.Thread(target=_producer_loop, daemon=True, name="homepage-cache")
        t.start()
        _started = True


def get_homepage_images():
    """
    Get a pre-assembled homepage image set.

    Returns:
        Tuple of (images_list, total_count) ready for template rendering.
        Each image dict has 'path', 'thumb', 'tags' keys.
    """
    _ensure_started()

    # Try to pop a pre-built page
    try:
        page, total = _buffer.popleft()
        # Signal producer to refill
        _buffer_event.set()
        return page, total
    except IndexError:
        pass

    # Cold start: build one synchronously
    images = _all_images
    if images is None:
        images = _refresh_image_list()

    page, total = _build_page(images)

    # Signal producer to start filling
    _buffer_event.set()
    return page, total


def invalidate():
    """
    Invalidate the hot cache (call after image add/delete).
    Flushes the buffer and refreshes the image list on next access.
    """
    global _all_images
    with _all_images_lock:
        _all_images = None
    _buffer.clear()
    # Wake producer to rebuild
    _buffer_event.set()

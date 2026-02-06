"""Tag similarity calculation with caching."""

import config
from database import models
from functools import lru_cache
from math import log
from events.cache_events import register_cache_invalidation_callback

# Global cache for tag categories - populated once on first use
_tag_category_cache = None
_similarity_context_cache = None


def _initialize_similarity_cache():
    """Initialize global caches for similarity calculations."""
    global _tag_category_cache, _similarity_context_cache

    if _tag_category_cache is not None:
        return

    from database import get_db_connection

    with get_db_connection() as conn:
        query = "SELECT id, category, extended_category FROM tags"
        results = conn.execute(query).fetchall()
        # Store both base category and extended category for each tag
        _tag_category_cache = {
            row["id"]: {
                'category': row["category"] or "general",
                'extended_category': row["extended_category"]
            }
            for row in results
        }

    _similarity_context_cache = {
        "tag_counts": models.get_tag_counts(),
        "total_images": models.get_image_count(),
    }


def invalidate_similarity_cache():
    """Invalidate similarity caches when data changes."""
    global _tag_category_cache, _similarity_context_cache
    _tag_category_cache = None
    _similarity_context_cache = None
    _get_tag_weight.cache_clear()


register_cache_invalidation_callback(invalidate_similarity_cache)


@lru_cache(maxsize=10000)
def _get_tag_weight(tag):
    """Get the combined IDF and category weight for a tag name (cached)."""
    _initialize_similarity_cache()

    from core.tag_id_cache import get_tag_id_cache

    cache = get_tag_id_cache()
    tag_id = cache.get_id(tag)

    if tag_id is None:
        return 0.1

    tag_freq = _similarity_context_cache["tag_counts"].get(tag_id, 1)
    idf_weight = 1.0 / log(tag_freq + 1)

    cat_info = _tag_category_cache.get(tag_id, {'category': 'general', 'extended_category': None})
    
    # Use extended category weight if enabled and available
    if config.USE_EXTENDED_SIMILARITY and cat_info['extended_category']:
        category_weight = config.SIMILARITY_EXTENDED_CATEGORY_WEIGHTS.get(
            cat_info['extended_category'],
            # Fall back to base category weight if extended category not in weights
            config.SIMILARITY_CATEGORY_WEIGHTS.get(cat_info['category'], 1.0)
        )
    else:
        # Use base category weight
        category_weight = config.SIMILARITY_CATEGORY_WEIGHTS.get(cat_info['category'], 1.0)

    return idf_weight * category_weight


def calculate_similarity(tags1, tags2):
    """Calculate similarity between two tag sets using the configured method."""
    if config.SIMILARITY_METHOD == "weighted":
        return calculate_weighted_similarity(tags1, tags2)
    return calculate_jaccard_similarity(tags1, tags2)


def calculate_jaccard_similarity(tags1, tags2):
    """Calculate basic Jaccard similarity between two tag sets."""
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())

    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2) if len(set1 | set2) > 0 else 0.0


def calculate_weighted_similarity(tags1, tags2):
    """
    Calculate weighted similarity using inverse frequency weighting and category multipliers.

    Rare tags contribute more to similarity (inverse document frequency),
    and tags in certain categories (character, copyright) are weighted higher.
    """
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())

    if not set1 or not set2:
        return 0.0

    _initialize_similarity_cache()

    intersection_weight = sum(_get_tag_weight(tag) for tag in set1 & set2)
    union_weight = sum(_get_tag_weight(tag) for tag in set1 | set2)

    return intersection_weight / union_weight if union_weight > 0 else 0.0

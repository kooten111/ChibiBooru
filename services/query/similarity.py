"""Tag similarity calculation with caching.

Supports multiple similarity methods:
- jaccard: Basic Jaccard (intersection/union)
- weighted: Original IDF + category weights
- weighted_tfidf: Enhanced TF-IDF formula (better discrimination)
- asymmetric: Prioritizes query coverage
- asymmetric_tfidf: Asymmetric + enhanced TF-IDF (recommended)
"""

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
    _get_tag_weight_tfidf.cache_clear()


register_cache_invalidation_callback(invalidate_similarity_cache)


def _get_category_weight(tag_id):
    """Get category weight for a tag ID."""
    cat_info = _tag_category_cache.get(tag_id, {'category': 'general', 'extended_category': None})
    
    # Use extended category weight if enabled and available
    if config.USE_EXTENDED_SIMILARITY and cat_info['extended_category']:
        return config.SIMILARITY_EXTENDED_CATEGORY_WEIGHTS.get(
            cat_info['extended_category'],
            # Fall back to base category weight if extended category not in weights
            config.SIMILARITY_CATEGORY_WEIGHTS.get(cat_info['category'], 1.0)
        )
    else:
        # Use base category weight
        return config.SIMILARITY_CATEGORY_WEIGHTS.get(cat_info['category'], 1.0)


@lru_cache(maxsize=10000)
def _get_tag_weight(tag):
    """Get the combined IDF and category weight for a tag name (cached).
    
    Uses the original IDF formula: 1 / log(freq + 1)
    """
    _initialize_similarity_cache()

    from core.tag_id_cache import get_tag_id_cache

    cache = get_tag_id_cache()
    tag_id = cache.get_id(tag)

    if tag_id is None:
        return 0.1

    tag_freq = _similarity_context_cache["tag_counts"].get(tag_id, 1)
    idf_weight = 1.0 / log(tag_freq + 1)
    category_weight = _get_category_weight(tag_id)

    return idf_weight * category_weight


@lru_cache(maxsize=10000)
def _get_tag_weight_tfidf(tag):
    """Get the combined TF-IDF and category weight for a tag name (cached).
    
    Uses standard TF-IDF formula: log(N / (freq + 1)) + 1
    This provides better discrimination between rare and common tags.
    """
    _initialize_similarity_cache()

    from core.tag_id_cache import get_tag_id_cache

    cache = get_tag_id_cache()
    tag_id = cache.get_id(tag)

    if tag_id is None:
        return 0.1

    tag_freq = _similarity_context_cache["tag_counts"].get(tag_id, 1)
    total_images = _similarity_context_cache["total_images"]
    
    # Standard TF-IDF formula with +1 to ensure positive values
    idf_weight = log(total_images / (tag_freq + 1)) + 1
    category_weight = _get_category_weight(tag_id)

    return idf_weight * category_weight


def calculate_similarity(tags1, tags2):
    """Calculate similarity between two tag sets using the configured method."""
    method = config.SIMILARITY_METHOD.lower()
    
    if method == "weighted":
        return calculate_weighted_similarity(tags1, tags2)
    elif method == "weighted_tfidf":
        return calculate_weighted_tfidf_similarity(tags1, tags2)
    elif method == "asymmetric":
        return calculate_asymmetric_similarity(tags1, tags2)
    elif method == "asymmetric_tfidf":
        return calculate_asymmetric_tfidf_similarity(tags1, tags2)
    else:  # jaccard or unknown
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
    
    Uses original IDF formula: 1 / log(freq + 1)
    """
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())

    if not set1 or not set2:
        return 0.0

    _initialize_similarity_cache()

    intersection_weight = sum(_get_tag_weight(tag) for tag in set1 & set2)
    union_weight = sum(_get_tag_weight(tag) for tag in set1 | set2)

    return intersection_weight / union_weight if union_weight > 0 else 0.0


def calculate_weighted_tfidf_similarity(tags1, tags2):
    """
    Calculate weighted similarity using standard TF-IDF formula.
    
    Uses TF-IDF formula: log(N / (freq + 1)) + 1
    This provides better discrimination between rare and common tags.
    """
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())

    if not set1 or not set2:
        return 0.0

    _initialize_similarity_cache()

    intersection_weight = sum(_get_tag_weight_tfidf(tag) for tag in set1 & set2)
    union_weight = sum(_get_tag_weight_tfidf(tag) for tag in set1 | set2)

    return intersection_weight / union_weight if union_weight > 0 else 0.0


def calculate_asymmetric_similarity(tags1, tags2):
    """
    Calculate asymmetric similarity that prioritizes query coverage.
    
    This is useful for "find similar to X" searches where we want images
    that contain X's important tags, without penalizing them for having 
    additional unrelated tags.
    
    Formula: α × (intersection/query) + (1-α) × (intersection/union)
    
    Uses original IDF formula: 1 / log(freq + 1)
    """
    set1 = set((tags1 or "").split())  # Query image tags
    set2 = set((tags2 or "").split())  # Candidate image tags

    if not set1 or not set2:
        return 0.0

    _initialize_similarity_cache()

    intersection_weight = sum(_get_tag_weight(tag) for tag in set1 & set2)
    query_weight = sum(_get_tag_weight(tag) for tag in set1)
    union_weight = sum(_get_tag_weight(tag) for tag in set1 | set2)

    if query_weight == 0 or union_weight == 0:
        return 0.0

    alpha = config.ASYMMETRIC_ALPHA
    query_coverage = intersection_weight / query_weight
    union_similarity = intersection_weight / union_weight

    return alpha * query_coverage + (1 - alpha) * union_similarity


def calculate_asymmetric_tfidf_similarity(tags1, tags2):
    """
    Calculate asymmetric similarity with enhanced TF-IDF.
    
    Combines:
    - Asymmetric matching (prioritizes query coverage)
    - Standard TF-IDF (better discrimination between rare/common tags)
    
    This is the recommended method for best results.
    """
    set1 = set((tags1 or "").split())  # Query image tags
    set2 = set((tags2 or "").split())  # Candidate image tags

    if not set1 or not set2:
        return 0.0

    _initialize_similarity_cache()

    intersection_weight = sum(_get_tag_weight_tfidf(tag) for tag in set1 & set2)
    query_weight = sum(_get_tag_weight_tfidf(tag) for tag in set1)
    union_weight = sum(_get_tag_weight_tfidf(tag) for tag in set1 | set2)

    if query_weight == 0 or union_weight == 0:
        return 0.0

    alpha = config.ASYMMETRIC_ALPHA
    query_coverage = intersection_weight / query_weight
    union_similarity = intersection_weight / union_weight

    return alpha * query_coverage + (1 - alpha) * union_similarity


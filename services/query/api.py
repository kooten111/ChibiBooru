"""Public API for query service."""

from .similarity import (
    calculate_jaccard_similarity,
    calculate_similarity,
    calculate_weighted_similarity,
    invalidate_similarity_cache,
)
from .stats import find_related_by_tags, get_enhanced_stats
from .search import perform_search

__all__ = [
    "calculate_jaccard_similarity",
    "calculate_similarity",
    "calculate_weighted_similarity",
    "find_related_by_tags",
    "get_enhanced_stats",
    "invalidate_similarity_cache",
    "perform_search",
]

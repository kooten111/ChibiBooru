"""Implication caching, pagination, and filtering."""

import time
from typing import Dict, List

from .detection import detect_substring_implications, detect_tag_correlations
from .models import ImplicationSuggestion


_suggestion_cache = {
    'suggestions': None,
    'timestamp': 0
}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached_suggestions() -> List[Dict]:
    """Get suggestions from cache or regenerate if stale."""
    current_time = time.time()
    if (_suggestion_cache['suggestions'] is not None and 
        current_time - _suggestion_cache['timestamp'] < _CACHE_TTL_SECONDS):
        return _suggestion_cache['suggestions']
    
    # Regenerate suggestions
    naming_suggestions = detect_substring_implications()
    correlation_suggestions = detect_tag_correlations(min_confidence=0.85, min_co_occurrence=3)
    
    all_suggestions = (
        [s.to_dict() for s in naming_suggestions] +
        [s.to_dict() for s in correlation_suggestions]
    )
    
    _suggestion_cache['suggestions'] = all_suggestions
    _suggestion_cache['timestamp'] = current_time
    
    return all_suggestions


def invalidate_suggestion_cache():
    """Clear the suggestion cache (call after approving/rejecting suggestions)."""
    _suggestion_cache['suggestions'] = None
    _suggestion_cache['timestamp'] = 0


def get_all_suggestions() -> Dict[str, List[Dict]]:
    """
    Get all auto-detected implication suggestions grouped by pattern type.
    Uses caching to avoid re-running expensive queries.
    """
    suggestions = _get_cached_suggestions()
    
    naming = [s for s in suggestions if s.get('pattern_type') == 'naming_pattern']
    correlation = [s for s in suggestions if s.get('pattern_type') == 'correlation']
    
    return {
        'naming': naming,
        'correlation': correlation,
        'summary': {
            'total': len(suggestions),
            'naming_count': len(naming),
            'correlation_count': len(correlation)
        }
    }


def get_paginated_suggestions(page: int = 1, 
                               limit: int = 50, 
                               pattern_type: str = None,
                               source_categories: List[str] = None,
                               implied_categories: List[str] = None,
                               query: str = None) -> Dict:
    """
    Get paginated suggestions with optional filtering.
    
    Args:
        page: Page number (1-indexed)
        limit: Items per page
        pattern_type: Optional filter ('naming_pattern' or 'correlation')
        source_categories: List of categories to include/exclude
        implied_categories: List of categories to include/exclude
    
    Returns:
        Dict with paginated results and metadata
    """
    all_suggestions = _get_cached_suggestions()
    
    # Apply filters
    filtered_suggestions = _filter_suggestions(
        all_suggestions, 
        pattern_type, 
        source_categories, 
        implied_categories,
        query
    )
    
    total = len(filtered_suggestions)
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    
    # Calculate slice indices
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    # Get the slice
    page_suggestions = filtered_suggestions[start_idx:end_idx]
    
    # Count by type for the full dataset
    naming_count = sum(1 for s in _get_cached_suggestions() if s.get('pattern_type') == 'naming_pattern')
    correlation_count = sum(1 for s in _get_cached_suggestions() if s.get('pattern_type') == 'correlation')
    
    return {
        'suggestions': page_suggestions,
        'page': page,
        'limit': limit,
        'total': total,
        'total_pages': total_pages,
        'has_more': page < total_pages,
        'summary': {
            'total': len(_get_cached_suggestions()),
            'naming_count': naming_count,
            'correlation_count': correlation_count
        }
    }


def _filter_suggestions(suggestions: List[Dict], pattern_type: str = None,
                        source_categories: List[str] = None,
                        implied_categories: List[str] = None,
                        query: str = None) -> List[Dict]:
    """Helper to filter detailed suggestions list."""
    filtered = suggestions
    
    # Text query filter
    if query:
        query = query.lower()
        filtered = [
            s for s in filtered
            if query in s.get('source_tag', '').lower() 
            or query in s.get('implied_tag', '').lower()
        ]
    
    # Pattern type filter
    if pattern_type and pattern_type != 'all':
        filtered = [s for s in filtered if s.get('pattern_type') == pattern_type]
        
    # Source category filter
    if source_categories and 'all' not in source_categories:
        # Separate inclusions and exclusions
        exclusions = [c[1:] for c in source_categories if c.startswith('!')]
        inclusions = [c for c in source_categories if not c.startswith('!')]
        
        filtered = [
            s for s in filtered
            if (not inclusions or s.get('source_category', 'general') in inclusions)
            and (not exclusions or s.get('source_category', 'general') not in exclusions)
        ]
        
    # Implied category filter
    if implied_categories and 'all' not in implied_categories:
        # Separate inclusions and exclusions
        exclusions = [c[1:] for c in implied_categories if c.startswith('!')]
        inclusions = [c for c in implied_categories if not c.startswith('!')]
        
        filtered = [
            s for s in filtered
            if (not inclusions or s.get('implied_category', 'general') in inclusions)
            and (not exclusions or s.get('implied_category', 'general') not in exclusions)
        ]
        
    return filtered

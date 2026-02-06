"""Auto-approval workflows for implications."""

from typing import Dict, List

from .management import approve_suggestion
from .application import apply_single_implication_to_images
from .suggestions import _get_cached_suggestions, invalidate_suggestion_cache, _filter_suggestions


def auto_approve_naming_pattern_suggestions() -> Dict:
    """
    Auto-approve all naming pattern suggestions.
    These are character_(copyright) → copyright patterns with high reliability.
    
    Returns:
        Dict with success count and any errors
    """
    suggestions = _get_cached_suggestions()
    
    # Filter to only naming pattern suggestions
    naming_suggestions = [s for s in suggestions if s.get('pattern_type') == 'naming_pattern']
    
    success_count = 0
    errors = []
    
    for suggestion in naming_suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        confidence = suggestion.get('confidence', 0.92)
        
        if not source_tag or not implied_tag:
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, 'naming_pattern', confidence)
            if success:
                success_count += 1
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    # Invalidate cache after bulk operation
    invalidate_suggestion_cache()
    
    return {
        'success_count': success_count,
        'total': len(naming_suggestions),
        'errors': errors,
        'pattern_type': 'naming_pattern'
    }


def auto_approve_high_confidence_suggestions(min_confidence: float = 0.95, 
                                              min_sample_size: int = 10,
                                              source_categories: List[str] = None,
                                              implied_categories: List[str] = None,
                                              apply_now: bool = False) -> Dict:
    """
    Auto-approve correlation suggestions that meet confidence and sample size thresholds.
    This ensures statistical significance before auto-approving.
    
    Args:
        min_confidence: Minimum confidence threshold (default 95%)
        min_sample_size: Minimum number of affected images for statistical significance
        source_categories: Optional list of source categories to filter by (supports ! prefix for exclusion)
        implied_categories: Optional list of implied categories to filter by (supports ! prefix for exclusion)
        apply_now: If True, apply the implications to existing images after approval
    
    Returns:
        Dict with success count and any errors
    """
    suggestions = _get_cached_suggestions()
    
    # Apply category filters if provided
    if source_categories or implied_categories:
        suggestions = _filter_suggestions(
            suggestions, 
            pattern_type=None,
            source_categories=source_categories,
            implied_categories=implied_categories
        )
    
    # Filter to correlation suggestions meeting thresholds
    # Note: sample_size is co-occurrence count (how many images have both tags)
    eligible_suggestions = [
        s for s in suggestions 
        if s.get('pattern_type') == 'correlation'
        and s.get('confidence', 0) >= min_confidence
        and s.get('sample_size', s.get('affected_images', 0)) >= min_sample_size
    ]
    
    success_count = 0
    errors = []
    tags_applied = 0
    
    for suggestion in eligible_suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        confidence = suggestion.get('confidence', min_confidence)
        
        if not source_tag or not implied_tag:
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, 'correlation', confidence)
            if success:
                success_count += 1
                # Apply to images if requested
                if apply_now:
                    tags_applied += apply_single_implication_to_images(source_tag, implied_tag)
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    # Invalidate cache after bulk operation
    invalidate_suggestion_cache()
    
    return {
        'success_count': success_count,
        'total': len(eligible_suggestions),
        'errors': errors,
        'tags_applied': tags_applied,
        'pattern_type': 'correlation',
        'thresholds': {
            'min_confidence': min_confidence,
            'min_sample_size': min_sample_size
        }
    }


def bulk_approve_implications(suggestions: List[Dict]) -> Dict:
    """
    Approve multiple suggestions at once.
    
    Args:
        suggestions: List of dicts with 'source_tag', 'implied_tag', 'inference_type', 'confidence'
    
    Returns:
        Dict with success count and any errors
    """
    success_count = 0
    errors = []
    
    for suggestion in suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        inference_type = suggestion.get('inference_type', 'manual')
        confidence = suggestion.get('confidence', 1.0)
        
        if not source_tag or not implied_tag:
            errors.append(f"Missing source_tag or implied_tag in suggestion")
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, inference_type, confidence)
            if success:
                success_count += 1
            else:
                errors.append(f"Failed to approve {source_tag} → {implied_tag}")
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    return {
        'success_count': success_count,
        'total': len(suggestions),
        'errors': errors
    }

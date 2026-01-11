"""
Tag display service for preparing tag data for image display.

This service handles the complex logic of preparing tags for display on image pages,
including categorization, extended categories, implied tags, and rating tags.
"""

from typing import Dict, List, Tuple
from database import get_db_connection
from database import models
from core.tag_id_cache import get_tag_count_by_name
from repositories.data_access import get_implied_tags_for_image


def prepare_tags_for_display(image_data: Dict) -> Dict:
    """
    Prepare all tag-related data for image display.
    
    Args:
        image_data: Dictionary containing image data with tags from get_image_details_with_merged_tags
        
    Returns:
        Dictionary containing:
        - tags_with_counts: List of (tag, count) tuples for general tags
        - categorized_tags: Dict mapping category to list of (tag, count) tuples
        - extended_grouped_tags: Dict mapping extended category to list of (tag, count) tuples
        - implied_tag_names: Set of tag names that were added via implication rules
        - merged_general_tags: List of merged general tags from local tagger
    """
    image_id = image_data.get('id')
    
    # Get general tags grouped by their extended categories
    general_tags = sorted((image_data.get("tags_general") or "").split())
    
    # Include merged local tagger predictions if available
    merged_general = image_data.get('merged_general_tags', [])
    if merged_general:
        general_tags = sorted(set(general_tags) | set(merged_general))
    
    # Get tags with extended categories
    tags_with_extended_categories = models.get_tags_with_extended_categories(general_tags)
    
    # Group tags by extended category for display
    extended_grouped_tags = {}
    for tag, count, extended_cat in tags_with_extended_categories:
        if extended_cat not in extended_grouped_tags:
            extended_grouped_tags[extended_cat] = []
        extended_grouped_tags[extended_cat].append((tag, count))
    
    # Keep the old format for backward compatibility (all general tags together)
    tags_with_counts = [(tag, get_tag_count_by_name(tag)) for tag in general_tags if tag]
    
    # Get rating tags from image_tags table and merge them into meta category
    rating_tags = _get_rating_tags(image_id)
    
    # Merge rating tags with meta tags
    meta_tags = (image_data.get("tags_meta") or "").split()
    meta_with_rating = sorted(set(meta_tags) | set(rating_tags))
    
    categorized_tags = {
        "character": [(t, get_tag_count_by_name(t)) for t in sorted((image_data.get("tags_character") or "").split()) if t],
        "copyright": [(t, get_tag_count_by_name(t)) for t in sorted((image_data.get("tags_copyright") or "").split()) if t],
        "artist": [(t, get_tag_count_by_name(t)) for t in sorted((image_data.get("tags_artist") or "").split()) if t],
        "species": [(t, get_tag_count_by_name(t)) for t in sorted((image_data.get("tags_species") or "").split()) if t],
        "meta": [(t, get_tag_count_by_name(t)) for t in meta_with_rating if t],
    }
    
    # Get tags that were added via implication rules
    implied_tags_map = get_implied_tags_for_image(image_id) if image_id else {}
    implied_tag_names = set(implied_tags_map.keys())
    
    # Merge implied tags into display lists ensuring they appear
    _merge_implied_tags(
        implied_tags_map,
        tags_with_counts,
        categorized_tags,
        extended_grouped_tags
    )
    
    return {
        'tags_with_counts': tags_with_counts,
        'categorized_tags': categorized_tags,
        'extended_grouped_tags': extended_grouped_tags,
        'implied_tag_names': implied_tag_names,
        'merged_general_tags': merged_general
    }


def _get_rating_tags(image_id: int) -> List[str]:
    """Get rating tags from image_tags table for a given image."""
    if not image_id:
        return []
    
    rating_tags = []
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ? AND t.category = 'rating'
        """, (image_id,))
        rating_tags = [row['name'] for row in cur.fetchall()]
    
    return rating_tags


def _merge_implied_tags(
    implied_tags_map: Dict,
    tags_with_counts: List[Tuple[str, int]],
    categorized_tags: Dict[str, List[Tuple[str, int]]],
    extended_grouped_tags: Dict[str, List[Tuple[str, int]]]
) -> None:
    """
    Merge implied tags into the various tag display structures.
    
    Modifies the lists in place.
    """
    for tag_name, info in implied_tags_map.items():
        category = info.get('category')
        extended_cat = info.get('extended_category')
        
        # 1. Update categorized_tags / tags_with_counts (Legacy/Sidebar)
        if category == 'general' or category not in categorized_tags:
            if not any(t[0] == tag_name for t in tags_with_counts):
                tags_with_counts.append((tag_name, get_tag_count_by_name(tag_name)))
                tags_with_counts.sort(key=lambda x: x[0])
        else:
            # Handle standard categories
            current_list = categorized_tags[category]
            if not any(t[0] == tag_name for t in current_list):
                current_list.append((tag_name, get_tag_count_by_name(tag_name)))
                current_list.sort(key=lambda x: x[0])
        
        # 2. Update extended_grouped_tags (Main Display)
        # Only relevant for general tags, as extended categorization usually applies to them
        if category == 'general':
            if extended_cat not in extended_grouped_tags:
                extended_grouped_tags[extended_cat] = []
            
            target_list = extended_grouped_tags[extended_cat]
            if not any(t[0] == tag_name for t in target_list):
                target_list.append((tag_name, get_tag_count_by_name(tag_name)))
                target_list.sort(key=lambda x: x[0])

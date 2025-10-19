import models
from utils import get_thumbnail_path

def calculate_similarity(tags1, tags2):
    """Calculate Jaccard similarity between two tag sets."""
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())
    
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2) if len(set1 | set2) > 0 else 0.0

def get_enhanced_stats():
    """Get detailed statistics about the collection from the database."""
    tag_counts = models.get_tag_counts()
    image_count = models.get_image_count()
    return {
        'total': image_count,
        'with_metadata': image_count,
        'without_metadata': 0,
        'total_tags': len(tag_counts),
        'avg_tags_per_image': models.get_avg_tags_per_image(),
        'source_breakdown': models.get_source_breakdown(),
        'top_tags': sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20],
        'category_counts': models.get_category_counts(),
        'saucenao_used': models.get_saucenao_lookup_count(),
        'local_tagger_used': models.get_source_breakdown().get('local_tagger', 0)
    }

def perform_search(search_query):
    """Perform a search using data from the database, handling special queries and combinations."""
    if not search_query:
        return models.get_all_images_with_tags(), True

    import re
    
    # Parse the query into components
    tokens = search_query.lower().split()
    source_filters = []
    filename_filter = None
    extension_filter = None
    tag_filters = []
    
    for token in tokens:
        if token.startswith('source:'):
            source_filters.append(token.split(':', 1)[1].strip())  # Append to list
        elif token.startswith('filename:'):
            filename_filter = token.split(':', 1)[1].strip()
        elif token.startswith('.'):
            extension_filter = token[1:]
        else:
            tag_filters.append(token)
    
    # Start with appropriate base query
    if source_filters:
        if len(source_filters) == 1:
            # Single source - use the existing optimized function
            results = models.search_images_by_source(source_filters[0])
        else:
            # Multiple sources - need AND logic
            results = models.search_images_by_multiple_sources(source_filters)
    elif tag_filters:
        # Use the dedicated tag search function
        results = models.search_images_by_tags(tag_filters)
    else:
        # Get all images for non-tag filters
        results = models.get_all_images_with_tags()
    
    # Apply extension filter if present
    if extension_filter:
        results = [img for img in results if img['filepath'].lower().endswith(f'.{extension_filter}')]
    
    # Apply filename filter if present
    if filename_filter:
        results = [img for img in results if filename_filter in img['filepath'].lower()]
    
    # If we started with source filter(s) but also have tag filters, filter by tags now
    if source_filters and tag_filters:
        # Filter the source results to only include images with all required tags
        filtered = []
        for img in results:
            img_tags = set((img.get('tags') or '').lower().split())
            if all(tag in img_tags for tag in tag_filters):
                filtered.append(img)
        results = filtered
    
    # Determine if we should shuffle
    # Only shuffle if it's purely tag-based search (no special filters)
    should_shuffle = bool(tag_filters) and not (source_filters or filename_filter or extension_filter)
    
    return results, should_shuffle


def find_related_by_tags(filepath, limit=20):
    """Find related images by weighted tag similarity using the database."""
    details = models.get_image_details(filepath.replace("images/", "", 1))
    if not details:
        return []

    ref_tags_str = details.get('tags_general', '') or details.get('all_tags', '')
    if not ref_tags_str:
        return []

    all_images = models.get_all_images_with_tags()
    similarities = []

    for img in all_images:
        if img['filepath'] == details['filepath']:
            continue
        
        sim = calculate_similarity(ref_tags_str, img['tags'])
        if sim > 0.1:
            similarities.append({
                'path': f"images/{img['filepath']}",
                'thumb': get_thumbnail_path(f"images/{img['filepath']}"),
                'match_type': 'similar',
                'score': sim
            })

    similarities.sort(key=lambda x: x['score'], reverse=True)
    return similarities[:limit]
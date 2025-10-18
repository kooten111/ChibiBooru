# services/query_service.py
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
    """Perform a search using data from the database, handling special queries."""
    if not search_query:
        return models.get_all_images_with_tags(), True

    # --- THIS IS THE CORRECTED BLOCK ---
    # Handle special queries first
    if search_query.startswith('source:'):
        source_name = search_query.split(':', 1)[1].strip()
        return models.search_images_by_source(source_name), False # Don't shuffle source results

    # Default to tag search
    query_tags = search_query.lower().split()
    return models.search_images_by_tags(query_tags), True
    # --- END OF CORRECTION ---


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
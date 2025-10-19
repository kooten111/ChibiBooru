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
    relationship_filter = None
    general_terms = []
    
    for token in tokens:
        if token.startswith('source:'):
            source_filters.append(token.split(':', 1)[1].strip())
        elif token.startswith('filename:'):
            filename_filter = token.split(':', 1)[1].strip()
        elif token.startswith('.'):
            extension_filter = token[1:]
        elif token.startswith('has:'):
            rel_type = token.split(':', 1)[1].strip()
            if rel_type in ['parent', 'child', 'relationship']:
                relationship_filter = 'any' if rel_type == 'relationship' else rel_type
        else:
            general_terms.append(token)
    
    # Start with all images and filter down
    results = models.get_all_images_with_tags()

    # Apply specific filters first
    if relationship_filter:
        # This is an expensive operation if not done in the DB
        relationship_images = {img['filepath'] for img in models.search_images_by_relationship(relationship_filter)}
        results = [img for img in results if img['filepath'] in relationship_images]

    if source_filters:
        # This is also very expensive. A dedicated SQL query would be better.
        # For now, we'll filter in Python.
        temp_results = []
        for img in results:
            details = models.get_image_details(img['filepath'])
            if details and details.get('raw_metadata'):
                sources = details['raw_metadata'].get('sources', {}).keys()
                if all(s in sources for s in source_filters):
                    temp_results.append(img)
        results = temp_results

    if extension_filter:
        results = [img for img in results if img['filepath'].lower().endswith(f'.{extension_filter}')]
    
    if filename_filter:
        results = [img for img in results if filename_filter in img['filepath'].lower()]
    
    # Now, apply the general search terms to the already filtered results
    if general_terms:
        filtered_results = []
        for img in results:
            # Create a combined string of searchable fields
            searchable_content = f"{img.get('tags', '')} {img.get('filepath')}".lower()
            
            # You could also add sources to this searchable string if you modify
            # get_all_images_with_tags to include source information.

            if all(term in searchable_content for term in general_terms):
                filtered_results.append(img)
        results = filtered_results

    should_shuffle = bool(general_terms) and not (source_filters or filename_filter or extension_filter)
    
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
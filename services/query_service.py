import models
import config
from utils import get_thumbnail_path
from math import log

def calculate_similarity(tags1, tags2):
    """Calculate similarity between two tag sets using the configured method."""
    if config.SIMILARITY_METHOD == 'weighted':
        return calculate_weighted_similarity(tags1, tags2)
    else:
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

    # Get tag counts for IDF calculation
    tag_counts = models.get_tag_counts()
    total_images = models.get_image_count()

    # Get tag categories from database
    tag_categories = _get_tag_categories(set1 | set2)

    # Calculate weighted intersection
    intersection_weight = 0.0
    for tag in set1 & set2:
        idf_weight = _calculate_idf_weight(tag, tag_counts, total_images)
        category_weight = _get_category_weight(tag, tag_categories)
        intersection_weight += idf_weight * category_weight

    # Calculate weighted union
    union_weight = 0.0
    for tag in set1 | set2:
        idf_weight = _calculate_idf_weight(tag, tag_counts, total_images)
        category_weight = _get_category_weight(tag, tag_categories)
        union_weight += idf_weight * category_weight

    return intersection_weight / union_weight if union_weight > 0 else 0.0

def _calculate_idf_weight(tag, tag_counts, total_images):
    """Calculate inverse document frequency weight for a tag."""
    # Get tag frequency (how many images have this tag)
    tag_freq = tag_counts.get(tag, 1)

    # IDF formula: 1 / log(frequency + 1)
    # Rare tags (low frequency) get higher weights
    # Common tags (high frequency) get lower weights
    return 1.0 / log(tag_freq + 1)

def _get_category_weight(tag, tag_categories):
    """Get the configured weight for a tag's category."""
    category = tag_categories.get(tag, 'general')
    return config.SIMILARITY_CATEGORY_WEIGHTS.get(category, 1.0)

def _get_tag_categories(tags):
    """Fetch categories for a set of tags from the database."""
    if not tags:
        return {}

    # Query database for tag categories
    from database import get_db_connection

    tag_list = list(tags)
    placeholders = ','.join(['?'] * len(tag_list))

    with get_db_connection() as conn:
        query = f"SELECT name, category FROM tags WHERE name IN ({placeholders})"
        results = conn.execute(query, tag_list).fetchall()

    return {row['name']: row['category'] or 'general' for row in results}

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
    pool_filter = None
    general_terms = []

    for token in tokens:
        if token.startswith('source:'):
            source_filters.append(token.split(':', 1)[1].strip())
        elif token.startswith('filename:'):
            filename_filter = token.split(':', 1)[1].strip()
        elif token.startswith('pool:'):
            pool_filter = token.split(':', 1)[1].strip()
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
    if pool_filter:
        # Find pool by name and get its images
        pool_images = models.search_images_by_pool(pool_filter)
        if pool_images:
            pool_filepaths = {img['filepath'] for img in pool_images}
            results = [img for img in results if img['filepath'] in pool_filepaths]
        else:
            # No pool found with that name, return empty results
            results = []

    if relationship_filter:
        # This is an expensive operation if not done in the DB
        relationship_images = {img['filepath'] for img in models.search_images_by_relationship(relationship_filter)}
        results = [img for img in results if img['filepath'] in relationship_images]

    if source_filters:
        # Use optimized SQL query instead of N+1 Python loop
        results = models.search_images_by_multiple_sources(source_filters)

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
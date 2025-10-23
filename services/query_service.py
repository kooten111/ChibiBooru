import models
import config
from utils import get_thumbnail_path
from math import log
from functools import lru_cache

# Global cache for tag categories - populated once on first use
_tag_category_cache = None
_similarity_context_cache = None

def _initialize_similarity_cache():
    """Initialize global caches for similarity calculations."""
    global _tag_category_cache, _similarity_context_cache

    if _tag_category_cache is not None:
        return

    # Load all tag categories from database once
    from database import get_db_connection
    with get_db_connection() as conn:
        query = "SELECT name, category FROM tags"
        results = conn.execute(query).fetchall()
        _tag_category_cache = {row['name']: row['category'] or 'general' for row in results}

    # Cache tag counts and image count
    _similarity_context_cache = {
        'tag_counts': models.get_tag_counts(),
        'total_images': models.get_image_count()
    }

def invalidate_similarity_cache():
    """Invalidate similarity caches when data changes."""
    global _tag_category_cache, _similarity_context_cache
    _tag_category_cache = None
    _similarity_context_cache = None
    _get_tag_weight.cache_clear()

@lru_cache(maxsize=10000)
def _get_tag_weight(tag):
    """Get the combined IDF and category weight for a tag (cached)."""
    _initialize_similarity_cache()

    # Get IDF weight
    tag_freq = _similarity_context_cache['tag_counts'].get(tag, 1)
    idf_weight = 1.0 / log(tag_freq + 1)

    # Get category weight
    category = _tag_category_cache.get(tag, 'general')
    category_weight = config.SIMILARITY_CATEGORY_WEIGHTS.get(category, 1.0)

    return idf_weight * category_weight

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

    This version is optimized with caching to avoid repeated database queries.
    """
    set1 = set((tags1 or "").split())
    set2 = set((tags2 or "").split())

    if not set1 or not set2:
        return 0.0

    # Initialize caches on first use
    _initialize_similarity_cache()

    # Calculate weighted intersection using cached weights
    intersection_weight = sum(_get_tag_weight(tag) for tag in set1 & set2)

    # Calculate weighted union using cached weights
    union_weight = sum(_get_tag_weight(tag) for tag in set1 | set2)

    return intersection_weight / union_weight if union_weight > 0 else 0.0

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

def _should_use_fts(general_terms):
    """
    Determine if we should use FTS5 instead of exact tag matching.
    Use FTS5 when search terms don't match existing tags exactly.
    """
    from database import get_db_connection

    # Check if any term doesn't exist as an exact tag
    with get_db_connection() as conn:
        for term in general_terms:
            # Strip quotes if present
            clean_term = term.strip('"')
            result = conn.execute("SELECT 1 FROM tags WHERE name = ? LIMIT 1", (clean_term,)).fetchone()
            if not result:
                # This term is not an exact tag, use FTS
                return True
    return False

def _fts_search(general_terms, negative_terms, source_filters, filename_filter,
               extension_filter, relationship_filter, pool_filter):
    """
    Perform full-text search using FTS5 and apply filters.
    Returns results ranked by relevance.
    """
    from database import get_db_connection

    # Build FTS5 query
    fts_query_parts = []

    # Add positive terms
    for term in general_terms:
        # Remove quotes for FTS query
        clean_term = term.strip('"')
        # Escape special FTS5 characters
        clean_term = clean_term.replace('"', '""')
        fts_query_parts.append(f'"{clean_term}"')

    # Add negative terms
    for term in negative_terms:
        clean_term = term.replace('"', '""')
        fts_query_parts.append(f'NOT "{clean_term}"')

    fts_query = ' '.join(fts_query_parts)

    with get_db_connection() as conn:
        # Build the SQL query with filters
        sql_parts = ["""
            SELECT i.id, i.filepath,
                   COALESCE(i.tags_character, '') || ' ' ||
                   COALESCE(i.tags_copyright, '') || ' ' ||
                   COALESCE(i.tags_artist, '') || ' ' ||
                   COALESCE(i.tags_species, '') || ' ' ||
                   COALESCE(i.tags_meta, '') || ' ' ||
                   COALESCE(i.tags_general, '') as tags,
                   fts.rank
            FROM images_fts fts
            INNER JOIN images i ON i.filepath = fts.filepath
        """]

        where_clauses = []
        params = []

        # FTS query
        if fts_query:
            where_clauses.append("images_fts MATCH ?")
            params.append(fts_query)

        # Pool filter
        if pool_filter:
            sql_parts[0] += """
                INNER JOIN pool_images pi ON i.id = pi.image_id
                INNER JOIN pools p ON pi.pool_id = p.id
            """
            where_clauses.append("LOWER(p.name) LIKE ?")
            params.append(f"%{pool_filter}%")

        # Relationship filter
        if relationship_filter:
            if relationship_filter == 'parent':
                where_clauses.append("i.parent_id IS NOT NULL")
            elif relationship_filter == 'child':
                where_clauses.append("i.has_children = 1")
            elif relationship_filter == 'any':
                where_clauses.append("(i.parent_id IS NOT NULL OR i.has_children = 1)")

        # Source filters
        if source_filters:
            placeholders = ','.join(['?'] * len(source_filters))
            sql_parts[0] += f"""
                INNER JOIN image_sources isrc ON i.id = isrc.image_id
                INNER JOIN sources s ON isrc.source_id = s.id
            """
            where_clauses.append(f"s.name IN ({placeholders})")
            params.extend(source_filters)

        # Extension filter
        if extension_filter:
            where_clauses.append("LOWER(i.filepath) LIKE ?")
            params.append(f"%.{extension_filter}")

        # Filename filter
        if filename_filter:
            where_clauses.append("LOWER(i.filepath) LIKE ?")
            params.append(f"%{filename_filter}%")

        # Add WHERE clause if we have conditions
        if where_clauses:
            sql_parts.append("WHERE " + " AND ".join(where_clauses))

        # Order by FTS5 rank (relevance)
        sql_parts.append("ORDER BY rank")

        full_query = '\n'.join(sql_parts)

        try:
            cursor = conn.execute(full_query, params)
            rows = cursor.fetchall()

            results = []
            for row in rows:
                results.append({
                    'filepath': row['filepath'],
                    'tags': row['tags']
                })

            return results
        except Exception as e:
            print(f"FTS search error: {e}")
            # Fallback to empty results on error
            return []

def perform_search(search_query):
    """Perform a search using data from the database, handling special queries and combinations."""
    if not search_query:
        return models.get_all_images_with_tags(), True

    import re
    from database import get_db_connection

    # Parse the query into components
    tokens = search_query.lower().split()
    source_filters = []
    filename_filter = None
    extension_filter = None
    relationship_filter = None
    pool_filter = None
    general_terms = []
    negative_terms = []
    freetext_mode = False

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
        elif token.startswith('-'):
            # Negative search: exclude this term
            negative_terms.append(token[1:])
        elif token.startswith('"') or (general_terms and general_terms[-1].startswith('"') and not general_terms[-1].endswith('"')):
            # Quoted phrase - switch to freetext mode
            freetext_mode = True
            general_terms.append(token)
        else:
            general_terms.append(token)
    
    # Decide whether to use FTS5 or tag-based search
    use_fts = freetext_mode or (general_terms and _should_use_fts(general_terms))

    if use_fts and (general_terms or negative_terms):
        # Use FTS5 for freetext search
        results = _fts_search(general_terms, negative_terms, source_filters, filename_filter,
                             extension_filter, relationship_filter, pool_filter)
        should_shuffle = False  # FTS results are ranked by relevance
    else:
        # Use traditional tag-based search
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

                if all(term in searchable_content for term in general_terms):
                    filtered_results.append(img)
            results = filtered_results

        # Apply negative terms
        if negative_terms:
            results = [img for img in results
                      if not any(term in f"{img.get('tags', '')} {img.get('filepath')}".lower()
                                for term in negative_terms)]

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
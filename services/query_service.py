import models
import config
from utils import get_thumbnail_path
from math import log
from functools import lru_cache
from events.cache_events import register_cache_invalidation_callback

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

# Register this module's invalidation function with the cache events system
# This breaks the circular dependency: models.py doesn't need to import query_service.py
register_cache_invalidation_callback(invalidate_similarity_cache)

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

    Returns True if FTS should be used (when any term is NOT an exact tag).
    Returns False if all terms are exact tags (use fast tag-based search).
    """
    from database import get_db_connection

    if not general_terms:
        return False

    # Check if all terms exist as exact tags (case-insensitive)
    with get_db_connection() as conn:
        for term in general_terms:
            # Strip quotes if present
            clean_term = term.strip('"').lower()

            # Check for exact tag match (case-insensitive)
            result = conn.execute(
                "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1",
                (clean_term,)
            ).fetchone()

            if not result:
                # This term is not an exact tag, use FTS for the whole query
                return True

    # All terms are exact tags - use fast tag-based search
    return False

def _fts_search(general_terms, negative_terms, source_filters, filename_filter,
               extension_filter, relationship_filter, pool_filter):
    """
    Perform full-text search using FTS5 and apply filters.
    Returns results ranked by relevance.

    Uses exact token matching with FTS5's caret (^) prefix operator
    to ensure "holo" doesn't match "hololive".

    For freetext terms, also uses filepath LIKE matching to catch
    substring matches that FTS tokenization might miss (e.g., hashes).
    """
    from database import get_db_connection

    # Build FTS5 query
    fts_query_parts = []
    freetext_filepath_terms = []  # Terms to search as substrings in filepath

    # Check which terms are exact tags vs freetext
    with get_db_connection() as conn:
        # Add positive terms
        for term in general_terms:
            # Remove quotes for FTS query
            clean_term = term.strip('"').lower()

            # Check if this is an exact tag
            result = conn.execute(
                "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1",
                (clean_term,)
            ).fetchone()

            # Escape special FTS5 characters
            clean_term_escaped = clean_term.replace('"', '""')

            if result:
                # Exact tag - use prefix match operator to ensure whole word
                # In FTS5, ^term means "token starts with", but we want exact
                # So we'll use quotes and rely on tokenization
                fts_query_parts.append(f'^"{clean_term_escaped}"')
            else:
                # Freetext term - use wildcard for prefix matching
                # This allows "fellini" to match "pulchra_fellini"
                fts_query_parts.append(f'{clean_term_escaped}*')
                # Also track for filepath substring matching
                freetext_filepath_terms.append(clean_term)

        # Add negative terms
        for term in negative_terms:
            clean_term = term.lower().replace('"', '""')
            fts_query_parts.append(f'NOT "{clean_term}"')

    fts_query = ' '.join(fts_query_parts)

    with get_db_connection() as conn:
        # For freetext terms, we'll use a simpler approach: LEFT JOIN with FTS
        # and rely on post-filtering for comprehensive matching
        if freetext_filepath_terms:
            # Use LEFT JOIN so we can include results that only match filepath
            sql_parts = ["""
                SELECT i.id, i.filepath,
                       COALESCE(i.tags_character, '') || ' ' ||
                       COALESCE(i.tags_copyright, '') || ' ' ||
                       COALESCE(i.tags_artist, '') || ' ' ||
                       COALESCE(i.tags_species, '') || ' ' ||
                       COALESCE(i.tags_meta, '') || ' ' ||
                       COALESCE(i.tags_general, '') as tags,
                       COALESCE(fts.rank, 0) as rank
                FROM images i
                LEFT JOIN images_fts fts ON i.filepath = fts.filepath
            """]
        else:
            # Regular FTS search with INNER JOIN
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

        # Add FTS match condition (only for non-freetext or as one option)
        if fts_query and not freetext_filepath_terms:
            where_clauses.append("images_fts MATCH ?")
            params.append(fts_query)
        elif fts_query and freetext_filepath_terms:
            # Build OR condition: FTS match OR filepath substring
            fts_or_conditions = ["fts.filepath IN (SELECT filepath FROM images_fts WHERE images_fts MATCH ?)"]
            params.append(fts_query)

            for term in freetext_filepath_terms:
                fts_or_conditions.append("LOWER(i.filepath) LIKE ?")
                params.append(f"%{term}%")

            where_clauses.append(f"({' OR '.join(fts_or_conditions)})")

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

            # Post-filter for exact tag matching
            # Check which search terms are exact tags
            exact_tag_terms = []
            freetext_terms = []

            for term in general_terms:
                clean_term = term.strip('"').lower()
                result = conn.execute(
                    "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1",
                    (clean_term,)
                ).fetchone()

                if result:
                    exact_tag_terms.append(clean_term)
                else:
                    freetext_terms.append(clean_term)

            results = []
            for row in rows:
                tags_str = row['tags'].lower()
                tag_list = set(tags_str.split())
                filepath_lower = row['filepath'].lower()

                # Check exact tags first
                match = True
                for term in exact_tag_terms:
                    # Must be exact tag match (not substring in filepath)
                    if term not in tag_list:
                        match = False
                        break

                # Check freetext terms (can match as substring in tags or filepath)
                if match:
                    for term in freetext_terms:
                        # Check for substring match in tags OR filepath
                        if term not in tags_str and term not in filepath_lower:
                            match = False
                            break

                if match:
                    results.append({
                        'filepath': row['filepath'],
                        'tags': row['tags']
                    })

            return results
        except Exception as e:
            print(f"FTS search error: {e}")
            import traceback
            traceback.print_exc()
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
    metadata_filter = None
    category_filters = {}  # {category: [tags]}
    general_terms = []
    negative_terms = []
    freetext_mode = False

    # Valid tag categories
    valid_categories = ['character', 'copyright', 'artist', 'species', 'meta', 'general']

    for token in tokens:
        if token.startswith('source:'):
            source_filters.append(token.split(':', 1)[1].strip())
        elif token.startswith('filename:'):
            filename_filter = token.split(':', 1)[1].strip()
        elif token.startswith('pool:'):
            pool_filter = token.split(':', 1)[1].strip()
        elif token.startswith('metadata:'):
            metadata_filter = token.split(':', 1)[1].strip()
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
        elif ':' in token:
            # Check if it's a category filter (e.g., character:holo)
            parts = token.split(':', 1)
            category = parts[0]
            tag = parts[1]
            if category in valid_categories and tag:
                if category not in category_filters:
                    category_filters[category] = []
                category_filters[category].append(tag)
            else:
                # Not a valid category, treat as general term
                general_terms.append(token)
        else:
            general_terms.append(token)
    
    # Decide whether to use FTS5 or tag-based search
    # Don't use FTS for very short terms or terms with underscores in the middle (infix matches)
    use_fts = freetext_mode or (general_terms and _should_use_fts(general_terms))

    # If any general term looks like an infix search (contains _ in middle or very short),
    # disable FTS and use LIKE-based search for better substring matching
    if use_fts and general_terms:
        for term in general_terms:
            # Skip if term is very short (< 3 chars) or looks like infix (has _ but not at start/end)
            if len(term) < 3 or ('_' in term.strip('_')):
                use_fts = False
                break

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

        if metadata_filter:
            # Handle metadata:missing - images that don't have any source data
            if metadata_filter == 'missing':
                with get_db_connection() as conn:
                    # Get images that have no source records or only local_tagger
                    # Need to join through images table to get image_id
                    local_tagger_id = conn.execute("SELECT id FROM sources WHERE name = 'local_tagger'").fetchone()
                    local_tagger_id = local_tagger_id[0] if local_tagger_id else None

                    filtered_results = []
                    for img in results:
                        # Get image_id for this filepath
                        img_row = conn.execute("SELECT id FROM images WHERE filepath = ?", (img['filepath'],)).fetchone()
                        if not img_row:
                            continue

                        image_id = img_row[0]

                        # Check if image has any sources other than local_tagger
                        has_other_sources = conn.execute(
                            "SELECT 1 FROM image_sources WHERE image_id = ? AND source_id != ? LIMIT 1",
                            (image_id, local_tagger_id)
                        ).fetchone() if local_tagger_id else conn.execute(
                            "SELECT 1 FROM image_sources WHERE image_id = ? LIMIT 1",
                            (image_id,)
                        ).fetchone()

                        if not has_other_sources:
                            filtered_results.append(img)

                    results = filtered_results

        # Apply category filters (e.g., character:holo)
        if category_filters:
            with get_db_connection() as conn:
                filtered_results = []
                for img in results:
                    match = True

                    # Check each category filter
                    for category, required_tags in category_filters.items():
                        # Get the specific category column from database
                        cursor = conn.execute(
                            f"SELECT tags_{category} FROM images WHERE filepath = ?",
                            (img['filepath'],)
                        )
                        row = cursor.fetchone()

                        if row:
                            category_tags = set((row[f'tags_{category}'] or '').lower().split())

                            # All tags in this category must match
                            for tag in required_tags:
                                if tag not in category_tags:
                                    match = False
                                    break

                        if not match:
                            break

                    if match:
                        filtered_results.append(img)

                results = filtered_results

        # Now, apply the general search terms to the already filtered results
        if general_terms:
            filtered_results = []
            for img in results:
                # Get tag list and filepath for matching
                tags_str = img.get('tags', '').lower()
                tag_list = set(tags_str.split())
                filepath_lower = img.get('filepath', '').lower()

                # Check if ALL general terms match
                match = True
                for term in general_terms:
                    # Check exact tag match OR substring match in tags OR filepath substring
                    if term not in tag_list and term not in tags_str and term not in filepath_lower:
                        match = False
                        break

                if match:
                    filtered_results.append(img)
            results = filtered_results

        # Apply negative terms (exact tag matching)
        if negative_terms:
            filtered_results = []
            for img in results:
                tags_str = img.get('tags', '').lower()
                tag_list = set(tags_str.split())
                filepath_lower = img.get('filepath', '').lower()

                # Exclude if any negative term matches (exact tag OR filepath substring)
                exclude = False
                for term in negative_terms:
                    if term in tag_list or term in filepath_lower:
                        exclude = True
                        break

                if not exclude:
                    filtered_results.append(img)
            results = filtered_results

        should_shuffle = bool(general_terms) and not (source_filters or filename_filter or extension_filter)

    return results, should_shuffle

@lru_cache(maxsize=10000)
def find_related_by_tags(filepath, limit=20):
    """
    Find related images by weighted tag similarity using efficient database queries.

    Uses SQL JOIN to only fetch candidates that share at least one tag,
    drastically reducing the number of similarity calculations needed.
    """
    from database import get_db_connection

    details = models.get_image_details(filepath.replace("images/", "", 1))
    if not details:
        return []

    ref_tags_str = details.get('tags_general', '') or details.get('all_tags', '')
    if not ref_tags_str:
        return []

    # Get the reference image's ID for exclusion
    image_id = details.get('id')
    if not image_id:
        return []

    # Strategy: Only calculate similarity for images that share at least one tag
    # This dramatically reduces the search space from O(N) to O(M) where M << N
    with get_db_connection() as conn:
        query = """
        SELECT DISTINCT i.filepath,
               COALESCE(i.tags_character, '') || ' ' ||
               COALESCE(i.tags_copyright, '') || ' ' ||
               COALESCE(i.tags_artist, '') || ' ' ||
               COALESCE(i.tags_species, '') || ' ' ||
               COALESCE(i.tags_meta, '') || ' ' ||
               COALESCE(i.tags_general, '') as tags
        FROM images i
        INNER JOIN image_tags it ON i.id = it.image_id
        WHERE it.tag_id IN (
            SELECT tag_id FROM image_tags WHERE image_id = ?
        )
        AND i.id != ?
        LIMIT 500
        """
        cursor = conn.execute(query, (image_id, image_id))
        candidates = cursor.fetchall()

    # Calculate similarity only for candidates (images that share tags)
    similarities = []
    for row in candidates:
        sim = calculate_similarity(ref_tags_str, row['tags'])
        if sim > 0.1:
            similarities.append({
                'path': f"images/{row['filepath']}",
                'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
                'match_type': 'similar',
                'score': sim
            })

    similarities.sort(key=lambda x: x['score'], reverse=True)
    return similarities[:limit]
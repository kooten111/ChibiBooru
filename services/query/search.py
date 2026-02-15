"""Full-text search and tag-based search implementation."""

import re
from database import models, get_db_connection
from repositories import favourites_repository
from .similarity import calculate_similarity


def _should_use_fts(general_terms):
    """
    Determine if we should use FTS5 instead of exact tag matching.

    Returns True if FTS should be used (when any term is NOT an exact tag).
    Returns False if all terms are exact tags (use fast tag-based search).
    """
    if not general_terms:
        return False

    with get_db_connection() as conn:
        for term in general_terms:
            clean_term = term.strip('"').lower()
            result = conn.execute(
                "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1", (clean_term,)
            ).fetchone()

            if not result:
                return True

    return False


def _build_fts_query(conn, general_terms, negative_terms):
    """
    Build FTS5 query string and identify freetext terms that need filepath matching.

    Returns:
        Tuple of (fts_query_string, freetext_filepath_terms)
    """
    fts_query_parts = []
    freetext_filepath_terms = []

    for term in general_terms:
        clean_term = term.strip('"').lower()
        result = conn.execute(
            "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1", (clean_term,)
        ).fetchone()

        clean_term_escaped = clean_term.replace('"', '""')
        filepath_fts_safe = (
            clean_term_escaped.replace('"', "") if ":" not in clean_term else ""
        )

        if result:
            freetext_filepath_terms.append(clean_term)
            part = f'^"{clean_term_escaped}"'
            if filepath_fts_safe:
                part = f"({part} OR filepath:{filepath_fts_safe}*)"
            fts_query_parts.append(part)
        else:
            freetext_filepath_terms.append(clean_term)
            if (
                "-" not in clean_term
                and not any(c in clean_term for c in [":", "(", ")", "{", "}", "[", "]"])
            ):
                part = f"{clean_term_escaped}*"
                if filepath_fts_safe:
                    part = f"({part} OR filepath:{filepath_fts_safe}*)"
                fts_query_parts.append(part)

    for term in negative_terms:
        clean_term = term.lower().replace('"', '""')
        fts_query_parts.append(f'NOT "{clean_term}"')

    fts_query = " ".join(fts_query_parts)
    return fts_query, freetext_filepath_terms


def _build_base_sql_query(freetext_filepath_terms):
    """Build the base SQL query with appropriate joins for FTS search."""
    if freetext_filepath_terms:
        return [
            """
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
        """
        ]
    return [
        """
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
    """
    ]


def _apply_filters(
    sql_parts,
    where_clauses,
    params,
    fts_query,
    freetext_filepath_terms,
    pool_filter,
    relationship_filter,
    source_filters,
    extension_filters,
    filename_filter,
    upscaled_filter,
    upscaled_filter_exclude,
):
    """Apply filters to the SQL query by adding WHERE clauses and JOINs."""
    tag_columns = [
        "tags_general",
        "tags_character",
        "tags_copyright",
        "tags_artist",
        "tags_species",
        "tags_meta",
    ]

    if fts_query and not freetext_filepath_terms:
        where_clauses.append("images_fts MATCH ?")
        params.append(fts_query)
    elif fts_query and freetext_filepath_terms:
        # Match FTS OR (filepath LIKE OR tag columns LIKE)
        or_conditions = []
        fts_subquery = "fts.filepath IN (SELECT filepath FROM images_fts WHERE images_fts MATCH ?)"
        or_conditions.append(fts_subquery)
        params.append(fts_query)

        term_conditions = []
        for term in freetext_filepath_terms:
            term_param = f"%{term}%"
            # Filepath match
            sub_conds = ["LOWER(i.filepath) LIKE ?"]
            params.append(term_param)

            # Tag columns match
            for col in tag_columns:
                sub_conds.append(f"COALESCE(i.{col}, '') LIKE ?")
                params.append(term_param)

            term_conditions.append("(" + " OR ".join(sub_conds) + ")")

        # Combine all term conditions with AND (must match all terms in some way)
        combined_term_condition = " AND ".join(term_conditions)
        or_conditions.append(combined_term_condition)

        where_clauses.append(f"({' OR '.join(or_conditions)})")

    elif freetext_filepath_terms:
        # No FTS, just freetext matching
        for term in freetext_filepath_terms:
            term_param = f"%{term}%"
            sub_conds = ["LOWER(i.filepath) LIKE ?"]
            params.append(term_param)

            for col in tag_columns:
                sub_conds.append(f"COALESCE(i.{col}, '') LIKE ?")
                params.append(term_param)

            where_clauses.append("(" + " OR ".join(sub_conds) + ")")

    if pool_filter:
        sql_parts[0] += """
            INNER JOIN pool_images pi ON i.id = pi.image_id
            INNER JOIN pools p ON pi.pool_id = p.id
        """
        if pool_filter != "_ANY_":
            where_clauses.append("LOWER(p.name) LIKE ?")
            params.append(f"%{pool_filter}%")

    if relationship_filter:
        if relationship_filter == "parent":
            where_clauses.append("i.parent_id IS NOT NULL")
        elif relationship_filter == "child":
            where_clauses.append("i.has_children = 1")
        elif relationship_filter == "any":
            where_clauses.append("(i.parent_id IS NOT NULL OR i.has_children = 1)")

    if source_filters:
        placeholders = ",".join(["?"] * len(source_filters))
        sql_parts[0] += f"""
            INNER JOIN image_sources isrc ON i.id = isrc.image_id
            INNER JOIN sources s ON isrc.source_id = s.id
        """
        where_clauses.append(f"s.name IN ({placeholders})")
        params.extend(source_filters)

    if extension_filters:
        extension_conditions = []
        for ext in extension_filters:
            extension_conditions.append("LOWER(i.filepath) LIKE ?")
            params.append(f"%.{ext}")
        where_clauses.append("(" + " OR ".join(extension_conditions) + ")")

    if filename_filter:
        where_clauses.append("LOWER(i.filepath) LIKE ?")
        params.append(f"%{filename_filter}%")

    if upscaled_filter_exclude:
        where_clauses.append("i.upscaled_width IS NULL AND i.upscaled_height IS NULL")
    elif upscaled_filter:
        where_clauses.append("i.upscaled_width IS NOT NULL AND i.upscaled_height IS NOT NULL")


def _post_filter_results(conn, rows, general_terms):
    """Post-filter results for exact tag matching."""
    exact_tag_terms = []
    freetext_terms = []

    for term in general_terms:
        clean_term = term.strip('"').lower()
        result = conn.execute(
            "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1", (clean_term,)
        ).fetchone()

        if result:
            exact_tag_terms.append(clean_term)
        else:
            freetext_terms.append(clean_term)

    results = []
    for row in rows:
        tags_str = row["tags"].lower()
        tag_list = set(tags_str.split())
        filepath_lower = row["filepath"].lower()

        match = True
        for term in exact_tag_terms:
            if term not in tag_list:
                match = False
                break

        if match:
            for term in freetext_terms:
                if term not in tags_str and term not in filepath_lower:
                    match = False
                    break

        if match:
            results.append({"filepath": row["filepath"], "tags": row["tags"]})

    return results


def _apply_ordering(conn, results, order_filter):
    """Apply ordering to search results."""
    if not order_filter:
        return results

    # Optimize by fetching all ordering data in a single query instead of N queries
    filepaths = [img["filepath"] for img in results if img]
    if not filepaths:
        return results
    
    if order_filter in ["score_desc", "score", "score_asc", "fav_desc", "fav", "fav_asc"]:
        # Fetch all score/fav data in one query
        placeholders = ",".join("?" * len(filepaths))
        query = f"SELECT filepath, score, fav_count FROM images WHERE filepath IN ({placeholders})"
        rows = conn.execute(query, filepaths).fetchall()
        
        filepath_to_value = {}
        for row in rows:
            if "score" in order_filter:
                filepath_to_value[row["filepath"]] = (
                    row["score"] if row["score"] is not None else -999999
                )
            else:
                filepath_to_value[row["filepath"]] = (
                    row["fav_count"] if row["fav_count"] is not None else -999999
                )
        
        # Set default for any missing filepaths
        for filepath in filepaths:
            if filepath not in filepath_to_value:
                filepath_to_value[filepath] = -999999

        reverse = not order_filter.endswith("_asc")
        return sorted(
            results,
            key=lambda x: filepath_to_value.get(x["filepath"], -999999),
            reverse=reverse,
        )

    if order_filter in ["new", "ingested", "newest", "recent"]:
        # Fetch all ingestion timestamps in one query
        placeholders = ",".join("?" * len(filepaths))
        query = f"SELECT filepath, ingested_at FROM images WHERE filepath IN ({placeholders})"
        rows = conn.execute(query, filepaths).fetchall()
        
        filepath_to_timestamp = {}
        for row in rows:
            if row["ingested_at"]:
                filepath_to_timestamp[row["filepath"]] = row["ingested_at"]
            else:
                filepath_to_timestamp[row["filepath"]] = "0000-00-00 00:00:00"
        
        # Set default for any missing filepaths
        for filepath in filepaths:
            if filepath not in filepath_to_timestamp:
                filepath_to_timestamp[filepath] = "0000-00-00 00:00:00"

        return sorted(
            results,
            key=lambda x: filepath_to_timestamp.get(x["filepath"], "0000-00-00 00:00:00"),
            reverse=True,
        )

    if order_filter in ["old", "oldest"]:
        # Fetch all ingestion timestamps in one query
        placeholders = ",".join("?" * len(filepaths))
        query = f"SELECT filepath, ingested_at FROM images WHERE filepath IN ({placeholders})"
        rows = conn.execute(query, filepaths).fetchall()
        
        filepath_to_timestamp = {}
        for row in rows:
            if row["ingested_at"]:
                filepath_to_timestamp[row["filepath"]] = row["ingested_at"]
            else:
                filepath_to_timestamp[row["filepath"]] = "9999-12-31 23:59:59"
        
        # Set default for any missing filepaths
        for filepath in filepaths:
            if filepath not in filepath_to_timestamp:
                filepath_to_timestamp[filepath] = "9999-12-31 23:59:59"

        return sorted(
            results,
            key=lambda x: filepath_to_timestamp.get(x["filepath"], "9999-12-31 23:59:59"),
        )

    return results


def _fts_search(
    general_terms,
    negative_terms,
    source_filters,
    filename_filter,
    extension_filters,
    relationship_filter,
    pool_filter,
    upscaled_filter,
    upscaled_filter_exclude,
    order_filter=None,
):
    """Perform full-text search using FTS5 and apply filters."""
    # print(f"DEBUG: _fts_search start. Terms: {general_terms}")
    with get_db_connection() as conn:
        fts_query, freetext_filepath_terms = _build_fts_query(
            conn, general_terms, negative_terms
        )
    # print(f"DEBUG: FTS Query built: {fts_query}, FreeText: {freetext_filepath_terms}")

    cte_parts = []
    params = []

    # Part 1: FTS Search (Prefix/Exact)
    if fts_query:
        cte_parts.append("SELECT filepath, rank FROM images_fts WHERE images_fts MATCH ?")
        params.append(fts_query)

    # Part 2: Substring Search (Partial matches on all tag columns)
    if freetext_filepath_terms:
        likes = []
        tag_columns = [
            "tags_general",
            "tags_character",
            "tags_copyright",
            "tags_artist",
            "tags_species",
            "tags_meta",
        ]
        
        for term in freetext_filepath_terms:
            term_param = f"%{term}%"
            # Filepath match
            likes.append("LOWER(filepath) LIKE ?")
            params.append(term_param)
            
            # Tag columns match
            for col in tag_columns:
                likes.append(f"COALESCE({col}, '') LIKE ?")
                params.append(term_param)
        
        if likes:
            like_clause = " OR ".join(likes)
            # Use 0 as rank for these results (lower priority than FTS exact matches)
            cte_parts.append(f"SELECT filepath, 0 as rank FROM images WHERE {like_clause}")

    if not cte_parts:
        return []

    cte_sql = " UNION ".join(cte_parts)

    sql_parts = [f"""
    WITH matches AS (
        {cte_sql}
    )
    SELECT i.id, i.filepath,
           COALESCE(i.tags_character, '') || ' ' ||
           COALESCE(i.tags_copyright, '') || ' ' ||
           COALESCE(i.tags_artist, '') || ' ' ||
           COALESCE(i.tags_species, '') || ' ' ||
           COALESCE(i.tags_meta, '') || ' ' ||
           COALESCE(i.tags_general, '') as tags,
           matches.rank
    FROM matches
    JOIN images i ON matches.filepath = i.filepath
    """]
    
    where_clauses = []
    
    # We pass None for text filters because we handled them in the CTE
    _apply_filters(
        sql_parts,
        where_clauses,
        params,
        None, # fts_query handled in CTE
        None, # freetext_filepath_terms handled in CTE
        pool_filter,
        relationship_filter,
        source_filters,
        extension_filters,
        filename_filter,
        upscaled_filter,
        upscaled_filter_exclude,
    )

    if where_clauses:
        sql_parts.append("WHERE " + " AND ".join(where_clauses))

    sql_parts.append("ORDER BY rank")
    full_query = "\n".join(sql_parts)

    # print("DEBUG: Executing SQL query...")
    with get_db_connection() as conn:
        try:
            cursor = conn.execute(full_query, params)
            rows = cursor.fetchall()
            # print(f"DEBUG: SQL returned {len(rows)} rows.")

            results = _post_filter_results(conn, rows, general_terms)
            # print(f"DEBUG: Post-filter returned {len(results)} results.")
            results = _apply_ordering(conn, results, order_filter)

            return results
        except Exception as e:
            print(f"FTS search error: {e}")
            import traceback

            traceback.print_exc()
            return []


def _simple_filter_query_with_ordering(order_filter):
    """
    Optimized query for simple order-only searches (e.g., 'order:new').
    Returns all images with tags, efficiently ordered by the database.
    """
    with get_db_connection() as conn:
        # Build ORDER BY clause
        order_clause = "ORDER BY i.id"
        if order_filter in ["new", "ingested", "newest", "recent"]:
            order_clause = "ORDER BY i.ingested_at DESC"
        elif order_filter in ["old", "oldest"]:
            order_clause = "ORDER BY i.ingested_at ASC"
        elif order_filter in ["score", "score_desc"]:
            order_clause = "ORDER BY i.score DESC NULLS LAST"
        elif order_filter == "score_asc":
            order_clause = "ORDER BY i.score ASC NULLS LAST"
        elif order_filter in ["fav", "fav_desc"]:
            order_clause = "ORDER BY i.fav_count DESC NULLS LAST"
        elif order_filter == "fav_asc":
            order_clause = "ORDER BY i.fav_count ASC NULLS LAST"
        
        query = f"""
        SELECT i.filepath, COALESCE(GROUP_CONCAT(t.name, ' '), '') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        GROUP BY i.id
        {order_clause}
        """
        return [dict(row) for row in conn.execute(query).fetchall()]


def perform_search(search_query):
    """Perform a search using data from the database, handling special queries and combinations."""
    print(f"DEBUG: Perform Search with query '{search_query}'")
    if not search_query:
        return models.get_all_images_with_tags(), True

    tokens = search_query.lower().split()
    source_filters = []
    filename_filter = None
    extension_filters = []
    relationship_filter = None
    pool_filter = None
    metadata_filter = None
    order_filter = None
    favourite_filter = False
    upscaled_filter = False
    upscaled_filter_exclude = False
    category_filters = {}
    general_terms = []
    negative_terms = []
    freetext_mode = False

    valid_categories = ["character", "copyright", "artist", "species", "meta", "general"]

    for token in tokens:
        if token.startswith("source:"):
            source_filters.append(token.split(":", 1)[1].strip())
        elif token.startswith("filename:"):
            filename_filter = token.split(":", 1)[1].strip()
        elif token.startswith("pool:"):
            pool_filter = token.split(":", 1)[1].strip()
        elif token.startswith("metadata:"):
            metadata_filter = token.split(":", 1)[1].strip()
        elif token.startswith("order:"):
            order_filter = token.split(":", 1)[1].strip()
        elif token.startswith("."):
            extension_filters.append(token[1:])
        elif token.startswith("has:"):
            rel_type = token.split(":", 1)[1].strip()
            if rel_type in ["parent", "child", "relationship"]:
                relationship_filter = "any" if rel_type == "relationship" else rel_type
            elif rel_type == "pool":
                pool_filter = "_ANY_"
            elif rel_type in ["upscaled", "upscale"]:
                upscaled_filter = True
            elif rel_type == "video":
                extension_filters.extend(["mp4", "webm"])
        elif token.startswith("-has:"):
            rel_type = token.split(":", 1)[1].strip()
            if rel_type in ["upscaled", "upscale"]:
                upscaled_filter_exclude = True
        elif token.startswith("is:"):
            is_type = token.split(":", 1)[1].strip()
            if is_type in ["favourite", "favorite", "fav"]:
                favourite_filter = True
        elif token.startswith("-"):
            negative_terms.append(token[1:])
        elif token.startswith('"') or (
            general_terms
            and general_terms[-1].startswith('"')
            and not general_terms[-1].endswith('"')
        ):
            freetext_mode = True
            general_terms.append(token)
        elif ":" in token:
            if token.startswith("rating:"):
                general_terms.append(token)
            else:
                parts = token.split(":", 1)
                category = parts[0]
                tag = parts[1]
                if category in valid_categories and tag:
                    if category not in category_filters:
                        category_filters[category] = []
                    category_filters[category].append(tag)
                else:
                    general_terms.append(token)
        else:
            general_terms.append(token)

    # Normalize rating tags and extract them
    print(f"DEBUG: General terms before normalization: {general_terms}")
    normalized_general_terms = []
    rating_terms = []

    for term in general_terms:
        if term.startswith("rating_"):
            term = term.replace("rating_", "rating:", 1)
        if term.startswith("general:rating_") or term.startswith("meta:rating_"):
            parts = term.split(":", 1)
            if len(parts) == 2:
                term = parts[1].replace("rating_", "rating:", 1)
        
        if term.startswith("rating:"):
            rating_terms.append(term)
        else:
            normalized_general_terms.append(term)
            
    general_terms = normalized_general_terms
    print(f"DEBUG: Rating terms: {rating_terms}, General terms: {general_terms}")

    for category in category_filters:
        normalized_tags = []
        for tag in category_filters[category]:
            if tag.startswith("rating_"):
                tag = tag.replace("rating_", "rating:", 1)
            normalized_tags.append(tag)
        category_filters[category] = normalized_tags

    use_fts = freetext_mode or (general_terms and _should_use_fts(general_terms))
    
    # Check if all general terms are exact tags (for non-FTS path)
    are_all_tags = general_terms and not _should_use_fts(general_terms)
    
    # Check if we have a simple filter-only query (no search terms, just filters)
    has_search_terms = general_terms or rating_terms or category_filters or negative_terms
    has_filters = (source_filters or filename_filter or extension_filters or 
                   relationship_filter or pool_filter or metadata_filter or 
                   favourite_filter or upscaled_filter or upscaled_filter_exclude)
    
    # Optimize simple order-only queries (e.g., "order:new" with no search terms or other filters)
    is_simple_order_query = (
        order_filter
        and not has_search_terms
        and not has_filters
    )
    
    # Optimize simple filter queries (e.g., "has:parent" or "source:danbooru" alone)
    # These can query directly for matching images instead of fetching all 19k then filtering
    is_simple_filter_query = (
        not has_search_terms
        and has_filters
        and not metadata_filter  # metadata filter logic is complex, keep it in regular path
    )
    
    if is_simple_order_query:
        # Use optimized query that does ordering in SQL
        results = _simple_filter_query_with_ordering(order_filter)
        should_shuffle = False
    elif is_simple_filter_query:
        # Start with a minimal base query - just filepaths, we'll add tags later if needed
        with get_db_connection() as conn:
            where_clauses = []
            params = []
            
            if relationship_filter:
                if relationship_filter == "parent":
                    where_clauses.append("i.parent_id IS NOT NULL")
                elif relationship_filter == "child":
                    where_clauses.append("i.has_children = 1")
                elif relationship_filter == "any":
                    where_clauses.append("(i.parent_id IS NOT NULL OR i.has_children = 1)")
            
            if upscaled_filter_exclude:
                where_clauses.append("i.upscaled_width IS NULL AND i.upscaled_height IS NULL")
            elif upscaled_filter:
                where_clauses.append("i.upscaled_width IS NOT NULL AND i.upscaled_height IS NOT NULL")
            
            joins = []
            
            if pool_filter:
                joins.append("INNER JOIN pool_images pi ON i.id = pi.image_id")
                joins.append("INNER JOIN pools p ON pi.pool_id = p.id")
                if pool_filter != "_ANY_":
                    where_clauses.append("LOWER(p.name) LIKE ?")
                    params.append(f"%{pool_filter}%")
            
            if source_filters:
                placeholders = ",".join(["?"] * len(source_filters))
                joins.append("INNER JOIN image_sources isrc ON i.id = isrc.image_id")
                joins.append("INNER JOIN sources s ON isrc.source_id = s.id")
                where_clauses.append(f"s.name IN ({placeholders})")
                params.extend(source_filters)
            
            if extension_filters:
                ext_conditions = []
                for ext in extension_filters:
                    ext_conditions.append("LOWER(i.filepath) LIKE ?")
                    params.append(f"%.{ext}")
                where_clauses.append("(" + " OR ".join(ext_conditions) + ")")
            
            if filename_filter:
                where_clauses.append("LOWER(i.filepath) LIKE ?")
                params.append(f"%{filename_filter}%")
            
            # Build query
            join_clause = " ".join(joins)
            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Apply ordering if specified
            order_clause = "ORDER BY i.id"
            if order_filter in ["new", "ingested", "newest", "recent"]:
                order_clause = "ORDER BY i.ingested_at DESC"
            elif order_filter in ["old", "oldest"]:
                order_clause = "ORDER BY i.ingested_at ASC"
            elif order_filter in ["score", "score_desc"]:
                order_clause = "ORDER BY i.score DESC NULLS LAST"
            elif order_filter == "score_asc":
                order_clause = "ORDER BY i.score ASC NULLS LAST"
            elif order_filter in ["fav", "fav_desc"]:
                order_clause = "ORDER BY i.fav_count DESC NULLS LAST"
            elif order_filter == "fav_asc":
                order_clause = "ORDER BY i.fav_count ASC NULLS LAST"
            
            query = f"""
            SELECT DISTINCT i.filepath,
                   COALESCE(GROUP_CONCAT(t.name, ' '), '') as tags
            FROM images i
            {join_clause}
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            WHERE {where_clause}
            GROUP BY i.id
            {order_clause}
            """
            
            results = [dict(row) for row in conn.execute(query, params).fetchall()]
        
        # Apply favourite filter if needed (can't easily do in SQL)
        if favourite_filter:
            favourite_filepaths = favourites_repository.get_favourite_filepaths()
            results = [img for img in results if img["filepath"] in favourite_filepaths]
        
        should_shuffle = False
    elif use_fts and (general_terms or negative_terms):
        results = _fts_search(
            general_terms,
            negative_terms,
            source_filters,
            filename_filter,
            extension_filters,
            relationship_filter,
            pool_filter,
            upscaled_filter,
            upscaled_filter_exclude,
            order_filter,
        )
        should_shuffle = False
    else:
        # If we only have rating terms, we should search by them (if no general terms)
        if not general_terms and rating_terms:
             results = models.search_images_by_tags(rating_terms)
             should_shuffle = False
             # We can clear rating_terms since we used them for search
             rating_terms = []
        
        elif are_all_tags:
            results = models.search_images_by_tags(general_terms)
        else:
            results = models.get_all_images_with_tags()

        # ... (rest of filtering)


        if pool_filter:
            search_param = "" if pool_filter == "_ANY_" else pool_filter
            pool_images = models.search_images_by_pool(search_param)
            if pool_images:
                pool_filepaths = {img["filepath"] for img in pool_images}
                results = [
                    img for img in results if img and img["filepath"] in pool_filepaths
                ]
            else:
                results = []

        if relationship_filter:
            relationship_images = {
                img["filepath"]
                for img in models.search_images_by_relationship(relationship_filter)
            }
            results = [
                img for img in results if img and img["filepath"] in relationship_images
            ]

        if upscaled_filter or upscaled_filter_exclude:
            if upscaled_filter_exclude:
                query = "SELECT filepath FROM images WHERE upscaled_width IS NULL AND upscaled_height IS NULL"
            else:
                query = "SELECT filepath FROM images WHERE upscaled_width IS NOT NULL AND upscaled_height IS NOT NULL"

            with get_db_connection() as conn:
                upscaled_rows = conn.execute(query).fetchall()

            upscaled_filepaths = {row["filepath"] for row in upscaled_rows}
            results = [
                img for img in results if img and img["filepath"] in upscaled_filepaths
            ]

        if source_filters:
            source_images = models.search_images_by_multiple_sources(source_filters)
            source_filepaths = {img["filepath"] for img in source_images}
            results = [
                img for img in results if img and img["filepath"] in source_filepaths
            ]

        if extension_filters:
            results = [
                img
                for img in results
                if img
                and any(
                    img["filepath"].lower().endswith(f".{ext}")
                    for ext in extension_filters
                )
            ]

        if filename_filter:
            results = [
                img
                for img in results
                if img and filename_filter in img["filepath"].lower()
            ]

        if favourite_filter:
            favourite_filepaths = favourites_repository.get_favourite_filepaths()
            results = [
                img for img in results if img and img["filepath"] in favourite_filepaths
            ]

        if metadata_filter:
            if metadata_filter == "missing":
                with get_db_connection() as conn:
                    local_tagger_id = conn.execute(
                        "SELECT id FROM sources WHERE name = 'local_tagger'"
                    ).fetchone()
                    local_tagger_id = local_tagger_id[0] if local_tagger_id else None

                    # Bulk query - get all filepaths that have non-local_tagger sources
                    filepaths = [img["filepath"] for img in results if img]
                    if not filepaths:
                        results = []
                    else:
                        placeholders = ",".join("?" * len(filepaths))
                        if local_tagger_id:
                            query = f"""
                            SELECT DISTINCT i.filepath
                            FROM images i
                            JOIN image_sources isrc ON i.id = isrc.image_id
                            WHERE i.filepath IN ({placeholders})
                            AND isrc.source_id != ?
                            """
                            rows = conn.execute(query, (*filepaths, local_tagger_id)).fetchall()
                        else:
                            query = f"""
                            SELECT DISTINCT i.filepath
                            FROM images i
                            JOIN image_sources isrc ON i.id = isrc.image_id
                            WHERE i.filepath IN ({placeholders})
                            """
                            rows = conn.execute(query, filepaths).fetchall()
                        
                        has_sources = {row["filepath"] for row in rows}
                        # Keep only images WITHOUT other sources (missing metadata)
                        results = [img for img in results if img and img["filepath"] not in has_sources]

        if category_filters:
            with get_db_connection() as conn:
                # Bulk query - get all category tags for all filepaths in one query
                filepaths = [img["filepath"] for img in results if img]
                if not filepaths:
                    results = []
                else:
                    placeholders = ",".join("?" * len(filepaths))
                    
                    # Build SELECT for all needed category columns
                    category_cols = ", ".join([f"tags_{cat}" for cat in category_filters.keys()])
                    query = f"SELECT filepath, {category_cols} FROM images WHERE filepath IN ({placeholders})"
                    rows = conn.execute(query, filepaths).fetchall()
                    
                    # Build lookup dict: filepath -> {category: tags_set}
                    filepath_to_tags = {}
                    for row in rows:
                        filepath = row["filepath"]
                        filepath_to_tags[filepath] = {}
                        for category in category_filters.keys():
                            tags_str = row[f"tags_{category}"] or ""
                            filepath_to_tags[filepath][category] = set(tags_str.lower().split())
                    
                    # Filter results
                    filtered_results = []
                    for img in results:
                        if img is None:
                            continue
                        
                        filepath = img["filepath"]
                        if filepath not in filepath_to_tags:
                            continue
                        
                        match = True
                        for category, required_tags in category_filters.items():
                            category_tags = filepath_to_tags[filepath].get(category, set())
                            for tag in required_tags:
                                if tag not in category_tags:
                                    match = False
                                    break
                            if not match:
                                break
                        
                        if match:
                            filtered_results.append(img)
                    
                    results = filtered_results

        if general_terms:
            filtered_results = []
            for img in results:
                if img is None:
                    continue
                tags_str = (img.get("tags") or "").lower()
                tag_list = set(tags_str.split())
                filepath_lower = (img.get("filepath") or "").lower()

                match = True
                for term in general_terms:
                    if (
                        term not in tag_list
                        and term not in tags_str
                        and term not in filepath_lower
                    ):
                        match = False
                        break

                if match:
                    filtered_results.append(img)
            results = filtered_results

        if negative_terms:
            filtered_results = []
            for img in results:
                if img is None:
                    continue
                tags_str = (img.get("tags") or "").lower()
                tag_list = set(tags_str.split())
                filepath_lower = (img.get("filepath") or "").lower()

                exclude = False
                for term in negative_terms:
                    if term in tag_list or term in filepath_lower:
                        exclude = True
                        break

                if not exclude:
                    filtered_results.append(img)
            results = filtered_results

        should_shuffle = bool(general_terms) and not (
            source_filters or filename_filter or extension_filters
        )

    # Apply rating filter to both FTS and non-FTS paths
    if rating_terms:
        print(f"DEBUG: Filtering {len(results)} results by rating terms: {rating_terms}")
        with get_db_connection() as conn:
            # Bulk query - get all images that have ALL the required rating tags
            filepaths = [img["filepath"] for img in results if img]
            if not filepaths:
                results = []
            else:
                filepath_placeholders = ",".join("?" * len(filepaths))
                rating_placeholders = ",".join("?" * len(rating_terms))
                
                query = f"""
                SELECT i.filepath, COUNT(DISTINCT t.name) as tag_count
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                WHERE i.filepath IN ({filepath_placeholders})
                AND t.name IN ({rating_placeholders})
                GROUP BY i.filepath
                HAVING tag_count = ?
                """
                
                rows = conn.execute(query, (*filepaths, *rating_terms, len(rating_terms))).fetchall()
                matching_filepaths = {row["filepath"] for row in rows}
                
                results = [img for img in results if img and img["filepath"] in matching_filepaths]
        print(f"DEBUG: Results after rating filter: {len(results)}")

    if order_filter and order_filter in [
        "score_desc",
        "score",
        "score_asc",
        "fav_desc",
        "fav",
        "fav_asc",
    ]:
        with get_db_connection() as conn:
            results = _apply_ordering(conn, results, order_filter)
            should_shuffle = False
    elif order_filter and order_filter in ["new", "ingested", "newest", "recent"]:
        with get_db_connection() as conn:
            results = _apply_ordering(conn, results, order_filter)
            should_shuffle = False
    elif order_filter and order_filter in ["old", "oldest"]:
        with get_db_connection() as conn:
            results = _apply_ordering(conn, results, order_filter)
            should_shuffle = False

    return results, should_shuffle

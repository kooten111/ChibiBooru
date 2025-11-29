# models.py
import os
import json
import sqlite3
from tqdm import tqdm
from .core import get_db_connection
from functools import lru_cache

from core.cache_manager import (
    tag_counts,
    image_data,
    post_id_to_md5,
    data_lock,
    load_data_from_db,
    reload_single_image,
    remove_image_from_cache,
    get_image_data,
    get_tag_counts,
)

from repositories.tag_repository import (
    reload_tag_counts,
    get_all_tags_sorted,
    recategorize_misplaced_tags,
    rebuild_categorized_tags_from_relations,
    update_image_tags,
    update_image_tags_categorized,
    add_implication,
    get_implications_for_tag,
    apply_implications_for_image,
)

from repositories.data_access import (
    md5_exists,
    get_image_count,
    get_avg_tags_per_image,
    get_source_breakdown,
    get_category_counts,
    get_saucenao_lookup_count,
    get_all_images_with_tags,
    get_all_filepaths,
    get_image_details,
    delete_image,
    search_images_by_tags,
    search_images_by_source,
    search_images_by_multiple_sources,
    search_images_by_relationship,
    add_image_with_metadata,
)

def repopulate_from_database():
    """Rebuilds the tag and source relationships by reading from the raw_metadata table."""
    # Import config here to ensure it's loaded within the application context
    import config

    print("Repopulating database from 'raw_metadata' table...")
    with get_db_connection() as con:
        cur = con.cursor()

        # Clear existing tag and source relationships
        cur.execute("DELETE FROM image_tags")
        cur.execute("DELETE FROM image_sources")
        cur.execute("DELETE FROM tags")
        cur.execute("DELETE FROM sources")

        source_map = {}
        known_sources = ["danbooru", "e621", "pixiv", "gelbooru", "yandere", "local_tagger"]
        for source_name in known_sources:
            cur.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (source_name,))
            cur.execute("SELECT id FROM sources WHERE name = ?", (source_name,))
            source_map[source_name] = cur.fetchone()[0]

        # Get all raw metadata
        cur.execute("SELECT image_id, data FROM raw_metadata")
        all_metadata = cur.fetchall()

        for row in tqdm(all_metadata, desc="Rebuilding from DB Metadata"):
            image_id = row['image_id']
            try:
                metadata = json.loads(row['data'])
            except (json.JSONDecodeError, TypeError):
                continue

            available_sources = metadata.get('sources', {})

            # Check if we should use merged sources by default
            use_merged = config.USE_MERGED_SOURCES_BY_DEFAULT and len(available_sources) > 1

            if use_merged:
                # Use merged mode - import the merge function
                from services.switch_source_db import merge_all_sources
                # Get the image filepath
                cur.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
                filepath_row = cur.fetchone()
                if filepath_row:
                    # Commit current transaction before calling merge_all_sources
                    # to avoid database lock (merge_all_sources opens its own connection)
                    con.commit()
                    merge_all_sources(filepath_row['filepath'])
                continue

            # Original single-source logic
            primary_source_data = None
            source_name = None

            for src in config.BOORU_PRIORITY:
                if src in available_sources:
                    primary_source_data = available_sources[src]
                    source_name = src
                    break

            # Fallback if no priority source is found
            if not source_name and available_sources:
                source_name = next(iter(available_sources.keys()), None)
                primary_source_data = next(iter(available_sources.values()), {})


            if not primary_source_data:
                continue

            parent_id = primary_source_data.get('parent_id')
            if source_name == 'e621':
                parent_id = primary_source_data.get('relationships', {}).get('parent_id')

            cur.execute("""
                UPDATE images
                SET post_id = ?, parent_id = ?, has_children = ?, active_source = ?
                WHERE id = ?
            """, (
                primary_source_data.get("id"),
                parent_id,
                primary_source_data.get("has_children", False),
                source_name,
                image_id
            ))

            for src in metadata.get('sources', {}).keys():
                if src in source_map:
                    cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_map[src]))

            categorized_tags = {}
            if source_name == 'danbooru':
                categorized_tags = {
                    'character': primary_source_data.get("tag_string_character", "").split(),
                    'copyright': primary_source_data.get("tag_string_copyright", "").split(),
                    'artist': primary_source_data.get("tag_string_artist", "").split(),
                    'meta': primary_source_data.get("tag_string_meta", "").split(),
                    'general': primary_source_data.get("tag_string_general", "").split(),
                }
            elif source_name == 'e621':
                tags = primary_source_data.get("tags", {})
                categorized_tags = {
                    'character': tags.get("character", []), 'copyright': tags.get("copyright", []),
                    'artist': tags.get("artist", []), 'species': tags.get("species", []),
                    'meta': tags.get("meta", []), 'general': tags.get("general", [])
                }
            elif source_name == 'local_tagger' or source_name == 'camie_tagger':
                tags = primary_source_data.get("tags", {})
                categorized_tags = {
                    'character': tags.get("character", []),
                    'copyright': tags.get("copyright", []),
                    'artist': tags.get("artist", []),
                    'meta': tags.get("meta", []),
                    'general': tags.get("general", [])
                }

            for category, tags_list in categorized_tags.items():
                for tag_name in tags_list:
                    if not tag_name: continue

                    # Normalize tag name (e.g., rating_explicit -> rating:explicit)
                    from repositories.tag_repository import normalize_tag_name, get_tag_category
                    normalized_tag_name = normalize_tag_name(tag_name)

                    # Determine correct category (rating tags override category)
                    final_category = get_tag_category(normalized_tag_name) or category

                    cur.execute("INSERT INTO tags (name, category) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET category=excluded.category", (normalized_tag_name, final_category))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (normalized_tag_name,))
                    tag_id = cur.fetchone()['id']
                    cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

            # Extract and insert rating if present
            if 'rating' in primary_source_data:
                rating_char = primary_source_data.get('rating', '').lower()
                # Map single-letter ratings to full tag names
                rating_map = {
                    'g': 'rating:general',
                    's': 'rating:sensitive',
                    'q': 'rating:questionable',
                    'e': 'rating:explicit'
                }
                rating_tag = rating_map.get(rating_char)

                if rating_tag:
                    # Determine source trust level
                    if source_name in ['danbooru', 'e621']:
                        rating_source = 'original'  # Trusted source
                    elif source_name in ['local_tagger', 'camie_tagger']:
                        rating_source = 'ai_inference'  # Less trusted
                    else:
                        rating_source = 'original'  # Default

                    # Insert rating tag
                    cur.execute("INSERT INTO tags (name, category) VALUES (?, 'meta') ON CONFLICT(name) DO UPDATE SET category='meta'", (rating_tag,))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (rating_tag,))
                    tag_id = cur.fetchone()['id']
                    cur.execute("INSERT OR REPLACE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)", (image_id, tag_id, rating_source))

        con.commit()

    print("Repopulation complete.")
    recategorize_misplaced_tags()
    rebuild_categorized_tags_from_relations()

    # Apply tag deltas to restore manual modifications
    print("Applying tag deltas to restore manual modifications...")
    apply_tag_deltas()

    print("Database rebuild complete.")

@lru_cache(maxsize=10000)
def get_related_images(post_id, parent_id):
    """Find parent and child images using pre-computed cross-source mapping."""
    from repositories.data_access import get_related_images as _get_related_images
    return _get_related_images(post_id, parent_id, post_id_to_md5)



from repositories.pool_repository import (
    create_pool,
    get_all_pools,
    get_pool_details,
    add_image_to_pool,
    remove_image_from_pool,
    delete_pool,
    update_pool,
    reorder_pool_images,
    search_pools,
    get_pools_for_image,
    search_images_by_pool,
)


from repositories.delta_tracker import (
    record_tag_delta,
    compute_tag_deltas,
    apply_tag_deltas,
    get_image_deltas,
)
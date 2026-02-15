"""Collection statistics and related image search."""

from functools import lru_cache
from database import models
from utils import get_thumbnail_path
from .similarity import calculate_similarity


@lru_cache(maxsize=1)
def get_enhanced_stats():
    """Get detailed statistics about the collection from the database.
    
    Results are cached since stats change infrequently (only when images/tags are added/removed).
    Cache is invalidated via cache_manager when collection changes.
    """
    from core.tag_id_cache import get_tag_counts_as_dict

    tag_counts_by_id = models.get_tag_counts()
    tag_counts_by_name = get_tag_counts_as_dict()
    image_count = models.get_image_count()

    return {
        "total": image_count,
        "with_metadata": image_count,
        "without_metadata": 0,
        "total_tags": len(tag_counts_by_id),
        "avg_tags_per_image": models.get_avg_tags_per_image(),
        "source_breakdown": models.get_source_breakdown(),
        "top_tags": sorted(
            tag_counts_by_name.items(), key=lambda x: x[1], reverse=True
        )[:20],
        "category_counts": models.get_category_counts(),
        "saucenao_used": models.get_saucenao_lookup_count(),
        "local_tagger_used": models.get_source_breakdown().get("local_tagger", 0),
    }


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

    ref_tags_str = details.get("tags_general", "") or details.get("all_tags", "")
    if not ref_tags_str:
        return []

    image_id = details.get("id")
    if not image_id:
        return []

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

    similarities = []
    for row in candidates:
        sim = calculate_similarity(ref_tags_str, row["tags"])
        if sim > 0.1:
            similarities.append(
                {
                    "path": f"images/{row['filepath']}",
                    "thumb": get_thumbnail_path(f"images/{row['filepath']}"),
                    "match_type": "similar",
                    "score": sim,
                }
            )

    similarities.sort(key=lambda x: x["score"], reverse=True)
    return similarities[:limit]

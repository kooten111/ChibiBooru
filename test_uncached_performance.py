#!/usr/bin/env python3
"""
Test performance WITHOUT caching to measure actual query improvements.
"""

import time
from database import get_db_connection
from repositories.data_access import get_image_details, get_related_images
from core.cache_manager import post_id_to_md5
import config

# Disable caching for similarity search
import services.query_service as query_service

def calculate_similarity_uncached(tags1, tags2):
    """Calculate similarity without caching."""
    if config.SIMILARITY_METHOD == 'weighted':
        return query_service.calculate_weighted_similarity(tags1, tags2)
    else:
        return query_service.calculate_jaccard_similarity(tags1, tags2)

def find_related_by_tags_uncached(filepath, limit=20):
    """Test similarity search without @lru_cache."""
    from utils import get_thumbnail_path

    details_dict = None
    with get_db_connection() as conn:
        query = """
        SELECT
            i.*,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id) as all_tags,
            COALESCE(i.tags_character, '') || ' ' ||
            COALESCE(i.tags_copyright, '') || ' ' ||
            COALESCE(i.tags_artist, '') || ' ' ||
            COALESCE(i.tags_species, '') || ' ' ||
            COALESCE(i.tags_meta, '') || ' ' ||
            COALESCE(i.tags_general, '') as tags_general
        FROM images i
        WHERE i.filepath = ?
        """
        details = conn.execute(query, (filepath.replace("images/", "", 1),)).fetchone()
        if details:
            details_dict = dict(details)

    if not details_dict:
        return []

    ref_tags_str = details_dict.get('tags_general', '') or details_dict.get('all_tags', '')
    if not ref_tags_str:
        return []

    image_id = details_dict.get('id')
    if not image_id:
        return []

    # Use optimized query that only gets candidates
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
        sim = calculate_similarity_uncached(ref_tags_str, row['tags'])
        if sim > 0.1:
            similarities.append({
                'path': f"images/{row['filepath']}",
                'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
                'match_type': 'similar',
                'score': sim
            })

    similarities.sort(key=lambda x: x['score'], reverse=True)
    return similarities[:limit]

def main():
    print("=" * 70)
    print("Uncached Performance Test - Measuring Actual Query Speed")
    print("=" * 70)

    # Load the post_id mapping (this is needed for relationships)
    import models
    if not post_id_to_md5:
        print("\nLoading post_id_to_md5 mapping...")
        models.load_data_from_db()

    # Get a few test images
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT filepath, post_id, parent_id FROM images
            WHERE tags_general IS NOT NULL
            LIMIT 10
        """)
        test_images = [dict(row) for row in cursor.fetchall()]

    print(f"\nTesting with {len(test_images)} images")
    print("\n" + "=" * 70)

    # Test similarity search (uncached)
    print("\n=== Similarity Search (Uncached) ===")
    sim_times = []
    for img in test_images[:5]:
        start = time.time()
        results = find_related_by_tags_uncached(f"images/{img['filepath']}", limit=20)
        elapsed = (time.time() - start) * 1000
        sim_times.append(elapsed)
        print(f"  {img['filepath'][:50]:50s} -> {elapsed:6.2f}ms ({len(results)} results)")

    print(f"\n  Average: {sum(sim_times)/len(sim_times):.2f}ms")

    # Test parent/child lookup (uses get_related_images which is not cached if we pass different args)
    print("\n=== Parent/Child Lookup ===")
    rel_times = []
    for img in test_images[:5]:
        # Call get_related_images directly to bypass @lru_cache
        start = time.time()
        results = get_related_images(img['post_id'], img['parent_id'], post_id_to_md5)
        elapsed = (time.time() - start) * 1000
        rel_times.append(elapsed)
        print(f"  {img['filepath'][:50]:50s} -> {elapsed:6.2f}ms ({len(results)} results)")

    print(f"\n  Average: {sum(rel_times)/len(rel_times):.2f}ms")

    # Combined time
    print("\n=== Combined Page Load ===")
    total_times = []
    for i in range(5):
        total = sim_times[i] + rel_times[i]
        total_times.append(total)
        print(f"  Page {i+1}: {total:.2f}ms")

    avg_total = sum(total_times) / len(total_times)
    print(f"\n  Average total page load: {avg_total:.2f}ms")
    print(f"\n  Improvement from baseline (500-600ms): {((600 - avg_total) / 600 * 100):.1f}%")

    print("\n" + "=" * 70)
    print("Test complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()

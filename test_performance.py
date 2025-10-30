#!/usr/bin/env python3
"""
Performance test script to measure query optimization improvements.

Tests the two main bottlenecks:
1. find_related_by_tags (similarity search)
2. get_related_images (parent/child lookup)
"""

import time
import random
from database import get_db_connection
from services import query_service
import models

def test_similarity_search():
    """Test the similarity search performance."""
    print("\n=== Testing Similarity Search ===")

    # Get a random image with tags
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT filepath FROM images
            WHERE tags_general IS NOT NULL
            LIMIT 10
        """)
        test_images = [row['filepath'] for row in cursor.fetchall()]

    if not test_images:
        print("No images found for testing")
        return

    times = []
    for filepath in test_images[:5]:  # Test 5 images
        start = time.time()
        results = query_service.find_related_by_tags(f"images/{filepath}", limit=20)
        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)
        print(f"  Image: {filepath[:50]:50s} -> {elapsed:6.2f}ms ({len(results)} results)")

    avg_time = sum(times) / len(times) if times else 0
    print(f"\n  Average time: {avg_time:.2f}ms")
    print(f"  Min time: {min(times):.2f}ms")
    print(f"  Max time: {max(times):.2f}ms")

def test_parent_child_lookup():
    """Test the parent/child relationship lookup performance."""
    print("\n=== Testing Parent/Child Lookup ===")

    # Get images with relationships
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT post_id, parent_id, filepath FROM images
            WHERE (parent_id IS NOT NULL OR has_children = 1)
            LIMIT 10
        """)
        test_images = [dict(row) for row in cursor.fetchall()]

    if not test_images:
        print("No images with relationships found for testing")
        return

    # Ensure post_id_to_md5 mapping is loaded
    if not models.post_id_to_md5:
        print("Loading post_id_to_md5 mapping...")
        models.load_data_from_db()

    times = []
    for img in test_images[:5]:  # Test 5 images
        start = time.time()
        results = models.get_related_images(img['post_id'], img['parent_id'])
        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)
        print(f"  Image: {img['filepath'][:50]:50s} -> {elapsed:6.2f}ms ({len(results)} results)")

    avg_time = sum(times) / len(times) if times else 0
    print(f"\n  Average time: {avg_time:.2f}ms")
    print(f"  Min time: {min(times):.2f}ms")
    print(f"  Max time: {max(times):.2f}ms")

def test_full_page_load():
    """Test a full image page load (combining both queries)."""
    print("\n=== Testing Full Page Load (show_image route simulation) ===")

    # Get random images
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT filepath, post_id, parent_id FROM images
            WHERE tags_general IS NOT NULL
            LIMIT 10
        """)
        test_images = [dict(row) for row in cursor.fetchall()]

    if not test_images:
        print("No images found for testing")
        return

    # Ensure caches are loaded
    if not models.post_id_to_md5:
        print("Loading caches...")
        models.load_data_from_db()

    times = []
    for img in test_images[:5]:  # Test 5 full page loads
        filepath = img['filepath']
        start = time.time()

        # Simulate what show_image does
        data = models.get_image_details(filepath)
        similar = query_service.find_related_by_tags(f"images/{filepath}", limit=20)
        related = models.get_related_images(img['post_id'], img['parent_id'])

        elapsed = (time.time() - start) * 1000  # Convert to ms
        times.append(elapsed)
        print(f"  Page: {filepath[:50]:50s} -> {elapsed:6.2f}ms")

    avg_time = sum(times) / len(times) if times else 0
    print(f"\n  Average full page load: {avg_time:.2f}ms")
    print(f"  Min time: {min(times):.2f}ms")
    print(f"  Max time: {max(times):.2f}ms")
    print(f"\n  Target: <100ms for excellent, <200ms for good")

def main():
    print("=" * 70)
    print("Performance Test - Query Optimization")
    print("=" * 70)

    # Get database stats
    with get_db_connection() as conn:
        total_images = conn.execute("SELECT COUNT(*) as cnt FROM images").fetchone()['cnt']
        total_tags = conn.execute("SELECT COUNT(*) as cnt FROM tags").fetchone()['cnt']
        total_relationships = conn.execute(
            "SELECT COUNT(*) as cnt FROM images WHERE parent_id IS NOT NULL OR has_children = 1"
        ).fetchone()['cnt']

    print(f"\nDatabase Stats:")
    print(f"  Total Images: {total_images}")
    print(f"  Total Tags: {total_tags}")
    print(f"  Images with Relationships: {total_relationships}")

    # Run tests
    test_similarity_search()
    test_parent_child_lookup()
    test_full_page_load()

    print("\n" + "=" * 70)
    print("Performance test complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()

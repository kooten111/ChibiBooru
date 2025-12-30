#!/usr/bin/env python3
"""
Test script to verify tag ID cache reload functionality.
Tests that the cache properly reloads when tags are added/modified.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from database import get_db_connection
from core.tag_id_cache import get_tag_id_cache, reload_tag_id_cache
from core.cache_manager import invalidate_tag_cache, load_data_from_db

def test_tag_id_cache_reload():
    """Test that tag ID cache reloads correctly when tags are modified."""

    print("=" * 70)
    print("Testing Tag ID Cache Reload Functionality")
    print("=" * 70)

    if not config.TAG_ID_CACHE_ENABLED:
        print("\n⚠️  TAG_ID_CACHE_ENABLED is False - skipping test")
        return

    # Get initial cache state
    cache = get_tag_id_cache()
    initial_count = cache.get_tag_count()
    print(f"\n1. Initial tag count: {initial_count}")

    # Create a test tag
    test_tag_name = "test_cache_reload_tag_12345"
    print(f"\n2. Creating test tag: {test_tag_name}")

    with get_db_connection() as conn:
        # Check if test tag exists (cleanup from previous run)
        result = conn.execute("SELECT id FROM tags WHERE name = ?", (test_tag_name,)).fetchone()
        if result:
            print(f"   Cleaning up existing test tag...")
            conn.execute("DELETE FROM tags WHERE name = ?", (test_tag_name,))
            conn.commit()

        # Insert test tag
        conn.execute("INSERT INTO tags (name, category) VALUES (?, ?)",
                     (test_tag_name, "general"))
        conn.commit()
        new_tag_id = conn.execute("SELECT id FROM tags WHERE name = ?",
                                   (test_tag_name,)).fetchone()['id']
        print(f"   Created tag with ID: {new_tag_id}")

    # Test 1: Cache should NOT have new tag yet
    tag_id = cache.get_id(test_tag_name)
    if tag_id is None:
        print(f"\n3. ✓ Cache correctly does NOT have new tag yet")
    else:
        print(f"\n3. ✗ ERROR: Cache already has new tag (ID: {tag_id})")

    # Test 2: Reload cache using invalidate_tag_cache()
    print(f"\n4. Calling invalidate_tag_cache()...")
    invalidate_tag_cache()

    # Test 3: Cache should have new tag now
    tag_id = cache.get_id(test_tag_name)
    if tag_id == new_tag_id:
        print(f"   ✓ Cache correctly reloaded! Tag ID: {tag_id}")
    else:
        print(f"   ✗ ERROR: Cache does not have new tag (got: {tag_id}, expected: {new_tag_id})")

    final_count = cache.get_tag_count()
    print(f"\n5. Final tag count: {final_count} (was {initial_count})")

    if final_count == initial_count + 1:
        print(f"   ✓ Tag count increased by 1 as expected")
    else:
        print(f"   ✗ ERROR: Tag count mismatch (expected +1)")

    # Cleanup
    print(f"\n6. Cleaning up test tag...")
    with get_db_connection() as conn:
        conn.execute("DELETE FROM tags WHERE name = ?", (test_tag_name,))
        conn.commit()

    # Reload cache after cleanup
    invalidate_tag_cache()
    final_count_after_cleanup = cache.get_tag_count()
    print(f"   Tag count after cleanup: {final_count_after_cleanup}")

    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)

if __name__ == '__main__':
    test_tag_id_cache_reload()

#!/usr/bin/env python3
"""
Integration test for tag ID cache helper functions.
Tests that helper functions work correctly with both string and ID formats.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from core.cache_manager import (
    get_image_data,
    get_image_tags_as_string,
    get_image_tags_as_set,
    get_image_tags_as_ids,
    get_image_tag_count,
    load_data_from_db
)
from core.tag_id_cache import get_tag_id_cache
from array import array

def test_helper_functions():
    """Test that helper functions work correctly in both modes."""

    print("=" * 70)
    print("Testing Tag ID Cache Helper Functions")
    print("=" * 70)

    print(f"\nTAG_ID_CACHE_ENABLED: {config.TAG_ID_CACHE_ENABLED}")

    # Load cache if empty
    print("\nLoading cache...")
    load_data_from_db()

    # Get image data
    image_data = get_image_data()
    if not image_data:
        print("\n⚠️  No image data loaded - cache may be empty")
        return

    # Test with first image
    test_image = image_data[0]
    print(f"\nTesting with image: {test_image['filepath']}")

    # Test 1: get_image_tags_as_string
    print("\n1. Testing get_image_tags_as_string()...")
    tags_string = get_image_tags_as_string(test_image)
    print(f"   Result type: {type(tags_string).__name__}")
    print(f"   Result length: {len(tags_string)} chars")
    print(f"   First 100 chars: {tags_string[:100]}...")

    if isinstance(tags_string, str):
        print(f"   ✓ Returns string type")
    else:
        print(f"   ✗ ERROR: Expected string, got {type(tags_string)}")

    # Test 2: get_image_tags_as_set
    print("\n2. Testing get_image_tags_as_set()...")
    tags_set = get_image_tags_as_set(test_image)
    print(f"   Result type: {type(tags_set).__name__}")
    print(f"   Number of tags: {len(tags_set)}")
    print(f"   Sample tags: {list(tags_set)[:5]}")

    if isinstance(tags_set, set):
        print(f"   ✓ Returns set type")
    else:
        print(f"   ✗ ERROR: Expected set, got {type(tags_set)}")

    # Test 3: get_image_tags_as_ids
    print("\n3. Testing get_image_tags_as_ids()...")
    tags_ids = get_image_tags_as_ids(test_image)
    print(f"   Result type: {type(tags_ids).__name__}")
    print(f"   Number of IDs: {len(tags_ids)}")
    print(f"   First 10 IDs: {list(tags_ids)[:10]}")

    if isinstance(tags_ids, array):
        print(f"   ✓ Returns array type")
    else:
        print(f"   ✗ ERROR: Expected array, got {type(tags_ids)}")

    # Test 4: get_image_tag_count
    print("\n4. Testing get_image_tag_count()...")
    tag_count = get_image_tag_count(test_image)
    print(f"   Result: {tag_count} tags")

    if isinstance(tag_count, int):
        print(f"   ✓ Returns int type")
    else:
        print(f"   ✗ ERROR: Expected int, got {type(tag_count)}")

    # Test 5: Consistency check
    print("\n5. Testing consistency between helper functions...")

    # All three should report same number of tags
    string_count = len(tags_string.split()) if tags_string else 0
    set_count = len(tags_set)
    ids_count = len(tags_ids)
    direct_count = tag_count

    print(f"   String count: {string_count}")
    print(f"   Set count: {set_count}")
    print(f"   IDs count: {ids_count}")
    print(f"   Direct count: {direct_count}")

    if string_count == set_count == ids_count == direct_count:
        print(f"   ✓ All counts match!")
    else:
        print(f"   ✗ ERROR: Counts don't match")

    # Test 6: Verify tags match between string and set
    print("\n6. Testing string/set tag content match...")
    string_tags = set(tags_string.split()) if tags_string else set()
    if string_tags == tags_set:
        print(f"   ✓ String and set contain same tags")
    else:
        print(f"   ✗ ERROR: String and set tags don't match")
        print(f"   String only: {string_tags - tags_set}")
        print(f"   Set only: {tags_set - string_tags}")

    # Test 7: If ID mode enabled, verify ID->name round-trip
    if config.TAG_ID_CACHE_ENABLED:
        print("\n7. Testing ID->name round-trip conversion...")
        cache = get_tag_id_cache()

        # Convert IDs back to names
        names_from_ids = set(cache.get_names(tags_ids))

        if names_from_ids == tags_set:
            print(f"   ✓ ID->name conversion matches original tags")
        else:
            print(f"   ✗ ERROR: ID->name conversion doesn't match")
            print(f"   Missing: {tags_set - names_from_ids}")
            print(f"   Extra: {names_from_ids - tags_set}")
    else:
        print("\n7. Skipping ID->name round-trip (TAG_ID_CACHE_ENABLED=false)")

    # Test 8: Test with multiple images
    print("\n8. Testing with multiple images...")
    sample_size = min(100, len(image_data))
    print(f"   Testing {sample_size} images...")

    errors = 0
    for i, img in enumerate(image_data[:sample_size]):
        try:
            s = get_image_tags_as_string(img)
            st = get_image_tags_as_set(img)
            ids = get_image_tags_as_ids(img)
            cnt = get_image_tag_count(img)

            # Quick consistency check
            if not (len(st) == len(ids) == cnt):
                print(f"   ✗ Image {i}: Inconsistent counts ({len(st)}, {len(ids)}, {cnt})")
                errors += 1
        except Exception as e:
            print(f"   ✗ Image {i}: Error - {e}")
            errors += 1

    if errors == 0:
        print(f"   ✓ All {sample_size} images processed without errors")
    else:
        print(f"   ✗ {errors} errors found in {sample_size} images")

    print("\n" + "=" * 70)
    print("Integration test completed!")
    print("=" * 70)

if __name__ == '__main__':
    test_helper_functions()

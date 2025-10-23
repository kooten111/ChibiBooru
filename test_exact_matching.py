#!/usr/bin/env python3
"""Test exact tag matching - 'holo' should not match 'hololive'."""

# Test the exact matching logic we implemented
def test_exact_tag_matching():
    print("Testing Exact Tag Matching Logic")
    print("=" * 60)

    # Simulate image tags
    test_images = [
        {
            'filepath': 'image1.jpg',
            'tags': 'holo solo female'  # Has "holo" tag
        },
        {
            'filepath': 'image2.jpg',
            'tags': 'hololive solo female'  # Has "hololive" tag
        },
        {
            'filepath': 'image3.jpg',
            'tags': 'holo hololive solo group'  # Has both tags + solo
        },
        {
            'filepath': 'image4.jpg',
            'tags': 'solo male'  # Has neither holo/hololive
        }
    ]

    # Test 1: Search for "holo" (exact match)
    print("\n1. Search for 'holo' (should match only images with 'holo' tag)")
    print("-" * 60)

    search_term = 'holo'
    results = []

    for img in test_images:
        tags_str = img.get('tags', '').lower()
        tag_list = set(tags_str.split())
        filepath_lower = img.get('filepath', '').lower()

        # Check exact tag match OR filepath substring match
        if search_term in tag_list or search_term in filepath_lower:
            results.append(img['filepath'])

    print(f"Results: {results}")
    print(f"Expected: ['image1.jpg', 'image3.jpg']")
    print(f"✓ PASS" if results == ['image1.jpg', 'image3.jpg'] else "✗ FAIL")

    # Test 2: Search for "hololive" (exact match)
    print("\n2. Search for 'hololive' (should match only images with 'hololive' tag)")
    print("-" * 60)

    search_term = 'hololive'
    results = []

    for img in test_images:
        tags_str = img.get('tags', '').lower()
        tag_list = set(tags_str.split())
        filepath_lower = img.get('filepath', '').lower()

        if search_term in tag_list or search_term in filepath_lower:
            results.append(img['filepath'])

    print(f"Results: {results}")
    print(f"Expected: ['image2.jpg', 'image3.jpg']")
    print(f"✓ PASS" if results == ['image2.jpg', 'image3.jpg'] else "✗ FAIL")

    # Test 3: Search for "holo solo" (both must match)
    print("\n3. Search for 'holo solo' (both tags must match)")
    print("-" * 60)

    search_terms = ['holo', 'solo']
    results = []

    for img in test_images:
        tags_str = img.get('tags', '').lower()
        tag_list = set(tags_str.split())
        filepath_lower = img.get('filepath', '').lower()

        # Check if ALL search terms match
        match = True
        for term in search_terms:
            if term not in tag_list and term not in filepath_lower:
                match = False
                break

        if match:
            results.append(img['filepath'])

    print(f"Results: {results}")
    print(f"Expected: ['image1.jpg', 'image3.jpg']")
    print(f"✓ PASS" if results == ['image1.jpg', 'image3.jpg'] else "✗ FAIL")

    # Test 4: Negative search "solo -male"
    print("\n4. Search for 'solo -male' (exclude male tag)")
    print("-" * 60)

    general_terms = ['solo']
    negative_terms = ['male']
    results = []

    for img in test_images:
        tags_str = img.get('tags', '').lower()
        tag_list = set(tags_str.split())
        filepath_lower = img.get('filepath', '').lower()

        # Check if ALL general terms match
        match = True
        for term in general_terms:
            if term not in tag_list and term not in filepath_lower:
                match = False
                break

        if not match:
            continue

        # Check if any negative term matches (exclude if true)
        exclude = False
        for term in negative_terms:
            if term in tag_list or term in filepath_lower:
                exclude = True
                break

        if not exclude:
            results.append(img['filepath'])

    print(f"Results: {results}")
    print(f"Expected: ['image1.jpg', 'image2.jpg', 'image3.jpg']")
    print(f"✓ PASS" if results == ['image1.jpg', 'image2.jpg', 'image3.jpg'] else "✗ FAIL")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("EXACT TAG MATCHING TEST")
    print("=" * 60)

    try:
        test_exact_tag_matching()

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

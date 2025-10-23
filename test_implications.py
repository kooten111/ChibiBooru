#!/usr/bin/env python3
"""Test the implication service."""

from services import implication_service

def test_suggestions():
    """Test getting suggestions."""
    print("Testing implication suggestions...")

    suggestions = implication_service.get_all_suggestions()

    print(f"\nSummary:")
    print(f"  Total suggestions: {suggestions['summary']['total']}")
    print(f"  Costume patterns: {suggestions['summary']['costume_count']}")
    print(f"  Franchise patterns: {suggestions['summary']['franchise_count']}")
    print(f"  Correlation patterns: {suggestions['summary']['correlation_count']}")

    if suggestions['costume']:
        print(f"\nFirst costume suggestion:")
        s = suggestions['costume'][0]
        print(f"  {s['source_tag']} → {s['implied_tag']}")
        print(f"  Confidence: {s['confidence']}")
        print(f"  Reason: {s['reason']}")
        print(f"  Affected images: {s['affected_images']}")

    if suggestions['franchise']:
        print(f"\nFirst franchise suggestion:")
        s = suggestions['franchise'][0]
        print(f"  {s['source_tag']} → {s['implied_tag']}")
        print(f"  Confidence: {s['confidence']}")
        print(f"  Affected images: {s['affected_images']}")

    if suggestions['correlation']:
        print(f"\nFirst 3 correlation suggestions:")
        for i, s in enumerate(suggestions['correlation'][:3]):
            print(f"  {i+1}. {s['source_tag']} → {s['implied_tag']}")
            print(f"     Confidence: {s['confidence']:.2f}")
            print(f"     Reason: {s['reason']}")
            print(f"     Affected images: {s['affected_images']}")

def test_existing_implications():
    """Test getting existing implications."""
    print("\n\nTesting existing implications...")

    implications = implication_service.get_all_implications()
    print(f"Found {len(implications)} existing implications")

    if implications:
        print("\nFirst 3 implications:")
        for imp in implications[:3]:
            print(f"  {imp['source_tag']} → {imp['implied_tag']} ({imp['inference_type']})")

if __name__ == '__main__':
    test_suggestions()
    test_existing_implications()
    print("\n✅ Tests completed!")

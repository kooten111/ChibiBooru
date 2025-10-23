#!/usr/bin/env python3
"""Test exact tag matching behavior."""

import sqlite3

def get_db_connection():
    conn = sqlite3.connect("booru.db")
    conn.row_factory = sqlite3.Row
    return conn

def test_tag_existence():
    """Check if specific tags exist in the database."""
    print("Testing Tag Existence")
    print("=" * 60)

    test_tags = ["holo", "hololive", "solo", "female"]

    with get_db_connection() as conn:
        for tag in test_tags:
            # Check exact match (case-insensitive)
            result = conn.execute(
                "SELECT name, category FROM tags WHERE LOWER(name) = ? LIMIT 1",
                (tag.lower(),)
            ).fetchone()

            if result:
                print(f"✓ '{tag}' EXISTS as tag: {result['name']} (category: {result['category']})")
            else:
                print(f"✗ '{tag}' does NOT exist as exact tag")

                # Show similar tags
                similar = conn.execute(
                    "SELECT name FROM tags WHERE LOWER(name) LIKE ? LIMIT 5",
                    (f"%{tag.lower()}%",)
                ).fetchall()

                if similar:
                    print(f"  Similar tags: {', '.join(row['name'] for row in similar)}")

def test_search_mode_detection():
    """Simulate the _should_use_fts logic."""
    print("\n\nTesting Search Mode Detection")
    print("=" * 60)

    test_queries = [
        ["holo"],
        ["hololive"],
        ["solo", "female"],
        ["randomtag123"],
        ["holo", "solo"],
    ]

    with get_db_connection() as conn:
        for terms in test_queries:
            should_use_fts = False

            for term in terms:
                clean_term = term.strip('"').lower()
                result = conn.execute(
                    "SELECT 1 FROM tags WHERE LOWER(name) = ? LIMIT 1",
                    (clean_term,)
                ).fetchone()

                if not result:
                    should_use_fts = True
                    break

            mode = "FTS (freetext)" if should_use_fts else "Tag-based (exact)"
            print(f"Query: {' '.join(terms):30s} -> Mode: {mode}")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TAG MATCHING TEST")
    print("=" * 60 + "\n")

    try:
        test_tag_existence()
        test_search_mode_detection()

        print("\n" + "=" * 60)
        print("TEST COMPLETED")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

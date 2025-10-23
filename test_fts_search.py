#!/usr/bin/env python3
"""Test script for FTS5 search functionality."""

import sqlite3

def get_db_connection():
    """Create a database connection."""
    conn = sqlite3.connect("booru.db")
    conn.row_factory = sqlite3.Row
    return conn

def test_fts_direct():
    """Test FTS5 directly via SQL."""
    print("\nTesting Direct FTS5 Query")
    print("=" * 50)

    with get_db_connection() as conn:
        # Test 1: Simple FTS match
        cursor = conn.execute("""
            SELECT i.filepath, rank
            FROM images_fts fts
            INNER JOIN images i ON i.filepath = fts.filepath
            WHERE images_fts MATCH 'solo'
            ORDER BY rank
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\n1. FTS search for 'solo': Found {len(results)} results (showing top 5)")
        for idx, row in enumerate(results, 1):
            print(f"   {idx}. {row['filepath']}")

        # Test 2: Multi-term FTS search
        cursor = conn.execute("""
            SELECT i.filepath, rank
            FROM images_fts fts
            INNER JOIN images i ON i.filepath = fts.filepath
            WHERE images_fts MATCH '"solo" "female"'
            ORDER BY rank
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\n2. FTS search for 'solo female': Found {len(results)} results (showing top 5)")
        for idx, row in enumerate(results, 1):
            print(f"   {idx}. {row['filepath']}")

        # Test 3: Negative FTS search
        cursor = conn.execute("""
            SELECT i.filepath, rank
            FROM images_fts fts
            INNER JOIN images i ON i.filepath = fts.filepath
            WHERE images_fts MATCH '"solo" NOT "male"'
            ORDER BY rank
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\n3. FTS search for 'solo -male': Found {len(results)} results (showing top 5)")
        for idx, row in enumerate(results, 1):
            print(f"   {idx}. {row['filepath']}")

        # Test 4: Partial word search
        cursor = conn.execute("""
            SELECT i.filepath, rank
            FROM images_fts fts
            INNER JOIN images i ON i.filepath = fts.filepath
            WHERE images_fts MATCH 'dra*'
            ORDER BY rank
            LIMIT 5
        """)
        results = cursor.fetchall()

        print(f"\n4. FTS prefix search for 'dra*': Found {len(results)} results (showing top 5)")
        for idx, row in enumerate(results, 1):
            print(f"   {idx}. {row['filepath']}")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("FTS5 SEARCH FUNCTIONALITY TEST")
    print("=" * 60)

    try:
        test_fts_direct()

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

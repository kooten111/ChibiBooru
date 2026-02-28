#!/usr/bin/env python3
"""
Backfill Image Relations from Booru Metadata

Scans existing images for parent_id/post_id metadata and populates the
image_relations table with parent_child and sibling relationships.

This replaces the old on-the-fly parent/child resolution that queried
images.parent_id → images.post_id on every request. After running this
script, the image_relations table becomes the canonical source of truth.

Features:
    - Resolves parent_id → local image ID via post_id lookup
    - Creates parent_child relations (a=parent, b=child)
    - Derives sibling relations (children sharing the same parent)
    - Skips already-existing relations (safe to re-run)
    - Progress bar with tqdm
    - Dry-run mode for preview

Usage:
    # Preview what would be created
    python scripts/backfill_image_relations.py --dry-run

    # Run the backfill
    python scripts/backfill_image_relations.py

    # Clear all backfilled/ingested relations first (keeps manual/duplicate_review)
    python scripts/backfill_image_relations.py --reset
"""

import os
import sys
import argparse
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: F401  (initializes config)
from database.core import get_db_connection
from repositories import relations_repository


def get_images_with_parent_id():
    """Fetch all images that declare a parent_id."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, post_id, parent_id
            FROM images
            WHERE parent_id IS NOT NULL
            ORDER BY id
        """)
        return [dict(row) for row in cur.fetchall()]


def get_post_id_to_local_id_map():
    """Build a mapping of booru post_id → local image id."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, post_id
            FROM images
            WHERE post_id IS NOT NULL
        """)
        return {row['post_id']: row['id'] for row in cur.fetchall()}


def reset_automated_relations():
    """Delete all relations created by backfill or ingest (preserves manual/duplicate_review)."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM image_relations
            WHERE source IN ('backfill', 'ingested')
        """)
        count = cur.rowcount
        conn.commit()
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Backfill image_relations from booru parent_id/post_id metadata."
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview counts without writing to the database'
    )
    parser.add_argument(
        '--reset', action='store_true',
        help='Clear backfill/ingested relations before running (keeps manual/duplicate_review)'
    )
    parser.add_argument(
        '--batch-size', type=int, default=500,
        help='Number of relations to insert per batch (default: 500)'
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  Backfill Image Relations")
    print("=" * 70)

    # Optional reset
    if args.reset and not args.dry_run:
        deleted = reset_automated_relations()
        print(f"\n  Reset: deleted {deleted} backfill/ingested relations")

    # Step 1: Load data
    print("\n  Loading images with parent_id...")
    images_with_parent = get_images_with_parent_id()
    print(f"  Found {len(images_with_parent)} images with parent_id set")

    print("  Building post_id → local id mapping...")
    post_id_map = get_post_id_to_local_id_map()
    print(f"  Mapped {len(post_id_map)} post IDs to local image IDs")

    # Step 2: Resolve parent_child relations
    parent_child_relations = []
    unresolved = 0
    parent_to_children = defaultdict(list)  # parent_local_id → [child_local_id, ...]

    for img in images_with_parent:
        child_local_id = img['id']
        booru_parent_id = img['parent_id']

        parent_local_id = post_id_map.get(booru_parent_id)
        if parent_local_id is None:
            unresolved += 1
            continue

        if parent_local_id == child_local_id:
            # Self-referencing parent, skip
            continue

        parent_child_relations.append({
            'image_id_a': parent_local_id,   # parent
            'image_id_b': child_local_id,     # child
            'relation_type': 'parent_child',
            'source': 'backfill',
        })

        parent_to_children[parent_local_id].append(child_local_id)

    print(f"\n  Parent/child relations to create: {len(parent_child_relations)}")
    print(f"  Unresolved parent IDs (parent not in DB): {unresolved}")

    # Step 3: Derive sibling relations
    sibling_relations = []
    for parent_id, children in parent_to_children.items():
        if len(children) < 2:
            continue
        # Create sibling pairs between all children of the same parent
        for i in range(len(children)):
            for j in range(i + 1, len(children)):
                sibling_relations.append({
                    'image_id_a': children[i],
                    'image_id_b': children[j],
                    'relation_type': 'sibling',
                    'source': 'backfill',
                })

    print(f"  Sibling relations to create: {len(sibling_relations)}")
    print(f"  Parents with multiple children: {sum(1 for c in parent_to_children.values() if len(c) > 1)}")

    total_relations = parent_child_relations + sibling_relations
    print(f"\n  Total relations to insert: {len(total_relations)}")

    if args.dry_run:
        print("\n  [DRY RUN] No changes written to database.")
        print("=" * 70)
        return 0

    if not total_relations:
        print("\n  No relations to create. Database is up to date.")
        print("=" * 70)
        return 0

    # Step 4: Insert in batches
    print("\n  Inserting relations...")
    total_success = 0
    total_skipped = 0

    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False

    batches = [total_relations[i:i + args.batch_size]
               for i in range(0, len(total_relations), args.batch_size)]

    iterator = tqdm(batches, desc="  Batches", unit="batch") if use_tqdm else batches

    for batch in iterator:
        success, skipped = relations_repository.bulk_add_relations(batch)
        total_success += success
        total_skipped += skipped

    # Summary
    print(f"\n  {'=' * 40}")
    print(f"  Results:")
    print(f"    Inserted:  {total_success}")
    print(f"    Skipped:   {total_skipped} (already existed)")
    print(f"    Total:     {total_success + total_skipped}")
    print("=" * 70)

    # Verify
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT relation_type, source, COUNT(*) as cnt
            FROM image_relations
            GROUP BY relation_type, source
            ORDER BY relation_type, source
        """)
        rows = cur.fetchall()
        if rows:
            print("\n  Current image_relations summary:")
            print(f"    {'Type':<20} {'Source':<20} {'Count':>8}")
            print(f"    {'-'*20} {'-'*20} {'-'*8}")
            for row in rows:
                print(f"    {row['relation_type']:<20} {row['source']:<20} {row['cnt']:>8}")

    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())

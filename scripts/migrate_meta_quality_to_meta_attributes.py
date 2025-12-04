#!/usr/bin/env python3
"""
Migrate tags from 19_Meta_Quality to 19_Meta_Attributes category name.

This script updates any tags that have the old category name to use the new,
more general category name.
"""

import sys
import os

# Add parent directory to path to import from database
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import get_db_connection


def migrate_meta_quality_to_meta_attributes():
    """Update tags from 19_Meta_Quality to 19_Meta_Attributes."""

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Check how many tags have the old category name
        cur.execute("""
            SELECT COUNT(*) as count
            FROM tags
            WHERE extended_category = '19_Meta_Quality'
        """)

        count = cur.fetchone()['count']

        if count == 0:
            print("No tags found with '19_Meta_Quality' category.")
            print("Migration not needed or already completed.")
            return

        print(f"Found {count} tags with '19_Meta_Quality' category.")
        print("Updating to '19_Meta_Attributes'...")

        # Update the category name
        cur.execute("""
            UPDATE tags
            SET extended_category = '19_Meta_Attributes'
            WHERE extended_category = '19_Meta_Quality'
        """)

        conn.commit()

        print(f"✓ Successfully updated {count} tags to '19_Meta_Attributes'")

        # Verify the update
        cur.execute("""
            SELECT COUNT(*) as count
            FROM tags
            WHERE extended_category = '19_Meta_Attributes'
        """)

        new_count = cur.fetchone()['count']
        print(f"✓ Verified: {new_count} tags now have '19_Meta_Attributes' category")


if __name__ == '__main__':
    print("=" * 60)
    print("Migrating Meta_Quality to Meta_Attributes")
    print("=" * 60)

    migrate_meta_quality_to_meta_attributes()

    print("\nMigration complete!")

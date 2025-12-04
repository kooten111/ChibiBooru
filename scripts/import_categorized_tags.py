#!/usr/bin/env python3
"""
Import tag categorizations from danbooru_categorized.csv and e621_categorized.csv
into the extended_category column of the tags table.
"""

import csv
import sqlite3
import os

# Get the database path
db_path = 'booru.db'
danbooru_csv = 'metadata/danbooru_categorized.csv'
e621_csv = 'metadata/e621_categorized.csv'

def import_categorizations(csv_file, source_name):
    """Import categorizations from a CSV file."""
    print(f"\n{'='*60}")
    print(f"Importing from {source_name}: {csv_file}")
    print(f"{'='*60}")

    if not os.path.exists(csv_file):
        print(f"❌ File not found: {csv_file}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    imported = 0
    skipped = 0
    errors = 0

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 5:
                print(f"⚠️  Skipping invalid row: {row}")
                errors += 1
                continue

            main_tag = row[0].strip()
            aliases_str = row[3].strip().strip('"')  # Remove quotes
            extended_category = row[4].strip()

            if not extended_category:
                skipped += 1
                continue

            # Build list of all tags to categorize (main tag + aliases)
            all_tags = [main_tag]
            if aliases_str:
                aliases = [alias.strip() for alias in aliases_str.split(',')]
                all_tags.extend([a for a in aliases if a])  # Add non-empty aliases

            # Categorize each tag
            for tag_name in all_tags:
                if not tag_name:
                    continue

                # Check if tag exists in database
                cur.execute("SELECT id, extended_category FROM tags WHERE name = ?", (tag_name,))
                result = cur.fetchone()

                if result:
                    # Only update if not already categorized
                    if result['extended_category'] is None:
                        cur.execute(
                            "UPDATE tags SET extended_category = ? WHERE name = ?",
                            (extended_category, tag_name)
                        )
                        imported += 1
                        if imported % 100 == 0:
                            print(f"  Imported {imported} tags...", end='\r')
                    else:
                        skipped += 1
                else:
                    skipped += 1

            # Commit every 100 tags
            if (imported + skipped) % 100 == 0:
                conn.commit()

    conn.commit()
    conn.close()

    print(f"\n✅ Imported: {imported}")
    print(f"⏭️  Skipped: {skipped}")
    if errors > 0:
        print(f"❌ Errors: {errors}")

    return imported

def main():
    print("=" * 60)
    print("TAG CATEGORIZATION IMPORT")
    print("=" * 60)

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        print(f"Current directory: {os.getcwd()}")
        return

    # Check if extended_category column exists
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tags)")
    columns = [row[1] for row in cur.fetchall()]

    if 'extended_category' not in columns:
        print("❌ extended_category column not found in tags table!")
        print("Run: python3 add_extended_category_column.py first")
        conn.close()
        return

    # Get stats before import
    cur.execute("SELECT COUNT(*) FROM tags WHERE extended_category IS NOT NULL")
    before_count = cur.fetchone()[0]
    conn.close()

    print(f"\n📊 Current stats:")
    print(f"   Tags with extended_category: {before_count}")

    # Import from both files
    total_imported = 0
    total_imported += import_categorizations(danbooru_csv, 'Danbooru')
    total_imported += import_categorizations(e621_csv, 'e621')

    # Get stats after import
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tags WHERE extended_category IS NOT NULL")
    after_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tags WHERE extended_category IS NULL")
    remaining_count = cur.fetchone()[0]

    # Count tags actually used in images
    cur.execute("""
        SELECT COUNT(DISTINCT t.id)
        FROM tags t
        JOIN image_tags it ON t.id = it.tag_id
        WHERE t.extended_category IS NULL
    """)
    remaining_used = cur.fetchone()[0]

    conn.close()

    print(f"\n{'='*60}")
    print("IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"📊 Final stats:")
    print(f"   Before: {before_count} categorized")
    print(f"   After:  {after_count} categorized")
    print(f"   Added:  {after_count - before_count}")
    print(f"\n   Remaining uncategorized: {remaining_count}")
    print(f"   Remaining (with images): {remaining_used}")
    print(f"\n✨ Success! Reload your application to see the changes.")

if __name__ == "__main__":
    main()

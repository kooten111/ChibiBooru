#!/usr/bin/env python3
"""
Clean up duplicate tag deltas by computing net changes.
This removes entries where add/remove operations cancel each other out.
"""

from database import get_db_connection

def cleanup_tag_deltas():
    """Clean up tag deltas by removing operations that cancel each other out."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all unique image/tag combinations that have deltas
        cursor.execute("""
            SELECT DISTINCT image_md5, tag_name
            FROM tag_deltas
        """)

        combinations = cursor.fetchall()

        cleaned_count = 0

        for combo in combinations:
            image_md5 = combo['image_md5']
            tag_name = combo['tag_name']

            # Get all operations for this image/tag in chronological order
            cursor.execute("""
                SELECT operation, tag_category
                FROM tag_deltas
                WHERE image_md5 = ? AND tag_name = ?
                ORDER BY timestamp
            """, (image_md5, tag_name))

            operations = cursor.fetchall()

            if len(operations) <= 1:
                continue

            # Calculate net state
            net_state = None  # None, 'add', or 'remove'
            last_category = None

            for op in operations:
                if op['operation'] == 'add':
                    if net_state == 'remove':
                        net_state = None  # Cancel out
                    else:
                        net_state = 'add'
                    last_category = op['tag_category']
                elif op['operation'] == 'remove':
                    if net_state == 'add':
                        net_state = None  # Cancel out
                    else:
                        net_state = 'remove'
                    last_category = op['tag_category']

            # Delete all entries for this combination
            cursor.execute("""
                DELETE FROM tag_deltas
                WHERE image_md5 = ? AND tag_name = ?
            """, (image_md5, tag_name))

            # If there's a net change, insert it
            if net_state:
                cursor.execute("""
                    INSERT INTO tag_deltas
                    (image_md5, tag_name, tag_category, operation, timestamp)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (image_md5, tag_name, last_category, net_state))
                print(f"Kept net change: {net_state} {tag_name} for {image_md5[:8]}...")
            else:
                print(f"Removed cancelled operations for {tag_name} on {image_md5[:8]}...")
                cleaned_count += 1

        conn.commit()
        print(f"\nCleaned up {cleaned_count} cancelled tag delta entries")

if __name__ == '__main__':
    cleanup_tag_deltas()

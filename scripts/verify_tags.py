
import sqlite3
import os

DB_PATH = '/mnt/Server/ChibiBooru/booru.db'

def check_uncategorized_tags():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("Checking for uncategorized tags (extended_category IS NULL AND category IN ('general', 'meta'))...")
    
    cur.execute("""
        SELECT
            t.name,
            t.category,
            t.extended_category,
            COUNT(DISTINCT it.image_id) as usage_count
        FROM tags t
        LEFT JOIN image_tags it ON t.id = it.tag_id
        WHERE t.extended_category IS NULL
        AND t.category IN ('general', 'meta')
        GROUP BY t.id, t.name, t.category, t.extended_category
    """)
    
    tags = cur.fetchall()
    
    print(f"Found {len(tags)} uncategorized tags.")
    for t in tags:
        print(f"Tag: {t[0]}, Category: {t[1]}, Extended: {t[2]}, Usage: {t[3]}")
        
    print("\nChecking specifically for tags with 0 usage:")
    zero_usage = [t for t in tags if t[3] == 0]
    print(f"Found {len(zero_usage)} uncategorized tags with 0 usage.")
    for t in zero_usage:
         print(f"Tag: {t[0]}")

    conn.close()

if __name__ == "__main__":
    check_uncategorized_tags()

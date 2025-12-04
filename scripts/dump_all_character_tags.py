import sqlite3

def get_all_tags(character_tag):
    conn = sqlite3.connect('booru.db')
    cursor = conn.cursor()

    # Get tag ID
    cursor.execute("SELECT id FROM tags WHERE name = ?", (character_tag,))
    res = cursor.fetchone()
    if not res:
        print(f"Tag '{character_tag}' not found.")
        return
    char_tag_id = res[0]

    # Get all images with this tag
    cursor.execute("SELECT image_id FROM image_tags WHERE tag_id = ?", (char_tag_id,))
    image_ids = [row[0] for row in cursor.fetchall()]
    total_images = len(image_ids)
    print(f"Total Images: {total_images}\n")

    if total_images == 0:
        return

    # Get all tags
    placeholders = ','.join(['?'] * len(image_ids))
    query = f"""
        SELECT t.name, t.category, t.extended_category, COUNT(*) as count
        FROM image_tags it
        JOIN tags t ON it.tag_id = t.id
        WHERE it.image_id IN ({placeholders})
        GROUP BY t.name, t.category, t.extended_category
        ORDER BY count DESC, t.category, t.extended_category
    """
    
    cursor.execute(query, image_ids)
    all_tags = cursor.fetchall()
    
    # Header
    print(f"{'Count':<6} {'Category':<15} {'Extended Category':<25} {'Tag Name'}")
    print("-" * 80)
    
    for name, category, extended_category, count in all_tags:
        ext_cat_str = extended_category if extended_category else ""
        print(f"{count:<6} {category:<15} {ext_cat_str:<25} {name}")

    conn.close()

if __name__ == "__main__":
    get_all_tags("pulchra_fellini")

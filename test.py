import sqlite3

DB_FILE = "booru.db"

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 60)
print("TESTING SPECIES TAG INSERTION")
print("=" * 60)

# Get the image ID for our test image
MD5 = "5e70e5272c9aeb2247dc33b281796bf4"
cur.execute("SELECT id FROM images WHERE md5 = ?", (MD5,))
image_row = cur.fetchone()
if not image_row:
    print("ERROR: Image not found in database!")
    exit(1)

image_id = image_row['id']
print(f"\n1. Found image_id: {image_id}")

# Try to insert a test species tag
test_tag = "test_avian"
print(f"\n2. Inserting test species tag: {test_tag}")

cur.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (test_tag, 'species'))
conn.commit()

# Check if it was inserted
cur.execute("SELECT id, name, category FROM tags WHERE name = ?", (test_tag,))
tag_row = cur.fetchone()
if tag_row:
    print(f"   ✓ Tag inserted: id={tag_row['id']}, name={tag_row['name']}, category={tag_row['category']}")
    tag_id = tag_row['id']
    
    # Link it to the image
    print(f"\n3. Linking tag to image...")
    cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
    conn.commit()
    print(f"   ✓ Linked tag_id={tag_id} to image_id={image_id}")
    
    # Verify the link
    cur.execute("""
        SELECT t.name, t.category 
        FROM tags t 
        JOIN image_tags it ON t.id = it.tag_id 
        WHERE it.image_id = ? AND t.category = 'species'
    """, (image_id,))
    species = cur.fetchall()
    print(f"\n4. Species tags for this image:")
    for row in species:
        print(f"   - {row['name']} (category: {row['category']})")
else:
    print("   ❌ Tag was NOT inserted!")

conn.close()
print("\n" + "=" * 60)
# migrate_to_db.py
import sqlite3
import json
import os
from tqdm import tqdm

DB_FILE = "booru.db"
TAGS_FILE = "tags.json"
METADATA_DIR = "metadata"

# --- Functions from database.py are now included directly ---

def get_db_connection():
    """Create a database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Create the database and tables if they don't exist."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Main images table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL UNIQUE,
            md5 TEXT NOT NULL UNIQUE,
            post_id INTEGER,
            parent_id INTEGER,
            has_children BOOLEAN,
            saucenao_lookup BOOLEAN
        )
        """)
        # Tags table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT
        )
        """)
        # Image-to-Tag mapping table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS image_tags (
            image_id INTEGER,
            tag_id INTEGER,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE,
            PRIMARY KEY (image_id, tag_id)
        )
        """)
        # Sources table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """)
        # Image-to-Source mapping table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS image_sources (
            image_id INTEGER,
            source_id INTEGER,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE,
            PRIMARY KEY (image_id, source_id)
        )
        """)
        # Table for raw metadata
        cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_metadata (
            image_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        print("Database initialized successfully.")

# --- Main Migration Logic ---

def migrate_data():
    """Migrate data from tags.json and /metadata/ to the SQLite database."""
    if not os.path.exists(TAGS_FILE):
        print(f"Error: {TAGS_FILE} not found. Nothing to migrate.")
        return

    # Initialize the database first
    initialize_database()

    con = get_db_connection()
    cur = con.cursor()

    print(f"Loading data from {TAGS_FILE}...")
    with open(TAGS_FILE, 'r') as f:
        data = json.load(f)

    source_map = {}
    known_sources = ["danbooru", "e621", "gelbooru", "yandere", "local_tagger"]
    for source_name in known_sources:
        cur.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (source_name,))
        cur.execute("SELECT id FROM sources WHERE name = ?", (source_name,))
        source_map[source_name] = cur.fetchone()[0]

    tag_category_map = {
        "tags_general": "general",
        "tags_character": "character",
        "tags_copyright": "copyright",
        "tags_artist": "artist",
        "tags_meta": "meta"
    }

    print("Migrating image and tag data...")
    for filepath, item in tqdm(data.items(), desc="Migrating Images"):
        if not isinstance(item, dict) or not item.get("md5"):
            continue

        cur.execute(
            """
            INSERT OR IGNORE INTO images (filepath, md5, post_id, parent_id, has_children, saucenao_lookup)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                filepath,
                item.get("md5"),
                item.get("id"),
                item.get("parent_id"),
                item.get("has_children", False),
                item.get("saucenao_lookup", False),
            )
        )
        
        cur.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
        result = cur.fetchone()
        if not result:
            continue
        image_id = result['id']

        for source_name in item.get("sources", []):
            if source_name in source_map:
                source_id = source_map[source_name]
                cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_id))
        if item.get("camie_tagger_lookup"):
             cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_map['local_tagger']))

        for tag_field, category in tag_category_map.items():
            tags_str = item.get(tag_field, "")
            if tags_str:
                for tag_name in tags_str.split():
                    cur.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, category))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cur.fetchone()['id']
                    cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
        
        general_tags_str = item.get("tags", "")
        if general_tags_str:
            for tag_name in general_tags_str.split():
                cur.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, "general"))
                cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_id = cur.fetchone()['id']
                cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

    con.commit()

    print("\nMigrating raw metadata...")
    if os.path.isdir(METADATA_DIR):
        metadata_files = [f for f in os.listdir(METADATA_DIR) if f.endswith('.json')]
        for filename in tqdm(metadata_files, desc="Migrating Metadata"):
            md5 = filename.replace('.json', '')
            try:
                with open(os.path.join(METADATA_DIR, filename), 'r') as f:
                    metadata_content = json.load(f)

                cur.execute("SELECT id FROM images WHERE md5 = ?", (md5,))
                result = cur.fetchone()
                if result:
                    image_id = result['id']
                    cur.execute(
                        "INSERT OR REPLACE INTO raw_metadata (image_id, data) VALUES (?, ?)",
                        (image_id, json.dumps(metadata_content))
                    )
            except Exception as e:
                print(f"Could not process {filename}: {e}")

    con.commit()
    con.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate_data()
# database.py
import sqlite3

DB_FILE = "booru.db"

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
            saucenao_lookup BOOLEAN,
            active_source TEXT
        )
        """)

        columns_to_add = {
            'tags_character': 'TEXT',
            'tags_copyright': 'TEXT',
            'tags_artist': 'TEXT',
            'tags_species': 'TEXT',
            'tags_meta': 'TEXT',
            'tags_general': 'TEXT'
        }
        
        cur.execute("PRAGMA table_info(images);")
        existing_columns = [row['name'] for row in cur.fetchall()]
        
        for col, col_type in columns_to_add.items():
            if col not in existing_columns:
                print(f"Adding column '{col}' to 'images' table...")
                cur.execute(f"ALTER TABLE images ADD COLUMN {col} {col_type}")

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

        cur.execute("""
        CREATE TABLE IF NOT EXISTS pools (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS pool_images (
            pool_id INTEGER,
            image_id INTEGER,
            sort_order INTEGER,
            FOREIGN KEY (pool_id) REFERENCES pools (id) ON DELETE CASCADE,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            PRIMARY KEY (pool_id, image_id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tag_implications (
            source_tag_id INTEGER,
            implied_tag_id INTEGER,
            FOREIGN KEY (source_tag_id) REFERENCES tags (id) ON DELETE CASCADE,
            FOREIGN KEY (implied_tag_id) REFERENCES tags (id) ON DELETE CASCADE,
            PRIMARY KEY (source_tag_id, implied_tag_id)
        )
        """)

        # Add metadata columns to tag_implications if they don't exist
        cur.execute("PRAGMA table_info(tag_implications);")
        impl_columns = [row['name'] for row in cur.fetchall()]

        if 'inference_type' not in impl_columns:
            cur.execute("ALTER TABLE tag_implications ADD COLUMN inference_type TEXT DEFAULT 'manual'")
        if 'confidence' not in impl_columns:
            cur.execute("ALTER TABLE tag_implications ADD COLUMN confidence REAL DEFAULT 1.0")
        if 'created_at' not in impl_columns:
            cur.execute("ALTER TABLE tag_implications ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if 'status' not in impl_columns:
            cur.execute("ALTER TABLE tag_implications ADD COLUMN status TEXT DEFAULT 'active'")

        # Index for faster implication lookups
        cur.execute("CREATE INDEX IF NOT EXISTS idx_implications_source ON tag_implications(source_tag_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_implications_status ON tag_implications(status)")

        cur.execute("""
        CREATE TABLE IF NOT EXISTS tag_deltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_md5 TEXT NOT NULL,
            tag_name TEXT NOT NULL,
            tag_category TEXT,
            operation TEXT NOT NULL CHECK(operation IN ('add', 'remove')),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(image_md5, tag_name, operation)
        )
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_tag_deltas_md5
        ON tag_deltas(image_md5)
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_filepath ON images(filepath)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_md5 ON images(md5)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_post_id ON images(post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_parent_id ON images(parent_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_has_children ON images(has_children)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_active_source ON images(active_source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_relationships ON images(parent_id, has_children)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_image_id ON image_tags(image_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_sources_image_id ON image_sources(image_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_sources_source_id ON image_sources(source_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_metadata_image_id ON raw_metadata(image_id)")

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images_fts'")
        fts_exists = cur.fetchone()

        if not fts_exists:
            cur.execute("""
            CREATE VIRTUAL TABLE images_fts USING fts5(
                filepath,
                tags_all,
                tags_character,
                tags_copyright,
                tags_artist,
                tags_species,
                tags_meta,
                tags_general
            )
            """)

        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS images_fts_insert AFTER INSERT ON images
        BEGIN
            INSERT INTO images_fts(filepath, tags_all, tags_character, tags_copyright, tags_artist, tags_species, tags_meta, tags_general)
            VALUES (
                new.filepath,
                COALESCE(new.tags_character, '') || ' ' ||
                COALESCE(new.tags_copyright, '') || ' ' ||
                COALESCE(new.tags_artist, '') || ' ' ||
                COALESCE(new.tags_species, '') || ' ' ||
                COALESCE(new.tags_meta, '') || ' ' ||
                COALESCE(new.tags_general, ''),
                COALESCE(new.tags_character, ''),
                COALESCE(new.tags_copyright, ''),
                COALESCE(new.tags_artist, ''),
                COALESCE(new.tags_species, ''),
                COALESCE(new.tags_meta, ''),
                COALESCE(new.tags_general, '')
            );
        END
        """)

        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS images_fts_update AFTER UPDATE ON images
        BEGIN
            DELETE FROM images_fts WHERE filepath = old.filepath;
            INSERT INTO images_fts(filepath, tags_all, tags_character, tags_copyright, tags_artist, tags_species, tags_meta, tags_general)
            VALUES (
                new.filepath,
                COALESCE(new.tags_character, '') || ' ' ||
                COALESCE(new.tags_copyright, '') || ' ' ||
                COALESCE(new.tags_artist, '') || ' ' ||
                COALESCE(new.tags_species, '') || ' ' ||
                COALESCE(new.tags_meta, '') || ' ' ||
                COALESCE(new.tags_general, ''),
                COALESCE(new.tags_character, ''),
                COALESCE(new.tags_copyright, ''),
                COALESCE(new.tags_artist, ''),
                COALESCE(new.tags_species, ''),
                COALESCE(new.tags_meta, ''),
                COALESCE(new.tags_general, '')
            );
        END
        """)

        cur.execute("""
        CREATE TRIGGER IF NOT EXISTS images_fts_delete AFTER DELETE ON images
        BEGIN
            DELETE FROM images_fts WHERE filepath = old.filepath;
        END
        """)

        conn.commit()
        print("Database initialized successfully.")

def populate_fts_table():
    """Populate the FTS table with existing data from images table."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Check if FTS table is empty
        cur.execute("SELECT COUNT(*) as cnt FROM images_fts")
        fts_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) as cnt FROM images")
        images_count = cur.fetchone()['cnt']

        if fts_count == 0 and images_count > 0:
            print(f"Populating FTS table with {images_count} images...")
            cur.execute("""
                INSERT INTO images_fts(filepath, tags_all, tags_character, tags_copyright, tags_artist, tags_species, tags_meta, tags_general)
                SELECT
                    filepath,
                    COALESCE(tags_character, '') || ' ' ||
                    COALESCE(tags_copyright, '') || ' ' ||
                    COALESCE(tags_artist, '') || ' ' ||
                    COALESCE(tags_species, '') || ' ' ||
                    COALESCE(tags_meta, '') || ' ' ||
                    COALESCE(tags_general, ''),
                    COALESCE(tags_character, ''),
                    COALESCE(tags_copyright, ''),
                    COALESCE(tags_artist, ''),
                    COALESCE(tags_species, ''),
                    COALESCE(tags_meta, ''),
                    COALESCE(tags_general, '')
                FROM images
            """)
            conn.commit()
            print(f"FTS table populated with {images_count} entries.")
        elif fts_count != images_count:
            print(f"Warning: FTS table has {fts_count} entries but images table has {images_count}. Consider rebuilding FTS.")
        else:
            print(f"FTS table already populated ({fts_count} entries).")

if __name__ == "__main__":
    initialize_database()
    populate_fts_table()
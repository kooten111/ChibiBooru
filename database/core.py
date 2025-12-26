# database.py
import sqlite3
import config

DB_FILE = "booru.db"

def get_db_connection():
    """Create a database connection with optimized performance settings."""
    # Set timeout to 30 seconds to wait for locks instead of failing immediately
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode = WAL")

    # Faster synchronization (safe with WAL mode)
    conn.execute("PRAGMA synchronous = NORMAL")

    # Increase cache size (configurable, default 64MB)
    # Negative value means KB
    cache_size_kb = -1 * config.DB_CACHE_SIZE_MB * 1024
    conn.execute(f"PRAGMA cache_size = {cache_size_kb}")

    # Increase page size for better performance with large blobs
    # Note: This only affects NEW databases, existing ones keep their page size
    conn.execute("PRAGMA page_size = 8192")

    # Memory-mapped I/O for faster reads (configurable, default 256MB)
    mmap_size_bytes = config.DB_MMAP_SIZE_MB * 1024 * 1024
    conn.execute(f"PRAGMA mmap_size = {mmap_size_bytes}")

    # Increase temp store to memory for faster sorts/indexes
    conn.execute("PRAGMA temp_store = MEMORY")

    # Optimize for multiple readers (configurable)
    conn.execute(f"PRAGMA wal_autocheckpoint = {config.DB_WAL_AUTOCHECKPOINT}")

    # Enable row factory for dict-like access
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
            'tags_general': 'TEXT',
            'score': 'INTEGER',
            'fav_count': 'INTEGER',
            'phash': 'TEXT',  # Perceptual hash for visual similarity
            'colorhash': 'TEXT',  # Color hash for color similarity
            'image_width': 'INTEGER',  # Original image width in pixels
            'image_height': 'INTEGER',  # Original image height in pixels
        }

        cur.execute("PRAGMA table_info(images);")
        existing_columns = [row['name'] for row in cur.fetchall()]

        for col, col_type in columns_to_add.items():
            if col not in existing_columns:
                print(f"Adding column '{col}' to 'images' table...")
                cur.execute(f"ALTER TABLE images ADD COLUMN {col} {col_type}")

        # Handle ingested_at column separately (requires special handling for CURRENT_TIMESTAMP)
        if 'ingested_at' not in existing_columns:
            print("Adding 'ingested_at' column to 'images' table...")
            # SQLite doesn't support DEFAULT CURRENT_TIMESTAMP in ALTER TABLE
            # Add without default, then update existing rows
            cur.execute("ALTER TABLE images ADD COLUMN ingested_at TIMESTAMP")
            # Set a default timestamp for existing rows (use current time)
            cur.execute("UPDATE images SET ingested_at = CURRENT_TIMESTAMP WHERE ingested_at IS NULL")
            print("Updated existing images with current timestamp")

        # Tags table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT
        )
        """)

        # Add extended_category column to tags if it doesn't exist (for Platinum Schema categorization)
        cur.execute("PRAGMA table_info(tags);")
        tag_columns = [row['name'] for row in cur.fetchall()]

        if 'extended_category' not in tag_columns:
            print("Adding 'extended_category' column to 'tags' table...")
            cur.execute("ALTER TABLE tags ADD COLUMN extended_category TEXT")

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

        # Add 'source' column to image_tags if it doesn't exist (for rating inference)
        cur.execute("PRAGMA table_info(image_tags);")
        image_tags_columns = [row['name'] for row in cur.fetchall()]

        if 'source' not in image_tags_columns:
            print("Adding 'source' column to 'image_tags' table...")
            cur.execute("""
                ALTER TABLE image_tags
                ADD COLUMN source TEXT DEFAULT 'original'
                CHECK(source IN ('original', 'user', 'ai_inference'))
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

        # Favourites table - stores user's favourite images
        cur.execute("""
        CREATE TABLE IF NOT EXISTS favourites (
            image_id INTEGER PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE
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

        # ===================================================================
        # Local Tagger Predictions Table
        # ===================================================================
        # Stores ALL predictions from local tagger with confidence scores.
        # This is immutable source data - display merging happens at runtime.
        cur.execute("""
        CREATE TABLE IF NOT EXISTS local_tagger_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_id INTEGER NOT NULL,
            tag_name TEXT NOT NULL,
            category TEXT,
            confidence REAL NOT NULL,
            tagger_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            UNIQUE(image_id, tag_name)
        )
        """)

        # ===================================================================
        # Rating Inference Tables
        # ===================================================================

        # Individual tag weights for ratings
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_tag_weights (
            tag_name TEXT NOT NULL,
            rating TEXT NOT NULL,
            weight REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            PRIMARY KEY (tag_name, rating)
        )
        """)

        # Tag pair weights for context-aware predictions
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_tag_pair_weights (
            tag1 TEXT NOT NULL,
            tag2 TEXT NOT NULL,
            rating TEXT NOT NULL,
            weight REAL NOT NULL,
            co_occurrence_count INTEGER NOT NULL,
            PRIMARY KEY (tag1, tag2, rating),
            CHECK (tag1 < tag2)
        )
        """)

        # Inference configuration
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_inference_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
        """)

        # Initialize default config if empty
        cur.execute("SELECT COUNT(*) as cnt FROM rating_inference_config")
        if cur.fetchone()['cnt'] == 0:
            print("Initializing rating inference config with defaults...")
            default_config = [
                ('threshold_general', 0.5),
                ('threshold_sensitive', 0.6),
                ('threshold_questionable', 0.7),
                ('threshold_explicit', 0.8),
                ('min_confidence', 0.4),
                ('pair_weight_multiplier', 1.5),
                ('min_training_samples', 50),
                ('min_pair_cooccurrence', 5),
                ('min_tag_frequency', 10),
                ('max_pair_count', 10000),
            ]
            cur.executemany(
                "INSERT INTO rating_inference_config (key, value) VALUES (?, ?)",
                default_config
            )

        # Model training metadata
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_model_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ===================================================================
        # Indexes
        # ===================================================================

        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_filepath ON images(filepath)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_md5 ON images(md5)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_post_id ON images(post_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_parent_id ON images(parent_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_has_children ON images(has_children)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_active_source ON images(active_source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_relationships ON images(parent_id, has_children)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_ingested_at ON images(ingested_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_score ON images(score DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_fav_count ON images(fav_count DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash)")  # For similarity lookups
        cur.execute("CREATE INDEX IF NOT EXISTS idx_images_colorhash ON images(colorhash)")  # For color similarity
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_name_lower ON tags(LOWER(name))")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tags_extended_category ON tags(extended_category)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_image_id ON image_tags(image_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_source ON image_tags(source)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_sources_image_id ON image_sources(image_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_image_sources_source_id ON image_sources(source_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_metadata_image_id ON raw_metadata(image_id)")

        # Local tagger predictions indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ltp_image_id ON local_tagger_predictions(image_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ltp_confidence ON local_tagger_predictions(confidence)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ltp_tag_name ON local_tagger_predictions(tag_name)")

        # Rating inference indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_rating ON rating_tag_weights(rating)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_weight ON rating_tag_weights(weight DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_rating ON rating_tag_pair_weights(rating)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_weight ON rating_tag_pair_weights(weight DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_tags ON rating_tag_pair_weights(tag1, tag2)")

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


def repair_orphaned_image_tags():
    """
    Auto-repair data integrity: rebuild image_tags for images that have
    denormalized tags but no entries in image_tags table.

    This handles cases where tags exist in tags_general, tags_species, etc.
    but haven't been populated into the relational image_tags table.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find orphaned images
        cur.execute("""
            SELECT id,
                   tags_general,
                   tags_species,
                   tags_character,
                   tags_copyright,
                   tags_artist,
                   tags_meta
            FROM images
            WHERE id NOT IN (SELECT DISTINCT image_id FROM image_tags)
              AND (
                  (tags_general IS NOT NULL AND tags_general != '') OR
                  (tags_species IS NOT NULL AND tags_species != '') OR
                  (tags_character IS NOT NULL AND tags_character != '') OR
                  (tags_copyright IS NOT NULL AND tags_copyright != '') OR
                  (tags_artist IS NOT NULL AND tags_artist != '') OR
                  (tags_meta IS NOT NULL AND tags_meta != '')
              )
        """)

        orphaned_images = cur.fetchall()

        if not orphaned_images:
            return 0

        print(f"Found {len(orphaned_images)} images with orphaned tags. Rebuilding relationships...")

        total_tags_added = 0

        for img in orphaned_images:
            image_id = img['id']

            tag_categories = {
                'general': img['tags_general'],
                'species': img['tags_species'],
                'character': img['tags_character'],
                'copyright': img['tags_copyright'],
                'artist': img['tags_artist'],
                'meta': img['tags_meta']
            }

            for category, tag_string in tag_categories.items():
                if not tag_string:
                    continue

                tags = tag_string.strip().split()

                for tag_name in tags:
                    if not tag_name:
                        continue

                    # Insert tag if it doesn't exist
                    cur.execute(
                        "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                        (tag_name, category)
                    )

                    # Get tag ID
                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_row = cur.fetchone()
                    if not tag_row:
                        continue

                    tag_id = tag_row['id']

                    # Create image_tags relationship
                    cur.execute(
                        "INSERT OR IGNORE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)",
                        (image_id, tag_id, 'original')
                    )

                    total_tags_added += 1

        conn.commit()
        print(f"✅ Repaired {len(orphaned_images)} images, added {total_tags_added} tag relationships")

        return len(orphaned_images)


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
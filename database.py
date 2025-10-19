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

if __name__ == "__main__":
    initialize_database()
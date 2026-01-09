# character_repository.py
"""
Separate model database management for character inference weights.

This allows the character model to be stored separately from the main database,
enabling distribution of pre-trained models and easier version control.
"""

import sqlite3
import os
from typing import Optional, Dict
from contextlib import contextmanager

# Default model database path
DEFAULT_MODEL_PATH = 'character_model.db'


def get_model_db_path() -> str:
    """
    Get the current model database path from config or use default.

    Returns:
        str: Path to model database
    """
    # For now, use environment variable or default
    # Later can be stored in main DB config
    return os.environ.get('CHARACTER_MODEL_PATH', DEFAULT_MODEL_PATH)


def _init_connection(conn: sqlite3.Connection) -> None:
    """
    Initialize database schema on an existing connection.

    Args:
        conn: Open SQLite connection to initialize
    """
    cur = conn.cursor()

    # Configuration table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_inference_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)

    # Insert default config from centralized config
    import config
    defaults = config.CHARACTER_MODEL_CONFIG.copy()
    
    # Add character-specific settings not in centralized config
    defaults.update({
        'min_character_samples': 10,
        'tag_weight': 1.0,
        'vector_weight': 0.0,  # Disabled by default (not implemented yet)
        'visual_weight': 0.0,  # Disabled by default (not implemented yet)
        'k_neighbors': 5,
    })

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO character_inference_config (key, value) VALUES (?, ?)",
            (key, value)
        )

    # Lookup tables for normalization
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tag_name ON tags(name)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_name ON characters(name)")

    # Optimized tag weights table with foreign keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_tag_weights (
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            character_id INTEGER NOT NULL REFERENCES characters(id),
            weight REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            PRIMARY KEY (tag_id, character_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_weights_character ON character_tag_weights(character_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_weights_weight ON character_tag_weights(weight DESC)")

    # Optimized tag pair weights table with foreign keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_tag_pair_weights (
            tag1_id INTEGER NOT NULL REFERENCES tags(id),
            tag2_id INTEGER NOT NULL REFERENCES tags(id),
            character_id INTEGER NOT NULL REFERENCES characters(id),
            weight REAL NOT NULL,
            co_occurrence_count INTEGER NOT NULL,
            PRIMARY KEY (tag1_id, tag2_id, character_id),
            CHECK (tag1_id < tag2_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_pair_weights_character ON character_tag_pair_weights(character_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_pair_weights_weight ON character_tag_pair_weights(weight DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_character_pair_weights_tags ON character_tag_pair_weights(tag1_id, tag2_id)")

    # Model metadata table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS character_model_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()


@contextmanager
def get_model_db_connection():
    """
    Context manager for model database connections.

    Auto-initializes the database if it doesn't exist.

    Yields:
        sqlite3.Connection: Database connection with row factory
    """
    db_path = get_model_db_path()

    # Check if database needs initialization
    needs_init = not os.path.exists(db_path)

    # Set timeout to 30 seconds to wait for locks instead of failing immediately
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrency (allows concurrent reads during writes)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    # Initialize if needed
    if needs_init:
        print(f"Initializing character model database at {db_path}...")
        _init_connection(conn)
    else:
        # Verify tables exist (in case file exists but is empty/corrupt)
        try:
            conn.execute("SELECT 1 FROM character_inference_config LIMIT 1")
        except sqlite3.OperationalError:
            print(f"Character model database exists but is missing tables. Re-initializing...")
            _init_connection(conn)

    try:
        yield conn
    finally:
        conn.close()


def init_model_database(db_path: Optional[str] = None) -> None:
    """
    Initialize a new model database with the required schema.

    Args:
        db_path: Path to create database (uses default if None)
    """
    if db_path is None:
        db_path = get_model_db_path()

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    _init_connection(conn)
    conn.close()

    print(f"✅ Initialized character model database: {db_path}")


def get_or_create_tag_id(conn: sqlite3.Connection, tag_name: str) -> int:
    """
    Get tag ID from name, creating it if it doesn't exist.
    
    Args:
        conn: Database connection
        tag_name: Tag name
        
    Returns:
        int: Tag ID
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    row = cur.fetchone()
    if row:
        # Handle both Row objects and tuples
        return row['id'] if hasattr(row, 'keys') else row[0]
    
    cur.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    return cur.lastrowid


def get_or_create_character_id(conn: sqlite3.Connection, character_name: str) -> int:
    """
    Get character ID from name, creating it if it doesn't exist.
    
    Args:
        conn: Database connection
        character_name: Character name (e.g., 'hatsune_miku')
        
    Returns:
        int: Character ID
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM characters WHERE name = ?", (character_name,))
    row = cur.fetchone()
    if row:
        # Handle both Row objects and tuples
        return row['id'] if hasattr(row, 'keys') else row[0]
    
    cur.execute("INSERT INTO characters (name) VALUES (?)", (character_name,))
    return cur.lastrowid


def get_tag_name(conn: sqlite3.Connection, tag_id: int) -> Optional[str]:
    """
    Get tag name from ID.
    
    Args:
        conn: Database connection
        tag_id: Tag ID
        
    Returns:
        str or None: Tag name if found
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
    row = cur.fetchone()
    if row:
        # Handle both Row objects and tuples
        return row['name'] if hasattr(row, 'keys') else row[0]
    return None


def get_character_name(conn: sqlite3.Connection, character_id: int) -> Optional[str]:
    """
    Get character name from ID.
    
    Args:
        conn: Database connection
        character_id: Character ID
        
    Returns:
        str or None: Character name if found
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM characters WHERE id = ?", (character_id,))
    row = cur.fetchone()
    if row:
        # Handle both Row objects and tuples
        return row['name'] if hasattr(row, 'keys') else row[0]
    return None


def get_model_info(model_path: Optional[str] = None) -> Dict:
    """
    Get information about a model database.

    Args:
        model_path: Path to model DB (uses default if None)

    Returns:
        dict: Model information including counts and metadata
    """
    if model_path is None:
        model_path = get_model_db_path()

    if not os.path.exists(model_path):
        return {
            'exists': False,
            'path': model_path
        }

    with sqlite3.connect(model_path, timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        cur = conn.cursor()

        # Get counts
        cur.execute("SELECT COUNT(*) as cnt FROM character_tag_weights")
        tag_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) as cnt FROM character_tag_pair_weights")
        pair_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) as cnt FROM characters")
        character_count = cur.fetchone()['cnt']

        # Get metadata
        cur.execute("SELECT key, value FROM character_model_metadata")
        metadata = {row['key']: row['value'] for row in cur.fetchall()}

        # Get file size
        file_size = os.path.getsize(model_path)

        return {
            'exists': True,
            'path': model_path,
            'file_size_bytes': file_size,
            'file_size_mb': round(file_size / (1024 * 1024), 2),
            'tag_weights': tag_count,
            'pair_weights': pair_count,
            'characters': character_count,
            'metadata': metadata
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python character_repository.py init [path]  - Initialize new model DB")
        print("  python character_repository.py info [path]  - Show model info")
        sys.exit(1)

    command = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else None

    if command == 'init':
        init_model_database(path)
    elif command == 'info':
        info = get_model_info(path)
        print("\nCharacter Model Database Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

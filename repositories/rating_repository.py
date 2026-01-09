# rating_model_db.py
"""
Separate model database management for rating inference weights.

This allows the model to be stored separately from the main database,
enabling distribution of pre-trained models and easier version control.
"""

import sqlite3
import os
import gzip
import shutil
from typing import Optional, Dict
from contextlib import contextmanager

# Default model database path
DEFAULT_MODEL_PATH = 'data/rating_model.db'


def get_model_db_path() -> str:
    """
    Get the current model database path from config or use default.

    Returns:
        str: Path to model database
    """
    # For now, use environment variable or default
    # Later can be stored in main DB config
    return os.environ.get('RATING_MODEL_PATH', DEFAULT_MODEL_PATH)


def _init_connection(conn: sqlite3.Connection) -> None:
    """
    Initialize database schema on an existing connection.

    Args:
        conn: Open SQLite connection to initialize
    """
    cur = conn.cursor()

    # Configuration table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_inference_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)

    # Insert default config from centralized config
    import config
    defaults = config.RATING_MODEL_CONFIG.copy()
    
    # Add rating-specific thresholds and settings
    defaults.update({
        'threshold_general': 0.5,
        'threshold_sensitive': 0.6,
        'threshold_questionable': 0.7,
        'threshold_explicit': 0.8,
        'min_training_samples': 50,
        'pruning_threshold': 0.0,
    })

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO rating_inference_config (key, value) VALUES (?, ?)",
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
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_name ON ratings(name)")

    # Pre-populate ratings table with the four rating values
    rating_values = ['rating:general', 'rating:sensitive', 'rating:questionable', 'rating:explicit']
    for rating in rating_values:
        cur.execute("INSERT OR IGNORE INTO ratings (name) VALUES (?)", (rating,))

    # Optimized tag weights table with foreign keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_tag_weights (
            tag_id INTEGER NOT NULL REFERENCES tags(id),
            rating_id INTEGER NOT NULL REFERENCES ratings(id),
            weight REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            PRIMARY KEY (tag_id, rating_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_rating ON rating_tag_weights(rating_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_weight ON rating_tag_weights(weight DESC)")

    # Optimized tag pair weights table with foreign keys
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_tag_pair_weights (
            tag1_id INTEGER NOT NULL REFERENCES tags(id),
            tag2_id INTEGER NOT NULL REFERENCES tags(id),
            rating_id INTEGER NOT NULL REFERENCES ratings(id),
            weight REAL NOT NULL,
            co_occurrence_count INTEGER NOT NULL,
            PRIMARY KEY (tag1_id, tag2_id, rating_id),
            CHECK (tag1_id < tag2_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_rating ON rating_tag_pair_weights(rating_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_weight ON rating_tag_pair_weights(weight DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_tags ON rating_tag_pair_weights(tag1_id, tag2_id)")

    # Model metadata table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_model_metadata (
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
    Auto-migrates weights from main DB if model DB is empty but main DB has weights.

    Yields:
        sqlite3.Connection: Database connection with row factory
    """
    db_path = get_model_db_path()

    # Check if database needs initialization
    needs_init = not os.path.exists(db_path)
    needs_migration = False

    # Set timeout to 30 seconds to wait for locks instead of failing immediately
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrency (allows concurrent reads during writes)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")

    # Initialize if needed
    if needs_init:
        print(f"Initializing model database at {db_path}...")
        _init_connection(conn)
        needs_migration = True  # Check for migration after init
    else:
        # Verify tables exist (in case file exists but is empty/corrupt)
        try:
            conn.execute("SELECT 1 FROM rating_inference_config LIMIT 1")
        except sqlite3.OperationalError:
            print(f"Model database exists but is missing tables. Re-initializing...")
            _init_connection(conn)
            needs_migration = True

    # Auto-migrate from main DB if model DB is empty but main DB has weights
    if needs_migration:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_weights")
            weight_count = cur.fetchone()['cnt']

            if weight_count == 0:
                # Model DB is empty, check if main DB has weights
                from database import get_db_connection
                with get_db_connection() as main_conn:
                    try:
                        main_cur = main_conn.cursor()
                        main_cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_weights")
                        main_weight_count = main_cur.fetchone()['cnt']

                        if main_weight_count > 0:
                            print(f"Found {main_weight_count} weights in main DB. Auto-migrating to model DB...")
                            _migrate_weights_from_main_db(conn, main_conn)
                    except sqlite3.OperationalError:
                        # Main DB doesn't have weight tables, that's fine
                        pass
        except Exception as e:
            print(f"Warning: Auto-migration check failed: {e}")

    try:
        yield conn
    finally:
        conn.close()


def _migrate_weights_from_main_db(model_conn: sqlite3.Connection, main_conn: sqlite3.Connection) -> None:
    """
    Internal helper to migrate weights from main DB to model DB.
    Handles both old schema (tag_name/rating text) and new schema (tag_id/rating_id integers).

    Args:
        model_conn: Open connection to model database (new schema)
        main_conn: Open connection to main database (may have old or new schema)
    """
    main_cur = main_conn.cursor()
    model_cur = model_conn.cursor()

    # Copy config
    try:
        main_cur.execute("SELECT key, value FROM rating_inference_config")
        config_data = main_cur.fetchall()
        for row in config_data:
            model_cur.execute(
                "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
                (row['key'], row['value'])
            )
    except sqlite3.OperationalError:
        pass  # Config table doesn't exist in main DB

    # Check if main DB has old schema (tag_name) or new schema (tag_id)
    try:
        main_cur.execute("PRAGMA table_info(rating_tag_weights)")
        # PRAGMA table_info returns tuples: (cid, name, type, notnull, dflt_value, pk)
        # Access by index, not by key
        columns = {row[1]: row[2] for row in main_cur.fetchall()}
        
        if 'tag_name' in columns:
            # Old schema - migrate to new normalized schema
            main_cur.execute("SELECT tag_name, rating, weight, sample_count FROM rating_tag_weights")
            tag_weights = main_cur.fetchall()
            for row in tag_weights:
                tag_id = get_or_create_tag_id(model_conn, row['tag_name'])
                rating_id = get_or_create_rating_id(model_conn, row['rating'])
                model_cur.execute(
                    "INSERT OR REPLACE INTO rating_tag_weights (tag_id, rating_id, weight, sample_count) VALUES (?, ?, ?, ?)",
                    (tag_id, rating_id, row['weight'], row['sample_count'])
                )
        else:
            # New schema - copy with ID mapping
            main_cur.execute("""
                SELECT tw.tag_id, tw.rating_id, tw.weight, tw.sample_count,
                       t.name as tag_name, r.name as rating_name
                FROM rating_tag_weights tw
                JOIN tags t ON tw.tag_id = t.id
                JOIN ratings r ON tw.rating_id = r.id
            """)
            tag_weights = main_cur.fetchall()
            for row in tag_weights:
                tag_id = get_or_create_tag_id(model_conn, row['tag_name'])
                rating_id = get_or_create_rating_id(model_conn, row['rating_name'])
                model_cur.execute(
                    "INSERT OR REPLACE INTO rating_tag_weights (tag_id, rating_id, weight, sample_count) VALUES (?, ?, ?, ?)",
                    (tag_id, rating_id, row['weight'], row['sample_count'])
                )
    except sqlite3.OperationalError:
        tag_weights = []

    # Copy pair weights (similar logic for old vs new schema)
    try:
        main_cur.execute("PRAGMA table_info(rating_tag_pair_weights)")
        # PRAGMA table_info returns tuples: (cid, name, type, notnull, dflt_value, pk)
        # Access by index, not by key
        columns = {row[1]: row[2] for row in main_cur.fetchall()}
        
        if 'tag1' in columns:
            # Old schema
            main_cur.execute("SELECT tag1, tag2, rating, weight, co_occurrence_count FROM rating_tag_pair_weights")
            pair_weights = main_cur.fetchall()
            for row in pair_weights:
                tag1_id = get_or_create_tag_id(model_conn, row['tag1'])
                tag2_id = get_or_create_tag_id(model_conn, row['tag2'])
                rating_id = get_or_create_rating_id(model_conn, row['rating'])
                model_cur.execute(
                    "INSERT OR REPLACE INTO rating_tag_pair_weights (tag1_id, tag2_id, rating_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                    (tag1_id, tag2_id, rating_id, row['weight'], row['co_occurrence_count'])
                )
        else:
            # New schema
            main_cur.execute("""
                SELECT pw.tag1_id, pw.tag2_id, pw.rating_id, pw.weight, pw.co_occurrence_count,
                       t1.name as tag1_name, t2.name as tag2_name, r.name as rating_name
                FROM rating_tag_pair_weights pw
                JOIN tags t1 ON pw.tag1_id = t1.id
                JOIN tags t2 ON pw.tag2_id = t2.id
                JOIN ratings r ON pw.rating_id = r.id
            """)
            pair_weights = main_cur.fetchall()
            for row in pair_weights:
                tag1_id = get_or_create_tag_id(model_conn, row['tag1_name'])
                tag2_id = get_or_create_tag_id(model_conn, row['tag2_name'])
                rating_id = get_or_create_rating_id(model_conn, row['rating_name'])
                model_cur.execute(
                    "INSERT OR REPLACE INTO rating_tag_pair_weights (tag1_id, tag2_id, rating_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                    (tag1_id, tag2_id, rating_id, row['weight'], row['co_occurrence_count'])
                )
    except sqlite3.OperationalError:
        pair_weights = []

    # Copy metadata
    try:
        main_cur.execute("SELECT key, value, updated_at FROM rating_model_metadata")
        metadata = main_cur.fetchall()
        for row in metadata:
            model_cur.execute(
                "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                (row['key'], row['value'], row['updated_at'])
            )
    except sqlite3.OperationalError:
        pass  # Metadata table doesn't exist in main DB

    model_conn.commit()

    print(f"✅ Auto-migrated {len(tag_weights)} tag weights and {len(pair_weights)} pair weights from main DB")


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

    print(f"✅ Initialized model database: {db_path}")


def export_model_from_main_db(output_path: Optional[str] = None) -> str:
    """
    Export model weights from main database to a separate model database.
    Uses normalized schema with tag/rating IDs.

    Args:
        output_path: Where to save the model DB (uses default if None)

    Returns:
        str: Path to exported model database
    """
    from database import get_db_connection

    if output_path is None:
        output_path = get_model_db_path()

    # Initialize new model database with new schema
    init_model_database(output_path)

    # Copy data from main DB to model DB
    with get_db_connection() as main_conn:
        main_conn.row_factory = sqlite3.Row
        with sqlite3.connect(output_path, timeout=30.0) as model_conn:
            model_conn.row_factory = sqlite3.Row
            model_conn.execute("PRAGMA journal_mode = WAL")
            model_conn.execute("PRAGMA synchronous = NORMAL")

            # Use the migration function which handles both old and new schemas
            _migrate_weights_from_main_db(model_conn, main_conn)

    print(f"✅ Exported model to: {output_path}")

    return output_path


def import_model_to_main_db(model_path: Optional[str] = None) -> Dict:
    """
    Import model weights from a model database to the main database.

    Args:
        model_path: Path to model DB to import (uses default if None)

    Returns:
        dict: Statistics about imported data
    """
    from database import get_db_connection

    if model_path is None:
        model_path = get_model_db_path()

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model database not found: {model_path}")

    stats = {
        'config_items': 0,
        'tag_weights': 0,
        'pair_weights': 0,
        'metadata_items': 0
    }

    with sqlite3.connect(model_path, timeout=30.0) as model_conn:
        model_conn.row_factory = sqlite3.Row
        model_conn.execute("PRAGMA journal_mode = WAL")
        model_conn.execute("PRAGMA synchronous = NORMAL")
        with get_db_connection() as main_conn:
            model_cur = model_conn.cursor()
            main_cur = main_conn.cursor()

            # Import config
            model_cur.execute("SELECT key, value FROM rating_inference_config")
            config_data = model_cur.fetchall()
            for row in config_data:
                main_cur.execute(
                    "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
                    (row['key'], row['value'])
                )
            stats['config_items'] = len(config_data)

            # Clear old weights
            main_cur.execute("DELETE FROM rating_tag_weights")
            main_cur.execute("DELETE FROM rating_tag_pair_weights")

            # Import tag weights
            model_cur.execute("SELECT tag_name, rating, weight, sample_count FROM rating_tag_weights")
            tag_weights = model_cur.fetchall()
            for row in tag_weights:
                main_cur.execute(
                    "INSERT INTO rating_tag_weights (tag_name, rating, weight, sample_count) VALUES (?, ?, ?, ?)",
                    (row['tag_name'], row['rating'], row['weight'], row['sample_count'])
                )
            stats['tag_weights'] = len(tag_weights)

            # Import pair weights
            model_cur.execute("SELECT tag1, tag2, rating, weight, co_occurrence_count FROM rating_tag_pair_weights")
            pair_weights = model_cur.fetchall()
            for row in pair_weights:
                main_cur.execute(
                    "INSERT INTO rating_tag_pair_weights (tag1, tag2, rating, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                    (row['tag1'], row['tag2'], row['rating'], row['weight'], row['co_occurrence_count'])
                )
            stats['pair_weights'] = len(pair_weights)

            # Import metadata
            model_cur.execute("SELECT key, value, updated_at FROM rating_model_metadata")
            metadata = model_cur.fetchall()
            for row in metadata:
                main_cur.execute(
                    "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                    (row['key'], row['value'], row['updated_at'])
                )
            stats['metadata_items'] = len(metadata)

            main_conn.commit()

    print(f"✅ Imported model from: {model_path}")
    print(f"   Config items: {stats['config_items']}")
    print(f"   Tag weights: {stats['tag_weights']}")
    print(f"   Pair weights: {stats['pair_weights']}")

    return stats


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


def get_or_create_rating_id(conn: sqlite3.Connection, rating_name: str) -> int:
    """
    Get rating ID from name, creating it if it doesn't exist.
    
    Args:
        conn: Database connection
        rating_name: Rating name (e.g., 'rating:general')
        
    Returns:
        int: Rating ID
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM ratings WHERE name = ?", (rating_name,))
    row = cur.fetchone()
    if row:
        # Handle both Row objects and tuples
        return row['id'] if hasattr(row, 'keys') else row[0]
    
    cur.execute("INSERT INTO ratings (name) VALUES (?)", (rating_name,))
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


def get_rating_name(conn: sqlite3.Connection, rating_id: int) -> Optional[str]:
    """
    Get rating name from ID.
    
    Args:
        conn: Database connection
        rating_id: Rating ID
        
    Returns:
        str or None: Rating name if found
    """
    cur = conn.cursor()
    cur.execute("SELECT name FROM ratings WHERE id = ?", (rating_id,))
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
        cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_weights")
        tag_count = cur.fetchone()['cnt']

        cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_pair_weights")
        pair_count = cur.fetchone()['cnt']

        # Get metadata
        cur.execute("SELECT key, value FROM rating_model_metadata")
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
            'metadata': metadata
        }


def export_model_compressed(model_path: Optional[str] = None, output_path: Optional[str] = None) -> str:
    """
    Export model database to a gzip-compressed file for distribution.
    
    Args:
        model_path: Path to model DB to compress (uses default if None)
        output_path: Where to save compressed file (auto-generates if None)
        
    Returns:
        str: Path to compressed file
    """
    if model_path is None:
        model_path = get_model_db_path()
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model database not found: {model_path}")
    
    if output_path is None:
        output_path = model_path + '.gz'
    
    print(f"Compressing {model_path} to {output_path}...")
    
    with open(model_path, 'rb') as f_in:
        with gzip.open(output_path, 'wb', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    original_size = os.path.getsize(model_path)
    compressed_size = os.path.getsize(output_path)
    compression_ratio = (1 - compressed_size / original_size) * 100
    
    print(f"✅ Compressed model exported to: {output_path}")
    print(f"   Original size: {original_size / (1024*1024):.2f} MB")
    print(f"   Compressed size: {compressed_size / (1024*1024):.2f} MB")
    print(f"   Compression ratio: {compression_ratio:.1f}%")
    
    return output_path


def import_model_compressed(compressed_path: str, output_path: Optional[str] = None) -> str:
    """
    Import and decompress a gzip-compressed model database.
    
    Args:
        compressed_path: Path to .db.gz file
        output_path: Where to save decompressed database (uses default if None)
        
    Returns:
        str: Path to decompressed database
    """
    if not os.path.exists(compressed_path):
        raise FileNotFoundError(f"Compressed model not found: {compressed_path}")
    
    if output_path is None:
        # Remove .gz extension if present
        if compressed_path.endswith('.gz'):
            output_path = compressed_path[:-3]
        else:
            output_path = compressed_path + '.decompressed'
    
    print(f"Decompressing {compressed_path} to {output_path}...")
    
    with gzip.open(compressed_path, 'rb') as f_in:
        with open(output_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    compressed_size = os.path.getsize(compressed_path)
    decompressed_size = os.path.getsize(output_path)
    
    print(f"✅ Model decompressed to: {output_path}")
    print(f"   Compressed size: {compressed_size / (1024*1024):.2f} MB")
    print(f"   Decompressed size: {decompressed_size / (1024*1024):.2f} MB")
    
    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python rating_model_db.py init [path]           - Initialize new model DB")
        print("  python rating_model_db.py export [path]         - Export from main DB")
        print("  python rating_model_db.py import [path]         - Import to main DB")
        print("  python rating_model_db.py info [path]           - Show model info")
        print("  python rating_model_db.py compress [path]       - Compress model to .gz")
        print("  python rating_model_db.py decompress <gz_path>  - Decompress .gz model")
        sys.exit(1)

    command = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else None

    if command == 'init':
        init_model_database(path)
    elif command == 'export':
        export_model_from_main_db(path)
    elif command == 'import':
        import_model_to_main_db(path)
    elif command == 'info':
        info = get_model_info(path)
        print("\nModel Database Info:")
        for key, value in info.items():
            print(f"  {key}: {value}")
    elif command == 'compress':
        export_model_compressed(path)
    elif command == 'decompress':
        if not path:
            print("Error: decompress requires a path to compressed file")
            sys.exit(1)
        import_model_compressed(path)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

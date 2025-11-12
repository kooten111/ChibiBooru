# rating_model_db.py
"""
Separate model database management for rating inference weights.

This allows the model to be stored separately from the main database,
enabling distribution of pre-trained models and easier version control.
"""

import sqlite3
import os
from typing import Optional, Dict
from contextlib import contextmanager

# Default model database path
DEFAULT_MODEL_PATH = 'rating_model.db'


def get_model_db_path() -> str:
    """
    Get the current model database path from config or use default.

    Returns:
        str: Path to model database
    """
    # For now, use environment variable or default
    # Later can be stored in main DB config
    return os.environ.get('RATING_MODEL_PATH', DEFAULT_MODEL_PATH)


@contextmanager
def get_model_db_connection():
    """
    Context manager for model database connections.

    Yields:
        sqlite3.Connection: Database connection with row factory
    """
    db_path = get_model_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Configuration table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_inference_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)

    # Insert default config
    defaults = {
        'threshold_general': 0.5,
        'threshold_sensitive': 0.6,
        'threshold_questionable': 0.7,
        'threshold_explicit': 0.8,
        'min_confidence': 0.4,
        'pair_weight_multiplier': 1.5,
        'min_training_samples': 50,
        'min_pair_cooccurrence': 5,
        'min_tag_frequency': 10,
        'max_pair_count': 10000,
    }

    for key, value in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO rating_inference_config (key, value) VALUES (?, ?)",
            (key, value)
        )

    # Tag weights table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_tag_weights (
            tag_name TEXT NOT NULL,
            rating TEXT NOT NULL,
            weight REAL NOT NULL,
            sample_count INTEGER NOT NULL,
            PRIMARY KEY (tag_name, rating)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_rating ON rating_tag_weights(rating)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_weights_weight ON rating_tag_weights(weight DESC)")

    # Tag pair weights table
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_rating ON rating_tag_pair_weights(rating)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_weight ON rating_tag_pair_weights(weight DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rating_pair_weights_tags ON rating_tag_pair_weights(tag1, tag2)")

    # Model metadata table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_model_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

    print(f"✅ Initialized model database: {db_path}")


def export_model_from_main_db(output_path: Optional[str] = None) -> str:
    """
    Export model weights from main database to a separate model database.

    Args:
        output_path: Where to save the model DB (uses default if None)

    Returns:
        str: Path to exported model database
    """
    from database import get_db_connection

    if output_path is None:
        output_path = get_model_db_path()

    # Initialize new model database
    init_model_database(output_path)

    # Copy data from main DB to model DB
    with get_db_connection() as main_conn:
        with sqlite3.connect(output_path) as model_conn:
            main_cur = main_conn.cursor()
            model_cur = model_conn.cursor()

            # Copy config
            main_cur.execute("SELECT key, value FROM rating_inference_config")
            config_data = main_cur.fetchall()
            model_cur.executemany(
                "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
                [(row['key'], row['value']) for row in config_data]
            )

            # Copy tag weights
            main_cur.execute("SELECT tag_name, rating, weight, sample_count FROM rating_tag_weights")
            tag_weights = main_cur.fetchall()
            model_cur.executemany(
                "INSERT OR REPLACE INTO rating_tag_weights (tag_name, rating, weight, sample_count) VALUES (?, ?, ?, ?)",
                [(row['tag_name'], row['rating'], row['weight'], row['sample_count']) for row in tag_weights]
            )

            # Copy pair weights
            main_cur.execute("SELECT tag1, tag2, rating, weight, co_occurrence_count FROM rating_tag_pair_weights")
            pair_weights = main_cur.fetchall()
            model_cur.executemany(
                "INSERT OR REPLACE INTO rating_tag_pair_weights (tag1, tag2, rating, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                [(row['tag1'], row['tag2'], row['rating'], row['weight'], row['co_occurrence_count']) for row in pair_weights]
            )

            # Copy metadata
            main_cur.execute("SELECT key, value, updated_at FROM rating_model_metadata")
            metadata = main_cur.fetchall()
            model_cur.executemany(
                "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
                [(row['key'], row['value'], row['updated_at']) for row in metadata]
            )

            model_conn.commit()

    print(f"✅ Exported model to: {output_path}")
    print(f"   Tag weights: {len(tag_weights)}")
    print(f"   Pair weights: {len(pair_weights)}")

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

    with sqlite3.connect(model_path) as model_conn:
        model_conn.row_factory = sqlite3.Row
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

    with sqlite3.connect(model_path) as conn:
        conn.row_factory = sqlite3.Row
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


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python rating_model_db.py init [path]           - Initialize new model DB")
        print("  python rating_model_db.py export [path]         - Export from main DB")
        print("  python rating_model_db.py import [path]         - Import to main DB")
        print("  python rating_model_db.py info [path]           - Show model info")
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
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

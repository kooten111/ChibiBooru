#!/usr/bin/env python3
"""
One-time migration script to convert existing rating model databases
from the old schema (text columns) to the new normalized schema (integer IDs).

Usage:
    python scripts/migrate_rating_model.py <input_db_path> [output_db_path]

If output_db_path is not provided, it will create a backup of the input file
and update it in-place.
"""

import sqlite3
import sys
import os
import shutil
from datetime import datetime


def check_schema_version(conn: sqlite3.Connection) -> str:
    """
    Determine if database uses old schema (text) or new schema (IDs).
    
    Returns:
        'old': Uses tag_name/rating text columns
        'new': Uses tag_id/rating_id integer columns
        'unknown': Can't determine (no tables exist)
    """
    cur = conn.cursor()
    
    try:
        cur.execute("PRAGMA table_info(rating_tag_weights)")
        columns = {row[1]: row[2] for row in cur.fetchall()}
        
        if not columns:
            return 'unknown'
        
        if 'tag_name' in columns:
            return 'old'
        elif 'tag_id' in columns:
            return 'new'
        else:
            return 'unknown'
    except sqlite3.OperationalError:
        return 'unknown'


def migrate_database(input_path: str, output_path: str = None) -> None:
    """
    Migrate rating model database from old schema to new normalized schema.
    
    Args:
        input_path: Path to existing database with old schema
        output_path: Path for new database (or None to update in-place)
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input database not found: {input_path}")
    
    # Check input schema
    with sqlite3.connect(input_path) as conn:
        conn.row_factory = sqlite3.Row
        schema_version = check_schema_version(conn)
    
    if schema_version == 'new':
        print(f"✅ Database {input_path} already uses the new schema. No migration needed.")
        return
    
    if schema_version == 'unknown':
        print(f"⚠️  Database {input_path} has no rating tables. Nothing to migrate.")
        return
    
    # Determine output path
    if output_path is None:
        # In-place update: create backup first
        backup_path = input_path + f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        print(f"Creating backup: {backup_path}")
        shutil.copy2(input_path, backup_path)
        output_path = input_path
        in_place = True
    else:
        in_place = False
    
    print(f"Migrating {input_path} to {output_path}...")
    
    # Read data from old database
    with sqlite3.connect(input_path) as old_conn:
        old_conn.row_factory = sqlite3.Row
        old_cur = old_conn.cursor()
        
        # Read config
        print("  Reading config...")
        old_cur.execute("SELECT key, value FROM rating_inference_config")
        config_data = old_cur.fetchall()
        
        # Read tag weights
        print("  Reading tag weights...")
        old_cur.execute("SELECT tag_name, rating, weight, sample_count FROM rating_tag_weights")
        tag_weights = old_cur.fetchall()
        
        # Read pair weights
        print("  Reading pair weights...")
        old_cur.execute("SELECT tag1, tag2, rating, weight, co_occurrence_count FROM rating_tag_pair_weights")
        pair_weights = old_cur.fetchall()
        
        # Read metadata
        print("  Reading metadata...")
        try:
            old_cur.execute("SELECT key, value, updated_at FROM rating_model_metadata")
            metadata = old_cur.fetchall()
        except sqlite3.OperationalError:
            metadata = []
    
    # Create new database with normalized schema
    if in_place:
        # For in-place, we need to drop old tables and recreate
        with sqlite3.connect(output_path) as new_conn:
            new_cur = new_conn.cursor()
            
            print("  Dropping old tables...")
            new_cur.execute("DROP TABLE IF EXISTS rating_tag_weights")
            new_cur.execute("DROP TABLE IF EXISTS rating_tag_pair_weights")
            
            print("  Creating new normalized schema...")
            _create_new_schema(new_conn)
            
            print("  Migrating data...")
            _migrate_data(new_conn, config_data, tag_weights, pair_weights, metadata)
    else:
        # Create new file from scratch
        if os.path.exists(output_path):
            print(f"⚠️  Output file {output_path} already exists. Removing...")
            os.remove(output_path)
        
        with sqlite3.connect(output_path) as new_conn:
            print("  Creating new normalized schema...")
            _create_new_schema(new_conn)
            
            print("  Migrating data...")
            _migrate_data(new_conn, config_data, tag_weights, pair_weights, metadata)
    
    # Verify migration
    print("  Verifying migration...")
    with sqlite3.connect(output_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_weights")
        new_tag_count = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM rating_tag_pair_weights")
        new_pair_count = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM tags")
        tag_count = cur.fetchone()['cnt']
        
        cur.execute("SELECT COUNT(*) as cnt FROM ratings")
        rating_count = cur.fetchone()['cnt']
    
    print(f"\n✅ Migration complete!")
    print(f"   Output: {output_path}")
    print(f"   Tag weights: {len(tag_weights)} → {new_tag_count}")
    print(f"   Pair weights: {len(pair_weights)} → {new_pair_count}")
    print(f"   Unique tags: {tag_count}")
    print(f"   Unique ratings: {rating_count}")
    
    if in_place:
        print(f"   Backup saved: {backup_path}")


def _create_new_schema(conn: sqlite3.Connection) -> None:
    """Create the new normalized schema."""
    cur = conn.cursor()
    
    # Config table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_inference_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
        )
    """)
    
    # Metadata table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rating_model_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Lookup tables
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
    
    # Pre-populate ratings
    rating_values = ['rating:general', 'rating:sensitive', 'rating:questionable', 'rating:explicit']
    for rating in rating_values:
        cur.execute("INSERT OR IGNORE INTO ratings (name) VALUES (?)", (rating,))
    
    # Weight tables
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
    
    conn.commit()


def _get_or_create_id(conn: sqlite3.Connection, table: str, name: str) -> int:
    """Get or create an ID for a tag or rating."""
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    
    cur.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cur.lastrowid


def _migrate_data(conn: sqlite3.Connection, config_data, tag_weights, pair_weights, metadata) -> None:
    """Migrate data to new schema."""
    cur = conn.cursor()
    
    # Migrate config
    for row in config_data:
        cur.execute(
            "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
            (row['key'], row['value'])
        )
    
    # Add pruning_threshold if not present
    cur.execute(
        "INSERT OR IGNORE INTO rating_inference_config (key, value) VALUES (?, ?)",
        ('pruning_threshold', 0.0)
    )
    
    # Migrate tag weights
    for row in tag_weights:
        tag_id = _get_or_create_id(conn, 'tags', row['tag_name'])
        rating_id = _get_or_create_id(conn, 'ratings', row['rating'])
        cur.execute(
            "INSERT OR REPLACE INTO rating_tag_weights (tag_id, rating_id, weight, sample_count) VALUES (?, ?, ?, ?)",
            (tag_id, rating_id, row['weight'], row['sample_count'])
        )
    
    # Migrate pair weights
    for row in pair_weights:
        tag1_id = _get_or_create_id(conn, 'tags', row['tag1'])
        tag2_id = _get_or_create_id(conn, 'tags', row['tag2'])
        rating_id = _get_or_create_id(conn, 'ratings', row['rating'])
        cur.execute(
            "INSERT OR REPLACE INTO rating_tag_pair_weights (tag1_id, tag2_id, rating_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
            (tag1_id, tag2_id, rating_id, row['weight'], row['co_occurrence_count'])
        )
    
    # Migrate metadata
    for row in metadata:
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            (row['key'], row['value'], row['updated_at'])
        )
    
    conn.commit()


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_rating_model.py <input_db_path> [output_db_path]")
        print("")
        print("If output_db_path is not provided, the input file will be updated in-place")
        print("(after creating a timestamped backup).")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        migrate_database(input_path, output_path)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

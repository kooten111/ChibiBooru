
import sqlite3
import numpy as np
import os
import config
from typing import List, Tuple, Optional, Dict
from datetime import datetime

DB_FILE = "similarity.db"

def get_db_connection():
    """Create a database connection to the similarity database."""
    # Use config-like settings but simplified for this dedicated DB
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the similarity database."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        cur.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            image_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Index on created_at for incremental updates?
        cur.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_created_at ON embeddings(created_at)")
        
        conn.commit()
        print(f"[Similarity DB] Initialized {DB_FILE}")

def save_embedding(image_id: int, embedding: np.ndarray):
    """
    Save an embedding to the database.
    
    Args:
        image_id: ID of the image from main DB
        embedding: numpy array of the 1024-d vector
    """
    # Ensure it's float32 bytes
    if embedding.dtype != np.float32:
        embedding = embedding.astype(np.float32)
    
    binary_data = embedding.tobytes()
    
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO embeddings (image_id, embedding, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
            (image_id, binary_data)
        )
        conn.commit()

def get_embedding(image_id: int) -> Optional[np.ndarray]:
    """Get embedding for a single image."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT embedding FROM embeddings WHERE image_id = ?",
            (image_id,)
        ).fetchone()
        
        if row:
            return np.frombuffer(row['embedding'], dtype=np.float32)
        return None

def get_all_embeddings() -> Tuple[List[int], np.ndarray]:
    """
    Get all embeddings for building the FAISS index.
    
    Returns:
        (ids, embeddings_matrix)
        ids: List of image_ids corresponding to rows
        embeddings_matrix: numpy array of shape (N, 1024)
    """
    EXPECTED_DIM = 1024
    
    with get_db_connection() as conn:
        # Fetch all
        cursor = conn.execute("SELECT image_id, embedding FROM embeddings")
        rows = cursor.fetchall()
    
    if not rows:
        return [], np.array([], dtype=np.float32)
    
    # Filter out embeddings with wrong dimensions
    valid_rows = []
    invalid_count = 0
    
    for row in rows:
        vec = np.frombuffer(row['embedding'], dtype=np.float32)
        if len(vec) == EXPECTED_DIM:
            valid_rows.append((row['image_id'], vec))
        else:
            invalid_count += 1
    
    if invalid_count > 0:
        print(f"[Similarity DB] WARNING: Skipped {invalid_count} embeddings with invalid dimensions")
        print(f"[Similarity DB] Use 'Find Broken Images' in debug menu to clean these up")
    
    if not valid_rows:
        return [], np.array([], dtype=np.float32)
    
    ids = [r[0] for r in valid_rows]
    matrix = np.empty((len(valid_rows), EXPECTED_DIM), dtype=np.float32)
    
    for i, (_, vec) in enumerate(valid_rows):
        matrix[i] = vec
        
    return ids, matrix

def get_missing_embeddings_count(total_images: int) -> int:
    """Get number of images missing embeddings."""
    with get_db_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) as cnt FROM embeddings")
        count = cur.fetchone()['cnt']
        return max(0, total_images - count)

def get_all_embedding_ids() -> List[int]:
    """Get all image IDs that have embeddings."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT image_id FROM embeddings")
        return [row['image_id'] for row in cursor.fetchall()]

# Initialize on import? better to call explicitly
if not os.path.exists(DB_FILE):
    init_db()

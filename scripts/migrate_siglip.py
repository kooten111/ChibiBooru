#!/usr/bin/env python3
"""
SigLIP Migration Script

Migrates from legacy tagger-based semantic embeddings to SigLIP 2.
This script:
1. Backs up the existing similarity.db
2. Clears the embeddings table
3. Recomputes all embeddings using SigLIP
4. Saves to database

Usage:
    python scripts/migrate_siglip.py
    
Requires:
    - SigLIP model exported to models/SigLIP/model.onnx
    - ML worker running or able to start
"""
import os
import sys
import shutil
import time
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from database import get_db_connection
from services import similarity_db
from ml_worker.client import get_ml_worker_client, MLWorkerError


def get_all_image_paths():
    """Get all image IDs and file paths from main database."""
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT id, filepath FROM images 
            ORDER BY id
        """)
        # Prepend IMAGE_DIRECTORY to get full paths
        return [(row[0], os.path.join(config.IMAGE_DIRECTORY, row[1])) for row in cursor.fetchall()]


def backup_database():
    """Backup the similarity database."""
    db_path = Path(similarity_db.DB_FILE)
    if not db_path.exists():
        print("No existing database to backup.")
        return None
    
    backup_name = f"similarity.db.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_path = db_path.parent / backup_name
    
    print(f"Backing up database to {backup_path}")
    shutil.copy2(db_path, backup_path)
    print(f"✓ Backup created: {backup_path}")
    return backup_path


def clear_embeddings():
    """Clear all existing embeddings."""
    print("Clearing existing embeddings...")
    conn = similarity_db.get_db_connection()
    try:
        conn.execute("DELETE FROM embeddings")
        conn.commit()
        print("✓ Embeddings cleared")
    finally:
        conn.close()


def migrate_embeddings(batch_size: int = 50, skip_existing: bool = False):
    """
    Recompute all embeddings using SigLIP.
    
    Args:
        batch_size: Number of images to process before committing
        skip_existing: If True, skip images that already have embeddings
    """
    print("=" * 70)
    print("SigLIP Migration")
    print("=" * 70)
    print(f"Model type: {config.SEMANTIC_MODEL_TYPE}")
    print(f"Model path: {config.SEMANTIC_MODEL_PATH}")
    print(f"Image size: {config.SEMANTIC_IMAGE_SIZE}")
    print(f"Embedding dim: {config.SEMANTIC_EMBEDDING_DIM}")
    print()
    
    # Check model exists
    if not os.path.exists(config.SEMANTIC_MODEL_PATH):
        print(f"ERROR: Model not found at {config.SEMANTIC_MODEL_PATH}")
        print("Run 'python scripts/export_siglip.py' first")
        return False
    
    # Get all images
    images = get_all_image_paths()
    total = len(images)
    print(f"Found {total} images to process")
    
    if total == 0:
        print("No images to process.")
        return True
    
    # Get existing embeddings if skipping
    existing_ids = set()
    if skip_existing:
        ids, _ = similarity_db.get_all_embeddings()
        existing_ids = set(ids)
        print(f"Skipping {len(existing_ids)} images with existing embeddings")
    
    # Get ML worker client
    client = get_ml_worker_client()
    
    # Process images
    success_count = 0
    error_count = 0
    skipped_count = 0
    start_time = time.time()
    
    print()
    print("Processing...")
    
    for i, (image_id, filepath) in enumerate(images):
        # Skip if existing
        if image_id in existing_ids:
            skipped_count += 1
            continue
            
        # Check file exists
        if not os.path.exists(filepath):
            print(f"  [SKIP] File not found: {filepath}")
            error_count += 1
            continue
        
        try:
            # Compute embedding
            result = client.compute_similarity(
                image_path=filepath,
                model_path=config.SEMANTIC_MODEL_PATH,
                model_type=config.SEMANTIC_MODEL_TYPE,
                image_size=config.SEMANTIC_IMAGE_SIZE,
                embedding_dim=config.SEMANTIC_EMBEDDING_DIM
            )
            
            embedding = result['embedding']
            
            # Save to database
            import numpy as np
            similarity_db.save_embedding(image_id, np.array(embedding, dtype=np.float32))
            
            success_count += 1
            
        except MLWorkerError as e:
            print(f"  [ERROR] {image_id}: {e}")
            error_count += 1
        except Exception as e:
            print(f"  [ERROR] {image_id}: {e}")
            error_count += 1
        
        # Progress
        processed = i + 1
        if processed % 10 == 0 or processed == total:
            elapsed = time.time() - start_time
            rate = success_count / elapsed if elapsed > 0 else 0
            remaining = (total - processed) / rate if rate > 0 else 0
            
            pct = processed / total * 100
            print(f"\r  [{processed}/{total}] {pct:.1f}% | "
                  f"Success: {success_count} | Errors: {error_count} | "
                  f"Rate: {rate:.1f}/s | ETA: {remaining:.0f}s", end='', flush=True)
    
    print()
    print()
    print("=" * 70)
    print("Migration Complete")
    print("=" * 70)
    print(f"Total images: {total}")
    print(f"Successfully processed: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Skipped (existing): {skipped_count}")
    print(f"Time: {time.time() - start_time:.1f}s")
    
    return error_count == 0


def main():
    print("=" * 70)
    print("SigLIP Embedding Migration Script")
    print("=" * 70)
    print()
    
    # Initialize database
    similarity_db.init_db()
    
    # Backup
    print("Step 1: Backup database")
    backup_path = backup_database()
    
    # Ask to continue
    if backup_path:
        response = input("\nProceed with migration? This will clear existing embeddings. [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Aborted.")
            return
    
    # Clear embeddings
    print("\nStep 2: Clear existing embeddings")
    clear_embeddings()
    
    # Migrate
    print("\nStep 3: Compute SigLIP embeddings")
    success = migrate_embeddings()
    
    if success:
        print("\n✓ Migration successful!")
        print(f"  Backup saved at: {backup_path}")
    else:
        print("\n⚠ Migration completed with errors.")
        print(f"  To rollback: cp {backup_path} data/similarity.db")


if __name__ == "__main__":
    main()

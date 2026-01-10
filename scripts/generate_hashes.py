#!/usr/bin/env python3
"""
Standalone script to generate perceptual hashes for images missing them.

This script replicates the functionality of the "Gen Hashes" button but uses
ProcessPoolExecutor for better CPU utilization across multiple cores.
"""

import os
import sys
import argparse
import multiprocessing
import concurrent.futures
from typing import Dict, List, Optional

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import project modules
import config
from database import get_db_connection
from services import similarity_service
from utils.file_utils import get_thumbnail_path


def _process_semantic_worker(row: dict) -> dict:
    """
    Process a single image for semantic embedding generation.
    
    This is a top-level function (required for ThreadPoolExecutor).
    Note: Semantic embeddings use ThreadPoolExecutor (not ProcessPoolExecutor)
    because the model should be shared across threads, not reloaded per process.
    
    Args:
        row: Dictionary with image data (id, filepath, md5, phash, colorhash)
        
    Returns:
        Dictionary with processing results
    """
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'semantic_generated': False,
        'errors': []
    }
    
    try:
        import time
        start_time = time.time()
        filepath = row['filepath']
        
        # Zip handling
        full_path = os.path.join("static/images", filepath)
        if filepath.lower().endswith('.zip'):
            thumb_rel = get_thumbnail_path(filepath)
            if thumb_rel != filepath:
                full_path = os.path.join("static", thumb_rel)
        
        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result
        
        # Use semantic engine (shared across threads)
        engine = similarity_service.get_semantic_engine()
        # Ensure loaded
        if not engine.ml_worker_ready:
            print(f"[Semantic Worker {row['id']}] Loading model (latency expected)...")
            engine.load_model()
        
        embedding = engine.get_embedding(full_path)
        duration = time.time() - start_time
        
        if embedding is not None:
            result['new_embedding'] = embedding
            result['semantic_generated'] = True
            result['success'] = True
            print(f"[Semantic Worker {row['id']}] Processed {filepath} in {duration:.2f}s")
        else:
            result['errors'].append(f"Failed to generate embedding")
            print(f"[Semantic Worker {row['id']}] Failed to embed {filepath} in {duration:.2f}s")
            
    except Exception as e:
        result['errors'].append(f"Semantic error: {e}")
        print(f"[Semantic Worker {row['id']}] Exception: {e}")
        
    return result


def _process_image_worker(row: dict) -> dict:
    """
    Process a single image for hash generation.
    
    This is a top-level function (required for ProcessPoolExecutor pickling).
    Each worker process will have its own database connection.
    
    Args:
        row: Dictionary with image data (id, filepath, md5, phash, colorhash)
        
    Returns:
        Dictionary with processing results
    """
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'phash_generated': False,
        'colorhash_generated': False,
        'errors': []
    }
    
    try:
        filepath = row['filepath']
        md5 = row['md5']
        full_path = os.path.join("static/images", filepath)
        
        # Special handling for ZIP files (animations) -> use thumbnail for hash
        if filepath.lower().endswith('.zip'):
            thumb_rel = get_thumbnail_path(filepath)
            if thumb_rel != filepath:
                full_path = os.path.join("static", thumb_rel)
        
        # Check if file exists
        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result
        
        updated_something = False
        
        # 1. Compute pHash if missing
        if not row['phash']:
            try:
                phash = similarity_service.compute_phash_for_file(full_path, md5)
                if phash:
                    result['new_phash'] = phash
                    result['phash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"pHash error: {e}")
        
        # 2. Compute ColorHash if missing
        if not row['colorhash']:
            try:
                chash = similarity_service.compute_colorhash_for_file(full_path)
                if chash:
                    result['new_colorhash'] = chash
                    result['colorhash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"ColorHash error: {e}")
        
        result['success'] = updated_something
        
    except Exception as e:
        result['errors'].append(f"Worker error: {e}")
        
    return result


def _bulk_save_hashes(results: List[Dict]):
    """
    Save a batch of computed hashes to the database in a single transaction.
    
    This is a wrapper around the similarity_service function to ensure
    we're using the correct database connection context.
    """
    if not results:
        return
    
    try:
        # Separate semantic updates (custom DB) from main DB updates
        semantic_updates = []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for res in results:
                # Update main DB hashes
                if 'new_phash' in res:
                    cursor.execute("UPDATE images SET phash = ? WHERE id = ?", (res['new_phash'], res['id']))
                
                if 'new_colorhash' in res:
                    cursor.execute("UPDATE images SET colorhash = ? WHERE id = ?", (res['new_colorhash'], res['id']))
                
                # Collect semantic embeddings (if any)
                if 'new_embedding' in res:
                    semantic_updates.append((res['id'], res['new_embedding']))
            
            conn.commit()
        
        # Save semantic embeddings if any (these use their own DB/file structure)
        if semantic_updates:
            from services import similarity_db
            for img_id, embedding in semantic_updates:
                similarity_db.save_embedding(img_id, embedding)
                
    except Exception as e:
        print(f"[Hash Gen] Error in bulk save: {e}")


def generate_missing_hashes(batch_size: int = 100, max_workers: Optional[int] = None, progress_callback=None, verbose: bool = False) -> Dict:
    """
    Generate perceptual hashes for images that don't have them.
    
    Uses ProcessPoolExecutor for parallel execution across multiple CPU cores.
    
    Args:
        batch_size: Number of images to process at a time (per chunk)
        max_workers: Number of worker processes (defaults to CPU count)
        progress_callback: Optional callback(current, total) for progress updates
        
    Returns:
        Dictionary with counts of processed, successful, failed, total
    """
    total_stats = {'processed': 0, 'success': 0, 'failed': 0, 'total': 0}
    
    # 1. Estimate total missing count for progress reporting
    # Exclude video files - only process image files and zip animations
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # First, get total counts for debugging
            cursor.execute("SELECT COUNT(*) FROM images")
            total_images = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE phash IS NULL OR colorhash IS NULL")
            missing_any_hash = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE phash IS NULL")
            missing_phash = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM images WHERE colorhash IS NULL")
            missing_colorhash = cursor.fetchone()[0]
            
            if verbose:
                print(f"[Hash Gen] Database stats:")
                print(f"  Total images: {total_images}")
                print(f"  Missing phash: {missing_phash}")
                print(f"  Missing colorhash: {missing_colorhash}")
                print(f"  Missing any hash: {missing_any_hash}")
            
            # Filter out video files - only process images and zip files
            video_extensions = config.SUPPORTED_VIDEO_EXTENSIONS
            if video_extensions:
                exclude_video_conditions = " AND ".join([
                    f"LOWER(filepath) NOT LIKE '%{ext.lower()}'" for ext in video_extensions
                ])
                exclude_clause = f"AND {exclude_video_conditions}"
                
                if verbose:
                    # Count videos with missing hashes
                    video_conditions = " OR ".join([
                        f"LOWER(filepath) LIKE '%{ext.lower()}'" for ext in video_extensions
                    ])
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM images 
                        WHERE (phash IS NULL OR colorhash IS NULL)
                        AND ({video_conditions})
                    """)
                    video_missing_count = cursor.fetchone()[0]
                    print(f"  Missing hashes (videos only): {video_missing_count}")
                    print(f"  Missing hashes (non-videos): {missing_any_hash - video_missing_count}")
            else:
                exclude_clause = ""
            
            cursor.execute(f"""
                SELECT COUNT(*) FROM images 
                WHERE (phash IS NULL OR colorhash IS NULL)
                {exclude_clause}
            """)
            missing_visual_count = cursor.fetchone()[0]
            
            # Also count missing semantic embeddings if available
            missing_semantic_count = 0
            if similarity_service.SEMANTIC_AVAILABLE:
                try:
                    from services import similarity_db
                    cursor.execute("SELECT id FROM images")
                    all_db_ids = set(row[0] for row in cursor.fetchall())
                    embedded_ids = set(similarity_db.get_all_embedding_ids())
                    missing_semantic_count = len(all_db_ids - embedded_ids)
                except Exception as e:
                    print(f"[Hash Gen] Error counting missing semantic embeddings: {e}")
            
            # Total tasks to process
            total_stats['total'] = missing_visual_count + missing_semantic_count
            
            if total_stats['total'] == 0:
                if missing_any_hash > 0:
                    print(f"[Hash Gen] Note: {missing_any_hash} video file(s) missing hashes (excluded from processing)")
                print("[Hash Gen] No images missing hashes. All done!")
                return total_stats
                
    except Exception as e:
        print(f"[Hash Gen] Error estimating total missing hashes: {e}")
        total_stats['total'] = 1000  # Fallback
    
    # Determine number of workers
    if max_workers is None:
        try:
            max_workers = config.MAX_WORKERS
            if max_workers <= 0:
                max_workers = max(1, multiprocessing.cpu_count() - 1)
        except AttributeError:
            max_workers = max(1, multiprocessing.cpu_count() - 1)
    
    print(f"[Hash Gen] Starting parallel hash generation with {max_workers} workers.")
    print(f"[Hash Gen] Total images to process: {total_stats['total']}")
    print(f"[Hash Gen] Batch size: {batch_size}")
    if similarity_service.SEMANTIC_AVAILABLE:
        print(f"[Hash Gen] Semantic embeddings: Enabled")
    else:
        print(f"[Hash Gen] Semantic embeddings: Disabled")
    
    # Track failed IDs to avoid infinite loops
    failed_ids = set()
    
    # Use ProcessPoolExecutor for CPU-bound visual hash processing
    # Use ThreadPoolExecutor for semantic embeddings (to share model across threads)
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as visual_executor:
        semantic_executor = None
        if similarity_service.SEMANTIC_AVAILABLE:
            semantic_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        
        try:
            while True:
                # Fetch candidates that need hashes
                # Exclude video files - only process image files and zip animations
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    # Exclude known failures
                    exclude_clause = ""
                    params = []
                    if failed_ids:
                        placeholders = ','.join('?' * len(failed_ids))
                        exclude_clause = f"AND id NOT IN ({placeholders})"
                        params.extend(list(failed_ids))
                    
                    # Exclude video files
                    video_extensions = config.SUPPORTED_VIDEO_EXTENSIONS
                    if video_extensions:
                        exclude_video_conditions = " AND ".join([
                            f"LOWER(filepath) NOT LIKE '%{ext.lower()}'" for ext in video_extensions
                        ])
                        exclude_video_clause = f"AND {exclude_video_conditions}"
                    else:
                        exclude_video_clause = ""
                    
                    params.append(batch_size)
                        
                    cursor.execute(f"""
                        SELECT id, filepath, md5, phash, colorhash
                        FROM images
                        WHERE (phash IS NULL OR colorhash IS NULL)
                        {exclude_video_clause}
                        {exclude_clause}
                        LIMIT ?
                    """, params)
                    missing_hashes = [dict(row) for row in cursor.fetchall()]
                
                # Also fetch semantic candidates if available
                missing_semantic = []
                if similarity_service.SEMANTIC_AVAILABLE and semantic_executor:
                    try:
                        from services import similarity_db
                        # Get current state
                        embedded_ids = set(similarity_db.get_all_embedding_ids())
                        embedded_ids.update(failed_ids)  # Don't retry failed ones
                        
                        # Compute missing IDs efficiently
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM images")
                            all_db_ids = set(row[0] for row in cursor.fetchall())
                        
                        # Exclude images already being processed for visual hashes
                        current_batch_ids = {r['id'] for r in missing_hashes}
                        
                        candidates_ids = list(all_db_ids - embedded_ids - current_batch_ids)
                        candidates_ids.sort(reverse=True)
                        
                        target_ids = candidates_ids[:batch_size]
                        
                        if target_ids:
                            target_placeholders = ','.join('?' * len(target_ids))
                            params = tuple(target_ids)
                            
                            with get_db_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute(f"""
                                    SELECT id, filepath, md5, phash, colorhash
                                    FROM images 
                                    WHERE id IN ({target_placeholders})
                                """, params)
                                missing_semantic = [dict(row) for row in cursor.fetchall()]
                                
                    except Exception as e:
                        print(f"[Hash Gen] Error finding missing semantic: {e}")
                
                if not missing_hashes and not missing_semantic:
                    break
                    
                # Submit all tasks
                futures = {}
                
                # Submit visual hash tasks to ProcessPoolExecutor
                for row in missing_hashes:
                    future = visual_executor.submit(_process_image_worker, row)
                    futures[future] = ('visual', row)
                
                # Submit semantic tasks to ThreadPoolExecutor
                if semantic_executor:
                    for row in missing_semantic:
                        future = semantic_executor.submit(_process_semantic_worker, row)
                        futures[future] = ('semantic', row)
                
                # Collect results
                results_buffer = []
                
                for future in concurrent.futures.as_completed(futures):
                    task_type, row = futures[future]
                    try:
                        result = future.result()
                        
                        total_stats['processed'] += 1
                        if result['success']:
                            total_stats['success'] += 1
                            results_buffer.append(result)
                        else:
                            total_stats['failed'] += 1
                            failed_ids.add(result['id'])
                        
                        if result.get('errors'):
                            error_msg = result['errors'][0]
                            if "File not found" in error_msg:
                                print(f"[Hash Gen] Warning: {result['filepath']} - {error_msg}")
                            else:
                                print(f"[Hash Gen] Error processing {result['filepath']}: {error_msg}")
                        
                        if progress_callback:
                            progress_callback(total_stats['processed'], total_stats['total'])
                        else:
                            # Simple progress output
                            if total_stats['processed'] % 10 == 0 or total_stats['processed'] == total_stats['total']:
                                print(f"[Hash Gen] Progress: {total_stats['processed']}/{total_stats['total']} "
                                      f"(✓ {total_stats['success']}, ✗ {total_stats['failed']})")
                            
                    except Exception as e:
                        print(f"[Hash Gen] Exception in {task_type} result: {e}")
                        total_stats['failed'] += 1
                        failed_ids.add(row['id'])
                
                # Bulk save
                if results_buffer:
                    _bulk_save_hashes(results_buffer)
                    print(f"[Hash Gen] Batch complete. Saved {len(results_buffer)} results.")
                    
                    # Rebuild semantic index if we saved any new embeddings
                    has_new_embeddings = any('new_embedding' in r for r in results_buffer)
                    if has_new_embeddings and similarity_service.SEMANTIC_AVAILABLE:
                        print("[Hash Gen] Rebuilding semantic index with new embeddings...")
                        similarity_service.get_semantic_index().rebuild()
        
        finally:
            if semantic_executor:
                semantic_executor.shutdown(wait=True)
    
    return total_stats


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Generate perceptual hashes for images missing them (multiprocessing version)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of images to process per batch (default: 100)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='Number of worker processes (default: uses config.MAX_WORKERS or CPU count - 1)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed database statistics'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Hash Generation Script (Multiprocessing)")
    print("=" * 60)
    print()
    
    # Run hash generation
    stats = generate_missing_hashes(
        batch_size=args.batch_size,
        max_workers=args.workers,
        verbose=args.verbose
    )
    
    print()
    print("=" * 60)
    print("Hash Generation Complete")
    print("=" * 60)
    print(f"Total processed: {stats['processed']}")
    print(f"Successfully generated: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total images: {stats['total']}")
    print()
    
    if stats['failed'] > 0:
        print(f"Warning: {stats['failed']} images failed to process. Check logs above for details.")
        sys.exit(1)
    else:
        print("All images processed successfully!")
        sys.exit(0)


if __name__ == '__main__':
    main()

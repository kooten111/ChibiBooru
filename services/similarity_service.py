"""
Perceptual Hash Similarity Service

Provides visual similarity detection using perceptual hashing algorithms.
This module is the main public API. Implementation is split into:
- services.similarity.hashing - hash computation
- services.similarity.semantic - FAISS/semantic search
"""
import os
import time
from typing import Optional, List, Dict, Tuple
from PIL import Image, UnidentifiedImageError
import config
from database import get_db_connection, models
from utils.file_utils import get_thumbnail_path
from services import similarity_db

# Import from new modules (these are the implementations)
from services.similarity.hashing import (
    compute_phash,
    compute_colorhash,
    compute_phash_for_video,
    compute_colorhash_for_video,
    compute_phash_for_zip_animation,
    compute_phash_for_file,
    compute_colorhash_for_file,
    hamming_distance,
    hash_similarity_score,
)
from services.similarity.semantic import (
    SEMANTIC_AVAILABLE,
    FAISS_AVAILABLE,
    ML_WORKER_AVAILABLE,
    NUMPY_AVAILABLE,
    SemanticIndex,
    get_semantic_index,
    SemanticBackend,
    MLWorkerSemanticBackend, 
    SemanticSearchEngine,
    get_semantic_engine,
    set_semantic_backend,
    find_semantic_similar as _find_semantic_similar,
)

# Re-import numpy if available (needed for batch operations)
try:
    import numpy as np
except ImportError:
    np = None


def _log(message: str, level: str = "info"):
    """Centralized logging helper."""
    try:
        from services import monitor_service
        monitor_service.add_log(f"[Similarity] {message}", level)
    except Exception:
        print(f"[Similarity] {message}")


# Wrapper for find_semantic_similar to use the local _get_family_filepaths helper
def find_semantic_similar(filepath: str, limit: int = 20, exclude_self: bool = True, exclude_family: bool = False) -> List[Dict]:
    """Find semantically similar images using local FAISS index."""
    return _find_semantic_similar(
        filepath=filepath,
        limit=limit,
        exclude_self=exclude_self,
        exclude_family=exclude_family,
        get_family_func=_get_family_filepaths if exclude_family else None
    )


# ============================================================================
# Database Operations
# ============================================================================


def get_image_phash(filepath: str) -> Optional[str]:
    """Get the stored phash for an image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT phash FROM images WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        return row['phash'] if row else None


def update_image_phash(filepath: str, phash: str) -> bool:
    """Update the phash for an image in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE images SET phash = ? WHERE filepath = ?",
                (phash, filepath)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"[Similarity] Error updating phash: {e}")
        return False


def get_image_colorhash(filepath: str) -> Optional[str]:
    """Get the stored colorhash for an image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT colorhash FROM images WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        return row['colorhash'] if row else None


def update_image_colorhash(filepath: str, colorhash: str) -> bool:
    """Update the colorhash for an image in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE images SET colorhash = ? WHERE filepath = ?",
                (colorhash, filepath)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        from services import monitor_service
        monitor_service.add_log(f"Error updating colorhash: {e}", "error")
        return False


def _ensure_image_hashes(filepath: str) -> tuple:
    """
    Ensure hashes exist for an image, computing them if missing.
    
    Args:
        filepath: Relative path to the image (without 'images/' prefix)
        
    Returns:
        Tuple of (phash, colorhash) - either may be None if computation fails
    """
    ref_phash = get_image_phash(filepath)
    ref_colorhash = get_image_colorhash(filepath)
    
    full_path = os.path.join("static/images", filepath)
    
    if not ref_phash and os.path.exists(full_path):
        ref_phash = compute_phash(full_path)
        if ref_phash:
            update_image_phash(filepath, ref_phash)
            
    if not ref_colorhash and os.path.exists(full_path):
        chash = compute_colorhash(full_path)
        if chash:
            ref_colorhash = chash
            update_image_colorhash(filepath, chash)
    
    return ref_phash, ref_colorhash


def _calculate_similarity_score(
    ref_phash: str,
    ref_colorhash: Optional[str],
    candidate_phash: str,
    candidate_colorhash: Optional[str],
    color_weight: float
) -> tuple:
    """
    Calculate hybrid similarity score between reference and candidate.
    
    Args:
        ref_phash: Reference image perceptual hash
        ref_colorhash: Reference image color hash (optional)
        candidate_phash: Candidate image perceptual hash
        candidate_colorhash: Candidate image color hash (optional)
        color_weight: Weight of color similarity (0.0 = only pHash, 1.0 = only ColorHash)
        
    Returns:
        Tuple of (final_score, effective_distance)
    """
    # pHash Score (Structure)
    phash_score = hash_similarity_score(ref_phash, candidate_phash)
    
    # ColorHash Score (Color)
    color_score = 0.0
    if candidate_colorhash and ref_colorhash:
        color_score = hash_similarity_score(ref_colorhash, candidate_colorhash)
    
    # Hybrid Score
    final_score = (phash_score * (1.0 - color_weight)) + (color_score * color_weight)
    
    # Convert to effective distance (0-64 scale)
    effective_distance = 64.0 * (1.0 - final_score)
    
    return final_score, effective_distance


def find_similar_images(
    filepath: str,
    threshold: int = 10,
    limit: int = 50,
    exclude_family: bool = False,
    color_weight: float = 0.0
) -> List[Dict]:
    """
    Find images visually similar to the given image.
    
    Args:
        filepath: Path to the reference image (relative, without 'images/' prefix)
        threshold: Maximum Hamming distance (lower = stricter, 0-64)
        limit: Maximum number of results
        exclude_family: If True, exclude images in the same parent/child chain
        color_weight: Weight of color similarity (0.0 = only pHash, 1.0 = only ColorHash)
        
    Returns:
        List of similar images with distance and similarity score
    """
    try:
        # Ensure reference hashes exist
        ref_phash, ref_colorhash = _ensure_image_hashes(filepath)
        
        if not ref_phash:
            return []
        
        # Get family exclusion set
        family_filepaths = set()
        if exclude_family:
            try:
                family_filepaths = _get_family_filepaths(filepath)
            except Exception as e:
                print(f"[Similarity] Error getting family for {filepath}: {e}")
        
        # Get all candidate images with hashes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filepath, phash, colorhash
                FROM images
                WHERE phash IS NOT NULL AND filepath != ?
            """, (filepath,))
            candidates = cursor.fetchall()
        
        # Calculate similarity scores
        similar = []
        for row in candidates:
            try:
                if exclude_family and row['filepath'] in family_filepaths:
                    continue
                
                final_score, effective_distance = _calculate_similarity_score(
                    ref_phash, ref_colorhash,
                    row['phash'], row['colorhash'],
                    color_weight
                )
                
                if effective_distance <= threshold:
                    similar.append({
                        'path': f"images/{row['filepath']}",
                        'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
                        'distance': int(effective_distance),
                        'score': float(final_score),
                        'similarity': float(final_score),
                        'match_type': 'visual'
                    })
            except Exception as e:
                from services import monitor_service
                monitor_service.add_log(f"Error processing candidate {row['filepath']}: {e}", "warning")
                continue
        
        similar.sort(key=lambda x: x['distance'])
        return similar[:limit]

    except Exception as e:
        import traceback
        traceback.print_exc()
        from services import monitor_service
        monitor_service.add_log(f"Critical error in find_similar_images: {e}", "error")
        return []


def find_all_duplicate_groups(threshold: int = 5) -> List[List[Dict]]:
    """
    Find all groups of visually similar/duplicate images.
    
    Args:
        threshold: Maximum Hamming distance to consider duplicates
        
    Returns:
        List of groups, where each group is a list of similar images
    """
    # Get all images with hashes
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filepath, phash, md5
            FROM images
            WHERE phash IS NOT NULL
            ORDER BY id
        """)
        all_images = cursor.fetchall()
    
    if not all_images:
        return []
    
    # Build groups using union-find approach
    visited = set()
    groups = []
    
    for i, img1 in enumerate(all_images):
        if img1['id'] in visited:
            continue
        
        group = [{
            'id': img1['id'],
            'path': f"images/{img1['filepath']}",
            'thumb': get_thumbnail_path(f"images/{img1['filepath']}"),
            'md5': img1['md5'],
            'distance': 0
        }]
        visited.add(img1['id'])
        
        for img2 in all_images[i+1:]:
            if img2['id'] in visited:
                continue
            
            distance = hamming_distance(img1['phash'], img2['phash'])
            if distance <= threshold:
                group.append({
                    'id': img2['id'],
                    'path': f"images/{img2['filepath']}",
                    'thumb': get_thumbnail_path(f"images/{img2['filepath']}"),
                    'md5': img2['md5'],
                    'distance': distance
                })
                visited.add(img2['id'])
        
        if len(group) > 1:
            groups.append(group)
    
    return groups


# ============================================================================
# Batch Operations
# ============================================================================

# Worker state management removed - ThreadPoolExecutor shares memory space

def _process_semantic_single(row: dict) -> dict:
    """
    Process a single image for semantic embedding.
    Designed to run in a THREAD (ProcessPoolExecutor would re-load model).
    """
    import os
    # Uses the main process global semantic engine (shared memory)
    # We don't import _worker_semantic_engine here, we use the module level one via get_semantic_engine or direct
    # But wait, we are in the same process, so direct access is fine.
    
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'semantic_generated': False,
        'errors': []
    }
    
    try:
        start_time = time.time()
        filepath = row['filepath']
        
        # Zip handling
        full_path = os.path.join("static/images", filepath)
        if filepath.lower().endswith('.zip'):
             from utils.file_utils import get_thumbnail_path
             thumb_rel = get_thumbnail_path(filepath)
             if thumb_rel != filepath:
                 full_path = os.path.join("static", thumb_rel)

        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result

        # Use global engine (which is thread-safe for inference usually, or we lock if needed, 
        # but ORT is generally thread safe for independent runs)
        engine = get_semantic_engine()
        # Ensure loaded
        if not engine.ml_worker_ready:
            # Load explicitly if not loaded (main thread should have loaded it, but self-repair is good)
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
             print(f"[Semantic Worker {row['id']}] Failed to embed {filepath} in {duration:.2f}s")
             
    except Exception as e:
        result['errors'].append(f"Semantic error: {e}")
        print(f"[Semantic Worker {row['id']}] Exception: {e}")
        
    return result


def _process_single_image_threaded(row: dict) -> dict:
    """
    Process a single image for hash generation in a thread.
    This is the threaded version that doesn't need to re-import modules.
    """
    import os
    from utils.file_utils import get_thumbnail_path
    
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'phash_generated': False,
        'colorhash_generated': False,
        'semantic_generated': False,
        'errors': []
    }
    
    try:
        filepath = row['filepath']
        md5 = row['md5']
        full_path = os.path.join("static/images", filepath)
        
        # Special handling for ZIP files (animations) -> use thumbnail for hash/embedding
        if filepath.lower().endswith('.zip'):
             thumb_rel = get_thumbnail_path(filepath)
             # get_thumbnail_path returns relative path like 'thumbnails/...' or original 'filepath' if not found
             if thumb_rel != filepath:
                 # Use the thumbnail instead
                 full_path = os.path.join("static", thumb_rel)
        
        # Check if file exists
        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result

        updated_something = False
        
        # 1. Compute pHash if missing
        if not row['phash']:
            try:
                phash = compute_phash_for_file(full_path, md5)
                if phash:
                    result['new_phash'] = phash
                    result['phash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"pHash error: {e}")
        
        # 2. Compute ColorHash if missing
        if not row['colorhash']:
            try:
                chash = compute_colorhash_for_file(full_path)
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
                
                # Collect semantic embeddings
                if 'new_embedding' in res:
                    semantic_updates.append((res['id'], res['new_embedding']))
            
            conn.commit()

        # Save semantic embeddings if any (these use their own DB/file structure)
        if semantic_updates:
            for img_id, embedding in semantic_updates:
                similarity_db.save_embedding(img_id, embedding)
                
    except Exception as e:
        print(f"[Similarity] Error in bulk save: {e}")


async def run_hash_generation_task(task_id: str, manager) -> Dict:
    """
    Async background task for generating hashes with progress updates.
    
    Args:
        task_id: The task identifier for progress tracking
        manager: The background task manager instance
        
    Returns:
        Dictionary with success, failed, and total counts
    """
    import asyncio
    import time
    from services import monitor_service
    
    monitor_service.add_log("Starting hash generation...", "info")
    
    loop = asyncio.get_running_loop()
    last_update_time = 0
    
    def progress_callback(current, total):
        nonlocal last_update_time
        current_time = time.time()
        
        # Throttle updates: only update if 0.1s passed OR it's the final update
        if (current_time - last_update_time > 0.1) or (current >= total):
            last_update_time = current_time
            asyncio.run_coroutine_threadsafe(
                manager.update_progress(task_id, current, total, "Generating hashes..."), 
                loop
            )
    
    # Run synchronous service function in thread
    stats = await asyncio.to_thread(
        generate_missing_hashes, 
        batch_size=100, 
        progress_callback=progress_callback
    )
    
    success = stats['success']
    failed = stats['failed']
    total = stats['total']
    
    result_msg = f"✓ Hash generation complete: {success} generated, {failed} failed"
    monitor_service.add_log(result_msg, "success")
    
    # Update task to 100%
    await manager.update_progress(task_id, total, total, "Complete")
    
    return {
        'success': success,
        'failed': failed,
        'total': total,
        'message': f"Generated {success} hashes ({failed} failed)"
    }


# ---------------------------------------------------------------------------
# Re-hash workers (module-level for pickling by ProcessPoolExecutor)
# ---------------------------------------------------------------------------

def _rehash_worker(args):
    """
    Process-pool worker: compute pHash for one image.

    Runs in a child process — no GIL contention.
    Receives (image_id, full_path, md5, hash_size) and returns the hex hash
    string or None on failure.
    """
    import os
    from PIL import Image, ImageFile, UnidentifiedImageError
    import imagehash

    _img_id, full_path, _md5, hash_size = args
    if not os.path.exists(full_path):
        return None
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(full_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if 'A' in img.mode:
                    bg.paste(img, mask=img.split()[-1])
                else:
                    bg.paste(img)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            return str(imagehash.phash(img, hash_size=hash_size))
    except (UnidentifiedImageError, OSError, Exception):
        return None


def _bulk_save_phashes(pairs):
    """Save a list of (image_id, phash_hex) pairs in one transaction."""
    if not pairs:
        return
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.executemany(
            "UPDATE images SET phash = ? WHERE id = ?",
            [(h, i) for i, h in pairs],
        )
        conn.commit()


async def run_rehash_all_task(task_id: str, manager) -> Dict:
    """
    Async background task: clear ALL phashes then regenerate at current PHASH_SIZE.

    Uses ProcessPoolExecutor for true parallelism (bypasses GIL).

    Steps:
        1. NULL-out every phash in the images table
        2. Clear the duplicate_pairs cache (old distances are invalid)
        3. Regenerate all phashes using multiprocessing
    """
    import asyncio
    import time
    import config
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from services import monitor_service

    phash_size = config.PHASH_SIZE

    monitor_service.add_log(
        f"Re-hash ALL: clearing existing hashes, will regenerate at PHASH_SIZE={phash_size}",
        "info",
    )

    # Step 1 — wipe existing phashes
    def _clear_phashes():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE images SET phash = NULL WHERE phash IS NOT NULL")
            cleared = cur.rowcount
            conn.commit()
        return cleared

    cleared = await asyncio.to_thread(_clear_phashes)
    monitor_service.add_log(f"Re-hash ALL: cleared {cleared} phashes", "info")

    # Step 2 — wipe duplicate_pairs cache (distances are stale)
    def _clear_dup_cache():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM duplicate_pairs")
            conn.commit()

    await asyncio.to_thread(_clear_dup_cache)

    # Step 3 — load all image rows, regenerate with ProcessPoolExecutor
    def _load_all_images():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, filepath, md5 FROM images")
            return [dict(r) for r in cur.fetchall()]

    all_images = await asyncio.to_thread(_load_all_images)
    total = len(all_images)

    if total == 0:
        await manager.update_progress(task_id, 0, 0, "No images to hash")
        return {'success': 0, 'failed': 0, 'total': 0, 'cleared': cleared,
                'message': "No images to re-hash"}

    # Build work items: (id, full_path, md5, hash_size)
    work_items = []
    for row in all_images:
        fp = row['filepath']
        if fp.lower().endswith(('.zip',)):
            from utils.file_utils import get_thumbnail_path
            thumb = get_thumbnail_path(fp)
            full_path = os.path.join("static", thumb) if thumb != fp else os.path.join("static/images", fp)
        else:
            full_path = os.path.join("static/images", fp)
        work_items.append((row['id'], full_path, row['md5'], phash_size))

    # Run in process pool — true parallelism, no GIL
    loop = asyncio.get_running_loop()
    last_update_time = [0.0]
    num_workers = max(1, min(os.cpu_count() or 4, 8))

    def _do_rehash():
        success = 0
        failed = 0
        done = 0
        results_buffer = []

        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(_rehash_worker, item): item[0]
                for item in work_items
            }
            for future in as_completed(futures):
                img_id = futures[future]
                done += 1
                try:
                    result = future.result()
                    if result is not None:
                        results_buffer.append((img_id, result))
                        success += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

                # Bulk save every 500 results to avoid huge memory use
                if len(results_buffer) >= 500:
                    _bulk_save_phashes(results_buffer)
                    results_buffer.clear()

                # Throttled progress
                now = time.time()
                if (now - last_update_time[0] > 0.25) or done >= total:
                    last_update_time[0] = now
                    asyncio.run_coroutine_threadsafe(
                        manager.update_progress(
                            task_id, done, total,
                            f"Re-hashing… {done}/{total} ({success} ok, {failed} fail)"
                        ),
                        loop,
                    )

            # Save remaining
            if results_buffer:
                _bulk_save_phashes(results_buffer)

        return success, failed

    success, failed = await asyncio.to_thread(_do_rehash)

    result_msg = (
        f"✓ Re-hash complete (PHASH_SIZE={phash_size}): "
        f"{success} generated, {failed} failed"
    )
    monitor_service.add_log(result_msg, "success")
    await manager.update_progress(task_id, total, total, "Complete")

    return {
        'success': success,
        'failed': failed,
        'total': total,
        'cleared': cleared,
        'message': f"Re-hashed {success} images at size {phash_size} ({failed} failed)",
    }


def generate_missing_hashes(batch_size: int = 100, progress_callback=None) -> Dict:
    """
    Generate perceptual hashes and semantic embeddings for images that don't have them.
    Continuously loops until all missing hashes are generated.
    Uses ThreadPoolExecutor for parallel execution.
    
    Args:
        batch_size: Number of images to process at a time (per chunk)
        progress_callback: Optional callback(current, total) for progress updates
        
    Returns:
        Dictionary with counts of processed, successful, failed
    """
    import concurrent.futures
    import multiprocessing
    
    total_stats = {'processed': 0, 'success': 0, 'failed': 0, 'total': 0}
    
    # 1. Estimate total missing count for progress reporting
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM images WHERE phash IS NULL OR colorhash IS NULL")
            missing_visual_count = cursor.fetchone()[0]
            
            if SEMANTIC_AVAILABLE:
                cursor.execute("SELECT id FROM images")
                all_db_ids = set(row[0] for row in cursor.fetchall())
                embedded_ids = set(similarity_db.get_all_embedding_ids())
                missing_semantic_count = len(all_db_ids - embedded_ids)
            else:
                missing_semantic_count = 0
                
            # Total tasks to process
            total_stats['total'] = missing_visual_count + missing_semantic_count
            
            if total_stats['total'] == 0:
                 return total_stats

    except Exception as e:
        print(f"[Similarity] Error estimating total missing hashes: {e}")
        total_stats['total'] = 1000 # Fallback
    
    # Determine number of workers
    import config
    try:
        max_workers = config.MAX_WORKERS
    except AttributeError:
        max_workers = 4 # Fallback
        
    if max_workers <= 0:
        max_workers = max(1, multiprocessing.cpu_count() - 1)
        
    print(f"[Similarity] Starting parallel hash generation with {max_workers} workers. Total to process: {total_stats['total']}")
    
    # Track failed IDs to avoid infinite loops
    failed_ids = set()
    
    # Use ThreadPoolExecutor for all hash computation
    # This avoids the overhead of ProcessPoolExecutor and works better with I/O-bound tasks
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="IngestWorker") as executor:

        while True:
            # Fetch candidates that need hashes
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Exclude known failures
                exclude_clause = ""
                params = [batch_size]
                if failed_ids:
                    placeholders = ','.join('?' * len(failed_ids))
                    exclude_clause = f"AND id NOT IN ({placeholders})"
                    params = list(failed_ids) + params
                    
                cursor.execute(f"""
                    SELECT id, filepath, md5, phash, colorhash
                    FROM images
                    WHERE (phash IS NULL OR colorhash IS NULL)
                    {exclude_clause}
                    LIMIT ?
                """, params)
                missing_hashes = [dict(row) for row in cursor.fetchall()]

            # Also fetch semantic candidates if available
            missing_semantic = []
            
            if SEMANTIC_AVAILABLE:
                try:
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
                    print(f"[Similarity] Error finding missing semantic: {e}")

            if not missing_hashes and not missing_semantic:
                break
                
            # Submit all tasks to thread pool
            futures = {}
            
            # Submit visual hash tasks
            for row in missing_hashes:
                future = executor.submit(_process_single_image_threaded, row)
                futures[future] = ('visual', row)
                
            # Submit semantic tasks
            for row in missing_semantic:
                future = executor.submit(_process_semantic_single, row)
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
                             # Warning level for missing files (clean_orphans should run)
                             print(f"[Similarity] Warning: {result['filepath']} - {error_msg}")
                         else:
                             print(f"[Similarity] Error processing {result['filepath']}: {error_msg}")

                    if progress_callback:
                        progress_callback(total_stats['processed'], total_stats['total'])
                        
                except Exception as e:
                    print(f"[Similarity] Exception in {task_type} result: {e}")
                    total_stats['failed'] += 1
                    failed_ids.add(row['id'])

            # Bulk save
            if results_buffer:
                _bulk_save_hashes(results_buffer)
                print(f"[Similarity] Batch complete. Saved {len(results_buffer)} results.")
                
                # Rebuild semantic index if we saved any new embeddings
                has_new_embeddings = any('new_embedding' in r for r in results_buffer)
                if has_new_embeddings and SEMANTIC_AVAILABLE:
                    print("[Similarity] Rebuilding semantic index with new embeddings...")
                    get_semantic_index().rebuild()
    
    return total_stats





def get_hash_coverage_stats() -> Dict:
    """Get statistics about hash coverage in the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM images")
        total = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as hashed FROM images WHERE phash IS NOT NULL")
        hashed = cursor.fetchone()['hashed']
        
        cursor.execute("SELECT COUNT(*) as missing FROM images WHERE phash IS NULL")
        missing = cursor.fetchone()['missing']
    
    return {
        'total': total,
        'hashed': hashed,
        'missing': missing,
        'coverage_percent': round(hashed / total * 100, 1) if total > 0 else 0
    }


# ============================================================================
# Blended Similarity (Visual + Tags)
# ============================================================================

def _get_family_filepaths(filepath: str) -> set:
    """
    Get filepaths of all images in the same parent/child family chain.
    
    Args:
        filepath: Path to the reference image (relative, without 'images/' prefix)
        
    Returns:
        Set of filepaths in the same family
    """
    family = set()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get the reference image's post_id and parent_id
        cursor.execute("""
            SELECT post_id, parent_id
            FROM images
            WHERE filepath = ?
        """, (filepath,))
        ref_row = cursor.fetchone()
        
        if not ref_row:
            return family
        
        post_id = ref_row['post_id']
        parent_id = ref_row['parent_id']
        
        # Get children (images where parent_id matches our post_id)
        if post_id:
            cursor.execute("""
                SELECT filepath FROM images WHERE parent_id = ?
            """, (post_id,))
            for row in cursor.fetchall():
                family.add(row['filepath'])
        
        # Get parent (image whose post_id matches our parent_id)
        if parent_id:
            cursor.execute("""
                SELECT filepath FROM images WHERE post_id = ?
            """, (parent_id,))
            for row in cursor.fetchall():
                family.add(row['filepath'])
            
            # Also get siblings (other children of same parent)
            cursor.execute("""
                SELECT filepath FROM images WHERE parent_id = ? AND filepath != ?
            """, (parent_id, filepath))
            for row in cursor.fetchall():
                family.add(row['filepath'])
    
    return family


def find_blended_similar(
    filepath: str,
    visual_weight: float = 0.2,
    tag_weight: float = 0.2,
    semantic_weight: float = 0.6,
    visual_threshold: int = 15,
    tag_threshold: float = 0.1,
    semantic_threshold: float = 0.3,
    exclude_family: bool = False,
    limit: int = 12,
    use_cache: bool = True
) -> List[Dict]:
    """
    Find similar images using a weighted blend of visual, semantic, and tag similarity.
    
    Args:
        filepath: Path to reference image
        visual_weight: Weight for pHash/ColorHash (structure/color)
        tag_weight: Weight for tag similarity
        semantic_weight: Weight for neural embeddings (content/vibe)
        visual_threshold: Max visual hamming distance (0-64, lower = stricter)
        tag_threshold: Min tag similarity score (0-1, higher = stricter)
        semantic_threshold: Min semantic similarity score (0-1, higher = stricter)
        exclude_family: If True, exclude images in the same parent/child chain
        limit: Maximum number of results to return (default 12 for sidebar)
        use_cache: If True, check cache first (default True for performance)
        
    Returns:
        List of similar images, limited to specified count
    """
    from services import query_service
    
    # Check cache first if enabled (and using default parameters)
    if use_cache and config.SIMILARITY_CACHE_ENABLED:
        # Only use cache if using default/standard parameters
        # This ensures cache is used for the common sidebar case
        is_default_params = (
            visual_weight == 0.2 and 
            tag_weight == 0.2 and 
            semantic_weight == 0.6 and
            visual_threshold == 15 and
            tag_threshold == 0.1 and
            semantic_threshold == 0.3
        )
        
        if is_default_params:
            # Get image ID from filepath
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
                row = cursor.fetchone()
                if row:
                    from services import similarity_cache
                    cached_results = similarity_cache.get_similar_from_cache(
                        row['id'], 
                        limit=limit,
                        similarity_type='blended'
                    )
                    
                    if cached_results:
                        # Apply family filter if requested
                        if exclude_family:
                            family_filepaths = _get_family_filepaths(filepath)
                            family_paths = {f"images/{fp}" for fp in family_filepaths}
                            cached_results = [r for r in cached_results if r['path'] not in family_paths]
                        
                        return cached_results[:limit]
    
    # Get family filepaths to exclude if requested
    family_paths = set()
    if exclude_family:
        family_filepaths = _get_family_filepaths(filepath)
        family_paths = {f"images/{fp}" for fp in family_filepaths}
    
    # Normalize weights
    total_weight = visual_weight + tag_weight + semantic_weight
    if total_weight > 0:
        visual_weight /= total_weight
        tag_weight /= total_weight
        semantic_weight /= total_weight
    
    # Fetch large candidate pools from all sources (500 each for good coverage)
    POOL_SIZE = 500
    
    # 1. Visual (pHash/ColorHash) - filter by threshold
    visual_results = find_similar_images(
        filepath, 
        threshold=visual_threshold, 
        limit=POOL_SIZE, 
        exclude_family=exclude_family
    )
    visual_scores = {r['path']: r['similarity'] for r in visual_results}
    
    # 2. Tag - fetch all then filter by threshold
    tag_results = query_service.find_related_by_tags(f"images/{filepath}", limit=POOL_SIZE)
    tag_scores = {r['path']: r.get('score', 0) for r in tag_results if r.get('score', 0) >= tag_threshold}
    
    # 3. Semantic - fetch all then filter by threshold
    semantic_scores = {}
    if SEMANTIC_AVAILABLE and semantic_weight > 0:
        semantic_results = find_semantic_similar(filepath, limit=POOL_SIZE)
        semantic_scores = {r['path']: r['score'] for r in semantic_results if r.get('score', 0) >= semantic_threshold}
        
    # Combine all candidates that pass at least one threshold
    all_paths = set(visual_scores.keys()) | set(tag_scores.keys()) | set(semantic_scores.keys())
    if exclude_family:
        all_paths = all_paths - family_paths
        
    blended = []
    for path in all_paths:
        v_score = visual_scores.get(path, 0)
        t_score = tag_scores.get(path, 0)
        s_score = semantic_scores.get(path, 0)
        
        combined_score = (v_score * visual_weight) + (t_score * tag_weight) + (s_score * semantic_weight)
        
        # Convert visual distance to display-friendly value
        v_distance = int(64 * (1.0 - v_score)) if v_score > 0 else None
        
        blended.append({
            'path': path,
            'thumb': get_thumbnail_path(path),
            'score': combined_score,
            'visual_score': v_score,
            'visual_distance': v_distance,
            'tag_score': t_score,
            'semantic_score': s_score,
            'match_type': 'blended'
        })
        
    blended.sort(key=lambda x: x['score'], reverse=True)
    return blended[:limit] if limit else blended

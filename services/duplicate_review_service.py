"""
Service for the duplicate review workflow.

Uses a pre-computed duplicate_pairs cache table so the heavy O(n²) pHash scan
runs once as a background task.  The UI reads from the cache instantly with
pagination and filters by the user's chosen threshold.
"""

import os
import time
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from database import get_db_connection
from services.similarity.hashing import hamming_distance
from services.image_service import delete_image_service
from repositories import relations_repository
from utils import get_thumbnail_path


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def get_cache_stats() -> Dict[str, Any]:
    """Return summary info about the duplicate_pairs cache table."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM duplicate_pairs")
        total = cur.fetchone()['cnt']
        cur.execute("SELECT MIN(computed_at) as oldest, MAX(computed_at) as newest FROM duplicate_pairs")
        row = cur.fetchone()
        cur.execute("SELECT COUNT(*) as cnt FROM images WHERE phash IS NOT NULL")
        hashed_images = cur.fetchone()['cnt']
    return {
        'cached_pairs': total,
        'oldest': row['oldest'],
        'newest': row['newest'],
        'hashed_images': hashed_images,
    }


def clear_duplicate_cache() -> int:
    """Delete all rows from the cache.  Returns count deleted."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pairs")
        conn.commit()
        return cur.rowcount


# ---------------------------------------------------------------------------
# Heavy scan (runs in background thread)
# ---------------------------------------------------------------------------

def compute_duplicate_pairs(
    threshold: int = 15,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    O(n²) pHash comparison — writes results into the duplicate_pairs table.

    Args:
        threshold: Max hamming distance to store (15 covers the full slider).
        progress_callback: Optional (current, total) callable for progress.

    Returns:
        Stats dict with pair_count, image_count, elapsed.
    """
    t0 = time.time()

    # 1. Load all hashed images
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, phash FROM images WHERE phash IS NOT NULL ORDER BY id"
        )
        images = cur.fetchall()

    n = len(images)
    total_comparisons = n * (n - 1) // 2
    found_pairs = []

    done = 0
    for i in range(n):
        id_a = images[i]['id']
        hash_a = images[i]['phash']
        for j in range(i + 1, n):
            id_b = images[j]['id']
            hash_b = images[j]['phash']
            dist = hamming_distance(hash_a, hash_b)
            if dist <= threshold:
                found_pairs.append((id_a, id_b, dist, threshold))
            done += 1

        # Throttle progress updates to once per outer-loop iteration
        if progress_callback and (i % 50 == 0 or i == n - 1):
            progress_callback(done, total_comparisons)

    # 2. Write to cache in a single transaction (replace old data)
    now = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pairs")
        cur.executemany(
            """INSERT INTO duplicate_pairs
               (image_id_a, image_id_b, distance, threshold, computed_at)
               VALUES (?, ?, ?, ?, ?)""",
            [(a, b, d, t, now) for a, b, d, t in found_pairs],
        )
        conn.commit()

    elapsed = round(time.time() - t0, 2)
    return {
        'pair_count': len(found_pairs),
        'image_count': n,
        'comparisons': total_comparisons,
        'elapsed_seconds': elapsed,
    }


# ---------------------------------------------------------------------------
# Background task wrapper (follows run_hash_generation_task pattern)
# ---------------------------------------------------------------------------

async def run_duplicate_scan_task(task_id: str, manager, threshold: int = 15) -> Dict:
    """Async bg task that calls compute_duplicate_pairs in a thread."""
    loop = asyncio.get_running_loop()
    last_update = 0

    def progress_cb(current, total):
        nonlocal last_update
        now = time.time()
        if now - last_update > 0.25 or current >= total:
            last_update = now
            pct = int(current / total * 100) if total else 0
            asyncio.run_coroutine_threadsafe(
                manager.update_progress(
                    task_id, current, total,
                    f"Scanning… {pct}% ({current}/{total} comparisons)"
                ),
                loop,
            )

    stats = await asyncio.to_thread(
        compute_duplicate_pairs,
        threshold=threshold,
        progress_callback=progress_cb,
    )

    await manager.update_progress(
        task_id, stats['comparisons'], stats['comparisons'], "Complete"
    )
    return stats


# ---------------------------------------------------------------------------
# Paginated queue (reads from cache — instant)
# ---------------------------------------------------------------------------

def get_duplicate_queue(
    threshold: int = 5,
    offset: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    Read from duplicate_pairs cache, filter by threshold, exclude
    already-reviewed pairs, enrich with metadata, and paginate.

    Returns dict with 'pairs', 'total', 'offset', 'limit'.
    """
    reviewed = relations_repository.get_all_reviewed_pairs()

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Total unreviewed count at this threshold
        cur.execute(
            "SELECT COUNT(*) as cnt FROM duplicate_pairs WHERE distance <= ?",
            (threshold,),
        )
        raw_total = cur.fetchone()['cnt']

        # Fetch a chunk — over-fetch to compensate for reviewed-pair filtering
        fetch_limit = limit + len(reviewed) + 100
        cur.execute(
            """SELECT image_id_a, image_id_b, distance
               FROM duplicate_pairs
               WHERE distance <= ?
               ORDER BY distance ASC
               LIMIT ? OFFSET ?""",
            (threshold, fetch_limit, max(0, offset - len(reviewed))),
        )
        rows = cur.fetchall()

    # Filter out reviewed pairs
    pairs = []
    skipped = 0
    for row in rows:
        pk = (row['image_id_a'], row['image_id_b'])
        if pk in reviewed:
            skipped += 1
            continue
        if len(pairs) >= limit:
            break
        distance = row['distance']
        confidence = max(0, round((1 - distance / 64) * 100, 1))
        pairs.append({
            'image_a': _enrich_image_by_id(row['image_id_a']),
            'image_b': _enrich_image_by_id(row['image_id_b']),
            'distance': distance,
            'confidence': confidence,
        })

    total_unreviewed = raw_total - len(reviewed)  # approximate
    if total_unreviewed < 0:
        total_unreviewed = 0

    return {
        'pairs': pairs,
        'total': total_unreviewed,
        'offset': offset,
        'limit': limit,
    }


# ---------------------------------------------------------------------------
# Enrichment helpers
# ---------------------------------------------------------------------------

def _enrich_image_by_id(image_id: int) -> Dict[str, Any]:
    """Build an enriched image dict from just an image ID."""
    meta = _get_image_metadata(image_id)
    filepath = meta.get('filepath', '')
    path = f"images/{filepath}" if filepath else ''
    thumb = get_thumbnail_path(path) if path else ''

    full_path = os.path.join("static", path) if path else ''
    file_size = 0
    if full_path and os.path.exists(full_path):
        file_size = os.path.getsize(full_path)

    return {
        'id': image_id,
        'path': path,
        'filepath': filepath,
        'thumb': thumb,
        'md5': meta.get('md5', ''),
        'width': meta.get('image_width', 0),
        'height': meta.get('image_height', 0),
        'file_size': file_size,
        'tag_count': meta.get('tag_count', 0),
        'ingested_at': meta.get('ingested_at', ''),
        'score': meta.get('score', 0),
    }


def _get_image_metadata(image_id: int) -> Dict[str, Any]:
    """Fetch image dimensions, tag count, filepath, and ingestion date."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                i.filepath, i.md5, i.image_width, i.image_height,
                i.ingested_at, i.score,
                (SELECT COUNT(*) FROM image_tags WHERE image_id = i.id) as tag_count
            FROM images i
            WHERE i.id = ?
        """, (image_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return {}


# ---------------------------------------------------------------------------
# Batch commit (unchanged from Phase 1)
# ---------------------------------------------------------------------------

def commit_actions(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Execute a batch of staged actions from the duplicate review UI.

    Args:
        actions: List of dicts with keys:
            - image_id_a (int)
            - image_id_b (int)
            - action (str): 'delete_a', 'delete_b', 'non_duplicate', 'related'
            - detail (str, optional): for 'related' — 'parent_child_ab', 'parent_child_ba', 'sibling'

    Returns:
        Summary dict with success_count, error_count, errors list
    """
    results = {
        'success_count': 0,
        'error_count': 0,
        'errors': []
    }

    for action_item in actions:
        try:
            _execute_action(action_item)
            results['success_count'] += 1
        except Exception as e:
            results['error_count'] += 1
            results['errors'].append({
                'image_id_a': action_item.get('image_id_a'),
                'image_id_b': action_item.get('image_id_b'),
                'action': action_item.get('action'),
                'error': str(e)
            })

    return results


def _execute_action(action_item: Dict[str, Any]) -> None:
    """Execute a single action from the batch."""
    action = action_item['action']
    id_a = action_item['image_id_a']
    id_b = action_item['image_id_b']

    if action == 'delete_a':
        filepath = _get_filepath_for_id(id_a)
        if filepath:
            delete_image_service({'filepath': f'images/{filepath}'})
            relations_repository.add_relation(id_a, id_b, 'non_duplicate', 'duplicate_review')

    elif action == 'delete_b':
        filepath = _get_filepath_for_id(id_b)
        if filepath:
            delete_image_service({'filepath': f'images/{filepath}'})
            relations_repository.add_relation(id_a, id_b, 'non_duplicate', 'duplicate_review')

    elif action == 'non_duplicate':
        relations_repository.add_relation(id_a, id_b, 'non_duplicate', 'duplicate_review')

    elif action == 'related':
        detail = action_item.get('detail', 'sibling')
        if detail == 'parent_child_ab':
            relations_repository.add_relation(id_a, id_b, 'parent_child', 'duplicate_review')
        elif detail == 'parent_child_ba':
            relations_repository.add_relation(id_b, id_a, 'parent_child', 'duplicate_review')
        elif detail == 'sibling':
            relations_repository.add_relation(id_a, id_b, 'sibling', 'duplicate_review')
    else:
        raise ValueError(f"Unknown action: {action}")


def _get_filepath_for_id(image_id: int) -> str:
    """Look up filepath from image ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cur.fetchone()
        return row['filepath'] if row else ''

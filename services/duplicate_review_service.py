"""
Service for the duplicate review workflow.

Uses a pre-computed duplicate_pairs cache table so the heavy O(n²) pHash scan
runs once as a background task.  The UI reads from the cache instantly with
pagination and filters by the user's chosen threshold.
"""

import os
import time
import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
import config
from database import get_db_connection
from services.similarity.hashing import hamming_distance
from services.image_service import delete_image_service
from repositories import relations_repository
from utils import get_thumbnail_path


# ---------------------------------------------------------------------------
# Parallel scan workers (module-level for pickling by ProcessPoolExecutor)
# ---------------------------------------------------------------------------

_worker_ids: Optional[List[int]] = None
_worker_hashes: Optional[List[int]] = None

# Below this image count we skip multiprocessing to avoid spawn overhead
_MP_THRESHOLD = 200


def _init_scan_worker(ids: List[int], hashes: List[int]):
    """Initializer for each pool worker — stores shared readonly data."""
    global _worker_ids, _worker_hashes
    _worker_ids = ids
    _worker_hashes = hashes


def _scan_chunk(args: Tuple[int, int, int]) -> List[Tuple[int, int, int]]:
    """
    Worker function: compare images[start:end] against all subsequent images.

    Uses bitwise XOR + popcount on pre-computed integer hashes — roughly
    50-100x faster than round-tripping through imagehash objects.

    Returns list of (id_a, id_b, distance) within threshold.
    """
    start_idx, end_idx, threshold = args
    ids = _worker_ids
    hashes = _worker_hashes
    n = len(ids)
    found: list = []
    append = found.append          # micro-opt: avoid attr lookup in hot loop

    for i in range(start_idx, end_idx):
        h_a = hashes[i]
        id_a = ids[i]
        for j in range(i + 1, n):
            dist = bin(h_a ^ hashes[j]).count('1')
            if dist <= threshold:
                append((id_a, ids[j], dist))

    return found


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
        cur.execute("SELECT MAX(threshold) as t FROM duplicate_pairs")
        scan_threshold = cur.fetchone()['t'] or 0
    return {
        'cached_pairs': total,
        'oldest': row['oldest'],
        'newest': row['newest'],
        'hashed_images': hashed_images,
        'phash_size': config.PHASH_SIZE,
        'phash_bits': config.PHASH_BITS,
        'scan_threshold': scan_threshold,
    }


def clear_duplicate_cache() -> int:
    """Delete all rows from the cache.  Returns count deleted."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pairs")
        conn.commit()
        return cur.rowcount


def _remove_pair_from_cache(id_a: int, id_b: int) -> None:
    """Remove a specific pair from the duplicate_pairs cache (normalised to min/max)."""
    lo, hi = min(id_a, id_b), max(id_a, id_b)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM duplicate_pairs WHERE image_id_a = ? AND image_id_b = ?",
            (lo, hi),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Heavy scan (runs in background thread)
# ---------------------------------------------------------------------------

def compute_duplicate_pairs(
    threshold: int = 15,
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    O(n²) pHash comparison — writes results into the duplicate_pairs table.

    Parallelized across CPU cores via ProcessPoolExecutor so the heavy work
    runs in child processes and does NOT block the main app's event loop.

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

    if n == 0:
        return {
            'pair_count': 0, 'image_count': 0,
            'comparisons': 0, 'elapsed_seconds': 0,
        }

    # 2. Convert hex hashes to integers once — makes each comparison a
    #    single XOR + popcount instead of creating imagehash objects.
    image_ids = [img['id'] for img in images]
    hash_ints = [int(img['phash'], 16) for img in images]

    # 3. Run comparisons
    if n < _MP_THRESHOLD:
        found_pairs = _scan_single_thread(
            image_ids, hash_ints, threshold, n,
            total_comparisons, progress_callback,
        )
    else:
        found_pairs = _scan_parallel(
            image_ids, hash_ints, threshold, n,
            total_comparisons, progress_callback,
        )

    # 4. Write to cache in a single transaction (replace old data)
    now = datetime.utcnow().isoformat()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pairs")
        cur.executemany(
            """INSERT INTO duplicate_pairs
               (image_id_a, image_id_b, distance, threshold, computed_at)
               VALUES (?, ?, ?, ?, ?)""",
            [(a, b, d, threshold, now) for a, b, d in found_pairs],
        )
        conn.commit()

    elapsed = round(time.time() - t0, 2)
    return {
        'pair_count': len(found_pairs),
        'image_count': n,
        'comparisons': total_comparisons,
        'elapsed_seconds': elapsed,
    }


def _scan_single_thread(
    image_ids: List[int],
    hash_ints: List[int],
    threshold: int,
    n: int,
    total_comparisons: int,
    progress_callback: Optional[Callable],
) -> List[Tuple[int, int, int]]:
    """Fast single-threaded scan (small datasets, avoids process-spawn overhead)."""
    found: list = []
    done = 0
    for i in range(n):
        h_a = hash_ints[i]
        id_a = image_ids[i]
        for j in range(i + 1, n):
            dist = bin(h_a ^ hash_ints[j]).count('1')
            if dist <= threshold:
                found.append((id_a, image_ids[j], dist))
            done += 1
        if progress_callback and (i % 50 == 0 or i == n - 1):
            progress_callback(done, total_comparisons)
    return found


def _scan_parallel(
    image_ids: List[int],
    hash_ints: List[int],
    threshold: int,
    n: int,
    total_comparisons: int,
    progress_callback: Optional[Callable],
) -> List[Tuple[int, int, int]]:
    """
    Parallel scan across CPU cores using ProcessPoolExecutor.

    The heavy comparison work runs in *child processes*, so it:
      - uses all available cores (no GIL limitation)
      - does NOT compete with the main app's async event loop
    """
    num_workers = max(1, min(os.cpu_count() or 4, 8))  # cap at 8

    # More chunks than workers → better load balancing (early indices
    # have more comparisons than late ones).
    num_chunks = num_workers * 4
    chunk_size = max(1, n // num_chunks)

    chunks: List[Tuple[int, int, int]] = []
    for c in range(num_chunks):
        start = c * chunk_size
        end = min((c + 1) * chunk_size, n) if c < num_chunks - 1 else n
        if start >= n:
            break
        chunks.append((start, end, threshold))

    found_pairs: list = []
    done_comparisons = 0

    with ProcessPoolExecutor(
        max_workers=num_workers,
        initializer=_init_scan_worker,
        initargs=(image_ids, hash_ints),
    ) as executor:
        futures = {
            executor.submit(_scan_chunk, chunk): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk_start, chunk_end, _ = futures[future]
            # Number of comparisons this chunk performed
            chunk_comps = sum(n - j - 1 for j in range(chunk_start, chunk_end))

            pairs = future.result()
            found_pairs.extend(pairs)
            done_comparisons += chunk_comps

            if progress_callback:
                progress_callback(done_comparisons, total_comparisons)

    return found_pairs


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

    Filtering is done at the SQL level via NOT EXISTS so that LIMIT/OFFSET
    paginate correctly over only the unreviewed pairs.

    Returns dict with 'pairs', 'total', 'offset', 'limit'.
    """
    # Subquery that matches any relation between the two images.
    # duplicate_pairs always stores (min_id, max_id).  image_relations
    # normalises sibling/non_duplicate the same way, but parent_child
    # preserves direction — so we check both orderings.
    _NOT_REVIEWED = """
        NOT EXISTS (
            SELECT 1 FROM image_relations ir
            WHERE (ir.image_id_a = dp.image_id_a AND ir.image_id_b = dp.image_id_b)
               OR (ir.image_id_a = dp.image_id_b AND ir.image_id_b = dp.image_id_a)
        )
    """

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Retrieve the scan threshold used during the last scan — this is the
        # natural "maximum interesting distance" and gives a much better
        # confidence spread than dividing by the full PHASH_BITS (256).
        cur.execute("SELECT MAX(threshold) as t FROM duplicate_pairs")
        scan_threshold = cur.fetchone()['t']
        if not scan_threshold:
            scan_threshold = max(config.PHASH_BITS // 4, 1)

        # Accurate unreviewed count at this threshold
        cur.execute(
            f"SELECT COUNT(*) as cnt FROM duplicate_pairs dp"
            f" WHERE dp.distance <= ? AND {_NOT_REVIEWED}",
            (threshold,),
        )
        total_unreviewed = cur.fetchone()['cnt']

        # Fetch the requested page — filtering + pagination handled by SQL
        cur.execute(
            f"""SELECT dp.image_id_a, dp.image_id_b, dp.distance
                FROM duplicate_pairs dp
                WHERE dp.distance <= ? AND {_NOT_REVIEWED}
                ORDER BY dp.distance ASC
                LIMIT ? OFFSET ?""",
            (threshold, limit, offset),
        )
        rows = cur.fetchall()

    pairs = []
    for row in rows:
        distance = row['distance']
        # Scale confidence against scan_threshold (not full PHASH_BITS)
        # so the 0-100% range spans the distances we actually store.
        confidence = max(0, round((1 - distance / scan_threshold) * 100, 1))
        pairs.append({
            'image_a': _enrich_image_by_id(row['image_id_a']),
            'image_b': _enrich_image_by_id(row['image_id_b']),
            'distance': distance,
            'confidence': confidence,
        })

    return {
        'pairs': pairs,
        'total': total_unreviewed,
        'offset': offset,
        'limit': limit,
        'phash_bits': config.PHASH_BITS,
        'scan_threshold': scan_threshold,
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

def commit_actions(
    actions: List[Dict[str, Any]],
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Execute a batch of staged actions from the duplicate review UI.

    Args:
        actions: List of dicts with keys:
            - image_id_a (int)
            - image_id_b (int)
            - action (str): 'delete_a', 'delete_b', 'non_duplicate', 'related'
            - detail (str, optional): for 'related' — 'parent_child_ab', 'parent_child_ba', 'sibling'
        progress_callback: Optional (current, total, message) callable for progress.

    Returns:
        Summary dict with success_count, error_count, errors list
    """
    results = {
        'success_count': 0,
        'error_count': 0,
        'errors': []
    }
    total = len(actions)

    for idx, action_item in enumerate(actions):
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
        if progress_callback:
            progress_callback(idx + 1, total)

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

    # Always remove the pair from the cache so it won't reappear in the queue
    _remove_pair_from_cache(id_a, id_b)


def _get_filepath_for_id(image_id: int) -> str:
    """Look up filepath from image ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cur.fetchone()
        return row['filepath'] if row else ''


# ---------------------------------------------------------------------------
# Background task wrapper for commit (follows run_duplicate_scan_task pattern)
# ---------------------------------------------------------------------------

async def run_commit_task(
    task_id: str,
    manager,
    actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Async bg task that calls commit_actions in a thread with progress."""
    loop = asyncio.get_running_loop()
    last_update = 0

    def progress_cb(current, total):
        nonlocal last_update
        now = time.time()
        if now - last_update > 0.15 or current >= total:
            last_update = now
            asyncio.run_coroutine_threadsafe(
                manager.update_progress(
                    task_id, current, total,
                    f"Committing {current}/{total}…"
                ),
                loop,
            )

    result = await asyncio.to_thread(
        commit_actions,
        actions,
        progress_callback=progress_cb,
    )

    await manager.update_progress(
        task_id, len(actions), len(actions), "Commit complete"
    )
    return result

"""
Service for the duplicate review workflow.

Uses a pre-computed duplicate_pairs cache table so the heavy O(n²) pHash scan
runs once as a background task.  The UI reads from the cache instantly with
pagination and filters by the user's chosen threshold.
"""

import os
import time
import asyncio
import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import lru_cache
from typing import List, Dict, Any, Optional, Callable, Tuple
import numpy as np
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
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
_SUGGESTION_PREVIEW_SIZE = 256
_SUGGESTION_LOWER_BOUND = 0.012
_SUGGESTION_UPPER_BOUND = 0.04
_DIFF_PIXEL_THRESHOLD = 24 / 255.0
_DIFF_NEIGHBOR_MIN = 4
_SUGGESTION_MP_THRESHOLD = 100
_LOW_VISUAL_SIGNAL_GUARD = 0.02
_LOW_BLOB_RATIO_GUARD = 0.0025


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


def _compute_suggestion_chunk(
    pair_payloads: List[Dict[str, Any]],
) -> List[Tuple]:
    """Worker: compute raw suggestion signals for a chunk of duplicate pairs."""
    now = datetime.utcnow().isoformat()
    rows = []

    for payload in pair_payloads:
        image_a = payload['image_a']
        image_b = payload['image_b']
        metrics = _compute_pair_visual_metrics(image_a, image_b)
        if not metrics.get('available'):
            continue
        suggestion = _build_suggestion_cache_record(metrics, image_a, image_b)
        rows.append((
            payload['image_id_a'],
            payload['image_id_b'],
            suggestion['signal'],
            suggestion['visual_signal'],
            suggestion['metadata_adjustment'],
            suggestion['mean_abs_diff'],
            suggestion['changed_ratio'],
            suggestion['largest_blob_ratio'],
            suggestion['blob_count'],
            suggestion['peak_blob_contrast'],
            suggestion['mask_mismatch'],
            suggestion['pixel_ratio'],
            suggestion['filesize_ratio'],
            suggestion['tag_gap_ratio'],
            now,
        ))

    return rows


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
        cur.execute("SELECT COUNT(*) as cnt FROM duplicate_pair_suggestions")
        suggestion_cached_pairs = cur.fetchone()['cnt']
        cur.execute("SELECT MAX(computed_at) as newest FROM duplicate_pair_suggestions")
        suggestion_newest = cur.fetchone()['newest']
    return {
        'cached_pairs': total,
        'oldest': row['oldest'],
        'newest': row['newest'],
        'hashed_images': hashed_images,
        'phash_size': config.PHASH_SIZE,
        'phash_bits': config.PHASH_BITS,
        'scan_threshold': scan_threshold,
        'suggestion_thresholds': {
            'lower': _SUGGESTION_LOWER_BOUND,
            'upper': _SUGGESTION_UPPER_BOUND,
        },
        'suggestion_cached_pairs': suggestion_cached_pairs,
        'suggestion_cache_ready': total > 0 and suggestion_cached_pairs >= total,
        'suggestion_newest': suggestion_newest,
    }


def clear_duplicate_cache() -> int:
    """Delete all rows from the cache.  Returns count deleted."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pairs")
        cur.execute("DELETE FROM duplicate_pair_suggestions")
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
        cur.execute(
            "DELETE FROM duplicate_pair_suggestions WHERE image_id_a = ? AND image_id_b = ?",
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
        cur.execute("DELETE FROM duplicate_pair_suggestions")
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


def compute_duplicate_pair_suggestions(
    progress_callback: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Precompute suggestion signals for all currently cached duplicate pairs."""
    t0 = time.time()

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT dp.image_id_a, dp.image_id_b, dp.distance
            FROM duplicate_pairs dp
            ORDER BY dp.distance ASC
        """)
        pairs = [dict(row) for row in cur.fetchall()]

    total = len(pairs)
    if total == 0:
        with get_db_connection() as conn:
            conn.execute("DELETE FROM duplicate_pair_suggestions")
            conn.commit()
        return {'pair_count': 0, 'elapsed_seconds': 0}

    image_ids = sorted({
        pair['image_id_a'] for pair in pairs
    } | {
        pair['image_id_b'] for pair in pairs
    })
    metadata_map = _get_images_metadata_map(image_ids)
    payloads = []
    for pair in pairs:
        payloads.append({
            'image_id_a': pair['image_id_a'],
            'image_id_b': pair['image_id_b'],
            'image_a': metadata_map[pair['image_id_a']],
            'image_b': metadata_map[pair['image_id_b']],
        })

    rows = _compute_duplicate_pair_suggestions_rows(payloads, progress_callback)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM duplicate_pair_suggestions")
        cur.executemany(
            """INSERT OR REPLACE INTO duplicate_pair_suggestions (
                image_id_a, image_id_b, signal, visual_signal, metadata_adjustment,
                mean_abs_diff, changed_ratio, largest_blob_ratio, blob_count,
                peak_blob_contrast, mask_mismatch, pixel_ratio, filesize_ratio,
                tag_gap_ratio, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()

    elapsed = round(time.time() - t0, 2)
    return {
        'pair_count': len(rows),
        'source_pairs': total,
        'elapsed_seconds': elapsed,
    }


def _compute_duplicate_pair_suggestions_rows(
    payloads: List[Dict[str, Any]],
    progress_callback: Optional[Callable],
) -> List[Tuple]:
    """Compute suggestion cache rows, using bounded thread workers for larger sets."""
    total = len(payloads)
    if total < _SUGGESTION_MP_THRESHOLD:
        rows = []
        for idx, payload in enumerate(payloads, start=1):
            rows.extend(_compute_suggestion_chunk([payload]))
            if progress_callback and (idx % 10 == 0 or idx == total):
                progress_callback(idx, total)
        return rows

    num_workers = max(1, min(os.cpu_count() or 4, 4))
    chunk_size = max(8, total // (num_workers * 6))
    chunks = [
        payloads[i:i + chunk_size]
        for i in range(0, total, chunk_size)
    ]

    rows: List[Tuple] = []
    done = 0
    # Use threads here to avoid large cross-process payload copies and keep the
    # web worker responsive while still parallelizing preview loading/scoring.
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_compute_suggestion_chunk, chunk): len(chunk) for chunk in chunks}
        for future in as_completed(futures):
            rows.extend(future.result())
            done += futures[future]
            if progress_callback:
                progress_callback(done, total)
    return rows


async def run_duplicate_suggestion_task(task_id: str, manager) -> Dict:
    """Async bg task that precomputes duplicate suggestion scores with progress."""
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
                    task_id,
                    current,
                    total,
                    f"Scoring duplicate pairs… {pct}% ({current}/{total})",
                ),
                loop,
            )

    stats = await asyncio.to_thread(
        compute_duplicate_pair_suggestions,
        progress_callback=progress_cb,
    )
    await manager.update_progress(
        task_id,
        stats.get('source_pairs', 0),
        stats.get('source_pairs', 0),
        "Suggestion cache complete",
    )
    return stats


# ---------------------------------------------------------------------------
# Paginated queue (reads from cache — instant)
# ---------------------------------------------------------------------------

def get_duplicate_queue(
    threshold: int = 5,
    offset: int = 0,
    limit: int = 50,
    suggestion_lower: Optional[float] = None,
    suggestion_upper: Optional[float] = None,
    queue_mode: str = 'distance',
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

    lower_bound, upper_bound = _coerce_suggestion_bounds(
        suggestion_lower,
        suggestion_upper,
    )
    normalized_mode = _normalize_queue_mode(queue_mode)

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Retrieve the scan threshold used during the last scan — this is the
        # natural "maximum interesting distance" and gives a much better
        # confidence spread than dividing by the full PHASH_BITS (256).
        cur.execute("SELECT MAX(threshold) as t FROM duplicate_pairs")
        scan_threshold = cur.fetchone()['t']
        if not scan_threshold:
            scan_threshold = max(config.PHASH_BITS // 4, 1)

        cur.execute("SELECT COUNT(*) as cnt FROM duplicate_pair_suggestions")
        suggestion_cached_pairs = cur.fetchone()['cnt']
        suggestion_cache_ready = suggestion_cached_pairs > 0 and suggestion_cached_pairs >= _count_duplicate_pairs(cur)

        if normalized_mode == 'distance':
            cur.execute(
                f"SELECT COUNT(*) as cnt FROM duplicate_pairs dp"
                f" WHERE dp.distance <= ? AND {_NOT_REVIEWED}",
                (threshold,),
            )
            total_unreviewed = cur.fetchone()['cnt']

            if suggestion_cache_ready:
                cur.execute(
                    f"""SELECT dp.image_id_a, dp.image_id_b, dp.distance,
                               dps.signal, dps.visual_signal, dps.metadata_adjustment,
                               dps.mean_abs_diff, dps.changed_ratio, dps.largest_blob_ratio,
                               dps.blob_count, dps.peak_blob_contrast, dps.mask_mismatch,
                               dps.pixel_ratio, dps.filesize_ratio, dps.tag_gap_ratio
                        FROM duplicate_pairs dp
                        LEFT JOIN duplicate_pair_suggestions dps
                          ON dps.image_id_a = dp.image_id_a AND dps.image_id_b = dp.image_id_b
                        WHERE dp.distance <= ? AND {_NOT_REVIEWED}
                        ORDER BY dp.distance ASC
                        LIMIT ? OFFSET ?""",
                    (threshold, limit, offset),
                )
            else:
                cur.execute(
                    f"""SELECT dp.image_id_a, dp.image_id_b, dp.distance
                        FROM duplicate_pairs dp
                        WHERE dp.distance <= ? AND {_NOT_REVIEWED}
                        ORDER BY dp.distance ASC
                        LIMIT ? OFFSET ?""",
                    (threshold, limit, offset),
                )
            rows = cur.fetchall()
        else:
            if not suggestion_cache_ready:
                return {
                    'pairs': [],
                    'total': 0,
                    'offset': offset,
                    'limit': limit,
                    'phash_bits': config.PHASH_BITS,
                    'scan_threshold': scan_threshold,
                    'queue_mode': normalized_mode,
                    'raw_total': 0,
                    'suggestion_cache_ready': False,
                    'suggestion_thresholds': {
                        'lower': lower_bound,
                        'upper': upper_bound,
                        'defaults': {
                            'lower': _SUGGESTION_LOWER_BOUND,
                            'upper': _SUGGESTION_UPPER_BOUND,
                        },
                    },
                }

            filter_clause = ""
            order_clause = ""
            count_params: List[Any] = [threshold]
            select_params: List[Any] = [threshold]
            if normalized_mode == 'likely_duplicates':
                filter_clause = "AND dps.signal <= ?"
                count_params.append(lower_bound)
                select_params.append(lower_bound)
                order_clause = "ORDER BY dps.signal ASC, dp.distance ASC"
            elif normalized_mode == 'duplicate_hunt':
                select_params.extend([lower_bound, upper_bound])
                order_clause = """
                    ORDER BY
                        CASE
                            WHEN dps.signal <= ? THEN 0
                            WHEN dps.signal < ? THEN 1
                            ELSE 2
                        END ASC,
                        dps.signal ASC,
                        dps.largest_blob_ratio ASC,
                        dps.peak_blob_contrast ASC,
                        dps.changed_ratio ASC,
                        dp.distance ASC,
                        dps.mean_abs_diff ASC
                """
            else:
                select_params.extend([lower_bound, upper_bound])
                order_clause = """
                    ORDER BY
                        CASE
                            WHEN dps.signal <= ? THEN 0
                            WHEN dps.signal < ? THEN 1
                            ELSE 2
                        END ASC,
                        dps.signal ASC,
                        dp.distance ASC
                """

            cur.execute(
                f"""SELECT COUNT(*) as cnt
                    FROM duplicate_pairs dp
                    JOIN duplicate_pair_suggestions dps
                      ON dps.image_id_a = dp.image_id_a AND dps.image_id_b = dp.image_id_b
                    WHERE dp.distance <= ? AND {_NOT_REVIEWED} {filter_clause}""",
                tuple(count_params),
            )
            total_unreviewed = cur.fetchone()['cnt']

            cur.execute(
                f"""SELECT dp.image_id_a, dp.image_id_b, dp.distance,
                           dps.signal, dps.visual_signal, dps.metadata_adjustment,
                           dps.mean_abs_diff, dps.changed_ratio, dps.largest_blob_ratio,
                           dps.blob_count, dps.peak_blob_contrast, dps.mask_mismatch,
                           dps.pixel_ratio, dps.filesize_ratio, dps.tag_gap_ratio
                    FROM duplicate_pairs dp
                    JOIN duplicate_pair_suggestions dps
                      ON dps.image_id_a = dp.image_id_a AND dps.image_id_b = dp.image_id_b
                    WHERE dp.distance <= ? AND {_NOT_REVIEWED} {filter_clause}
                    {order_clause}
                    LIMIT ? OFFSET ?""",
                tuple(select_params + [limit, offset]),
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
            'cached_suggestion': _get_cached_suggestion_payload(row) if suggestion_cache_ready else None,
        })

    _attach_visual_suggestions(
        pairs,
        lower_bound,
        upper_bound,
        use_cached=suggestion_cache_ready,
    )
    total_visible = total_unreviewed

    return {
        'pairs': pairs,
        'total': total_visible,
        'offset': offset,
        'limit': limit,
        'phash_bits': config.PHASH_BITS,
        'scan_threshold': scan_threshold,
        'queue_mode': normalized_mode,
        'raw_total': total_unreviewed,
        'suggestion_cache_ready': suggestion_cache_ready,
        'suggestion_cached_pairs': suggestion_cached_pairs,
        'suggestion_thresholds': {
            'lower': lower_bound,
            'upper': upper_bound,
            'defaults': {
                'lower': _SUGGESTION_LOWER_BOUND,
                'upper': _SUGGESTION_UPPER_BOUND,
            },
        },
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


def _get_images_metadata_map(image_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """Bulk-load enriched image metadata for a set of IDs."""
    if not image_ids:
        return {}

    placeholders = ','.join('?' for _ in image_ids)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                i.id, i.filepath, i.md5, i.image_width, i.image_height,
                i.ingested_at, i.score,
                (SELECT COUNT(*) FROM image_tags WHERE image_id = i.id) as tag_count
            FROM images i
            WHERE i.id IN ({placeholders})
        """, tuple(image_ids))
        rows = [dict(row) for row in cur.fetchall()]

    result = {}
    for meta in rows:
        filepath = meta.get('filepath', '')
        path = f"images/{filepath}" if filepath else ''
        full_path = os.path.join("static", path) if path else ''
        result[meta['id']] = {
            'id': meta['id'],
            'path': path,
            'filepath': filepath,
            'thumb': get_thumbnail_path(path) if path else '',
            'md5': meta.get('md5', ''),
            'width': meta.get('image_width', 0),
            'height': meta.get('image_height', 0),
            'file_size': os.path.getsize(full_path) if full_path and os.path.exists(full_path) else 0,
            'tag_count': meta.get('tag_count', 0),
            'ingested_at': meta.get('ingested_at', ''),
            'score': meta.get('score', 0),
        }
    return result


def _normalize_queue_mode(queue_mode: str) -> str:
    """Clamp queue mode to supported values."""
    allowed_modes = {'distance', 'duplicate_first', 'likely_duplicates', 'duplicate_hunt'}
    return queue_mode if queue_mode in allowed_modes else 'distance'


def _count_duplicate_pairs(cur) -> int:
    """Return total pair count in duplicate_pairs for cache readiness checks."""
    cur.execute("SELECT COUNT(*) as cnt FROM duplicate_pairs")
    return cur.fetchone()['cnt']


def _get_cached_suggestion_payload(row: Any) -> Optional[Dict[str, Any]]:
    """Extract cached suggestion columns from a queue row when present."""
    required = (
        'signal', 'visual_signal', 'metadata_adjustment', 'mean_abs_diff',
        'changed_ratio', 'largest_blob_ratio', 'blob_count',
        'peak_blob_contrast', 'mask_mismatch', 'pixel_ratio',
        'filesize_ratio', 'tag_gap_ratio',
    )
    row_dict = dict(row)
    if not all(key in row_dict for key in required):
        return None
    return {key: row_dict[key] for key in required}


def _coerce_suggestion_bounds(
    lower: Optional[float],
    upper: Optional[float],
) -> Tuple[float, float]:
    """Clamp and normalize visual suggestion bounds."""
    lower_bound = _SUGGESTION_LOWER_BOUND if lower is None else float(lower)
    upper_bound = _SUGGESTION_UPPER_BOUND if upper is None else float(upper)

    lower_bound = max(0.0, min(lower_bound, 1.0))
    upper_bound = max(0.0, min(upper_bound, 1.0))

    if upper_bound <= lower_bound:
        upper_bound = min(1.0, lower_bound + 0.05)

    return round(lower_bound, 4), round(upper_bound, 4)


def _attach_visual_suggestions(
    pairs: List[Dict[str, Any]],
    lower_bound: float,
    upper_bound: float,
    use_cached: bool = False,
) -> None:
    """Annotate duplicate-review pairs with a bounded visual suggestion."""
    for pair in pairs:
        if use_cached and pair.get('cached_suggestion'):
            pair['suggestion'] = _build_visual_suggestion_from_cache_record(
                pair['cached_suggestion'],
                lower_bound,
                upper_bound,
            )
        else:
            metrics = _compute_pair_visual_metrics(pair['image_a'], pair['image_b'])
            pair['suggestion'] = _build_visual_suggestion(
                metrics,
                pair['image_a'],
                pair['image_b'],
                lower_bound,
                upper_bound,
            )


def _build_visual_suggestion(
    metrics: Dict[str, Any],
    image_a: Dict[str, Any],
    image_b: Dict[str, Any],
    lower_bound: float,
    upper_bound: float,
) -> Dict[str, Any]:
    """Classify the visual diff signal into duplicate/variation/uncertain."""
    if not metrics.get('available'):
        return {
            'label': 'unavailable',
            'text': 'No suggestion',
            'signal': None,
            'confidence': 0.0,
            'bounds': {'lower': lower_bound, 'upper': upper_bound},
            'metrics': {},
            'reason': metrics.get('reason', 'visual_diff_unavailable'),
        }

    metadata_metrics = _compute_metadata_metrics(image_a, image_b)
    visual_signal = metrics['variation_signal']
    signal = min(1.0, visual_signal + metadata_metrics['variation_adjustment'])
    cache_record = _build_suggestion_cache_record(metrics, image_a, image_b)
    cache_record['signal'] = signal
    cache_record['visual_signal'] = visual_signal
    cache_record['metadata_adjustment'] = metadata_metrics['variation_adjustment']
    return _build_visual_suggestion_from_cache_record(cache_record, lower_bound, upper_bound)


def _build_visual_suggestion_from_cache_record(
    cache_record: Dict[str, Any],
    lower_bound: float,
    upper_bound: float,
) -> Dict[str, Any]:
    """Classify from a cached or freshly computed raw suggestion record."""
    signal = float(cache_record['signal'])
    band_width = max(upper_bound - lower_bound, 1e-6)
    if signal <= lower_bound:
        label = 'likely_duplicate'
        text = 'Suggest duplicate'
        confidence = min(1.0, (lower_bound - signal) / max(lower_bound, 1e-6))
    elif signal >= upper_bound:
        label = 'likely_variation'
        text = 'Suggest variation'
        confidence = min(1.0, (signal - upper_bound) / max(1.0 - upper_bound, 1e-6))
    else:
        label = 'uncertain'
        text = 'Needs review'
        midpoint = (lower_bound + upper_bound) / 2.0
        confidence = 1.0 - min(1.0, abs(signal - midpoint) / (band_width / 2.0))

    return {
        'label': label,
        'text': text,
        'signal': round(signal, 4),
        'confidence': round(confidence, 4),
        'bounds': {'lower': lower_bound, 'upper': upper_bound},
        'metrics': {
            'visual_signal': round(float(cache_record['visual_signal']), 4),
            'metadata_adjustment': round(float(cache_record['metadata_adjustment']), 4),
            'mean_abs_diff': round(float(cache_record['mean_abs_diff']), 4),
            'changed_ratio': round(float(cache_record['changed_ratio']), 4),
            'largest_blob_ratio': round(float(cache_record['largest_blob_ratio']), 4),
            'blob_count': int(cache_record['blob_count']),
            'peak_blob_contrast': round(float(cache_record['peak_blob_contrast']), 4),
            'mask_mismatch': round(float(cache_record.get('mask_mismatch', 0.0)), 4),
            'pixel_ratio': round(float(cache_record['pixel_ratio']), 4),
            'filesize_ratio': round(float(cache_record['filesize_ratio']), 4),
            'tag_gap_ratio': round(float(cache_record['tag_gap_ratio']), 4),
        },
    }


def _build_suggestion_cache_record(
    metrics: Dict[str, Any],
    image_a: Dict[str, Any],
    image_b: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a raw suggestion record suitable for caching and later thresholding."""
    metadata_metrics = _compute_metadata_metrics(image_a, image_b)
    visual_signal = metrics['variation_signal']
    metadata_adjustment = _apply_metadata_adjustment_guard(
        metadata_metrics['variation_adjustment'],
        visual_signal,
        metrics['largest_blob_ratio'],
    )
    return {
        'signal': min(1.0, visual_signal + metadata_adjustment),
        'visual_signal': visual_signal,
        'metadata_adjustment': metadata_adjustment,
        'mean_abs_diff': metrics['mean_abs_diff'],
        'changed_ratio': metrics['changed_ratio'],
        'largest_blob_ratio': metrics['largest_blob_ratio'],
        'blob_count': metrics['blob_count'],
        'peak_blob_contrast': metrics['peak_blob_contrast'],
        'mask_mismatch': metrics.get('mask_mismatch', 0.0),
        'pixel_ratio': metadata_metrics['pixel_ratio'],
        'filesize_ratio': metadata_metrics['filesize_ratio'],
        'tag_gap_ratio': metadata_metrics['tag_gap_ratio'],
    }


def _apply_metadata_adjustment_guard(
    raw_adjustment: float,
    visual_signal: float,
    largest_blob_ratio: float,
) -> float:
    """Prevent metadata from overpowering visually near-identical pairs."""
    if raw_adjustment <= 0:
        return 0.0

    if visual_signal >= _LOW_VISUAL_SIGNAL_GUARD or largest_blob_ratio >= _LOW_BLOB_RATIO_GUARD:
        return raw_adjustment

    visual_scale = min(1.0, max(visual_signal, 0.0) / _LOW_VISUAL_SIGNAL_GUARD)
    blob_scale = min(1.0, max(largest_blob_ratio, 0.0) / _LOW_BLOB_RATIO_GUARD)
    guard_scale = max(0.15, max(visual_scale, blob_scale))
    return raw_adjustment * guard_scale


def _compute_metadata_metrics(
    image_a: Dict[str, Any],
    image_b: Dict[str, Any],
) -> Dict[str, float]:
    """Compute secondary metadata evidence that can nudge the suggestion."""
    pixels_a = max(1, int(image_a.get('width', 0) or 0) * int(image_a.get('height', 0) or 0))
    pixels_b = max(1, int(image_b.get('width', 0) or 0) * int(image_b.get('height', 0) or 0))
    file_a = max(1, int(image_a.get('file_size', 0) or 0))
    file_b = max(1, int(image_b.get('file_size', 0) or 0))
    tags_a = max(0, int(image_a.get('tag_count', 0) or 0))
    tags_b = max(0, int(image_b.get('tag_count', 0) or 0))

    pixel_ratio = min(pixels_a, pixels_b) / max(pixels_a, pixels_b)
    filesize_ratio = min(file_a, file_b) / max(file_a, file_b)
    tag_gap_ratio = abs(tags_a - tags_b) / max(max(tags_a, tags_b), 1)

    variation_adjustment = (
        ((1.0 - pixel_ratio) * 0.020)
        + ((1.0 - filesize_ratio) * 0.012)
        + (tag_gap_ratio * 0.006)
    )

    return {
        'pixel_ratio': pixel_ratio,
        'filesize_ratio': filesize_ratio,
        'tag_gap_ratio': tag_gap_ratio,
        'variation_adjustment': variation_adjustment,
    }


def _compute_pair_visual_metrics(
    image_a: Dict[str, Any],
    image_b: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute symmetric visual diff metrics for a pair using previews."""
    path_a, mtime_a = _resolve_preview_path(image_a)
    path_b, mtime_b = _resolve_preview_path(image_b)
    if not path_a or not path_b:
        return {'available': False, 'reason': 'missing_preview'}

    ordered_paths = sorted(
        [(path_a, mtime_a), (path_b, mtime_b)],
        key=lambda item: item[0],
    )
    (path_1, mtime_1), (path_2, mtime_2) = ordered_paths

    return _compute_pair_visual_metrics_cached(path_1, mtime_1, path_2, mtime_2)


def _resolve_preview_path(image: Dict[str, Any]) -> Tuple[Optional[str], float]:
    """Prefer the thumbnail preview, falling back to the original image path."""
    candidates = [image.get('thumb', ''), image.get('path', '')]
    for rel_path in candidates:
        if not rel_path:
            continue
        abs_path = os.path.join("static", rel_path)
        if os.path.exists(abs_path):
            return abs_path, os.path.getmtime(abs_path)
    return None, 0.0


@lru_cache(maxsize=4096)
def _compute_pair_visual_metrics_cached(
    path_a: str,
    mtime_a: float,
    path_b: str,
    mtime_b: float,
) -> Dict[str, Any]:
    """Cached visual-diff metrics derived from normalized preview images."""
    del mtime_a, mtime_b

    try:
        rgb_a, gray_a, mask_a = _load_visual_diff_arrays(path_a)
        rgb_b, gray_b, mask_b = _load_visual_diff_arrays(path_b)
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return {'available': False, 'reason': 'image_load_failed'}
    except Exception:
        return {'available': False, 'reason': 'visual_diff_failed'}

    union_mask = np.maximum(mask_a, mask_b) > 0
    if not np.any(union_mask):
        return {'available': False, 'reason': 'empty_overlay'}

    rgb_diff = np.max(np.abs(rgb_a - rgb_b), axis=2)
    gray_diff = np.abs(gray_a - gray_b)
    mask_diff = np.abs(mask_a - mask_b)

    mean_abs_diff = float(np.mean(rgb_diff[union_mask]))
    raw_change_mask = (rgb_diff >= _DIFF_PIXEL_THRESHOLD) & union_mask
    cleaned_change_mask = _remove_diff_speckles(raw_change_mask)
    changed_ratio = float(np.mean(cleaned_change_mask[union_mask]))
    mask_mismatch = float(np.mean(mask_diff))
    blob_count, largest_blob_pixels, peak_blob_contrast = _extract_change_regions(
        cleaned_change_mask,
        gray_diff,
        union_mask,
    )
    overlay_pixels = max(int(np.count_nonzero(union_mask)), 1)
    largest_blob_ratio = largest_blob_pixels / overlay_pixels
    variation_signal = (
        (largest_blob_ratio * 0.55)
        + (peak_blob_contrast * 0.25)
        + (changed_ratio * 0.15)
        + (mask_mismatch * 0.05)
    )

    return {
        'available': True,
        'mean_abs_diff': mean_abs_diff,
        'changed_ratio': changed_ratio,
        'largest_blob_ratio': largest_blob_ratio,
        'blob_count': blob_count,
        'peak_blob_contrast': peak_blob_contrast,
        'mask_mismatch': mask_mismatch,
        'variation_signal': variation_signal,
    }


def _load_visual_diff_arrays(path: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load and aspect-fit an image preview for overlay-style visual diff metrics."""
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        rgba = img.convert('RGBA')

        fitted = Image.new(
            'RGBA',
            (_SUGGESTION_PREVIEW_SIZE, _SUGGESTION_PREVIEW_SIZE),
            (255, 255, 255, 0),
        )
        contained = ImageOps.contain(
            rgba,
            (_SUGGESTION_PREVIEW_SIZE, _SUGGESTION_PREVIEW_SIZE),
            Image.Resampling.LANCZOS,
        )
        offset = (
            (_SUGGESTION_PREVIEW_SIZE - contained.width) // 2,
            (_SUGGESTION_PREVIEW_SIZE - contained.height) // 2,
        )
        fitted.paste(contained, offset, contained)

        alpha = np.asarray(fitted.getchannel('A'), dtype=np.float32) / 255.0
        background = Image.new('RGB', fitted.size, (255, 255, 255))
        background.paste(fitted, mask=fitted.getchannel('A'))

        gray = background.convert('L').filter(ImageFilter.GaussianBlur(radius=0.4))
        return (
            np.asarray(background, dtype=np.float32) / 255.0,
            np.asarray(gray, dtype=np.float32) / 255.0,
            alpha,
        )


def _remove_diff_speckles(change_mask: np.ndarray) -> np.ndarray:
    """Drop isolated diff pixels so compression noise doesn't dominate region scoring."""
    padded = np.pad(change_mask.astype(np.uint8), 1, mode='constant')
    neighbor_count = sum(
        padded[1 + dy:1 + dy + change_mask.shape[0], 1 + dx:1 + dx + change_mask.shape[1]]
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
    )
    return change_mask & (neighbor_count >= _DIFF_NEIGHBOR_MIN)


def _extract_change_regions(
    change_mask: np.ndarray,
    gray_diff: np.ndarray,
    union_mask: np.ndarray,
) -> Tuple[int, int, float]:
    """Measure coherent changed regions in the overlay diff mask."""
    visited = np.zeros(change_mask.shape, dtype=bool)
    rows, cols = change_mask.shape
    blob_count = 0
    largest_blob_pixels = 0
    peak_blob_contrast = 0.0

    for row, col in np.argwhere(change_mask):
        if visited[row, col]:
            continue

        stack = [(int(row), int(col))]
        visited[row, col] = True
        blob_pixels = []

        while stack:
            r, c = stack.pop()
            blob_pixels.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = r + dr, c + dc
                    if nr < 0 or nc < 0 or nr >= rows or nc >= cols:
                        continue
                    if visited[nr, nc] or not change_mask[nr, nc]:
                        continue
                    visited[nr, nc] = True
                    stack.append((nr, nc))

        blob_size = len(blob_pixels)
        if blob_size == 0:
            continue

        blob_count += 1
        largest_blob_pixels = max(largest_blob_pixels, blob_size)
        contrasts = [gray_diff[r, c] for r, c in blob_pixels if union_mask[r, c]]
        if contrasts:
            peak_blob_contrast = max(peak_blob_contrast, float(np.mean(contrasts)))

    return blob_count, largest_blob_pixels, peak_blob_contrast


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
        'errors': [],
        'calibration_log_path': (
            os.path.abspath(config.DUPLICATE_REVIEW_CALIBRATION_LOG)
            if config.ENABLE_DUPLICATE_REVIEW_CALIBRATION
            else None
        ),
        'calibration': {
            'matches': 0,
            'uncertain': 0,
            'mismatches': 0,
            'logged': 0,
        },
    }
    total = len(actions)

    for idx, action_item in enumerate(actions):
        try:
            _execute_action(action_item)
            results['success_count'] += 1
            outcome = _log_calibration_sample(action_item)
            if outcome:
                results['calibration'][outcome] += 1
                results['calibration']['logged'] += 1
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


def _log_calibration_sample(action_item: Dict[str, Any]) -> Optional[str]:
    """Append a calibration sample comparing suggestion vs manual decision."""
    if not config.ENABLE_DUPLICATE_REVIEW_CALIBRATION:
        return None

    suggestion = action_item.get('suggestion')
    if not isinstance(suggestion, dict):
        suggestion = _rebuild_suggestion_for_action(action_item)
        if not suggestion:
            return None

    manual_class = _manual_action_class(action_item)
    suggested_class = suggestion.get('label', 'unavailable')
    outcome = _calibration_outcome(suggested_class, manual_class)

    record = {
        'timestamp': datetime.utcnow().isoformat(),
        'image_id_a': action_item.get('image_id_a'),
        'image_id_b': action_item.get('image_id_b'),
        'action': action_item.get('action'),
        'detail': action_item.get('detail'),
        'manual_class': manual_class,
        'suggested_class': suggested_class,
        'outcome': outcome,
        'signal': suggestion.get('signal'),
        'confidence': suggestion.get('confidence'),
        'bounds': suggestion.get('bounds', {}),
        'metrics': suggestion.get('metrics', {}),
    }

    log_path = os.path.abspath(config.DUPLICATE_REVIEW_CALIBRATION_LOG)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, sort_keys=True) + '\n')

    return outcome


def _manual_action_class(action_item: Dict[str, Any]) -> str:
    """Collapse review actions to duplicate vs variation for calibration."""
    action = action_item.get('action')
    if action in {'delete_a', 'delete_b'}:
        return 'duplicate'
    if action in {'non_duplicate', 'related'}:
        return 'variation'
    return 'other'


def _rebuild_suggestion_for_action(action_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Recompute a suggestion snapshot when the client did not send one."""
    id_a = action_item.get('image_id_a')
    id_b = action_item.get('image_id_b')
    if not id_a or not id_b:
        return None

    image_a = _enrich_image_by_id(id_a)
    image_b = _enrich_image_by_id(id_b)
    metrics = _compute_pair_visual_metrics(image_a, image_b)
    return _build_visual_suggestion(
        metrics,
        image_a,
        image_b,
        _SUGGESTION_LOWER_BOUND,
        _SUGGESTION_UPPER_BOUND,
    )


def _calibration_outcome(suggested_class: str, manual_class: str) -> str:
    """Classify a suggestion as match, uncertain, or mismatch."""
    if suggested_class in {'uncertain', 'unavailable'} or manual_class == 'other':
        return 'uncertain'
    if suggested_class == 'likely_duplicate' and manual_class == 'duplicate':
        return 'matches'
    if suggested_class == 'likely_variation' and manual_class == 'variation':
        return 'matches'
    return 'mismatches'


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

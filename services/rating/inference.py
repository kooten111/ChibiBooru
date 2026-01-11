"""
Rating inference and prediction logic.
"""

import math
import multiprocessing
import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from database import get_db_connection
from .config import RATINGS, get_model_connection, get_config
from .data import get_unrated_images, get_unrated_images_count, get_unrated_images_batched

logger = logging.getLogger(__name__)


def load_weights() -> Tuple[Dict, Dict]:
    """
    Load tag and pair weights from database.

    Returns:
        tuple: (tag_weights, pair_weights)
            tag_weights: {(tag, rating): weight}
            pair_weights: {(tag1, tag2, rating): weight}
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Load tag weights with joins to get names
        cur.execute("""
            SELECT t.name as tag_name, r.name as rating, tw.weight
            FROM rating_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN ratings r ON tw.rating_id = r.id
        """)
        tag_weights = {
            (row['tag_name'], row['rating']): row['weight']
            for row in cur.fetchall()
        }

        # Load pair weights with joins to get names
        cur.execute("""
            SELECT t1.name as tag1, t2.name as tag2, r.name as rating, pw.weight
            FROM rating_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN ratings r ON pw.rating_id = r.id
        """)
        pair_weights = {
            (row['tag1'], row['tag2'], row['rating']): row['weight']
            for row in cur.fetchall()
        }

        return tag_weights, pair_weights


def calculate_rating_scores(image_tags: List[str],
                            tag_weights: Dict,
                            pair_weights: Dict,
                            config: Dict) -> Dict[str, float]:
    """
    Calculate raw scores for each rating.

    Args:
        image_tags: Tags to score
        tag_weights: Individual tag weights
        pair_weights: Tag pair weights
        config: Inference config (for pair multiplier)

    Returns:
        dict: {rating: raw_score}
    """
    scores = {rating: 0.0 for rating in RATINGS}

    # Accumulate individual tag weights
    for tag in image_tags:
        for rating in RATINGS:
            weight = tag_weights.get((tag, rating), 0.0)
            scores[rating] += weight

    # Accumulate tag pair weights
    # Limit tags to prevent O(n²) explosion for images with many tags
    pair_multiplier = config['pair_weight_multiplier']
    MAX_TAGS_FOR_PAIRS = 100  # 100 tags = ~5000 pairs, which is manageable
    
    # Use only the first N tags (sorted for consistency)
    from itertools import combinations
    sorted_tags = sorted(image_tags)
    if len(sorted_tags) > MAX_TAGS_FOR_PAIRS:
        sorted_tags = sorted_tags[:MAX_TAGS_FOR_PAIRS]

    for tag1, tag2 in combinations(sorted_tags, 2):
        for rating in RATINGS:
            pair_weight = pair_weights.get((tag1, tag2, rating), 0.0)
            scores[rating] += pair_weight * pair_multiplier

    return scores


def scores_to_probabilities(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Convert log-likelihood scores to normalized probabilities using softmax.

    Args:
        scores: {rating: raw_score}

    Returns:
        dict: {rating: probability} (sums to 1.0)
    """
    if not scores:
        return {rating: 0.0 for rating in RATINGS}

    # Softmax with numerical stability (subtract max)
    max_score = max(scores.values())
    exp_scores = {rating: math.exp(score - max_score)
                  for rating, score in scores.items()}

    total = sum(exp_scores.values())
    if total == 0:
        return {rating: 1.0 / len(RATINGS) for rating in RATINGS}

    probabilities = {rating: exp_score / total
                    for rating, exp_score in exp_scores.items()}

    return probabilities


def predict_rating(image_tags: List[str],
                  tag_weights: Dict = None,
                  pair_weights: Dict = None,
                  config: Dict = None) -> Tuple[Optional[str], float]:
    """
    Predict rating for an image based on its tags.

    Args:
        image_tags: List of tag names for the image
        tag_weights: Preloaded tag weights (optional, will load if not provided)
        pair_weights: Preloaded pair weights (optional, will load if not provided)
        config: Preloaded config (optional, will load if not provided)

    Returns:
        tuple: (rating, confidence) or (None, confidence) if below threshold
    """
    if not image_tags:
        return None, 0.0

    # Load weights and config if not provided
    if tag_weights is None or pair_weights is None:
        tag_weights, pair_weights = load_weights()

    if config is None:
        config = get_config()

    # Check if model is trained
    if not tag_weights and not pair_weights:
        return None, 0.0

    # Calculate scores
    scores = calculate_rating_scores(image_tags, tag_weights, pair_weights, config)

    # Convert to probabilities
    probabilities = scores_to_probabilities(scores)

    # Find best rating
    best_rating = max(probabilities, key=probabilities.get)
    confidence = probabilities[best_rating]

    # Check against thresholds
    rating_key = best_rating.split(':')[1]  # 'rating:general' -> 'general'
    rating_threshold = config.get(f'threshold_{rating_key}', 0.5)
    min_confidence = config['min_confidence']

    if confidence >= max(rating_threshold, min_confidence):
        return best_rating, confidence
    else:
        return None, confidence


def infer_rating_for_image(image_id: int) -> Dict:
    """
    Run inference on a single image.

    Args:
        image_id: Database ID of image

    Returns:
        dict: {'rated': bool, 'rating': str | None, 'confidence': float}
    """
    # Get image tags
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ?
              AND t.name NOT IN ({})
        """.format(','.join('?' * len(RATINGS))), [image_id] + RATINGS)

        tags = [row['name'] for row in cur.fetchall()]

    if not tags:
        return {'rated': False, 'rating': None, 'confidence': 0.0}

    # Predict rating
    rating, confidence = predict_rating(tags)

    if rating:
        # Add rating tag with source='ai_inference'
        set_image_rating(image_id, rating, source='ai_inference', confidence=confidence)
        return {'rated': True, 'rating': rating, 'confidence': confidence}
    else:
        return {'rated': False, 'rating': None, 'confidence': confidence}


def infer_all_unrated_images(progress_callback=None) -> Dict:
    """
    Run inference on all images without rating tags.
    
    Args:
        progress_callback: Optional callable(percent, message)

    Returns:
        dict: Statistics about inference run
    """
    start_time = datetime.now()
    
    if progress_callback:
        progress_callback(0, "Initializing inference...")

    # Load weights once for efficiency
    tag_weights, pair_weights = load_weights()
    config = get_config()

    if not tag_weights and not pair_weights:
        raise ValueError("Model not trained. Run train_model() first.")

    unrated_images = get_unrated_images()
    
    if not unrated_images:
        if progress_callback:
            progress_callback(100, "No unrated images found.")
        return {
            'processed': 0, 'rated': 0, 'skipped_low_confidence': 0, 'by_rating': {}, 'duration_seconds': 0
        }

    stats = {
        'processed': 0,
        'rated': 0,
        'skipped_low_confidence': 0,
        'by_rating': {r: 0 for r in RATINGS}
    }

    print(f"Running inference on {len(unrated_images)} unrated images...")
    
    total_images = len(unrated_images)

    for i, (image_id, tags) in enumerate(unrated_images):
        stats['processed'] += 1

        if not tags:
            stats['skipped_low_confidence'] += 1
            continue

        rating, confidence = predict_rating(tags, tag_weights, pair_weights, config)

        if rating:
            set_image_rating(image_id, rating, source='ai_inference', confidence=confidence)
            stats['rated'] += 1
            stats['by_rating'][rating] += 1
        else:
            stats['skipped_low_confidence'] += 1

        if (i + 1) % 10 == 0 or (i + 1) == total_images:
            percent = int((i + 1) / total_images * 90)
            if progress_callback:
                progress_callback(percent, f"Processed {i + 1}/{total_images}...")
            
            # Log less frequently
            if (i + 1) % 50 == 0:
                print(f"  Processed {stats['processed']}/{len(unrated_images)}...")
            
    # Final progress update
    if progress_callback:
        progress_callback(100, "Inference complete!")

    duration = (datetime.now() - start_time).total_seconds()
    stats['duration_seconds'] = round(duration, 2)

    print(f"Inference complete in {duration:.2f}s")
    print(f"  Rated: {stats['rated']}")
    print(f"  Skipped (low confidence): {stats['skipped_low_confidence']}")

    return stats


def _process_rating_chunk_worker(args):
    """
    Worker function for processing a chunk of images in parallel for rating inference.
    This runs in a separate process, so it needs to load weights itself.
    
    Args:
        args: Tuple of (image_chunk, tag_weights, pair_weights, config)
            image_chunk: List of (image_id, tags) tuples
    
    Returns:
        dict: {'ratings': {image_id: (rating, confidence)}, 'stats': {...}}
    """
    image_chunk, tag_weights, pair_weights, config = args
    
    process_id = os.getpid()
    worker_name = multiprocessing.current_process().name
    
    print(f"[WORKER] {worker_name} (PID {process_id}) processing {len(image_chunk)} images", file=sys.stderr, flush=True)
    logger.info(f"Worker {worker_name} (PID {process_id}) processing {len(image_chunk)} images")
    
    ratings_dict = {}
    stats = {
        'processed': 0,
        'rated': 0,
        'skipped_low_confidence': 0,
        'skipped_no_tags': 0
    }
    
    for image_id, tags in image_chunk:
        stats['processed'] += 1
        
        if not tags:
            stats['skipped_no_tags'] += 1
            continue
        
        # Predict rating (without storing - main process will batch store)
        rating, confidence = predict_rating(tags, tag_weights, pair_weights, config)
        
        if rating:
            ratings_dict[image_id] = (rating, confidence)
            stats['rated'] += 1
        else:
            stats['skipped_low_confidence'] += 1
    
    print(f"[WORKER] {worker_name} (PID {process_id}) completed: {stats['processed']} processed, {stats['rated']} rated", file=sys.stderr, flush=True)
    logger.info(f"Worker {worker_name} (PID {process_id}) completed: {stats['processed']} processed, {stats['rated']} rated")
    return {'ratings': ratings_dict, 'stats': stats}


def precompute_ratings_for_unrated_images(limit: int = None, progress_callback=None, batch_size: int = 200, num_workers: int = None) -> Dict:
    """
    Pre-compute and store rating predictions for unrated images using multiprocessing.
    This allows the review interface to load quickly.
    
    Uses batched processing with multiprocessing to reduce memory usage and utilize multiple CPU cores.
    
    Args:
        limit: Optional limit on number of images to process
        progress_callback: Optional callback function(processed, total)
        batch_size: Number of images to process per batch (default: 200)
        num_workers: Number of parallel worker processes (default: auto-detect from CPU count, max 4)
    
    Returns:
        dict: Statistics about precomputation
    """
    # Log to monitor service (visible in UI) - do this FIRST
    try:
        from services import monitor_service
        monitor_service.add_log("=== Starting rating prediction precomputation ===", "info")
    except Exception as e:
        logger.error(f"Failed to log to monitor_service: {e}")
    
    logger.info("=== precompute_ratings_for_unrated_images called ===")
    
    start_time = datetime.now()
    
    # Load weights once for efficiency
    tag_weights, pair_weights = load_weights()
    config = get_config()
    
    if not tag_weights and not pair_weights:
        raise ValueError("Model not trained. Run train_model() first.")
    
    # Get total count first for progress tracking
    total_images = get_unrated_images_count()
    if limit:
        total_images = min(total_images, limit)
    
    stats = {
        'processed': 0,
        'rated': 0,
        'skipped_low_confidence': 0,
        'skipped_no_tags': 0,
        'total': total_images
    }
    
    # Determine number of workers
    if num_workers is None:
        try:
            import config as app_config
            num_workers = getattr(app_config, 'MAX_WORKERS', None)
        except:
            num_workers = None
        
        if num_workers is None or num_workers <= 0:
            cpu_count = multiprocessing.cpu_count()
            num_workers = max(1, min(cpu_count - 1, 4))  # Use up to 4 workers, leave 1 core free
    
    main_pid = os.getpid()
    
    # Log to monitor service (visible in UI)
    try:
        monitor_service.add_log(f"Main process PID: {main_pid}, Using {num_workers} worker processes", "info")
        monitor_service.add_log(f"Pre-computing ratings for {total_images} unrated images (batch size: {batch_size})", "info")
    except:
        pass
    
    print(f"[MAIN] Main process PID: {main_pid}", file=sys.stderr, flush=True)
    print(f"[MAIN] Starting ProcessPoolExecutor with {num_workers} workers...", file=sys.stderr, flush=True)
    logger.info(f"Main process PID: {main_pid}")
    logger.info(f"Pre-computing ratings for {total_images} unrated images (batch size: {batch_size}, workers: {num_workers})...")
    
    # Initialize progress callback with total count
    if progress_callback:
        progress_callback(0, total_images)
    
    # Process in batches to reduce memory usage
    offset = 0
    remaining = total_images
    
    # Use multiprocessing for CPU-bound prediction work
    # Force 'spawn' method for better process isolation (works on all platforms)
    try:
        current_method = multiprocessing.get_start_method(allow_none=True)
        try:
            monitor_service.add_log(f"Multiprocessing start method: {current_method}", "info")
        except:
            pass
        print(f"[MAIN] Current multiprocessing start method: {current_method}", file=sys.stderr, flush=True)
        if current_method != 'spawn':
            try:
                multiprocessing.set_start_method('spawn', force=True)
                try:
                    monitor_service.add_log("Changed start method to 'spawn'", "info")
                except:
                    pass
                print(f"[MAIN] Changed start method to 'spawn'", file=sys.stderr, flush=True)
            except RuntimeError as e:
                try:
                    monitor_service.add_log(f"Could not change start method: {e}", "warning")
                except:
                    pass
                print(f"[MAIN] Could not change start method (may already be set): {e}", file=sys.stderr, flush=True)
    except Exception as e:
        try:
            monitor_service.add_log(f"Warning checking start method: {e}", "warning")
        except:
            pass
        print(f"[MAIN] Warning checking start method: {e}", file=sys.stderr, flush=True)
    
    logger.info(f"Starting ProcessPoolExecutor with {num_workers} workers...")
    try:
        monitor_service.add_log(f"Creating ProcessPoolExecutor with {num_workers} workers for parallel processing", "info")
    except:
        pass
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        while remaining > 0:
            # Get current batch
            current_batch_size = min(batch_size, remaining)
            unrated_images = get_unrated_images_batched(
                batch_size=current_batch_size,
                offset=offset,
                limit=limit
            )
            
            if not unrated_images:
                # No more images to process
                break
            
            # Split batch into chunks for parallel processing
            chunk_size = max(1, len(unrated_images) // num_workers)
            if chunk_size == 0:
                chunk_size = 1
            
            chunks = []
            for i in range(0, len(unrated_images), chunk_size):
                chunk = unrated_images[i:i + chunk_size]
                if chunk:
                    chunks.append((chunk, tag_weights, pair_weights, config))
            
            try:
                monitor_service.add_log(f"Split batch of {len(unrated_images)} images into {len(chunks)} chunks", "info")
            except:
                pass
            print(f"[MAIN] Split batch of {len(unrated_images)} images into {len(chunks)} chunks (chunk size: {chunk_size})", file=sys.stderr, flush=True)
            logger.info(f"Split batch of {len(unrated_images)} images into {len(chunks)} chunks (chunk size: {chunk_size})")
            
            # Submit all chunks to workers
            future_to_chunk = {}
            for chunk_idx, chunk in enumerate(chunks):
                try:
                    try:
                        monitor_service.add_log(f"Submitting chunk {chunk_idx + 1}/{len(chunks)} to worker...", "info")
                    except:
                        pass
                    print(f"[MAIN] Submitting chunk {chunk_idx + 1}/{len(chunks)} to worker pool...", file=sys.stderr, flush=True)
                    future = executor.submit(_process_rating_chunk_worker, chunk)
                    future_to_chunk[future] = chunk
                    print(f"[MAIN] Chunk {chunk_idx + 1} submitted successfully", file=sys.stderr, flush=True)
                    logger.info(f"Submitted chunk {chunk_idx + 1}/{len(chunks)} to worker pool")
                except Exception as e:
                    error_msg = f"ERROR submitting chunk {chunk_idx + 1}: {e}"
                    try:
                        monitor_service.add_log(error_msg, "error")
                    except:
                        pass
                    print(f"[MAIN] {error_msg}", file=sys.stderr, flush=True)
                    logger.error(f"Error submitting chunk {chunk_idx + 1}: {e}", exc_info=True)
            
            # Collect results as they complete (progress updates as each chunk finishes)
            all_ratings = {}
            completed_chunks = 0
            total_chunks = len(chunks)
            
            try:
                monitor_service.add_log(f"Waiting for {total_chunks} chunks to complete...", "info")
            except:
                pass
            
            for future in as_completed(future_to_chunk):
                try:
                    result = future.result()
                    all_ratings.update(result['ratings'])
                    
                    # Aggregate stats
                    chunk_stats = result['stats']
                    stats['processed'] += chunk_stats['processed']
                    stats['rated'] += chunk_stats['rated']
                    stats['skipped_low_confidence'] += chunk_stats['skipped_low_confidence']
                    stats['skipped_no_tags'] += chunk_stats['skipped_no_tags']
                    
                    completed_chunks += 1
                    
                    try:
                        monitor_service.add_log(f"Chunk {completed_chunks}/{total_chunks} completed: {chunk_stats['processed']} processed", "info")
                    except:
                        pass
                    
                    # Update progress after each chunk completes
                    if progress_callback:
                        progress_callback(stats['processed'], total_images)
                        
                except Exception as e:
                    error_msg = f"Error processing chunk: {e}"
                    try:
                        monitor_service.add_log(error_msg, "error")
                    except:
                        pass
                    logger.error(error_msg, exc_info=True)
                    completed_chunks += 1  # Count failed chunks too
            
            # Batch store all ratings from this batch
            if all_ratings:
                for image_id, (rating, confidence) in all_ratings.items():
                    set_image_rating(image_id, rating, source='ai_inference', confidence=confidence)
                all_ratings = {}  # Clear to free memory
            
            # Get batch length before clearing
            batch_length = len(unrated_images)
            
            # Clear the batch data to free memory
            del unrated_images
            
            # Update offset and remaining count
            offset += batch_length
            remaining = total_images - offset
            
            # Log progress
            if stats['processed'] % 100 == 0:
                logger.info(f"  Processed {stats['processed']}/{total_images}...")
            
            # If we got fewer images than requested, we're done
            if batch_length < current_batch_size:
                break
            
            # Check if we've hit the limit
            if limit and stats['processed'] >= limit:
                break
    
    duration = (datetime.now() - start_time).total_seconds()
    stats['duration_seconds'] = round(duration, 2)
    
    logger.info(f"Pre-computation complete in {duration:.2f}s")
    logger.info(f"  Rated: {stats['rated']} images")
    
    return stats


def set_image_rating(image_id: int, rating: Optional[str],
                    source: str = 'user', confidence: float = None) -> Dict:
    """
    Set or remove rating for an image.

    Args:
        image_id: Image to rate
        rating: Rating tag name (or None to remove rating)
        source: Tag source (default 'user')
        confidence: Optional confidence score for AI predictions

    Returns:
        dict: {'old_rating': str | None, 'new_rating': str | None}
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get old rating
        cur.execute(f"""
            SELECT t.name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ?
              AND t.name IN ({','.join('?' * len(RATINGS))})
        """, [image_id] + RATINGS)

        old_rating_row = cur.fetchone()
        old_rating = old_rating_row['name'] if old_rating_row else None

        # Remove all existing rating tags and rating-source tags
        if old_rating:
            cur.execute("""
                DELETE FROM image_tags
                WHERE image_id = ?
                  AND tag_id IN (
                      SELECT id FROM tags WHERE name IN ({})
                  )
            """.format(','.join('?' * len(RATINGS))), [image_id] + RATINGS)

        # Remove old rating-source tags
        cur.execute("""
            DELETE FROM image_tags
            WHERE image_id = ?
              AND tag_id IN (
                  SELECT id FROM tags WHERE name LIKE 'rating-source:%'
              )
        """, (image_id,))

        # Add new rating if provided
        if rating:
            # Ensure rating tag exists
            cur.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (rating, 'meta')
            )

            # Get rating tag ID
            cur.execute("SELECT id FROM tags WHERE name = ?", (rating,))
            tag_id = cur.fetchone()['id']

            # Add rating tag
            cur.execute(
                "INSERT OR REPLACE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)",
                (image_id, tag_id, source)
            )

            # Add rating-source tag for searchability
            source_tag_name = f'rating-source:{source.replace("_", "-")}'
            cur.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (source_tag_name, 'meta')
            )
            cur.execute("SELECT id FROM tags WHERE name = ?", (source_tag_name,))
            source_tag_id = cur.fetchone()['id']
            cur.execute(
                "INSERT OR REPLACE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)",
                (image_id, source_tag_id, source)
            )

            # Record in tag_deltas if user-initiated
            if source == 'user':
                cur.execute("""
                    INSERT OR IGNORE INTO tag_deltas (image_md5, tag_name, tag_category, operation)
                    SELECT md5, ?, 'meta', 'add'
                    FROM images
                    WHERE id = ?
                """, (rating, image_id))

                if old_rating and old_rating != rating:
                    cur.execute("""
                        INSERT OR IGNORE INTO tag_deltas (image_md5, tag_name, tag_category, operation)
                        SELECT md5, ?, 'meta', 'remove'
                        FROM images
                        WHERE id = ?
                    """, (old_rating, image_id))

        conn.commit()

        # Increment pending corrections counter in model DB if user-initiated
        if source == 'user' and rating:
            with get_model_connection() as model_conn:
                model_cur = model_conn.cursor()
                model_cur.execute("""
                    INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at)
                    VALUES ('pending_user_corrections',
                            COALESCE((SELECT CAST(value AS INTEGER) + 1
                                     FROM rating_model_metadata
                                     WHERE key = 'pending_user_corrections'), 1),
                            ?)
                """, (datetime.now(),))
                model_conn.commit()

        return {'old_rating': old_rating, 'new_rating': rating}

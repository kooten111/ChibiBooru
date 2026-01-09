# rating_inference.py
"""
Rating inference system for automatic content rating classification.

This module implements a self-learning rating prediction system that learns from
your tagging habits to automatically classify images by content rating.
"""

import sqlite3
import math
from collections import defaultdict, Counter
from itertools import combinations
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from database import get_db_connection
from repositories.rating_repository import get_or_create_tag_id, get_or_create_rating_id

# Rating categories
RATINGS = [
    'rating:general',
    'rating:sensitive',
    'rating:questionable',
    'rating:explicit'
]

# Model database configuration
USE_SEPARATE_MODEL_DB = True


def get_model_connection():
    """Get connection to model database (separate or main DB)."""
    if USE_SEPARATE_MODEL_DB:
        from repositories.rating_repository import get_model_db_connection
        return get_model_db_connection()
    else:
        return get_db_connection()

# ============================================================================
# Configuration Management
# ============================================================================

def get_config() -> Dict[str, float]:
    """Get current inference configuration from database."""
    with get_model_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM rating_inference_config")
        return {row['key']: row['value'] for row in cur.fetchall()}


def update_config(key: str, value: float) -> None:
    """Update a single config value."""
    with get_model_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO rating_inference_config (key, value) VALUES (?, ?)",
            (key, value)
        )
        conn.commit()


def reset_config_to_defaults() -> None:
    """Reset all config to factory defaults."""
    import config
    defaults = config.RATING_MODEL_CONFIG.copy()
    
    # Add rating-specific thresholds
    defaults.update({
        'threshold_general': 0.5,
        'threshold_sensitive': 0.6,
        'threshold_questionable': 0.7,
        'threshold_explicit': 0.8,
        'min_training_samples': 50,
    })

    with get_model_connection() as conn:
        cur = conn.cursor()
        for key, value in defaults.items():
            cur.execute(
                "UPDATE rating_inference_config SET value = ? WHERE key = ?",
                (value, key)
            )
        conn.commit()


# ============================================================================
# Data Retrieval
# ============================================================================

def get_rated_images(sources: List[str] = None, progress_callback=None) -> List[Tuple[int, str, List[str]]]:
    """
    Get all images with rating tags from trusted sources.

    Args:
        sources: Which tag sources to trust (default: ['user', 'original'])

    Returns:
        List of (image_id, rating, tags) tuples
    """
    if sources is None:
        sources = ['user', 'original']

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find images with rating tags from trusted sources
        placeholders = ','.join('?' * len(sources))
        cur.execute(f"""
            SELECT DISTINCT it.image_id, t.name as rating
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name IN ({','.join('?' * len(RATINGS))})
              AND it.source IN ({placeholders})
        """, RATINGS + sources)

        rated_image_map = {}
        for row in cur.fetchall():
            image_id = row['image_id']
            rating = row['rating']
            if image_id not in rated_image_map:
                rated_image_map[image_id] = rating

        # Get all tags for these images
        if not rated_image_map:
            return []

        image_ids = list(rated_image_map.keys())
        total_images = len(image_ids)
        
        image_tags_map = defaultdict(list)
        
        # Batch processing to avoid SQLite limit and provide progress
        batch_size = 900 # Safe limit for SQLite variables
        for i in range(0, total_images, batch_size):
            batch = image_ids[i:i + batch_size]
            
            if progress_callback:
                progress = 5 + int((i / total_images) * 15) # 5-20% range
                progress_callback(progress, f"Loading tags for images {i+1}-{min(i+len(batch), total_images)}/{total_images}...")
            
            placeholders = ','.join('?' * len(batch))
            cur.execute(f"""
                SELECT it.image_id, t.name as tag_name
                FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id IN ({placeholders})
                  AND t.name NOT IN ({','.join('?' * len(RATINGS))})
            """, batch + RATINGS)

            for row in cur.fetchall():
                image_tags_map[row['image_id']].append(row['tag_name'])

        # Combine into result
        result = []
        for image_id, rating in rated_image_map.items():
            tags = image_tags_map.get(image_id, [])
            result.append((image_id, rating, tags))

        return result


def get_unrated_images() -> List[Tuple[int, List[str]]]:
    """
    Get all images without any rating tag.

    Returns:
        List of (image_id, tags) tuples
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find images without rating tags
        cur.execute(f"""
            SELECT i.id
            FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id = i.id
                  AND t.name IN ({','.join('?' * len(RATINGS))})
            )
        """, RATINGS)

        image_ids = [row['id'] for row in cur.fetchall()]

        if not image_ids:
            return []

        # Get tags for these images
        placeholders = ','.join('?' * len(image_ids))
        cur.execute(f"""
            SELECT it.image_id, t.name as tag_name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id IN ({placeholders})
        """, image_ids)

        image_tags_map = defaultdict(list)
        for row in cur.fetchall():
            image_tags_map[row['image_id']].append(row['tag_name'])

        result = [(img_id, image_tags_map.get(img_id, [])) for img_id in image_ids]
        return result


def get_unrated_images_count() -> int:
    """
    Get count of images without any rating tag (optimized for performance).

    Returns:
        Number of unrated images
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Count images without rating tags
        cur.execute(f"""
            SELECT COUNT(*) as count
            FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id = i.id
                  AND t.name IN ({','.join('?' * len(RATINGS))})
            )
        """, RATINGS)

        return cur.fetchone()['count']


def get_unrated_images_batched(batch_size: int = 500, offset: int = 0, limit: int = None) -> List[Tuple[int, List[str]]]:
    """
    Get images without rating tags in batches to reduce memory usage.
    
    Args:
        batch_size: Number of images to fetch per batch (default: 500)
        offset: Starting offset for pagination
        limit: Optional maximum total number of images to fetch
    
    Returns:
        List of (image_id, tags) tuples for the current batch
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find images without rating tags with pagination
        query = f"""
            SELECT i.id
            FROM images i
            WHERE NOT EXISTS (
                SELECT 1 FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id = i.id
                  AND t.name IN ({','.join('?' * len(RATINGS))})
            )
            ORDER BY i.id
            LIMIT ?
            OFFSET ?
        """
        
        # Apply limit if specified
        if limit is not None:
            effective_limit = min(batch_size, limit - offset)
            if effective_limit <= 0:
                return []
        else:
            effective_limit = batch_size
        
        cur.execute(query, RATINGS + [effective_limit, offset])
        image_ids = [row['id'] for row in cur.fetchall()]

        if not image_ids:
            return []

        # Get tags for these images (only current batch)
        placeholders = ','.join('?' * len(image_ids))
        cur.execute(f"""
            SELECT it.image_id, t.name as tag_name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id IN ({placeholders})
        """, image_ids)

        image_tags_map = defaultdict(list)
        for row in cur.fetchall():
            image_tags_map[row['image_id']].append(row['tag_name'])

        result = [(img_id, image_tags_map.get(img_id, [])) for img_id in image_ids]
        return result


# ============================================================================
# Training Algorithm
# ============================================================================

def calculate_tag_weights(rated_images: List[Tuple[int, str, List[str]]]) -> Dict[Tuple[str, str], Tuple[float, int]]:
    """
    Calculate log-likelihood ratio weights for individual tags.

    Args:
        rated_images: List of (image_id, rating, tags) tuples

    Returns:
        dict: {(tag, rating): (weight, sample_count)}
    """
    # Count tag occurrences per rating
    tag_rating_counts = defaultdict(int)  # (tag, rating) -> count
    rating_counts = Counter()  # rating -> total count
    tag_counts = Counter()  # tag -> total count across all ratings

    for image_id, rating, tags in rated_images:
        rating_counts[rating] += 1
        for tag in tags:
            tag_rating_counts[(tag, rating)] += 1
            tag_counts[tag] += 1

    total_images = len(rated_images)
    weights = {}

    for rating in RATINGS:
        rating_count = rating_counts[rating]
        if rating_count == 0:
            continue

        not_rating_count = total_images - rating_count
        if not_rating_count == 0:
            continue

        for tag in tag_counts:
            # Count images with (tag AND rating)
            with_rating = tag_rating_counts.get((tag, rating), 0)

            # Count images with (tag AND NOT rating)
            total_tag = tag_counts[tag]
            without_rating = total_tag - with_rating

            # Calculate probabilities
            # P(tag | rating)
            p_tag_given_rating = with_rating / rating_count if rating_count > 0 else 0

            # P(tag | NOT rating)
            p_tag_given_not_rating = without_rating / not_rating_count if not_rating_count > 0 else 0

            # Log-likelihood ratio (with smoothing to avoid log(0))
            epsilon = 1e-10
            p_tag_given_rating = max(p_tag_given_rating, epsilon)
            p_tag_given_not_rating = max(p_tag_given_not_rating, epsilon)

            weight = math.log(p_tag_given_rating / p_tag_given_not_rating)

            # Only store meaningful weights
            if abs(weight) > 0.01:
                weights[(tag, rating)] = (weight, with_rating)

    return weights


def find_frequent_tag_pairs(rated_images: List[Tuple[int, str, List[str]]],
                            min_cooccurrence: int,
                            min_tag_frequency: int,
                            limit: int) -> List[Tuple[str, str, int]]:
    """
    Find tag pairs that appear together frequently enough to be useful.

    Args:
        rated_images: Training data
        min_cooccurrence: Minimum times pair must appear together
        min_tag_frequency: Minimum images each tag must appear in
        limit: Maximum number of pairs to return

    Returns:
        List of (tag1, tag2, count) sorted by count descending
    """
    # Count individual tag frequencies
    tag_frequencies = Counter()
    for _, _, tags in rated_images:
        for tag in tags:
            tag_frequencies[tag] += 1

    # Filter to frequent tags
    frequent_tags = {tag for tag, count in tag_frequencies.items()
                     if count >= min_tag_frequency}

    # Count pair co-occurrences
    pair_counts = Counter()
    for _, _, tags in rated_images:
        # Only consider frequent tags
        filtered_tags = [tag for tag in tags if tag in frequent_tags]

        # Generate pairs (canonical order: tag1 < tag2)
        for tag1, tag2 in combinations(sorted(filtered_tags), 2):
            pair_counts[(tag1, tag2)] += 1

    # Filter by minimum co-occurrence and limit
    frequent_pairs = [(tag1, tag2, count)
                      for (tag1, tag2), count in pair_counts.items()
                      if count >= min_cooccurrence]

    # Sort by count descending and limit
    frequent_pairs.sort(key=lambda x: x[2], reverse=True)
    return frequent_pairs[:limit]


def calculate_tag_pair_weights(rated_images: List[Tuple[int, str, List[str]]],
                               frequent_pairs: List[Tuple[str, str, int]]) -> Dict[Tuple[str, str, str], Tuple[float, int]]:
    """
    Calculate log-likelihood ratio weights for tag pairs.

    Args:
        rated_images: List of (image_id, rating, tags) tuples
        frequent_pairs: List of (tag1, tag2, count) pairs to calculate weights for

    Returns:
        dict: {(tag1, tag2, rating): (weight, co_occurrence_count)}
    """
    # Convert pairs to set for fast lookup
    pair_set = {(tag1, tag2) for tag1, tag2, _ in frequent_pairs}

    # Count pair occurrences per rating
    pair_rating_counts = defaultdict(int)  # (tag1, tag2, rating) -> count
    rating_counts = Counter()  # rating -> total count
    pair_counts = Counter()  # (tag1, tag2) -> total count across all ratings

    for image_id, rating, tags in rated_images:
        rating_counts[rating] += 1

        # Generate pairs from this image's tags
        sorted_tags = sorted(tags)
        for tag1, tag2 in combinations(sorted_tags, 2):
            if (tag1, tag2) in pair_set:
                pair_rating_counts[(tag1, tag2, rating)] += 1
                pair_counts[(tag1, tag2)] += 1

    total_images = len(rated_images)
    weights = {}

    for rating in RATINGS:
        rating_count = rating_counts[rating]
        if rating_count == 0:
            continue

        not_rating_count = total_images - rating_count
        if not_rating_count == 0:
            continue

        for tag1, tag2, _ in frequent_pairs:
            # Count images with (pair AND rating)
            with_rating = pair_rating_counts.get((tag1, tag2, rating), 0)

            # Count images with (pair AND NOT rating)
            total_pair = pair_counts[(tag1, tag2)]
            without_rating = total_pair - with_rating

            # Calculate probabilities
            p_pair_given_rating = with_rating / rating_count if rating_count > 0 else 0
            p_pair_given_not_rating = without_rating / not_rating_count if not_rating_count > 0 else 0

            # Log-likelihood ratio (with smoothing)
            epsilon = 1e-10
            p_pair_given_rating = max(p_pair_given_rating, epsilon)
            p_pair_given_not_rating = max(p_pair_given_not_rating, epsilon)

            weight = math.log(p_pair_given_rating / p_pair_given_not_rating)

            # Only store meaningful weights
            if abs(weight) > 0.01:
                weights[(tag1, tag2, rating)] = (weight, with_rating)

    return weights


def train_model(progress_callback=None) -> Dict:
    """
    Train the rating inference model on all trusted ratings.

    Args:
        progress_callback: Optional callable(percent, message)

    Returns:
        dict: Training statistics including sample counts, duration, etc.

    Raises:
        ValueError: If not enough training samples available
    """
    start_time = datetime.now()
    
    if progress_callback:
        progress_callback(0, "Initializing training...")

    config = get_config()
    min_samples = int(config['min_training_samples'])

    # Get training data
    if progress_callback:
        progress_callback(5, "Loading rated images...")
        
    rated_images = get_rated_images(sources=['user', 'original'], progress_callback=progress_callback)

    if len(rated_images) < min_samples:
        raise ValueError(
            f"Not enough training samples. Need {min_samples}, have {len(rated_images)}. "
            "Manually rate more images before training."
        )

    print(f"Training on {len(rated_images)} rated images...")

    # Calculate individual tag weights
    if progress_callback:
        progress_callback(20, f"Calculating weights for {len(rated_images)} images...")
    
    print("Calculating individual tag weights...")
    tag_weights = calculate_tag_weights(rated_images)
    print(f"Calculated weights for {len(tag_weights)} tag-rating pairs")

    # Find frequent tag pairs
    if progress_callback:
        progress_callback(50, "Finding frequent tag pairs...")
        
    print("Finding frequent tag pairs...")
    frequent_pairs = find_frequent_tag_pairs(
        rated_images,
        min_cooccurrence=int(config['min_pair_cooccurrence']),
        min_tag_frequency=int(config['min_tag_frequency']),
        limit=int(config['max_pair_count'])
    )
    print(f"Found {len(frequent_pairs)} frequent tag pairs")

    # Calculate pair weights
    if progress_callback:
        progress_callback(70, "Calculating tag pair weights...")
        
    print("Calculating tag pair weights...")
    pair_weights = calculate_tag_pair_weights(rated_images, frequent_pairs)
    print(f"Calculated weights for {len(pair_weights)} pair-rating combinations")

    # Store weights in database
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Clear old weights
        if progress_callback:
            progress_callback(80, "Clearing old weights...")
            
        cur.execute("DELETE FROM rating_tag_weights")
        cur.execute("DELETE FROM rating_tag_pair_weights")
        conn.commit()

        # Get pruning threshold from config
        pruning_threshold = config.get('pruning_threshold', 0.0)
        
        # Batch size for inserts
        BATCH_SIZE = 5000

        # Pre-load all tags and ratings into memory caches
        print("Pre-loading tag and rating IDs...")
        if progress_callback:
            progress_callback(81, "Caching database IDs...")
            
        # Cache ratings
        cur.execute("SELECT name, id FROM ratings")
        rating_cache = {row['name']: row['id'] for row in cur.fetchall()}
        
        # Cache tags
        cur.execute("SELECT name, id FROM tags")
        tag_cache = {row['name']: row['id'] for row in cur.fetchall()}
        
        # Helper to get/create ID with cache
        def get_cached_tag_id(name):
            if name in tag_cache:
                return tag_cache[name]
            cur.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            new_id = cur.lastrowid
            tag_cache[name] = new_id
            return new_id
            
        def get_cached_rating_id(name):
            if name in rating_cache:
                return rating_cache[name]
            cur.execute("INSERT INTO ratings (name) VALUES (?)", (name,))
            new_id = cur.lastrowid
            rating_cache[name] = new_id
            return new_id

        # Insert new tag weights with batch commits
        if progress_callback:
            progress_callback(85, "Saving tag weights...")

        print("Writing tag weights in batches...")
        tag_weight_params = []
        tag_weight_count = 0
        current_batch = 0
        total_tags = len(tag_weights)
        
        for i, ((tag, rating), (weight, sample_count)) in enumerate(tag_weights.items()):
            # Apply pruning threshold (disabled by default with 0.0)
            if abs(weight) >= pruning_threshold:
                tag_id = get_cached_tag_id(tag)
                rating_id = get_cached_rating_id(rating)
                tag_weight_params.append((tag_id, rating_id, weight, sample_count))
                current_batch += 1
                tag_weight_count += 1
                
                if current_batch >= BATCH_SIZE:
                    cur.executemany(
                        "INSERT INTO rating_tag_weights (tag_id, rating_id, weight, sample_count) VALUES (?, ?, ?, ?)",
                        tag_weight_params
                    )
                    conn.commit()
                    tag_weight_params = []
                    current_batch = 0
                    
                    # Report detailed progress for every batch
                    if progress_callback:
                        pct = 85 + int((i / total_tags) * 5)  # 85-90%
                        progress_callback(pct, f"Saving tag weights... {i}/{total_tags}")

        # Insert remaining tag weights
        if tag_weight_params:
            cur.executemany(
                "INSERT INTO rating_tag_weights (tag_id, rating_id, weight, sample_count) VALUES (?, ?, ?, ?)",
                tag_weight_params
            )
            conn.commit()
            
        # Cache stats for later
        unique_tags_count = len({tag for tag, _ in tag_weights.keys()})

        # Clear memory
        del tag_weights
        del tag_weight_params
        # clear tag cache if memory is tight, but we need it for pairs next
        # tag_cache.clear() # Keep for pairs
        import gc
        gc.collect()

        # Insert new pair weights with batch commits
        if progress_callback:
            progress_callback(90, "Saving tag pair weights...")
            
        print("Writing pair weights in batches...")
        pair_weight_params = []
        pair_weight_count = 0
        current_batch = 0
        total_pairs = len(pair_weights)
        
        for i, ((tag1, tag2, rating), (weight, co_count)) in enumerate(pair_weights.items()):
            # Apply pruning threshold (disabled by default with 0.0)
            if abs(weight) >= pruning_threshold:
                tag1_id = get_cached_tag_id(tag1)
                tag2_id = get_cached_tag_id(tag2)
                # Ensure tag1_id < tag2_id for database constraint
                if tag1_id > tag2_id:
                    tag1_id, tag2_id = tag2_id, tag1_id
                rating_id = get_cached_rating_id(rating)
                pair_weight_params.append((tag1_id, tag2_id, rating_id, weight, co_count))
                current_batch += 1
                pair_weight_count += 1
                
                if current_batch >= BATCH_SIZE:
                    cur.executemany(
                        "INSERT INTO rating_tag_pair_weights (tag1_id, tag2_id, rating_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                        pair_weight_params
                    )
                    conn.commit()
                    pair_weight_params = []
                    current_batch = 0
                    
                    # Report detailed progress for every batch
                    if progress_callback:
                        pct = 90 + int((i / total_pairs) * 5)  # 90-95%
                        progress_callback(pct, f"Saving pair weights... {i}/{total_pairs}")
        
        # Insert remaining pair weights
        if pair_weight_params:
            cur.executemany(
                "INSERT INTO rating_tag_pair_weights (tag1_id, tag2_id, rating_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                pair_weight_params
            )
            conn.commit()
            
        # Clear memory
        del pair_weights
        del pair_weight_params
        del tag_cache
        del rating_cache
        gc.collect()

        # Update metadata
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('last_trained', datetime.now().isoformat(), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('training_sample_count', str(len(rated_images)), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('unique_tags_used', str(unique_tags_count), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('unique_pairs_used', str(len(frequent_pairs)), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('pending_user_corrections', '0', datetime.now())
        )
        
        conn.commit()
        
        if progress_callback:
            progress_callback(98, "Finalizing training...")

    duration = (datetime.now() - start_time).total_seconds()

    stats = {
        'training_samples': len(rated_images),
        'unique_tags': unique_tags_count,
        'unique_pairs': len(frequent_pairs),
        'tag_weights_count': tag_weight_count,
        'pair_weights_count': pair_weight_count,
        'pruning_threshold': config.get('pruning_threshold', 0.0),
        'duration_seconds': round(duration, 2)
    }

    print(f"Training complete in {duration:.2f}s")
    if config.get('pruning_threshold', 0.0) > 0:
        print(f"  Applied pruning threshold: {config['pruning_threshold']}")
        print(f"  Kept {tag_weight_count}/{len(tag_weights)} tag weights")
        print(f"  Kept {pair_weight_count}/{len(pair_weights)} pair weights")
    return stats


# ============================================================================
# Inference Algorithm
# ============================================================================

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
    import os
    import multiprocessing
    import sys
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Log which process is handling this (for debugging)
    process_id = os.getpid()
    worker_name = multiprocessing.current_process().name
    
    print(f"[WORKER] {worker_name} (PID {process_id}) starting to process rating chunk", file=sys.stderr, flush=True)
    sys.stderr.flush()
    
    image_chunk, tag_weights, pair_weights, config = args
    
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
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import os
    import sys
    
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
            import config
            num_workers = getattr(config, 'MAX_WORKERS', None)
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


# ============================================================================
# Data Management
# ============================================================================

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


def clear_ai_inferred_ratings() -> int:
    """
    Remove all tags with source='ai_inference'.

    Returns:
        int: Number of tags deleted
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Count before deletion
        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM image_tags
            WHERE source = 'ai_inference'
        """)
        count = cur.fetchone()['cnt']

        # Delete
        cur.execute("DELETE FROM image_tags WHERE source = 'ai_inference'")
        conn.commit()

        print(f"Cleared {count} AI-inferred rating tags")
        return count


def retrain_and_reapply_all() -> Dict:
    """
    Nuclear option: clear AI ratings, retrain, re-infer everything.

    Returns:
        dict: Combined statistics from all operations
    """
    result = {}

    # Clear AI ratings
    result['cleared'] = clear_ai_inferred_ratings()

    # Retrain
    result['training_stats'] = train_model()

    # Re-infer
    result['inference_stats'] = infer_all_unrated_images()

    return result


# ============================================================================
# Statistics & Metadata
# ============================================================================

def get_model_stats() -> Dict:
    """
    Get comprehensive model statistics.

    Returns:
        dict: Model metadata, config, rating distribution, etc.
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Get metadata
        cur.execute("SELECT key, value FROM rating_model_metadata")
        metadata = {row['key']: row['value'] for row in cur.fetchall()}

        # Check if model is trained
        model_trained = 'last_trained' in metadata

        # Get config
        config = get_config()

        # Get rating distribution
        distribution = get_rating_distribution()

        # Get pending corrections
        pending = get_pending_corrections_count()

        # Check staleness
        stale = is_model_stale()

        # Count unrated images
        unrated = get_unrated_images_count()

        return {
            'model_trained': model_trained,
            'metadata': metadata,
            'config': config,
            'rating_distribution': distribution,
            'pending_corrections': pending,
            'model_stale': stale,
            'unrated_images': unrated
        }


def get_rating_distribution() -> Dict:
    """
    Count images by rating and source.

    Returns:
        dict: {rating: {'total': int, 'ai': int, 'user': int, 'original': int}}
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        distribution = {rating: {'total': 0, 'ai': 0, 'user': 0, 'original': 0}
                       for rating in RATINGS}

        for rating in RATINGS:
            for source in ['ai_inference', 'user', 'original']:
                cur.execute("""
                    SELECT COUNT(*) as cnt
                    FROM image_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE t.name = ?
                      AND it.source = ?
                """, (rating, source))

                count = cur.fetchone()['cnt']
                distribution[rating][source.replace('_inference', '')] = count
                distribution[rating]['total'] += count

        return distribution


def get_top_weighted_tags(rating: str, limit: int = 50) -> Dict:
    """
    Get highest-weighted tags for a rating.

    Args:
        rating: Rating to query
        limit: Max tags to return

    Returns:
        dict: {'tags': [...], 'pairs': [...]}
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Get top individual tags with joins
        cur.execute("""
            SELECT t.name as tag_name, tw.weight, tw.sample_count
            FROM rating_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN ratings r ON tw.rating_id = r.id
            WHERE r.name = ?
            ORDER BY tw.weight DESC
            LIMIT ?
        """, (rating, limit))

        tags = [
            {
                'name': row['tag_name'],
                'weight': round(row['weight'], 3),
                'samples': row['sample_count']
            }
            for row in cur.fetchall()
        ]

        # Get top tag pairs with joins
        cur.execute("""
            SELECT t1.name as tag1, t2.name as tag2, pw.weight, pw.co_occurrence_count
            FROM rating_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN ratings r ON pw.rating_id = r.id
            WHERE r.name = ?
            ORDER BY pw.weight DESC
            LIMIT ?
        """, (rating, limit))

        pairs = [
            {
                'tag1': row['tag1'],
                'tag2': row['tag2'],
                'weight': round(row['weight'], 3),
                'count': row['co_occurrence_count']
            }
            for row in cur.fetchall()
        ]

        return {'tags': tags, 'pairs': pairs}


def update_model_metadata(updates: Dict) -> None:
    """
    Update model metadata entries.

    Args:
        updates: {key: value} pairs to update
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        for key, value in updates.items():
            cur.execute("""
                INSERT OR REPLACE INTO rating_model_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, str(value), datetime.now()))

        conn.commit()


def get_pending_corrections_count() -> int:
    """
    Count user corrections since last training.

    Returns:
        int: Number of tag_deltas entries since last_trained timestamp
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Try to get from metadata first
        cur.execute("""
            SELECT value FROM rating_model_metadata
            WHERE key = 'pending_user_corrections'
        """)

        row = cur.fetchone()
        if row:
            try:
                return int(row['value'])
            except (ValueError, TypeError):
                pass

    # Fallback: count tag_deltas since last training from main DB
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get last_trained from model DB first
        with get_model_connection() as model_conn:
            model_cur = model_conn.cursor()
            model_cur.execute("""
                SELECT value FROM rating_model_metadata
                WHERE key = 'last_trained'
            """)
            last_trained_row = model_cur.fetchone()

        if not last_trained_row:
            return 0

        last_trained = last_trained_row['value']

        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM tag_deltas
            WHERE timestamp > ?
              AND tag_name LIKE 'rating:%'
        """, (last_trained,))

        return cur.fetchone()['cnt']


def is_model_stale(threshold: int = 50) -> bool:
    """
    Check if model needs retraining.

    Args:
        threshold: Trigger retraining after this many corrections

    Returns:
        bool: True if corrections >= threshold
    """
    pending = get_pending_corrections_count()
    return pending >= threshold


if __name__ == "__main__":
    # Test training
    print("Testing rating inference system...")
    try:
        stats = train_model()
        print("\nTraining stats:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except ValueError as e:
        print(f"Error: {e}")

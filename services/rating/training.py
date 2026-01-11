"""
Training logic for rating inference model.
"""

import math
import gc
from collections import defaultdict, Counter
from itertools import combinations
from datetime import datetime
from typing import Dict, List, Tuple
from .config import RATINGS, get_model_connection, get_config
from .data import get_rated_images
from repositories.rating_repository import get_or_create_tag_id, get_or_create_rating_id


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

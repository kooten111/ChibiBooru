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
            "UPDATE rating_inference_config SET value = ? WHERE key = ?",
            (value, key)
        )
        conn.commit()


def reset_config_to_defaults() -> None:
    """Reset all config to factory defaults."""
    defaults = {
        'threshold_general': 0.5,
        'threshold_sensitive': 0.6,
        'threshold_questionable': 0.7,
        'threshold_explicit': 0.8,
        'min_confidence': 0.4,
        'pair_weight_multiplier': 1.5,
        'min_training_samples': 50,
        'min_pair_cooccurrence': 5,
        'min_tag_frequency': 10,
        'max_pair_count': 10000,
    }

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

def get_rated_images(sources: List[str] = None) -> List[Tuple[int, str, List[str]]]:
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
        placeholders = ','.join('?' * len(image_ids))
        cur.execute(f"""
            SELECT it.image_id, t.name as tag_name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id IN ({placeholders})
              AND t.name NOT IN ({','.join('?' * len(RATINGS))})
        """, image_ids + RATINGS)

        image_tags_map = defaultdict(list)
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


def train_model() -> Dict:
    """
    Train the rating inference model on all trusted ratings.

    Returns:
        dict: Training statistics including sample counts, duration, etc.

    Raises:
        ValueError: If not enough training samples available
    """
    start_time = datetime.now()

    config = get_config()
    min_samples = int(config['min_training_samples'])

    # Get training data
    rated_images = get_rated_images(sources=['user', 'original'])

    if len(rated_images) < min_samples:
        raise ValueError(
            f"Not enough training samples. Need {min_samples}, have {len(rated_images)}. "
            "Manually rate more images before training."
        )

    print(f"Training on {len(rated_images)} rated images...")

    # Calculate individual tag weights
    print("Calculating individual tag weights...")
    tag_weights = calculate_tag_weights(rated_images)
    print(f"Calculated weights for {len(tag_weights)} tag-rating pairs")

    # Find frequent tag pairs
    print("Finding frequent tag pairs...")
    frequent_pairs = find_frequent_tag_pairs(
        rated_images,
        min_cooccurrence=int(config['min_pair_cooccurrence']),
        min_tag_frequency=int(config['min_tag_frequency']),
        limit=int(config['max_pair_count'])
    )
    print(f"Found {len(frequent_pairs)} frequent tag pairs")

    # Calculate pair weights
    print("Calculating tag pair weights...")
    pair_weights = calculate_tag_pair_weights(rated_images, frequent_pairs)
    print(f"Calculated weights for {len(pair_weights)} pair-rating combinations")

    # Store weights in database
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Clear old weights
        cur.execute("DELETE FROM rating_tag_weights")
        cur.execute("DELETE FROM rating_tag_pair_weights")

        # Insert new tag weights
        tag_weight_data = [
            (tag, rating, weight, sample_count)
            for (tag, rating), (weight, sample_count) in tag_weights.items()
        ]
        cur.executemany(
            "INSERT INTO rating_tag_weights (tag_name, rating, weight, sample_count) VALUES (?, ?, ?, ?)",
            tag_weight_data
        )

        # Insert new pair weights
        pair_weight_data = [
            (tag1, tag2, rating, weight, co_count)
            for (tag1, tag2, rating), (weight, co_count) in pair_weights.items()
        ]
        cur.executemany(
            "INSERT INTO rating_tag_pair_weights (tag1, tag2, rating, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
            pair_weight_data
        )

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
            ('unique_tags_used', str(len({tag for tag, _ in tag_weights.keys()})), datetime.now())
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

    duration = (datetime.now() - start_time).total_seconds()

    stats = {
        'training_samples': len(rated_images),
        'unique_tags': len({tag for tag, _ in tag_weights.keys()}),
        'unique_pairs': len(frequent_pairs),
        'tag_weights_count': len(tag_weights),
        'pair_weights_count': len(pair_weights),
        'duration_seconds': round(duration, 2)
    }

    print(f"Training complete in {duration:.2f}s")
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

        # Load tag weights
        cur.execute("SELECT tag_name, rating, weight FROM rating_tag_weights")
        tag_weights = {
            (row['tag_name'], row['rating']): row['weight']
            for row in cur.fetchall()
        }

        # Load pair weights
        cur.execute("SELECT tag1, tag2, rating, weight FROM rating_tag_pair_weights")
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
    pair_multiplier = config['pair_weight_multiplier']
    sorted_tags = sorted(image_tags)

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


def infer_all_unrated_images() -> Dict:
    """
    Run inference on all images without rating tags.

    Returns:
        dict: Statistics about inference run
    """
    start_time = datetime.now()

    # Load weights once for efficiency
    tag_weights, pair_weights = load_weights()
    config = get_config()

    if not tag_weights and not pair_weights:
        raise ValueError("Model not trained. Run train_model() first.")

    unrated_images = get_unrated_images()

    stats = {
        'processed': 0,
        'rated': 0,
        'skipped_low_confidence': 0,
        'by_rating': {r: 0 for r in RATINGS}
    }

    print(f"Running inference on {len(unrated_images)} unrated images...")

    for image_id, tags in unrated_images:
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

        if stats['processed'] % 100 == 0:
            print(f"  Processed {stats['processed']}/{len(unrated_images)}...")

    duration = (datetime.now() - start_time).total_seconds()
    stats['duration_seconds'] = round(duration, 2)

    print(f"Inference complete in {duration:.2f}s")
    print(f"  Rated: {stats['rated']}")
    print(f"  Skipped (low confidence): {stats['skipped_low_confidence']}")

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
        unrated = len(get_unrated_images())

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

        # Get top individual tags
        cur.execute("""
            SELECT tag_name, weight, sample_count
            FROM rating_tag_weights
            WHERE rating = ?
            ORDER BY weight DESC
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

        # Get top tag pairs
        cur.execute("""
            SELECT tag1, tag2, weight, co_occurrence_count
            FROM rating_tag_pair_weights
            WHERE rating = ?
            ORDER BY weight DESC
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

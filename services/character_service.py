# character_service.py
"""
Character inference system for automatic character tag classification.

This module implements a self-learning character prediction system that learns from
booru-tagged images to automatically identify characters in locally-tagged images.
"""

import sqlite3
import math
from collections import defaultdict, Counter
from itertools import combinations
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from database import get_db_connection
from repositories.character_repository import get_or_create_tag_id, get_or_create_character_id

# Model database configuration
USE_SEPARATE_MODEL_DB = True

# Extended category weights for character inference
# Categories most useful for character identification get higher weights
EXTENDED_CATEGORY_WEIGHTS = {
    # Highly character-specific (permanent physical traits)
    '02_Body_Hair': 1.5,        # Hair color, style - very distinctive
    '03_Body_Face': 1.4,        # Eye color - very distinctive
    '01_Body_Physique': 1.3,    # Animal ears, tail, horns - distinctive features
    
    # Character-specific attire (outfit-based identification)
    '05_Attire_Main': 1.2,      # Signature outfits
    '06_Attire_Inner': 1.1,     # Specific underwear/swimwear
    '07_Attire_Legwear': 1.1,   # Distinctive legwear
    '08_Attire_Acc': 1.1,       # Signature accessories
    
    # Moderately useful
    '00_Subject_Count': 0.8,    # Less specific for individual characters
    '04_Body_Genitalia': 0.7,   # NSFW features - less distinctive
    
    # Less useful for character ID (more situational)
    '09_Action': 0.5,           # Actions are character-agnostic
    '10_Pose': 0.5,             # Poses are situational
    '11_Expression': 0.5,       # Expressions vary
    '21_Status': 0.5,           # State of being is situational
    
    # Not useful for character ID (environmental/technical)
    '12_Sexual_Act': 0.3,       # Situational
    '13_Object': 0.4,           # Objects held vary
    '14_Setting': 0.2,          # Background irrelevant
    '15_Framing': 0.1,          # Camera angle irrelevant
    '16_Focus': 0.2,            # Focus irrelevant
    '17_Style_Art': 0.1,        # Art style irrelevant
    '18_Style_Tech': 0.1,       # Visual effects irrelevant
    '19_Meta_Attributes': 0.1,  # Metadata irrelevant
    '20_Meta_Text': 0.1,        # Text irrelevant
}

# Default weight for tags without extended category
DEFAULT_TAG_WEIGHT = 1.0


def get_model_connection():
    """Get connection to model database (separate or main DB)."""
    if USE_SEPARATE_MODEL_DB:
        from repositories.character_repository import get_model_db_connection
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
        cur.execute("SELECT key, value FROM character_inference_config")
        return {row['key']: row['value'] for row in cur.fetchall()}


def update_config(key: str, value: float) -> None:
    """Update a single config value."""
    with get_model_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE character_inference_config SET value = ? WHERE key = ?",
            (value, key)
        )
        conn.commit()


def reset_config_to_defaults() -> None:
    """Reset all config to factory defaults."""
    defaults = {
        'min_character_samples': 10,
        'tag_weight': 1.0,
        'vector_weight': 0.0,
        'visual_weight': 0.0,
        'k_neighbors': 5,
        'min_confidence': 0.3,
        'max_predictions': 3,
        'pair_weight_multiplier': 1.5,
        'min_pair_cooccurrence': 5,
        'min_tag_frequency': 10,
        'max_pair_count': 10000,
        'pruning_threshold': 0.0,
    }

    with get_model_connection() as conn:
        cur = conn.cursor()
        for key, value in defaults.items():
            cur.execute(
                "UPDATE character_inference_config SET value = ? WHERE key = ?",
                (value, key)
            )
        conn.commit()


# ============================================================================
# Data Retrieval
# ============================================================================

def get_character_tagged_images(sources: List[str] = None) -> List[Tuple[int, List[str], List[Tuple[str, Optional[str]]]]]:
    """
    Get all images with character tags from trusted sources (boorus).

    Args:
        sources: Which sources to trust (default: ['danbooru', 'e621', 'gelbooru', 'yandere'])

    Returns:
        List of (image_id, characters, tags_with_extended) tuples
        where tags_with_extended is List[(tag_name, extended_category)]
    """
    if sources is None:
        sources = ['danbooru', 'e621', 'gelbooru', 'yandere']

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get all images from raw_metadata with character tags
        cur.execute("""
            SELECT i.id, i.md5, rm.data, i.active_source
            FROM images i
            JOIN raw_metadata rm ON i.id = rm.image_id
            WHERE i.active_source IN ({})
        """.format(','.join('?' * len(sources))), sources)

        result = []
        import json
        from utils.tag_extraction import extract_tags_from_source

        for row in cur.fetchall():
            image_id = row['id']
            source_name = row['active_source']
            
            try:
                raw_metadata = json.loads(row['data']) if row['data'] else {}
            except (json.JSONDecodeError, TypeError):
                continue

            # Get the actual source data from the nested structure
            # raw_metadata has structure: {"sources": {"danbooru": {...}, "e621": {...}}}
            sources = raw_metadata.get('sources', {})
            source_data = sources.get(source_name, {})
            
            if not source_data:
                continue

            # Extract character tags
            tags_dict = extract_tags_from_source(source_data, source_name)
            character_str = tags_dict.get('tags_character', '')
            characters = [c for c in character_str.split() if c]
            
            if not characters:
                continue

            # Get all other tags for this image (excluding characters)
            all_tags_str = ' '.join([
                tags_dict.get('tags_general', ''),
                tags_dict.get('tags_meta', ''),
                tags_dict.get('tags_copyright', ''),
                tags_dict.get('tags_species', ''),
            ])
            tag_names = [t for t in all_tags_str.split() if t]
            
            # Get extended categories for these tags from database
            if tag_names:
                placeholders = ','.join('?' * len(tag_names))
                cur.execute(f"""
                    SELECT name, extended_category
                    FROM tags
                    WHERE name IN ({placeholders})
                """, tag_names)
                
                tag_extended_map = {row['name']: row['extended_category'] for row in cur.fetchall()}
                tags_with_extended = [(tag, tag_extended_map.get(tag)) for tag in tag_names]
            else:
                tags_with_extended = []

            result.append((image_id, characters, tags_with_extended))

        return result


def get_untagged_character_images() -> List[Tuple[int, List[Tuple[str, Optional[str]]]]]:
    """
    Get all images without any character tag (from local tagger or AI).

    Returns:
        List of (image_id, tags_with_extended) tuples
        where tags_with_extended is List[(tag_name, extended_category)]
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find images from local_tagger source without character tags
        cur.execute("""
            SELECT i.id
            FROM images i
            WHERE i.active_source = 'local_tagger'
              AND NOT EXISTS (
                  SELECT 1 FROM image_tags it
                  JOIN tags t ON it.tag_id = t.id
                  WHERE it.image_id = i.id
                    AND t.category = 'character'
              )
        """)

        image_ids = [row['id'] for row in cur.fetchall()]

        if not image_ids:
            return []

        # Get tags with extended categories for these images
        placeholders = ','.join('?' * len(image_ids))
        cur.execute(f"""
            SELECT it.image_id, t.name as tag_name, t.extended_category
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id IN ({placeholders})
              AND t.category != 'character'
        """, image_ids)

        image_tags_map = defaultdict(list)
        for row in cur.fetchall():
            image_tags_map[row['image_id']].append((row['tag_name'], row['extended_category']))

        result = [(img_id, image_tags_map.get(img_id, [])) for img_id in image_ids]
        return result


def get_untagged_character_images_count() -> int:
    """
    Get count of images without any character tag (optimized for performance).

    Returns:
        Number of untagged images
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) as count
            FROM images i
            WHERE i.active_source = 'local_tagger'
              AND NOT EXISTS (
                  SELECT 1 FROM image_tags it
                  JOIN tags t ON it.tag_id = t.id
                  WHERE it.image_id = i.id
                    AND t.category = 'character'
              )
        """)

        return cur.fetchone()['count']


# ============================================================================
# Training Algorithm
# ============================================================================

def calculate_tag_weights(character_images: List[Tuple[int, List[str], List[Tuple[str, Optional[str]]]]]) -> Dict[Tuple[str, str], Tuple[float, int]]:
    """
    Calculate log-likelihood ratio weights for individual tags.
    Applies extended category multipliers to boost character-relevant tags.

    Args:
        character_images: List of (image_id, characters, tags_with_extended) tuples
                         where tags_with_extended is List[(tag_name, extended_category)]

    Returns:
        dict: {(tag, character): (weight, sample_count)}
    """
    # Count tag occurrences per character
    tag_character_counts = defaultdict(int)  # (tag, character) -> count
    character_counts = Counter()  # character -> total count
    tag_counts = Counter()  # tag -> total count across all characters
    tag_extended_map = {}  # tag -> extended_category mapping

    for image_id, characters, tags_with_extended in character_images:
        for character in characters:
            character_counts[character] += 1
            for tag, extended_category in tags_with_extended:
                tag_character_counts[(tag, character)] += 1
                tag_counts[tag] += 1
                # Store extended category for this tag (last one wins if multiple)
                if extended_category:
                    tag_extended_map[tag] = extended_category

    total_images = len(character_images)
    weights = {}

    for character in character_counts:
        character_count = character_counts[character]
        if character_count == 0:
            continue

        not_character_count = total_images - character_count
        if not_character_count == 0:
            continue

        for tag in tag_counts:
            # Count images with (tag AND character)
            with_character = tag_character_counts.get((tag, character), 0)

            # Count images with (tag AND NOT character)
            total_tag = tag_counts[tag]
            without_character = total_tag - with_character

            # Calculate probabilities
            # P(tag | character)
            p_tag_given_character = with_character / character_count if character_count > 0 else 0

            # P(tag | NOT character)
            p_tag_given_not_character = without_character / not_character_count if not_character_count > 0 else 0

            # Log-likelihood ratio (with smoothing to avoid log(0))
            epsilon = 1e-10
            p_tag_given_character = max(p_tag_given_character, epsilon)
            p_tag_given_not_character = max(p_tag_given_not_character, epsilon)

            weight = math.log(p_tag_given_character / p_tag_given_not_character)
            
            # Apply extended category multiplier to boost character-relevant tags
            extended_category = tag_extended_map.get(tag)
            if extended_category in EXTENDED_CATEGORY_WEIGHTS:
                category_multiplier = EXTENDED_CATEGORY_WEIGHTS[extended_category]
                weight *= category_multiplier

            # Only store meaningful weights
            if abs(weight) > 0.01:
                weights[(tag, character)] = (weight, with_character)

    return weights


def find_frequent_tag_pairs(character_images: List[Tuple[int, List[str], List[Tuple[str, Optional[str]]]]],
                            min_cooccurrence: int,
                            min_tag_frequency: int,
                            limit: int) -> List[Tuple[str, str, int]]:
    """
    Find tag pairs that appear together frequently enough to be useful.

    Args:
        character_images: Training data with (image_id, characters, tags_with_extended)
        min_cooccurrence: Minimum times pair must appear together
        min_tag_frequency: Minimum images each tag must appear in
        limit: Maximum number of pairs to return

    Returns:
        List of (tag1, tag2, count) sorted by count descending
    """
    # Count individual tag frequencies
    tag_frequencies = Counter()
    for _, _, tags_with_extended in character_images:
        for tag, _ in tags_with_extended:
            tag_frequencies[tag] += 1

    # Filter to frequent tags
    frequent_tags = {tag for tag, count in tag_frequencies.items()
                     if count >= min_tag_frequency}

    # Count pair co-occurrences
    pair_counts = Counter()
    for _, _, tags_with_extended in character_images:
        # Only consider frequent tags (extract tag names only)
        filtered_tags = [tag for tag, _ in tags_with_extended if tag in frequent_tags]

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


def calculate_tag_pair_weights(character_images: List[Tuple[int, List[str], List[Tuple[str, Optional[str]]]]],
                               frequent_pairs: List[Tuple[str, str, int]]) -> Dict[Tuple[str, str, str], Tuple[float, int]]:
    """
    Calculate log-likelihood ratio weights for tag pairs.

    Args:
        character_images: List of (image_id, characters, tags_with_extended) tuples
        frequent_pairs: List of (tag1, tag2, count) pairs to calculate weights for

    Returns:
        dict: {(tag1, tag2, character): (weight, co_occurrence_count)}
    """
    # Convert pairs to set for fast lookup
    pair_set = {(tag1, tag2) for tag1, tag2, _ in frequent_pairs}

    # Count pair occurrences per character
    pair_character_counts = defaultdict(int)  # (tag1, tag2, character) -> count
    character_counts = Counter()  # character -> total count
    pair_counts = Counter()  # (tag1, tag2) -> total count across all characters

    for image_id, characters, tags_with_extended in character_images:
        for character in characters:
            character_counts[character] += 1

            # Generate pairs from this image's tags (extract tag names only)
            tag_names = [tag for tag, _ in tags_with_extended]
            sorted_tags = sorted(tag_names)
            for tag1, tag2 in combinations(sorted_tags, 2):
                if (tag1, tag2) in pair_set:
                    pair_character_counts[(tag1, tag2, character)] += 1
                    pair_counts[(tag1, tag2)] += 1

    total_images = len(character_images)
    weights = {}

    for character in character_counts:
        character_count = character_counts[character]
        if character_count == 0:
            continue

        not_character_count = total_images - character_count
        if not_character_count == 0:
            continue

        for tag1, tag2, _ in frequent_pairs:
            # Count images with (pair AND character)
            with_character = pair_character_counts.get((tag1, tag2, character), 0)

            # Count images with (pair AND NOT character)
            total_pair = pair_counts[(tag1, tag2)]
            without_character = total_pair - with_character

            # Calculate probabilities
            p_pair_given_character = with_character / character_count if character_count > 0 else 0
            p_pair_given_not_character = without_character / not_character_count if not_character_count > 0 else 0

            # Log-likelihood ratio (with smoothing)
            epsilon = 1e-10
            p_pair_given_character = max(p_pair_given_character, epsilon)
            p_pair_given_not_character = max(p_pair_given_not_character, epsilon)

            weight = math.log(p_pair_given_character / p_pair_given_not_character)

            # Only store meaningful weights
            if abs(weight) > 0.01:
                weights[(tag1, tag2, character)] = (weight, with_character)

    return weights


def train_model() -> Dict:
    """
    Train the character inference model on all booru-tagged images.

    Returns:
        dict: Training statistics including sample counts, duration, etc.

    Raises:
        ValueError: If not enough training samples available
    """
    start_time = datetime.now()

    config = get_config()
    min_samples = int(config['min_character_samples'])

    # Get training data
    character_images = get_character_tagged_images()

    if len(character_images) < min_samples:
        raise ValueError(
            f"Not enough training samples. Need {min_samples}, have {len(character_images)}. "
            "Import more images from boorus with character tags."
        )

    # Count unique characters
    all_characters = set()
    for _, characters, _ in character_images:
        all_characters.update(characters)

    print(f"Training on {len(character_images)} images with {len(all_characters)} unique characters...")

    # Calculate individual tag weights
    print("Calculating individual tag weights...")
    tag_weights = calculate_tag_weights(character_images)
    print(f"Calculated weights for {len(tag_weights)} tag-character pairs")

    # Find frequent tag pairs
    print("Finding frequent tag pairs...")
    frequent_pairs = find_frequent_tag_pairs(
        character_images,
        min_cooccurrence=int(config['min_pair_cooccurrence']),
        min_tag_frequency=int(config['min_tag_frequency']),
        limit=int(config['max_pair_count'])
    )
    print(f"Found {len(frequent_pairs)} frequent tag pairs")

    # Calculate pair weights
    print("Calculating tag pair weights...")
    pair_weights = calculate_tag_pair_weights(character_images, frequent_pairs)
    print(f"Calculated weights for {len(pair_weights)} pair-character combinations")

    # Store weights in database
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Clear old weights
        cur.execute("DELETE FROM character_tag_weights")
        cur.execute("DELETE FROM character_tag_pair_weights")

        # Get pruning threshold from config
        pruning_threshold = config.get('pruning_threshold', 0.0)

        # Insert new tag weights with optional pruning
        tag_weight_count = 0
        for (tag, character), (weight, sample_count) in tag_weights.items():
            # Apply pruning threshold (disabled by default with 0.0)
            if abs(weight) >= pruning_threshold:
                tag_id = get_or_create_tag_id(conn, tag)
                character_id = get_or_create_character_id(conn, character)
                cur.execute(
                    "INSERT INTO character_tag_weights (tag_id, character_id, weight, sample_count) VALUES (?, ?, ?, ?)",
                    (tag_id, character_id, weight, sample_count)
                )
                tag_weight_count += 1

        # Insert new pair weights with optional pruning
        pair_weight_count = 0
        for (tag1, tag2, character), (weight, co_count) in pair_weights.items():
            # Apply pruning threshold (disabled by default with 0.0)
            if abs(weight) >= pruning_threshold:
                tag1_id = get_or_create_tag_id(conn, tag1)
                tag2_id = get_or_create_tag_id(conn, tag2)
                # Ensure tag1_id < tag2_id for database constraint
                if tag1_id > tag2_id:
                    tag1_id, tag2_id = tag2_id, tag1_id
                character_id = get_or_create_character_id(conn, character)
                cur.execute(
                    "INSERT INTO character_tag_pair_weights (tag1_id, tag2_id, character_id, weight, co_occurrence_count) VALUES (?, ?, ?, ?, ?)",
                    (tag1_id, tag2_id, character_id, weight, co_count)
                )
                pair_weight_count += 1

        # Update metadata
        cur.execute(
            "INSERT OR REPLACE INTO character_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('last_trained', datetime.now().isoformat(), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO character_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('training_sample_count', str(len(character_images)), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO character_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('unique_characters', str(len(all_characters)), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO character_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('unique_tags_used', str(len({tag for tag, _ in tag_weights.keys()})), datetime.now())
        )
        cur.execute(
            "INSERT OR REPLACE INTO character_model_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ('unique_pairs_used', str(len(frequent_pairs)), datetime.now())
        )

        conn.commit()

    duration = (datetime.now() - start_time).total_seconds()

    stats = {
        'training_samples': len(character_images),
        'unique_characters': len(all_characters),
        'unique_tags': len({tag for tag, _ in tag_weights.keys()}),
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
            tag_weights: {(tag, character): weight}
            pair_weights: {(tag1, tag2, character): weight}
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Load tag weights with joins to get names
        cur.execute("""
            SELECT t.name as tag_name, c.name as character, tw.weight
            FROM character_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN characters c ON tw.character_id = c.id
        """)
        tag_weights = {
            (row['tag_name'], row['character']): row['weight']
            for row in cur.fetchall()
        }

        # Load pair weights with joins to get names
        cur.execute("""
            SELECT t1.name as tag1, t2.name as tag2, c.name as character, pw.weight
            FROM character_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN characters c ON pw.character_id = c.id
        """)
        pair_weights = {
            (row['tag1'], row['tag2'], row['character']): row['weight']
            for row in cur.fetchall()
        }

        return tag_weights, pair_weights


def calculate_character_scores(image_tags: List[str],
                               tag_weights: Dict,
                               pair_weights: Dict,
                               config: Dict) -> Dict[str, float]:
    """
    Calculate raw scores for each character.

    Args:
        image_tags: Tags to score
        tag_weights: Individual tag weights
        pair_weights: Tag pair weights
        config: Inference config (for pair multiplier)

    Returns:
        dict: {character: raw_score}
    """
    # Get all characters that have weights
    all_characters = set()
    for tag, character in tag_weights.keys():
        all_characters.add(character)
    for tag1, tag2, character in pair_weights.keys():
        all_characters.add(character)

    scores = {character: 0.0 for character in all_characters}

    # Accumulate individual tag weights
    for tag in image_tags:
        for character in all_characters:
            weight = tag_weights.get((tag, character), 0.0)
            scores[character] += weight

    # Accumulate tag pair weights
    pair_multiplier = config['pair_weight_multiplier']
    sorted_tags = sorted(image_tags)

    for tag1, tag2 in combinations(sorted_tags, 2):
        for character in all_characters:
            pair_weight = pair_weights.get((tag1, tag2, character), 0.0)
            scores[character] += pair_weight * pair_multiplier

    return scores


def scores_to_probabilities(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Convert log-likelihood scores to normalized probabilities using softmax.

    Args:
        scores: {character: raw_score}

    Returns:
        dict: {character: probability} (sums to 1.0)
    """
    if not scores:
        return {}

    # Softmax with numerical stability (subtract max)
    max_score = max(scores.values())
    exp_scores = {character: math.exp(score - max_score)
                  for character, score in scores.items()}

    total = sum(exp_scores.values())
    if total == 0:
        return {character: 0.0 for character in scores}

    probabilities = {character: exp_score / total
                    for character, exp_score in exp_scores.items()}

    return probabilities


def predict_characters(image_tags: List[str],
                      tag_weights: Dict = None,
                      pair_weights: Dict = None,
                      config: Dict = None) -> List[Tuple[str, float]]:
    """
    Predict characters for an image based on its tags.

    Args:
        image_tags: List of tag names for the image
        tag_weights: Preloaded tag weights (optional, will load if not provided)
        pair_weights: Preloaded pair weights (optional, will load if not provided)
        config: Preloaded config (optional, will load if not provided)

    Returns:
        list: [(character, confidence), ...] sorted by confidence descending
    """
    if not image_tags:
        return []

    # Load weights and config if not provided
    if tag_weights is None or pair_weights is None:
        tag_weights, pair_weights = load_weights()

    if config is None:
        config = get_config()

    # Check if model is trained
    if not tag_weights and not pair_weights:
        return []

    # Calculate scores
    scores = calculate_character_scores(image_tags, tag_weights, pair_weights, config)

    if not scores:
        return []

    # Convert to probabilities
    probabilities = scores_to_probabilities(scores)

    # Filter by confidence and max predictions
    min_confidence = config['min_confidence']
    max_predictions = int(config['max_predictions'])

    # Sort by probability descending
    predictions = [(char, prob) for char, prob in probabilities.items()
                   if prob >= min_confidence]
    predictions.sort(key=lambda x: x[1], reverse=True)

    return predictions[:max_predictions]


def infer_character_for_image(image_id: int) -> Dict:
    """
    Run inference on a single image.

    Args:
        image_id: Database ID of image

    Returns:
        dict: {'characters': [(character, confidence), ...]}
    """
    # Get image tags (excluding existing character tags)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ?
              AND t.category != 'character'
        """, (image_id,))

        tags = [row['name'] for row in cur.fetchall()]

    if not tags:
        return {'characters': []}

    # Predict characters
    predictions = predict_characters(tags)

    if predictions:
        # Add character tags with source='ai_inference'
        for character, confidence in predictions:
            set_image_character(image_id, character, source='ai_inference', confidence=confidence, add=True)

    return {'characters': predictions}


def infer_all_untagged_images() -> Dict:
    """
    Run inference on all images without character tags.

    Returns:
        dict: Statistics about inference run
    """
    start_time = datetime.now()

    # Load weights once for efficiency
    tag_weights, pair_weights = load_weights()
    config = get_config()

    if not tag_weights and not pair_weights:
        raise ValueError("Model not trained. Run train_model() first.")

    untagged_images = get_untagged_character_images()

    stats = {
        'processed': 0,
        'tagged': 0,
        'skipped_low_confidence': 0,
        'characters_added': 0,
        'by_character': defaultdict(int)
    }

    print(f"Running inference on {len(untagged_images)} untagged images...")

    for image_id, tags_with_extended in untagged_images:
        stats['processed'] += 1

        if not tags_with_extended:
            stats['skipped_low_confidence'] += 1
            continue

        # Extract tag names only for prediction
        tag_names = [tag for tag, _ in tags_with_extended]
        predictions = predict_characters(tag_names, tag_weights, pair_weights, config)

        if predictions:
            stats['tagged'] += 1
            for character, confidence in predictions:
                set_image_character(image_id, character, source='ai_inference', confidence=confidence, add=True)
                stats['characters_added'] += 1
                stats['by_character'][character] += 1
        else:
            stats['skipped_low_confidence'] += 1

        if stats['processed'] % 100 == 0:
            print(f"  Processed {stats['processed']}/{len(untagged_images)}...")

    duration = (datetime.now() - start_time).total_seconds()
    stats['duration_seconds'] = round(duration, 2)
    # Convert defaultdict to regular dict for JSON serialization
    stats['by_character'] = dict(stats['by_character'])

    print(f"Inference complete in {duration:.2f}s")
    print(f"  Tagged: {stats['tagged']} images")
    print(f"  Added: {stats['characters_added']} character tags")
    print(f"  Skipped (low confidence): {stats['skipped_low_confidence']}")

    return stats


# ============================================================================
# Data Management
# ============================================================================

def set_image_character(image_id: int, character: str,
                       source: str = 'user', confidence: float = None,
                       add: bool = False) -> Dict:
    """
    Set or add a character tag for an image.

    Args:
        image_id: Image to tag
        character: Character name
        source: Tag source (default 'user')
        confidence: Optional confidence score for AI predictions
        add: If True, add to existing characters; if False, replace all

    Returns:
        dict: {'added': bool, 'character': str}
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Ensure character tag exists
        cur.execute(
            "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
            (character, 'character')
        )

        # Get character tag ID
        cur.execute("SELECT id FROM tags WHERE name = ?", (character,))
        tag_id = cur.fetchone()['id']

        # Check if already exists
        cur.execute("""
            SELECT 1 FROM image_tags
            WHERE image_id = ? AND tag_id = ?
        """, (image_id, tag_id))
        
        already_exists = cur.fetchone() is not None

        if not already_exists:
            # Add character tag
            cur.execute(
                "INSERT OR REPLACE INTO image_tags (image_id, tag_id, source) VALUES (?, ?, ?)",
                (image_id, tag_id, source)
            )

            # Record in tag_deltas if user-initiated
            if source == 'user':
                cur.execute("""
                    INSERT OR IGNORE INTO tag_deltas (image_md5, tag_name, tag_category, operation)
                    SELECT md5, ?, 'character', 'add'
                    FROM images
                    WHERE id = ?
                """, (character, image_id))

        conn.commit()

        return {'added': not already_exists, 'character': character}


def clear_ai_inferred_characters() -> int:
    """
    Remove all character tags with source='ai_inference'.

    Returns:
        int: Number of tags deleted
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Count before deletion
        cur.execute("""
            SELECT COUNT(*) as cnt
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.source = 'ai_inference'
              AND t.category = 'character'
        """)
        count = cur.fetchone()['cnt']

        # Delete
        cur.execute("""
            DELETE FROM image_tags
            WHERE source = 'ai_inference'
              AND tag_id IN (SELECT id FROM tags WHERE category = 'character')
        """)
        conn.commit()

        print(f"Cleared {count} AI-inferred character tags")
        return count


def retrain_and_reapply_all() -> Dict:
    """
    Nuclear option: clear AI characters, retrain, re-infer everything.

    Returns:
        dict: Combined statistics from all operations
    """
    result = {}

    # Clear AI characters
    result['cleared'] = clear_ai_inferred_characters()

    # Retrain
    result['training_stats'] = train_model()

    # Re-infer
    result['inference_stats'] = infer_all_untagged_images()

    return result


# ============================================================================
# Statistics & Metadata
# ============================================================================

def get_model_stats() -> Dict:
    """
    Get comprehensive model statistics.

    Returns:
        dict: Model metadata, config, character distribution, etc.
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Get metadata
        cur.execute("SELECT key, value FROM character_model_metadata")
        metadata = {row['key']: row['value'] for row in cur.fetchall()}

        # Check if model is trained
        model_trained = 'last_trained' in metadata

        # Get config
        config = get_config()

        # Get character distribution
        distribution = get_character_distribution()

        # Count untagged images
        untagged = get_untagged_character_images_count()

        return {
            'model_trained': model_trained,
            'metadata': metadata,
            'config': config,
            'character_distribution': distribution,
            'untagged_images': untagged
        }


def get_character_distribution() -> Dict:
    """
    Count images by character and source.

    Returns:
        dict: {character: {'total': int, 'ai': int, 'user': int, 'original': int}}
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get all character tags and their counts by source
        cur.execute("""
            SELECT t.name as character, it.source, COUNT(*) as cnt
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.category = 'character'
            GROUP BY t.name, it.source
        """)

        distribution = defaultdict(lambda: {'total': 0, 'ai': 0, 'user': 0, 'original': 0, 'local_tagger': 0})
        
        for row in cur.fetchall():
            character = row['character']
            source = row['source']
            count = row['cnt']
            
            distribution[character]['total'] += count
            if source == 'ai_inference':
                distribution[character]['ai'] = count
            elif source == 'user':
                distribution[character]['user'] = count
            elif source == 'original':
                distribution[character]['original'] = count
            elif source == 'local_tagger':
                distribution[character]['local_tagger'] = count

        return dict(distribution)


def get_all_known_characters() -> List[Dict]:
    """
    Get list of all known characters with sample counts.

    Returns:
        list: [{'name': str, 'sample_count': int}, ...]
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Get characters with their sample counts from training
        cur.execute("""
            SELECT c.name, SUM(tw.sample_count) as total_samples
            FROM characters c
            LEFT JOIN character_tag_weights tw ON c.id = tw.character_id
            GROUP BY c.name
            ORDER BY total_samples DESC
        """)

        characters = [
            {
                'name': row['name'],
                'sample_count': row['total_samples'] or 0
            }
            for row in cur.fetchall()
        ]

        return characters


def get_top_weighted_tags(character: str, limit: int = 50) -> Dict:
    """
    Get highest-weighted tags for a character.

    Args:
        character: Character to query
        limit: Max tags to return

    Returns:
        dict: {'tags': [...], 'pairs': [...]}
    """
    with get_model_connection() as conn:
        cur = conn.cursor()

        # Get top individual tags with joins
        cur.execute("""
            SELECT t.name as tag_name, tw.weight, tw.sample_count
            FROM character_tag_weights tw
            JOIN tags t ON tw.tag_id = t.id
            JOIN characters c ON tw.character_id = c.id
            WHERE c.name = ?
            ORDER BY tw.weight DESC
            LIMIT ?
        """, (character, limit))

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
            FROM character_tag_pair_weights pw
            JOIN tags t1 ON pw.tag1_id = t1.id
            JOIN tags t2 ON pw.tag2_id = t2.id
            JOIN characters c ON pw.character_id = c.id
            WHERE c.name = ?
            ORDER BY pw.weight DESC
            LIMIT ?
        """, (character, limit))

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


if __name__ == "__main__":
    # Test training
    print("Testing character inference system...")
    try:
        stats = train_model()
        print("\nTraining stats:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except ValueError as e:
        print(f"Error: {e}")

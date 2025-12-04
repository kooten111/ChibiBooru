"""
Repository for local tagger predictions.
Handles storage and retrieval of AI tagger predictions with confidence scores.
"""
import config
from database import get_db_connection


def store_predictions(image_id: int, predictions: list, tagger_version: str = None):
    """
    Store local tagger predictions for an image.
    
    Args:
        image_id: Database ID of the image
        predictions: List of dicts with 'tag_name', 'category', 'confidence'
        tagger_version: Version/name of the tagger model used
    
    Returns:
        Number of predictions stored
    """
    if not predictions:
        return 0
    
    tagger_version = tagger_version or config.LOCAL_TAGGER_NAME
    storage_threshold = config.LOCAL_TAGGER_STORAGE_THRESHOLD
    
    # Filter predictions above storage threshold
    filtered = [p for p in predictions if p['confidence'] >= storage_threshold]
    
    if not filtered:
        return 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Clear existing predictions for this image (fresh start each time)
        cursor.execute("DELETE FROM local_tagger_predictions WHERE image_id = ?", (image_id,))
        
        # Insert new predictions
        cursor.executemany("""
            INSERT INTO local_tagger_predictions 
            (image_id, tag_name, category, confidence, tagger_version)
            VALUES (?, ?, ?, ?, ?)
        """, [
            (image_id, p['tag_name'], p['category'], p['confidence'], tagger_version)
            for p in filtered
        ])
        
        conn.commit()
        return len(filtered)


def get_predictions_for_image(image_id: int, min_confidence: float = None):
    """
    Get all predictions for an image above the threshold.
    
    Args:
        image_id: Database ID of the image
        min_confidence: Minimum confidence threshold (defaults to display threshold)
    
    Returns:
        List of dicts with tag_name, category, confidence
    """
    if min_confidence is None:
        min_confidence = config.LOCAL_TAGGER_DISPLAY_THRESHOLD
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tag_name, category, confidence
            FROM local_tagger_predictions
            WHERE image_id = ? AND confidence >= ?
            ORDER BY confidence DESC
        """, (image_id, min_confidence))
        
        return [dict(row) for row in cursor.fetchall()]


def get_merged_general_tags(image_id: int, existing_general_tags: set, min_confidence: float = None):
    """
    Get general tags from local tagger that should be merged into display.
    Only returns tags NOT already in existing_general_tags.
    
    Args:
        image_id: Database ID of the image
        existing_general_tags: Set of general tag names already present from primary source
        min_confidence: Minimum confidence threshold
    
    Returns:
        Set of new tag names to add
    """
    if min_confidence is None:
        min_confidence = config.LOCAL_TAGGER_DISPLAY_THRESHOLD
    
    merge_categories = config.LOCAL_TAGGER_MERGE_CATEGORIES
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Build category filter
        placeholders = ','.join(['?' for _ in merge_categories])
        
        cursor.execute(f"""
            SELECT tag_name, confidence
            FROM local_tagger_predictions
            WHERE image_id = ? 
              AND confidence >= ?
              AND category IN ({placeholders})
            ORDER BY confidence DESC
        """, (image_id, min_confidence, *merge_categories))
        
        # Filter out tags already present
        new_tags = set()
        for row in cursor.fetchall():
            tag_name = row['tag_name']
            if tag_name not in existing_general_tags:
                new_tags.add(tag_name)
        
        return new_tags


def get_all_predictions_for_image(image_id: int):
    """
    Get ALL stored predictions for an image (for debugging/analysis).
    Returns everything above storage threshold.
    
    Args:
        image_id: Database ID of the image
    
    Returns:
        List of dicts with tag_name, category, confidence
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tag_name, category, confidence
            FROM local_tagger_predictions
            WHERE image_id = ?
            ORDER BY confidence DESC
        """, (image_id,))
        
        return [dict(row) for row in cursor.fetchall()]


def get_tag_frequency_for_character(character_tag: str, min_confidence: float = 0.3, min_count: int = 10):
    """
    Cross-reference: Find tags that frequently appear with a specific character.
    Useful for discovering attributes the tagger sees consistently but with low confidence.
    
    Args:
        character_tag: The character tag to analyze (e.g., 'pulchra_fellini')
        min_confidence: Minimum average confidence to include
        min_count: Minimum number of images the tag must appear in
    
    Returns:
        List of dicts with tag_name, avg_confidence, image_count
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                ltp.tag_name,
                AVG(ltp.confidence) as avg_confidence,
                COUNT(DISTINCT ltp.image_id) as image_count
            FROM local_tagger_predictions ltp
            JOIN image_tags it ON ltp.image_id = it.image_id
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
              AND ltp.tag_name != ?
            GROUP BY ltp.tag_name
            HAVING COUNT(DISTINCT ltp.image_id) >= ?
               AND AVG(ltp.confidence) >= ?
            ORDER BY image_count DESC, avg_confidence DESC
        """, (character_tag, character_tag, min_count, min_confidence))
        
        return [dict(row) for row in cursor.fetchall()]


def clear_predictions_for_source(source_name: str = 'local_tagger'):
    """
    Clear all local tagger predictions for images from a specific source.
    Used for bulk re-tagging operations.
    
    Args:
        source_name: The active_source to match (default: 'local_tagger')
    
    Returns:
        Number of images affected
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get image IDs with this source
        cursor.execute("""
            SELECT id FROM images WHERE active_source = ?
        """, (source_name,))
        
        image_ids = [row['id'] for row in cursor.fetchall()]
        
        if not image_ids:
            return 0
        
        # Delete predictions for these images
        placeholders = ','.join(['?' for _ in image_ids])
        cursor.execute(f"""
            DELETE FROM local_tagger_predictions WHERE image_id IN ({placeholders})
        """, image_ids)
        
        conn.commit()
        return len(image_ids)


def clear_all_predictions():
    """
    Clear ALL local tagger predictions.
    Used for complete re-tagging of the entire library.
    
    Returns:
        Number of rows deleted
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM local_tagger_predictions")
        deleted = cursor.rowcount
        conn.commit()
        return deleted

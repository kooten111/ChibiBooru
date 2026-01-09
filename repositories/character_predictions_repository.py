"""
Repository for character predictions.
Handles storage and retrieval of character predictions with confidence scores.
"""
from database import get_db_connection
from typing import List, Dict, Optional


def store_predictions(image_id: int, predictions: List[tuple], min_confidence: float = 0.0) -> int:
    """
    Store character predictions for an image.
    
    Args:
        image_id: Database ID of the image
        predictions: List of (character_name, confidence) tuples
        min_confidence: Minimum confidence threshold for storing
    
    Returns:
        Number of predictions stored
    """
    if not predictions:
        return 0
    
    # Filter predictions above threshold
    filtered = [(char, conf) for char, conf in predictions if conf >= min_confidence]
    
    if not filtered:
        return 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Clear existing predictions for this image (fresh start each time)
        cursor.execute("DELETE FROM character_predictions WHERE image_id = ?", (image_id,))
        
        # Insert new predictions
        cursor.executemany("""
            INSERT INTO character_predictions 
            (image_id, character_name, confidence)
            VALUES (?, ?, ?)
        """, [
            (image_id, char, conf) for char, conf in filtered
        ])
        
        conn.commit()
        return len(filtered)


def get_predictions_for_image(image_id: int, min_confidence: float = None, limit: int = None) -> List[Dict]:
    """
    Get stored character predictions for an image.
    
    Args:
        image_id: Database ID of the image
        min_confidence: Optional minimum confidence threshold
        limit: Optional maximum number of predictions to return
    
    Returns:
        List of dicts with 'character_name' and 'confidence'
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        query = """
            SELECT character_name, confidence
            FROM character_predictions
            WHERE image_id = ?
        """
        params = [image_id]
        
        if min_confidence is not None:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        
        query += " ORDER BY confidence DESC"
        
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        
        return [
            {
                'character': row['character_name'],
                'confidence': row['confidence']
            }
            for row in cursor.fetchall()
        ]


def get_predictions_for_images(image_ids: List[int], min_confidence: float = None) -> Dict[int, List[Dict]]:
    """
    Get stored character predictions for multiple images.
    
    Args:
        image_ids: List of image IDs
        min_confidence: Optional minimum confidence threshold
    
    Returns:
        Dict mapping image_id to list of predictions
    """
    if not image_ids:
        return {}
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(image_ids))
        query = f"""
            SELECT image_id, character_name, confidence
            FROM character_predictions
            WHERE image_id IN ({placeholders})
        """
        params = list(image_ids)
        
        if min_confidence is not None:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        
        query += " ORDER BY image_id, confidence DESC"
        
        cursor.execute(query, params)
        
        result = {img_id: [] for img_id in image_ids}
        for row in cursor.fetchall():
            result[row['image_id']].append({
                'character': row['character_name'],
                'confidence': row['confidence']
            })
        
        return result


def clear_predictions_for_image(image_id: int) -> None:
    """Clear all predictions for an image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM character_predictions WHERE image_id = ?", (image_id,))
        conn.commit()


def clear_all_predictions() -> int:
    """Clear all stored predictions. Returns count of deleted rows."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM character_predictions")
        count = cursor.rowcount
        conn.commit()
        return count


def store_predictions_batch(predictions_by_image: Dict[int, List[tuple]], min_confidence: float = 0.0) -> int:
    """
    Store character predictions for multiple images in a single transaction.
    Much faster than calling store_predictions individually.
    
    Args:
        predictions_by_image: Dict mapping image_id to list of (character_name, confidence) tuples
        min_confidence: Minimum confidence threshold for storing
    
    Returns:
        Total number of predictions stored
    """
    if not predictions_by_image:
        return 0
    
    # Filter and prepare all predictions
    all_predictions = []
    image_ids_to_clear = []
    
    for image_id, predictions in predictions_by_image.items():
        if not predictions:
            continue
        
        # Filter predictions above threshold
        filtered = [(image_id, char, conf) for char, conf in predictions if conf >= min_confidence]
        
        if filtered:
            all_predictions.extend(filtered)
            image_ids_to_clear.append(image_id)
    
    if not all_predictions:
        return 0
    
    # Batch delete and insert in a single transaction
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Clear existing predictions for all images in batch
        if image_ids_to_clear:
            placeholders = ','.join('?' * len(image_ids_to_clear))
            cursor.execute(f"""
                DELETE FROM character_predictions 
                WHERE image_id IN ({placeholders})
            """, image_ids_to_clear)
        
        # Insert all new predictions in one go
        cursor.executemany("""
            INSERT INTO character_predictions 
            (image_id, character_name, confidence)
            VALUES (?, ?, ?)
        """, all_predictions)
        
        conn.commit()
        return len(all_predictions)

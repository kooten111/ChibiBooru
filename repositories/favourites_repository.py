"""
Favourites Repository Module

This module handles all database operations for user favourites.
"""

from database import get_db_connection


def add_favourite(image_id: int) -> bool:
    """
    Add an image to favourites.
    
    Args:
        image_id: The image ID to favourite
        
    Returns:
        True if successfully added, False if already favourited
    """
    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO favourites (image_id) VALUES (?)",
                (image_id,)
            )
            conn.commit()
            return True
        except Exception:
            # Already exists (PRIMARY KEY constraint)
            return False


def remove_favourite(image_id: int) -> bool:
    """
    Remove an image from favourites.
    
    Args:
        image_id: The image ID to unfavourite
        
    Returns:
        True if successfully removed, False if wasn't favourited
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM favourites WHERE image_id = ?",
            (image_id,)
        )
        conn.commit()
        return cursor.rowcount > 0


def toggle_favourite(image_id: int) -> bool:
    """
    Toggle the favourite status of an image.
    
    Args:
        image_id: The image ID to toggle
        
    Returns:
        True if now favourited, False if now unfavourited
    """
    if is_favourite(image_id):
        remove_favourite(image_id)
        return False
    else:
        add_favourite(image_id)
        return True


def is_favourite(image_id: int) -> bool:
    """
    Check if an image is favourited.
    
    Args:
        image_id: The image ID to check
        
    Returns:
        True if favourited, False otherwise
    """
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM favourites WHERE image_id = ? LIMIT 1",
            (image_id,)
        ).fetchone()
        return result is not None


def is_favourite_by_filepath(filepath: str) -> bool:
    """
    Check if an image is favourited by filepath.
    
    Args:
        filepath: The image filepath (without 'images/' prefix)
        
    Returns:
        True if favourited, False otherwise
    """
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    with get_db_connection() as conn:
        result = conn.execute("""
            SELECT 1 FROM favourites f
            JOIN images i ON f.image_id = i.id
            WHERE i.filepath = ?
            LIMIT 1
        """, (filepath,)).fetchone()
        return result is not None


def get_favourite_image_ids() -> set:
    """
    Get all favourite image IDs.
    
    Returns:
        Set of image IDs that are favourited
    """
    with get_db_connection() as conn:
        results = conn.execute("SELECT image_id FROM favourites").fetchall()
        return {row['image_id'] for row in results}


def get_favourite_filepaths() -> set:
    """
    Get all favourite image filepaths.
    
    Returns:
        Set of filepaths that are favourited
    """
    with get_db_connection() as conn:
        results = conn.execute("""
            SELECT i.filepath FROM favourites f
            JOIN images i ON f.image_id = i.id
        """).fetchall()
        return {row['filepath'] for row in results}


def get_image_id_by_filepath(filepath: str) -> int | None:
    """
    Get the image ID for a given filepath.
    
    Args:
        filepath: The image filepath (without 'images/' prefix)
        
    Returns:
        Image ID or None if not found
    """
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    with get_db_connection() as conn:
        result = conn.execute(
            "SELECT id FROM images WHERE filepath = ?",
            (filepath,)
        ).fetchone()
        return result['id'] if result else None


def get_favourites_count() -> int:
    """
    Get the total count of favourited images.
    
    Returns:
        Number of favourited images
    """
    with get_db_connection() as conn:
        result = conn.execute("SELECT COUNT(*) as count FROM favourites").fetchone()
        return result['count'] if result else 0

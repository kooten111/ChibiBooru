"""
Tag Database Utilities

Centralized utilities for tag database operations to reduce duplication
across models.py, services, and API endpoints.
"""

from database import get_db_connection
from utils.logging_config import get_logger

logger = get_logger(__name__)


def _validate_tag_name(tag_name: str) -> str:
    """
    Validate and normalize tag name.
    
    Args:
        tag_name: Tag name to validate
        
    Returns:
        Stripped tag name
        
    Raises:
        ValueError: If tag name is empty or invalid
    """
    if not tag_name or not tag_name.strip():
        raise ValueError("Tag name cannot be empty")
    return tag_name.strip()


def insert_tag(tag_name: str, category: str = None) -> int:
    """
    Insert a tag and return its ID.
    
    Args:
        tag_name: The tag name to insert
        category: Optional category (general, character, copyright, artist, species, meta)
        
    Returns:
        The tag ID (integer)
        
    Raises:
        ValueError: If tag_name is empty or invalid
    """
    tag_name = _validate_tag_name(tag_name)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if category:
            # Insert or update with category
            cursor.execute(
                "INSERT INTO tags (name, category) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET category=excluded.category",
                (tag_name, category)
            )
        else:
            # Insert without category (or keep existing category)
            cursor.execute(
                "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (tag_name,)
            )
        
        # Fetch the tag ID
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        result = cursor.fetchone()
        
        if result:
            tag_id = result['id']
            logger.debug(f"Inserted/retrieved tag '{tag_name}' with ID {tag_id}")
            return tag_id
        else:
            raise RuntimeError(f"Failed to insert or retrieve tag '{tag_name}'")


def bulk_insert_tags(tags: list[dict]) -> dict:
    """
    Bulk insert tags and return mapping of names to IDs.
    
    Args:
        tags: List of dicts with 'name' and optional 'category' keys
              Example: [{'name': 'tag1', 'category': 'general'}, {'name': 'tag2'}]
    
    Returns:
        Dictionary mapping tag names to their IDs
        Example: {'tag1': 1, 'tag2': 2}
        
    Raises:
        ValueError: If tags list is empty or contains invalid entries
    """
    if not tags:
        raise ValueError("Tags list cannot be empty")
    
    tag_map = {}
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        for tag_data in tags:
            if not isinstance(tag_data, dict):
                logger.warning(f"Skipping invalid tag entry: {tag_data}")
                continue
                
            tag_name = tag_data.get('name', '').strip()
            if not tag_name:
                logger.warning("Skipping tag with empty name")
                continue
                
            category = tag_data.get('category')
            
            # Insert or update tag
            if category:
                cursor.execute(
                    "INSERT INTO tags (name, category) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET category=excluded.category",
                    (tag_name, category)
                )
            else:
                cursor.execute(
                    "INSERT INTO tags (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                    (tag_name,)
                )
            
            # Retrieve the tag ID
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            result = cursor.fetchone()
            if result:
                tag_map[tag_name] = result['id']
        
        conn.commit()
        
    logger.info(f"Bulk inserted {len(tag_map)} tags")
    return tag_map


def update_tag_category(tag_name: str, category: str) -> bool:
    """
    Update a tag's category.
    
    Args:
        tag_name: The tag name to update
        category: New category (general, character, copyright, artist, species, meta)
        
    Returns:
        True if successful, False if tag not found
        
    Raises:
        ValueError: If tag_name or category is empty
    """
    tag_name = _validate_tag_name(tag_name)
    
    if not category or not category.strip():
        raise ValueError("Category cannot be empty")
    
    category = category.strip()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if tag exists
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Tag '{tag_name}' not found for category update")
            return False
        
        # Update category
        cursor.execute(
            "UPDATE tags SET category = ? WHERE name = ?",
            (category, tag_name)
        )
        conn.commit()
        
        logger.info(f"Updated tag '{tag_name}' to category '{category}'")
        return True


def get_or_create_tag(tag_name: str, category: str = None) -> int:
    """
    Get existing tag ID or create a new tag if it doesn't exist.
    
    This is a convenience wrapper around insert_tag that ensures
    a tag ID is always returned.
    
    Args:
        tag_name: The tag name
        category: Optional category
        
    Returns:
        The tag ID
    """
    return insert_tag(tag_name, category)

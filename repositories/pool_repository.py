"""
Pool Repository - Database operations for pool management.

Handles all pool-related database operations:
- Pool CRUD (Create, Read, Update, Delete)
- Pool membership (adding/removing images)
- Pool searching and querying
- Image-pool relationships
"""

from database import get_db_connection


def create_pool(name, description=""):
    """Create a new pool.

    Args:
        name (str): Pool name
        description (str, optional): Pool description. Defaults to "".

    Returns:
        int: ID of the newly created pool
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pools (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
        return cursor.lastrowid


def get_all_pools():
    """Get a list of all pools.

    Returns:
        list[dict]: List of pool dictionaries with id, name, description
    """
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM pools ORDER BY name ASC").fetchall()]


def get_pool_details(pool_id):
    """Get details for a single pool and its images.

    Args:
        pool_id (int): Pool ID

    Returns:
        dict | None: Dictionary with 'pool' and 'images' keys, or None if pool doesn't exist
            - pool: dict with id, name, description
            - images: list of dicts with filepath, sort_order
    """
    with get_db_connection() as conn:
        pool = conn.execute("SELECT * FROM pools WHERE id = ?", (pool_id,)).fetchone()
        if not pool:
            return None

        images_query = """
        SELECT i.filepath, pi.sort_order
        FROM images i
        JOIN pool_images pi ON i.id = pi.image_id
        WHERE pi.pool_id = ?
        ORDER BY pi.sort_order ASC
        """
        images = [dict(row) for row in conn.execute(images_query, (pool_id,)).fetchall()]
        return {"pool": dict(pool), "images": images}


def add_image_to_pool(pool_id, image_id):
    """Add an image to a pool.

    Args:
        pool_id (int): Pool ID
        image_id (int): Image ID

    Note:
        Uses INSERT OR IGNORE to prevent duplicate entries.
        Automatically assigns the next sort_order value.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get the next sort order
        cursor.execute("SELECT MAX(sort_order) FROM pool_images WHERE pool_id = ?", (pool_id,))
        max_order = cursor.fetchone()[0]
        next_order = (max_order or 0) + 1

        cursor.execute("INSERT OR IGNORE INTO pool_images (pool_id, image_id, sort_order) VALUES (?, ?, ?)",
                       (pool_id, image_id, next_order))
        conn.commit()


def remove_image_from_pool(pool_id, image_id):
    """Remove an image from a pool.

    Args:
        pool_id (int): Pool ID
        image_id (int): Image ID
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pool_images WHERE pool_id = ? AND image_id = ?", (pool_id, image_id))
        conn.commit()


def delete_pool(pool_id):
    """Delete a pool (cascade deletes pool_images entries).

    Args:
        pool_id (int): Pool ID to delete

    Note:
        pool_images entries are automatically deleted due to CASCADE constraint.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pools WHERE id = ?", (pool_id,))
        conn.commit()


def update_pool(pool_id, name=None, description=None):
    """Update pool name and/or description.

    Args:
        pool_id (int): Pool ID
        name (str, optional): New pool name. If None, name is not updated.
        description (str, optional): New description. If None, description is not updated.

    Note:
        At least one of name or description should be provided.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if name is not None and description is not None:
            cursor.execute("UPDATE pools SET name = ?, description = ? WHERE id = ?", (name, description, pool_id))
        elif name is not None:
            cursor.execute("UPDATE pools SET name = ? WHERE id = ?", (name, pool_id))
        elif description is not None:
            cursor.execute("UPDATE pools SET description = ? WHERE id = ?", (description, pool_id))
        conn.commit()


def reorder_pool_images(pool_id, image_id, new_position):
    """Reorder an image within a pool to a new position (1-indexed).

    Args:
        pool_id (int): Pool ID
        image_id (int): Image ID to reorder
        new_position (int): New sort order position (1-indexed)

    Note:
        Automatically adjusts sort_order of other images in the pool.
        If new_position equals current position, no changes are made.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get current position
        cursor.execute("SELECT sort_order FROM pool_images WHERE pool_id = ? AND image_id = ?", (pool_id, image_id))
        result = cursor.fetchone()
        if not result:
            return

        old_position = result[0]
        if old_position == new_position:
            return

        # Shift other images
        if new_position < old_position:
            # Moving up: increment sort_order for images in between
            cursor.execute("""
                UPDATE pool_images
                SET sort_order = sort_order + 1
                WHERE pool_id = ? AND sort_order >= ? AND sort_order < ?
            """, (pool_id, new_position, old_position))
        else:
            # Moving down: decrement sort_order for images in between
            cursor.execute("""
                UPDATE pool_images
                SET sort_order = sort_order - 1
                WHERE pool_id = ? AND sort_order > ? AND sort_order <= ?
            """, (pool_id, old_position, new_position))

        # Set new position for the moved image
        cursor.execute("UPDATE pool_images SET sort_order = ? WHERE pool_id = ? AND image_id = ?",
                       (new_position, pool_id, image_id))
        conn.commit()


def search_pools(search_term):
    """Search for pools by name or description.

    Args:
        search_term (str): Search term (case-insensitive, partial match)

    Returns:
        list[dict]: List of matching pools with image_count field
    """
    with get_db_connection() as conn:
        query = """
        SELECT p.*, COUNT(pi.image_id) as image_count
        FROM pools p
        LEFT JOIN pool_images pi ON p.id = pi.pool_id
        WHERE p.name LIKE ? OR p.description LIKE ?
        GROUP BY p.id
        ORDER BY p.name ASC
        """
        search_pattern = f"%{search_term}%"
        return [dict(row) for row in conn.execute(query, (search_pattern, search_pattern)).fetchall()]


def get_pools_for_image(image_id):
    """Get all pools that contain a specific image.

    Args:
        image_id (int): Image ID

    Returns:
        list[dict]: List of pool dictionaries containing this image
    """
    with get_db_connection() as conn:
        query = """
        SELECT p.*
        FROM pools p
        JOIN pool_images pi ON p.id = pi.pool_id
        WHERE pi.image_id = ?
        ORDER BY p.name ASC
        """
        return [dict(row) for row in conn.execute(query, (image_id,)).fetchall()]


def search_images_by_pool(pool_name):
    """Get all images in a pool by pool name (case-insensitive partial match).

    Args:
        pool_name (str): Pool name or partial name to search for

    Returns:
        list[dict]: List of dicts with 'filepath' key, ordered by sort_order
    """
    with get_db_connection() as conn:
        query = """
        SELECT i.filepath
        FROM images i
        JOIN pool_images pi ON i.id = pi.image_id
        JOIN pools p ON pi.pool_id = p.id
        WHERE LOWER(p.name) LIKE LOWER(?)
        ORDER BY pi.sort_order ASC
        """
        search_pattern = f"%{pool_name}%"
        return [dict(row) for row in conn.execute(query, (search_pattern,)).fetchall()]

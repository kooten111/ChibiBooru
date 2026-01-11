"""
Data retrieval functions for rating inference system.
"""

from collections import defaultdict
from typing import List, Tuple
from database import get_db_connection
from .config import RATINGS


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
        batch_size = 900  # Safe limit for SQLite variables
        for i in range(0, total_images, batch_size):
            batch = image_ids[i:i + batch_size]
            
            if progress_callback:
                progress = 5 + int((i / total_images) * 15)  # 5-20% range
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

"""
Statistics and analysis functions for rating inference system.
"""

from datetime import datetime
from typing import Dict
from database import get_db_connection
from .config import RATINGS, get_model_connection, get_config
from .data import get_unrated_images_count


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
    from .training import train_model
    from .inference import infer_all_unrated_images

    result = {}

    # Clear AI ratings
    result['cleared'] = clear_ai_inferred_ratings()

    # Retrain
    result['training_stats'] = train_model()

    # Re-infer
    result['inference_stats'] = infer_all_unrated_images()

    return result

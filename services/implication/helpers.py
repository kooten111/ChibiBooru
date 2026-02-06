"""Helper functions for implication operations."""

from typing import Dict, List

from database import get_db_connection


def _flatten_chain(chain: Dict) -> List[str]:
    """Flatten implication chain tree into a list of tag names."""
    tags = []

    def traverse(node):
        if node.get('implies'):
            for child in node['implies']:
                tags.append(child['tag'])
                traverse(child)

    traverse(chain)
    return tags


def _implication_exists(source_tag: str, implied_tag: str) -> bool:
    """Check if an implication already exists."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM tag_implications ti
            JOIN tags t_source ON ti.source_tag_id = t_source.id
            JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
            WHERE t_source.name = ? AND t_implied.name = ?
        """, (source_tag, implied_tag))

        return cursor.fetchone() is not None


def _count_images_with_tag(tag_name: str) -> int:
    """Count images that have a specific tag."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(DISTINCT it.image_id) as count
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
        """, (tag_name,))

        result = cursor.fetchone()
        return result['count'] if result else 0

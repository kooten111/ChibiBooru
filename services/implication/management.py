"""CRUD operations and queries for tag implications."""

from typing import Dict, List

from database import get_db_connection


def create_manual_implication(source_tag: str, implied_tag: str) -> bool:
    """Create a manual implication between two tags."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
        source_result = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag,))
        implied_result = cursor.fetchone()

        if not source_result or not implied_result:
            return False

        source_id = source_result['id']
        implied_id = implied_result['id']

        cursor.execute("""
            INSERT OR IGNORE INTO tag_implications
            (source_tag_id, implied_tag_id, inference_type, confidence, status, created_at)
            VALUES (?, ?, 'manual', 1.0, 'active', CURRENT_TIMESTAMP)
        """, (source_id, implied_id))

        conn.commit()
        return cursor.rowcount > 0


def approve_suggestion(source_tag: str, implied_tag: str, inference_type: str,
                       confidence: float = 1.0) -> bool:
    """Approve a suggestion and create the implication in the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
        source_result = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag,))
        implied_result = cursor.fetchone()

        if not source_result or not implied_result:
            return False

        source_id = source_result['id']
        implied_id = implied_result['id']

        cursor.execute("""
            INSERT OR IGNORE INTO tag_implications
            (source_tag_id, implied_tag_id, inference_type, confidence, status, created_at)
            VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """, (source_id, implied_id, inference_type, confidence))

        conn.commit()
        return cursor.rowcount > 0


def delete_implication(source_tag: str, implied_tag: str) -> bool:
    """Delete an implication."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM tag_implications
            WHERE source_tag_id = (SELECT id FROM tags WHERE name = ?)
            AND implied_tag_id = (SELECT id FROM tags WHERE name = ?)
        """, (source_tag, implied_tag))

        conn.commit()
        return cursor.rowcount > 0


def delete_all_implications() -> int:
    """Delete all active implications."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tag_implications WHERE status = 'active'")
        deleted_count = cursor.rowcount
        conn.commit()
        return deleted_count


def get_all_implications() -> List[Dict]:
    """Get all existing implications with metadata."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                t_source.name as source_tag,
                t_source.category as source_category,
                t_implied.name as implied_tag,
                t_implied.category as implied_category,
                ti.inference_type,
                ti.confidence,
                ti.status,
                ti.created_at
            FROM tag_implications ti
            JOIN tags t_source ON ti.source_tag_id = t_source.id
            JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
            WHERE ti.status = 'active'
            ORDER BY t_source.category, t_source.name
        """)

        return [dict(row) for row in cursor.fetchall()]


def get_implication_chain(tag_name: str, max_depth: int = 10) -> Dict:
    """Get the full implication chain for a tag (what it implies recursively)."""
    visited = set()

    def build_chain(current_tag: str, depth: int = 0) -> Dict:
        if depth >= max_depth or current_tag in visited:
            return {'tag': current_tag, 'implies': []}

        visited.add(current_tag)

        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get tag category
            cursor.execute("SELECT category FROM tags WHERE name = ?", (current_tag,))
            result = cursor.fetchone()
            category = result['category'] if result else 'general'

            # Get direct implications
            cursor.execute("""
                SELECT t_implied.name
                FROM tag_implications ti
                JOIN tags t_source ON ti.source_tag_id = t_source.id
                JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
                WHERE t_source.name = ? AND ti.status = 'active'
            """, (current_tag,))

            implications = []
            for row in cursor.fetchall():
                implied_tag = row['name']
                implications.append(build_chain(implied_tag, depth + 1))

            return {
                'tag': current_tag,
                'category': category,
                'implies': implications
            }

    return build_chain(tag_name)


def get_tags_implying(tag_name: str) -> List[str]:
    """Get all tags that imply this tag (reverse lookup)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT t_source.name
            FROM tag_implications ti
            JOIN tags t_source ON ti.source_tag_id = t_source.id
            JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
            WHERE t_implied.name = ? AND ti.status = 'active'
        """, (tag_name,))

        return [row['name'] for row in cursor.fetchall()]


def get_implications_for_tag(tag_name: str) -> Dict:
    """Get all implications related to a specific tag (tag-centric view)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get tag info
        cursor.execute("SELECT id, name, category FROM tags WHERE name = ?", (tag_name,))
        tag_result = cursor.fetchone()
        
        if not tag_result:
            return {
                'tag': None,
                'implies': [],
                'implied_by': [],
                'suggestions': []
            }
        
        tag_id = tag_result['id']
        tag_info = dict(tag_result)
        
        # Get implications where this tag is the source
        cursor.execute("""
            SELECT
                t_implied.name as implied_tag,
                t_implied.category as implied_category,
                ti.inference_type,
                ti.confidence,
                ti.created_at
            FROM tag_implications ti
            JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
            WHERE ti.source_tag_id = ? AND ti.status = 'active'
            ORDER BY t_implied.name
        """, (tag_id,))
        
        implies = [dict(row) for row in cursor.fetchall()]
        
        # Get implications where this tag is the target
        cursor.execute("""
            SELECT
                t_source.name as source_tag,
                t_source.category as source_category,
                ti.inference_type,
                ti.confidence,
                ti.created_at
            FROM tag_implications ti
            JOIN tags t_source ON ti.source_tag_id = t_source.id
            WHERE ti.implied_tag_id = ? AND ti.status = 'active'
            ORDER BY t_source.name
        """, (tag_id,))
        
        implied_by = [dict(row) for row in cursor.fetchall()]
        
        # Get suggestions involving this tag
        from .suggestions import get_all_suggestions
        all_suggestions = get_all_suggestions()
        tag_suggestions = []
        
        for pattern_type in ['naming', 'correlation']:
            for suggestion in all_suggestions.get(pattern_type, []):
                if suggestion['source_tag'] == tag_name or suggestion['implied_tag'] == tag_name:
                    tag_suggestions.append(suggestion)
        
        return {
            'tag': tag_info,
            'implies': implies,
            'implied_by': implied_by,
            'suggestions': tag_suggestions
        }


def preview_implication_impact(source_tag: str, implied_tag: str) -> Dict:
    """Preview the impact of creating an implication."""
    from .helpers import _flatten_chain
    
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Count images with source tag
        cursor.execute("""
            SELECT COUNT(DISTINCT it.image_id) as count
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
        """, (source_tag,))
        total_images = cursor.fetchone()['count']

        # Count images that already have implied tag
        cursor.execute("""
            SELECT COUNT(DISTINCT it.image_id) as count
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
            AND it.image_id IN (
                SELECT it2.image_id
                FROM image_tags it2
                JOIN tags t2 ON it2.tag_id = t2.id
                WHERE t2.name = ?
            )
        """, (implied_tag, source_tag))
        already_has = cursor.fetchone()['count']

        will_gain = total_images - already_has

        # Get chain implications
        chain = get_implication_chain(implied_tag)
        chain_tags = _flatten_chain(chain)
        
        # Detect circular implications
        conflicts = []
        if source_tag in chain_tags:
            conflicts.append(f"Circular implication detected: {source_tag} -> {implied_tag} -> ... -> {source_tag}")

        return {
            'total_images': total_images,
            'already_has_tag': already_has,
            'will_gain_tag': will_gain,
            'chain_implications': chain_tags,
            'conflicts': conflicts
        }

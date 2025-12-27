"""
Tag Implication Service
Handles automatic pattern detection and suggestion generation for tag implications.
"""
import re
from database import get_db_connection
from typing import List, Dict, Tuple, Set


class ImplicationSuggestion:
    """Represents a suggested tag implication."""
    def __init__(self, source_tag: str, implied_tag: str, confidence: float,
                 pattern_type: str, reason: str, affected_images: int = 0):
        self.source_tag = source_tag
        self.implied_tag = implied_tag
        self.confidence = confidence
        self.pattern_type = pattern_type
        self.reason = reason
        self.affected_images = affected_images

    def to_dict(self):
        return {
            'source_tag': self.source_tag,
            'implied_tag': self.implied_tag,
            'confidence': self.confidence,
            'pattern_type': self.pattern_type,
            'reason': self.reason,
            'affected_images': self.affected_images
        }


def detect_substring_implications() -> List[ImplicationSuggestion]:
    """
    Detect implications based on substring/naming patterns.

    Generic pattern detection that finds:
    - character_(something)_(franchise) → character_(franchise) (costume variants)
    - character_(franchise) → franchise (character → copyright)
    - any tag with parentheses → extracted portion if it exists

    This replaces hardcoded costume and franchise detection with a data-driven approach.
    """
    suggestions = []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all character tags
        cursor.execute("SELECT name FROM tags WHERE category = 'character'")
        character_tags = [row['name'] for row in cursor.fetchall()]

        for tag_name in character_tags:
            # Pattern 1: Extract final parenthesized portion
            # e.g., character_(franchise) → franchise
            match = re.search(r'\(([^)]+)\)$', tag_name)

            if match:
                potential_implied = match.group(1)

                # Check if this exists as a copyright tag
                cursor.execute(
                    "SELECT category FROM tags WHERE name = ?",
                    (potential_implied,)
                )
                result = cursor.fetchone()

                if result and result['category'] == 'copyright':
                    if not _implication_exists(tag_name, potential_implied):
                        affected = _count_images_with_tag(tag_name)

                        suggestions.append(ImplicationSuggestion(
                            source_tag=tag_name,
                            implied_tag=potential_implied,
                            confidence=0.92,
                            pattern_type='naming_pattern',
                            reason=f'Naming pattern: extracted "{potential_implied}" from tag name',
                            affected_images=affected
                        ))

            # Pattern 2: Substring variations (costume, form, alt, etc.)
            # e.g., character_(costume)_(franchise) → character_(franchise)
            # Look for tags that contain this tag as a substring
            pattern = r'^(.+?)_\([^)]+\)_\((.+?)\)$'
            match = re.match(pattern, tag_name)

            if match:
                # This is a tag with intermediate parentheses (like costume variants)
                base_part = match.group(1)
                franchise_part = match.group(2)
                base_tag = f"{base_part}_({franchise_part})"

                # Check if simpler version exists
                if base_tag in character_tags:
                    if not _implication_exists(tag_name, base_tag):
                        affected = _count_images_with_tag(tag_name)

                        # Extract what's in the middle parentheses for the reason
                        middle_match = re.search(r'_\(([^)]+)\)_', tag_name)
                        middle_part = middle_match.group(1) if middle_match else 'variant'

                        suggestions.append(ImplicationSuggestion(
                            source_tag=tag_name,
                            implied_tag=base_tag,
                            confidence=0.95,
                            pattern_type='naming_pattern',
                            reason=f'Variant pattern: {middle_part} form implies base character',
                            affected_images=affected
                        ))

    return suggestions


def detect_tag_correlations(min_confidence: float = 0.85, min_co_occurrence: int = 3) -> List[ImplicationSuggestion]:
    """
    Detect tag implications based on statistical correlation.

    Finds cases where:
    - Tag A appears with Tag B in X% of cases (high co-occurrence rate)
    - Tag A never (or rarely) appears without Tag B
    - This suggests A → B implication

    Args:
        min_confidence: Minimum co-occurrence rate (0.0-1.0) to suggest implication
        min_co_occurrence: Minimum number of times tags must appear together
    """
    suggestions = []

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all character tags with sufficient usage
        cursor.execute("""
            SELECT t.id, t.name, COUNT(it.image_id) as usage_count
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE t.category = 'character'
            GROUP BY t.id
            HAVING usage_count >= ?
        """, (min_co_occurrence,))

        character_tags = cursor.fetchall()

        for char_tag in character_tags:
            char_id = char_tag['id']
            char_name = char_tag['name']
            char_count = char_tag['usage_count']

            # Find all tags that appear with this character
            cursor.execute("""
                SELECT
                    t2.id,
                    t2.name,
                    t2.category,
                    COUNT(DISTINCT it2.image_id) as co_occurrence
                FROM image_tags it1
                JOIN image_tags it2 ON it1.image_id = it2.image_id
                JOIN tags t2 ON it2.tag_id = t2.id
                WHERE it1.tag_id = ?
                AND it2.tag_id != ?
                AND t2.category IN ('copyright', 'general')
                GROUP BY t2.id
                HAVING co_occurrence >= ?
            """, (char_id, char_id, min_co_occurrence))

            correlated_tags = cursor.fetchall()

            for corr_tag in correlated_tags:
                corr_name = corr_tag['name']
                corr_category = corr_tag['category']
                co_occurrence = corr_tag['co_occurrence']

                # Calculate confidence: how often does character appear WITH this tag?
                confidence = co_occurrence / char_count

                # Only suggest if confidence is high enough
                if confidence >= min_confidence:
                    # Check if implication already exists
                    if not _implication_exists(char_name, corr_name):
                        # Calculate reason based on statistics
                        reason = f'{int(confidence * 100)}% co-occurrence ({co_occurrence}/{char_count} images)'

                        suggestions.append(ImplicationSuggestion(
                            source_tag=char_name,
                            implied_tag=corr_name,
                            confidence=confidence,
                            pattern_type='correlation',
                            reason=reason,
                            affected_images=char_count - co_occurrence  # Images that will gain the tag
                        ))

    return suggestions


def get_all_suggestions() -> Dict[str, List[Dict]]:
    """
    Get all auto-detected implication suggestions grouped by pattern type.
    """
    naming_suggestions = detect_substring_implications()
    correlation_suggestions = detect_tag_correlations(min_confidence=0.85, min_co_occurrence=3)

    return {
        'naming': [s.to_dict() for s in naming_suggestions],
        'correlation': [s.to_dict() for s in correlation_suggestions],
        'summary': {
            'total': len(naming_suggestions) + len(correlation_suggestions),
            'naming_count': len(naming_suggestions),
            'correlation_count': len(correlation_suggestions)
        }
    }


def approve_suggestion(source_tag: str, implied_tag: str, inference_type: str,
                       confidence: float = 1.0) -> bool:
    """
    Approve a suggestion and create the implication in the database.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get tag IDs
        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
        source_result = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag,))
        implied_result = cursor.fetchone()

        if not source_result or not implied_result:
            return False

        source_id = source_result['id']
        implied_id = implied_result['id']

        # Insert implication with metadata
        cursor.execute("""
            INSERT OR IGNORE INTO tag_implications
            (source_tag_id, implied_tag_id, inference_type, confidence, status, created_at)
            VALUES (?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        """, (source_id, implied_id, inference_type, confidence))

        conn.commit()
        return cursor.rowcount > 0


def create_manual_implication(source_tag: str, implied_tag: str) -> bool:
    """
    Create a manual implication between two tags.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get or create tags
        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
        source_result = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag,))
        implied_result = cursor.fetchone()

        if not source_result or not implied_result:
            return False

        source_id = source_result['id']
        implied_id = implied_result['id']

        # Insert implication
        cursor.execute("""
            INSERT OR IGNORE INTO tag_implications
            (source_tag_id, implied_tag_id, inference_type, confidence, status, created_at)
            VALUES (?, ?, 'manual', 1.0, 'active', CURRENT_TIMESTAMP)
        """, (source_id, implied_id))

        conn.commit()
        return cursor.rowcount > 0


def delete_implication(source_tag: str, implied_tag: str) -> bool:
    """
    Delete an implication.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM tag_implications
            WHERE source_tag_id = (SELECT id FROM tags WHERE name = ?)
            AND implied_tag_id = (SELECT id FROM tags WHERE name = ?)
        """, (source_tag, implied_tag))

        conn.commit()
        return cursor.rowcount > 0


def get_all_implications() -> List[Dict]:
    """
    Get all existing implications with metadata.
    """
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
    """
    Get the full implication chain for a tag (what it implies recursively).
    Returns a tree structure.
    """
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
    """
    Get all tags that imply this tag (reverse lookup).
    """
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


def preview_implication_impact(source_tag: str, implied_tag: str) -> Dict:
    """
    Preview the impact of creating an implication.
    Returns info about affected images and potential chain effects.
    """
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

        return {
            'total_images': total_images,
            'already_has_tag': already_has,
            'will_gain_tag': will_gain,
            'chain_implications': chain_tags,
            'conflicts': []  # TODO: Detect conflicts (e.g., circular implications)
        }


def batch_apply_implications_to_all_images() -> int:
    """
    Apply all active implications to all existing images.
    Returns count of tags added.
    """
    count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Get all images
        cursor.execute("SELECT id FROM images")
        images = cursor.fetchall()

        for img_row in images:
            image_id = img_row['id']

            # Import from repository to reuse existing function
            from repositories.tag_repository import apply_implications_for_image
            if apply_implications_for_image(image_id):
                count += 1

    return count


# Helper functions

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

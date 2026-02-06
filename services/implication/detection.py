"""Automatic implication detection from tag data."""

import re
from typing import List
from database import get_db_connection
from .models import ImplicationSuggestion


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
                            affected_images=affected,
                            source_category='character',
                            implied_category='copyright'
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
                            affected_images=affected,
                            source_category='character',
                            implied_category='character'
                        ))

    return suggestions


def detect_tag_correlations(min_confidence: float = 0.85, min_co_occurrence: int = 3) -> List[ImplicationSuggestion]:
    """
    Detect tag implications based on statistical correlation.

    Finds cases where:
    - Tag A appears with Tag B in X% of cases (high co-occurrence rate)
    - Tag A never (or rarely) appears without Tag B
    - This suggests A → B implication

    Only suggests implications for tags in allowed extended categories (permanent traits)
    to avoid contextual tags like poses, actions, expressions.

    Args:
        min_confidence: Minimum co-occurrence rate (0.0-1.0) to suggest implication
        min_co_occurrence: Minimum number of times tags must appear together
    """
    import config
    suggestions = []
    
    # Build SQL placeholders for allowed categories
    allowed_categories = config.IMPLICATION_ALLOWED_EXTENDED_CATEGORIES
    if not allowed_categories:
        # If no filter configured, allow all (backwards compatible)
        category_filter = ""
    else:
        placeholders = ','.join('?' for _ in allowed_categories)
        category_filter = f"AND t2.extended_category IN ({placeholders})"

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
            # Only include tags in allowed extended categories (permanent traits)
            query = f"""
                SELECT
                    t2.id,
                    t2.name,
                    t2.category,
                    t2.extended_category,
                    COUNT(DISTINCT it2.image_id) as co_occurrence
                FROM image_tags it1
                JOIN image_tags it2 ON it1.image_id = it2.image_id
                JOIN tags t2 ON it2.tag_id = t2.id
                WHERE it1.tag_id = ?
                AND it2.tag_id != ?
                AND t2.category IN ('copyright', 'general')
                {category_filter}
                GROUP BY t2.id
                HAVING co_occurrence >= ?
            """
            
            params = [char_id, char_id]
            if allowed_categories:
                params.extend(allowed_categories)
            params.append(min_co_occurrence)
            
            cursor.execute(query, params)

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
                            affected_images=char_count - co_occurrence,
                            sample_size=co_occurrence,
                            source_category='character',
                            implied_category=corr_category
                        ))

    return suggestions


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

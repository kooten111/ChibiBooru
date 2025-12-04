"""
Tag categorization service for manually categorizing uncategorized tags.

This service provides functionality to manage and categorize tags that don't
have a category assigned, showing them by frequency for efficient categorization.
"""

from database import get_db_connection
from typing import List, Dict, Optional, Tuple


# Extended tag categories based on Platinum Schema (22 categories)
# Format: (key, display_name, keyboard_shortcut, description)
EXTENDED_CATEGORIES = [
    ('00_Subject_Count', 'Subject Count', '0', 'Count & Gender (1girl, solo, 1boy)'),
    ('01_Body_Physique', 'Body Physique', '1', 'Permanent body traits (breasts, tail, animal_ears)'),
    ('02_Body_Hair', 'Body Hair', '2', 'Hair properties (long_hair, twintails, blonde_hair)'),
    ('03_Body_Face', 'Body Face', '3', 'Eye color & permanent face marks (blue_eyes, sharp_teeth)'),
    ('04_Body_Genitalia', 'Body Genitalia', '4', 'NSFW Anatomy (nipples, penis, pussy)'),
    ('05_Attire_Main', 'Attire Main', '5', 'Main outer clothing (shirt, dress, school_uniform)'),
    ('06_Attire_Inner', 'Attire Inner', '6', 'Underwear/Swimwear (panties, bra, bikini)'),
    ('07_Attire_Legwear', 'Attire Legwear', '7', 'Socks & Hosiery (thighhighs, pantyhose)'),
    ('08_Attire_Acc', 'Attire Accessories', '8', 'Accessories (gloves, ribbon, glasses)'),
    ('09_Action', 'Action', 'a', 'Active verbs (holding, eating, walking)'),
    ('10_Pose', 'Pose', 'p', 'Static body position & gaze (sitting, looking_at_viewer)'),
    ('11_Expression', 'Expression', 'e', 'Temporary emotion (blush, smile, crying)'),
    ('12_Sexual_Act', 'Sexual Act', 'x', 'NSFW interaction (sex, vaginal, fellatio)'),
    ('13_Object', 'Object', 'o', 'Props not worn (flower, weapon, phone)'),
    ('14_Setting', 'Setting', 's', 'Background/Time/Location (simple_background, outdoors)'),
    ('15_Framing', 'Framing', 'f', 'Camera angle/Crop (upper_body, cowboy_shot)'),
    ('16_Focus', 'Focus', 'u', 'Specific part focus (foot_focus, solo_focus)'),
    ('17_Style_Art', 'Style Art', 'y', 'Medium/Art style (monochrome, comic, sketch)'),
    ('18_Style_Tech', 'Style Tech', 't', 'Visual effects (blurry, chromatic_aberration)'),
    ('19_Meta_Attributes', 'Meta Attributes', 'q', 'General metadata attributes (highres, absurdres, bad_anatomy)'),
    ('20_Meta_Text', 'Meta Text', 'w', 'Text & UI elements (speech_bubble, signature)'),
    ('21_Status', 'Status', 'z', 'State of being (nude, wet, censored)'),
]

# Simple categories for basic mode (existing database categories)
SIMPLE_CATEGORIES = [
    'character',
    'copyright',
    'artist',
    'species',
    'general',
    'meta'
]

# Use extended categories by default
TAG_CATEGORIES = [cat[0] for cat in EXTENDED_CATEGORIES]  # Extract just the category keys


def get_uncategorized_tags_by_frequency(limit: int = 100, include_simple_categories: bool = True) -> List[Dict]:
    """
    Get uncategorized tags sorted by usage frequency.

    Args:
        limit: Maximum number of tags to return
        include_simple_categories: If True, also include tags with simple categories
                                   (character, copyright, etc.) that need extended categorization

    Returns:
        List of dicts with tag info: {name, usage_count, sample_images, current_category}
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get tags that need extended categorization (tags without extended_category)
        cur.execute("""
            SELECT
                t.name,
                t.category,
                t.extended_category,
                COUNT(DISTINCT it.image_id) as usage_count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE t.extended_category IS NULL
            GROUP BY t.name, t.category, t.extended_category
            HAVING usage_count > 0
            ORDER BY usage_count DESC
            LIMIT ?
        """, (limit,))

        tags = []
        for row in cur.fetchall():
            tag_name = row['name']
            current_category = row['category']
            usage_count = row['usage_count']

            # Get sample images for this tag
            cur.execute("""
                SELECT i.filepath
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                WHERE t.name = ?
                ORDER BY RANDOM()
                LIMIT 3
            """, (tag_name,))

            sample_images = [r['filepath'] for r in cur.fetchall()]

            tags.append({
                'name': tag_name,
                'usage_count': usage_count,
                'sample_images': sample_images,
                'current_category': current_category
            })

        return tags


def get_categorization_stats() -> Dict:
    """
    Get statistics about tag categorization status.

    Returns:
        Dict with categorization stats
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Total tags
        cur.execute("SELECT COUNT(*) as total FROM tags")
        total_tags = cur.fetchone()['total']

        # Extended categorization stats
        cur.execute("SELECT COUNT(*) as extended_uncategorized FROM tags WHERE extended_category IS NULL")
        extended_uncategorized = cur.fetchone()['extended_uncategorized']

        # Extended categorized tags
        extended_categorized = total_tags - extended_uncategorized

        # Tags by extended category
        cur.execute("""
            SELECT extended_category, COUNT(*) as count
            FROM tags
            WHERE extended_category IS NOT NULL
            GROUP BY extended_category
            ORDER BY count DESC
        """)

        by_extended_category = {row['extended_category']: row['count'] for row in cur.fetchall()}

        # Tags with extended category that are actually used
        cur.execute("""
            SELECT COUNT(DISTINCT t.id) as meaningful_extended_categorized
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE t.extended_category IS NOT NULL
        """)
        meaningful_extended_categorized = cur.fetchone()['meaningful_extended_categorized']

        # Tags without extended category that are used
        cur.execute("""
            SELECT COUNT(DISTINCT t.id) as meaningful_extended_uncategorized
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE t.extended_category IS NULL
        """)
        meaningful_extended_uncategorized = cur.fetchone()['meaningful_extended_uncategorized']

        return {
            'total_tags': total_tags,
            'categorized': extended_categorized,
            'uncategorized': extended_uncategorized,
            'meaningful_uncategorized': meaningful_extended_uncategorized,
            'meaningful_categorized': meaningful_extended_categorized,
            'by_category': by_extended_category,
            'categories': TAG_CATEGORIES,
            'extended_categories': EXTENDED_CATEGORIES
        }


def set_tag_category(tag_name: str, category: Optional[str]) -> Dict:
    """
    Set or update the category for a tag.

    Args:
        tag_name: Name of the tag to categorize
        category: Category to assign (or None to uncategorize)

    Returns:
        Dict with old_category and new_category
    """
    if category and category not in TAG_CATEGORIES:
        raise ValueError(f"Invalid category. Must be one of: {', '.join(TAG_CATEGORIES)}")

    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get old extended category
        cur.execute("SELECT extended_category FROM tags WHERE name = ?", (tag_name,))
        row = cur.fetchone()
        old_category = row['extended_category'] if row else None

        if not row:
            raise ValueError(f"Tag '{tag_name}' not found")

        # Update extended category
        cur.execute(
            "UPDATE tags SET extended_category = ? WHERE name = ?",
            (category, tag_name)
        )

        conn.commit()

        return {
            'old_category': old_category,
            'new_category': category
        }


def bulk_categorize_tags(categorizations: List[Tuple[str, str]]) -> Dict:
    """
    Categorize multiple tags at once.

    Args:
        categorizations: List of (tag_name, category) tuples

    Returns:
        Dict with success count and errors
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        success_count = 0
        errors = []

        for tag_name, category in categorizations:
            if category and category not in TAG_CATEGORIES:
                errors.append(f"{tag_name}: Invalid category '{category}'")
                continue

            try:
                cur.execute(
                    "UPDATE tags SET category = ? WHERE name = ?",
                    (category, tag_name)
                )
                success_count += 1
            except Exception as e:
                errors.append(f"{tag_name}: {str(e)}")

        conn.commit()

        return {
            'success_count': success_count,
            'error_count': len(errors),
            'errors': errors
        }


def suggest_category_for_tag(tag_name: str) -> Optional[str]:
    """
    Suggest a category for a tag based on naming patterns and co-occurrence.

    This is a simple heuristic-based suggestion system.

    Args:
        tag_name: Name of the tag to suggest category for

    Returns:
        Suggested category or None
    """
    tag_lower = tag_name.lower()

    # Pattern-based suggestions
    if tag_lower.startswith('rating:'):
        return 'meta'

    if tag_lower.startswith('rating-source:'):
        return 'meta'

    if any(x in tag_lower for x in ['_(copyright)', '_(series)', '_(game)', '_(anime)']):
        return 'copyright'

    if any(x in tag_lower for x in ['_(character)', '_(cosplay)']):
        return 'character'

    if any(x in tag_lower for x in ['artist:', 'by_']):
        return 'artist'

    # Species indicators
    species_keywords = ['anthro', 'feral', 'humanoid', 'taur']
    if any(keyword in tag_lower for keyword in species_keywords):
        return 'species'

    # Check co-occurrence with categorized tags
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Find tags that frequently appear with this tag
        cur.execute("""
            SELECT t2.category, COUNT(*) as cooccurrence
            FROM image_tags it1
            JOIN image_tags it2 ON it1.image_id = it2.image_id
            JOIN tags t1 ON it1.tag_id = t1.id
            JOIN tags t2 ON it2.tag_id = t2.id
            WHERE t1.name = ?
              AND t2.category IS NOT NULL
              AND t2.id != t1.id
            GROUP BY t2.category
            ORDER BY cooccurrence DESC
            LIMIT 1
        """, (tag_name,))

        row = cur.fetchone()
        if row:
            return row['category']

    # Default to general
    return 'general'


def get_tag_details(tag_name: str) -> Dict:
    """
    Get detailed information about a tag.

    Args:
        tag_name: Name of the tag

    Returns:
        Dict with tag details
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Get tag info
        cur.execute("""
            SELECT t.name, t.category, COUNT(DISTINCT it.image_id) as usage_count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE t.name = ?
            GROUP BY t.name, t.category
        """, (tag_name,))

        row = cur.fetchone()
        if not row:
            raise ValueError(f"Tag '{tag_name}' not found")

        # Get frequently co-occurring tags with categories
        cur.execute("""
            SELECT t2.name, t2.category, COUNT(*) as cooccurrence
            FROM image_tags it1
            JOIN image_tags it2 ON it1.image_id = it2.image_id
            JOIN tags t1 ON it1.tag_id = t1.id
            JOIN tags t2 ON it2.tag_id = t2.id
            WHERE t1.name = ?
              AND t2.category IS NOT NULL
              AND t2.id != t1.id
            GROUP BY t2.name, t2.category
            ORDER BY cooccurrence DESC
            LIMIT 10
        """, (tag_name,))

        cooccurring_tags = [
            {
                'name': r['name'],
                'category': r['category'],
                'cooccurrence': r['cooccurrence']
            }
            for r in cur.fetchall()
        ]

        return {
            'name': row['name'],
            'category': row['category'],
            'usage_count': row['usage_count'],
            'suggested_category': suggest_category_for_tag(tag_name),
            'cooccurring_tags': cooccurring_tags
        }


def export_tag_categorizations(categorized_only: bool = False) -> Dict:
    """
    Export tag categorizations to a dictionary suitable for JSON serialization.

    Args:
        categorized_only: If True, only export tags that have extended categories

    Returns:
        Dict with export metadata and tag categorizations
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        if categorized_only:
            cur.execute("""
                SELECT name, extended_category
                FROM tags
                WHERE extended_category IS NOT NULL
                ORDER BY name
            """)
        else:
            cur.execute("""
                SELECT name, extended_category
                FROM tags
                ORDER BY name
            """)

        tags = {}
        for row in cur.fetchall():
            tags[row['name']] = row['extended_category']

        from datetime import datetime
        return {
            'export_version': '1.0',
            'export_date': datetime.utcnow().isoformat(),
            'tag_count': len(tags),
            'categorized_only': categorized_only,
            'categories': TAG_CATEGORIES,
            'tags': tags
        }


def import_tag_categorizations(data: Dict, mode: str = 'merge') -> Dict:
    """
    Import tag categorizations from exported data.

    Args:
        data: Exported categorization data
        mode: Import mode - 'merge' (keep existing), 'overwrite' (replace all), or 'update' (only update existing)

    Returns:
        Dict with import statistics
    """
    if not data or 'tags' not in data:
        raise ValueError("Invalid import data: missing 'tags' field")

    tags_data = data['tags']
    stats = {
        'total': len(tags_data),
        'updated': 0,
        'skipped': 0,
        'errors': []
    }

    with get_db_connection() as conn:
        cur = conn.cursor()

        for tag_name, category in tags_data.items():
            # Validate category
            if category is not None and category not in TAG_CATEGORIES:
                stats['errors'].append(f"{tag_name}: Invalid category '{category}'")
                stats['skipped'] += 1
                continue

            try:
                # Check if tag exists
                cur.execute("SELECT extended_category FROM tags WHERE name = ?", (tag_name,))
                row = cur.fetchone()

                if not row:
                    stats['errors'].append(f"{tag_name}: Tag not found in database")
                    stats['skipped'] += 1
                    continue

                existing_category = row['extended_category']

                # Apply import mode logic
                if mode == 'merge' and existing_category is not None:
                    # Keep existing categorization
                    stats['skipped'] += 1
                    continue
                elif mode == 'update' and existing_category is None:
                    # Only update already categorized tags
                    stats['skipped'] += 1
                    continue

                # Update the tag
                cur.execute(
                    "UPDATE tags SET extended_category = ? WHERE name = ?",
                    (category, tag_name)
                )
                stats['updated'] += 1

            except Exception as e:
                stats['errors'].append(f"{tag_name}: {str(e)}")
                stats['skipped'] += 1

        conn.commit()

    return stats

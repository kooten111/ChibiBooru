"""
Tag categorization service for manually categorizing uncategorized tags.

This service provides functionality to manage and categorize tags that don't
have a category assigned, showing them by frequency for efficient categorization.
"""

from database import get_db_connection
from typing import List, Dict, Optional, Tuple


# Extended tag categories based on extended category system (22 categories)
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

# Mapping from extended categories to base categories
# This determines which base category a tag should have based on its extended category
EXTENDED_TO_BASE_CATEGORY_MAP = {
    # Meta categories - these contain metadata tags
    '19_Meta_Attributes': 'meta',
    '20_Meta_Text': 'meta',

    # All other extended categories default to 'general'
    # Character, artist, copyright, and species tags should be manually set or detected separately
}

def get_base_category_from_extended(extended_category: str) -> str:
    """
    Get the base category for a tag based on its extended category.

    Args:
        extended_category: The extended category key (e.g., '19_Meta_Attributes')

    Returns:
        The base category ('character', 'copyright', 'artist', 'species', 'general', or 'meta')
    """
    return EXTENDED_TO_BASE_CATEGORY_MAP.get(extended_category, 'general')


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
        # Only include 'general' and 'meta' tags - character, artist, copyright, and species
        # tags don't need extended categories
        cur.execute("""
            SELECT
                t.id,
                t.name,
                t.category,
                t.extended_category,
                COUNT(DISTINCT it.image_id) as usage_count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE t.extended_category IS NULL
            AND t.category IN ('general', 'meta')
            GROUP BY t.id, t.name, t.category, t.extended_category

            ORDER BY usage_count DESC
            LIMIT ?
        """, (limit,))

        tag_rows = cur.fetchall()

        if not tag_rows:
            return []

        # Build tag results
        tags = []
        tag_id_to_index = {}

        for idx, row in enumerate(tag_rows):
            tag_id_to_index[row['id']] = idx
            tags.append({
                'name': row['name'],
                'usage_count': row['usage_count'],
                'sample_images': [],
                'current_category': row['category']
            })

        # Batch fetch sample images for all tags at once (much faster than individual queries)
        # Using a subquery to get 3 random images per tag
        tag_ids = [row['id'] for row in tag_rows]
        placeholders = ','.join('?' for _ in tag_ids)

        # Get sample images in a single query
        # Use a window function to limit to 3 per tag
        cur.execute(f"""
            SELECT tag_id, filepath
            FROM (
                SELECT
                    it.tag_id,
                    i.filepath,
                    ROW_NUMBER() OVER (PARTITION BY it.tag_id ORDER BY i.id) as rn
                FROM image_tags it
                JOIN images i ON it.image_id = i.id
                WHERE it.tag_id IN ({placeholders})
            )
            WHERE rn <= 3
        """, tag_ids)

        # Distribute sample images to their respective tags
        for row in cur.fetchall():
            tag_id = row['tag_id']
            if tag_id in tag_id_to_index:
                idx = tag_id_to_index[tag_id]
                tags[idx]['sample_images'].append(row['filepath'])

        return tags


def get_categorization_stats(include_meaningful: bool = True) -> Dict:
    """
    Get statistics about tag categorization status.

    Args:
        include_meaningful: If True, include stats for tags actually used in images (slower).
                          If False, only include basic tag counts (faster).

    Returns:
        Dict with categorization stats
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # Fast basic stats - only count tags table (no expensive joins)
        cur.execute("""
            SELECT
                COUNT(*) as total_tags,
                SUM(CASE WHEN extended_category IS NULL AND category IN ('general', 'meta') THEN 1 ELSE 0 END) as extended_uncategorized,
                SUM(CASE WHEN extended_category IS NOT NULL OR category NOT IN ('general', 'meta') THEN 1 ELSE 0 END) as extended_categorized
            FROM tags
        """)

        stats_row = cur.fetchone()

        meaningful_categorized = 0
        meaningful_uncategorized = 0

        if include_meaningful:
            # Count "meaningful" tags (tags that are actually used in images)
            # Use INNER JOIN with GROUP BY on the tags side - this leverages the tag_id index
            # and avoids the expensive DISTINCT operation in a subquery
            cur.execute("""
                SELECT
                    SUM(CASE
                        WHEN t.extended_category IS NOT NULL OR t.category NOT IN ('general', 'meta')
                        THEN 1 ELSE 0
                    END) as meaningful_categorized,
                    SUM(CASE
                        WHEN t.extended_category IS NULL AND t.category IN ('general', 'meta')
                        THEN 1 ELSE 0
                    END) as meaningful_uncategorized
                FROM (
                    SELECT DISTINCT tag_id FROM image_tags
                ) it
                INNER JOIN tags t ON it.tag_id = t.id
            """)

            meaningful_row = cur.fetchone()
            meaningful_categorized = meaningful_row['meaningful_categorized'] or 0
            meaningful_uncategorized = meaningful_row['meaningful_uncategorized'] or 0

        # Get tags by extended category (simple aggregation - no joins needed)
        cur.execute("""
            SELECT extended_category, COUNT(*) as count
            FROM tags
            WHERE extended_category IS NOT NULL
            GROUP BY extended_category
            ORDER BY count DESC
        """)
        by_extended_category = {row['extended_category']: row['count'] for row in cur.fetchall()}

        return {
            'total_tags': stats_row['total_tags'],
            'categorized': stats_row['extended_categorized'],
            'uncategorized': stats_row['extended_uncategorized'],
            'meaningful_uncategorized': meaningful_uncategorized,
            'meaningful_categorized': meaningful_categorized,
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

        # Get old extended category and current base category
        cur.execute("SELECT extended_category, category FROM tags WHERE name = ?", (tag_name,))
        row = cur.fetchone()
        old_category = row['extended_category'] if row else None

        if not row:
            raise ValueError(f"Tag '{tag_name}' not found")

        # Determine the base category from extended category
        base_category = get_base_category_from_extended(category) if category else row['category']

        # Only update base category if it's currently 'general' or 'meta'
        # Don't override character, artist, copyright, or species tags
        current_base = row['category']
        if current_base in ['general', 'meta']:
            # Update both extended and base category
            cur.execute(
                "UPDATE tags SET extended_category = ?, category = ? WHERE name = ?",
                (category, base_category, tag_name)
            )
        else:
            # Keep existing base category, only update extended category
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
            # Only export extended categories for general and meta tags
            # Artist/character/copyright/species tags don't need extended categories
            cur.execute("""
                SELECT name, category, extended_category
                FROM tags
                WHERE extended_category IS NOT NULL
                AND category IN ('general', 'meta')
                ORDER BY name
            """)
        else:
            cur.execute("""
                SELECT name, category, extended_category
                FROM tags
                WHERE category IN ('general', 'meta')
                ORDER BY name
            """)

        tags = {}
        for row in cur.fetchall():
            # Only export extended category if tag is general or meta
            if row['category'] in ('general', 'meta'):
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
                cur.execute("SELECT extended_category, category FROM tags WHERE name = ?", (tag_name,))
                row = cur.fetchone()

                if not row:
                    # Tag doesn't exist - skip it
                    # New tags should only be created when images are imported from sources
                    # that provide the correct base category (character, artist, etc.)
                    stats['skipped'] += 1
                    continue

                existing_category = row['extended_category']
                existing_base_category = row['category']

                # Don't apply extended categories to character/artist/copyright/species tags
                # These are already fully categorized by their base category
                if existing_base_category in ('character', 'artist', 'copyright', 'species'):
                    stats['skipped'] += 1
                    continue

                # Apply import mode logic
                if mode == 'merge' and existing_category is not None:
                    # Keep existing categorization
                    stats['skipped'] += 1
                    continue
                elif mode == 'update' and existing_category is None:
                    # Only update already categorized tags
                    stats['skipped'] += 1
                    continue

                # Update the tag with proper base category mapping
                # Get current base category
                cur.execute("SELECT category FROM tags WHERE name = ?", (tag_name,))
                current_base = cur.fetchone()['category']

                # Determine new base category from extended category
                base_category = get_base_category_from_extended(category) if category else current_base

                # Only update base category if it's currently 'general' or 'meta'
                # Don't override character, artist, copyright, or species tags
                if current_base in ['general', 'meta']:
                    cur.execute(
                        "UPDATE tags SET extended_category = ?, category = ? WHERE name = ?",
                        (category, base_category, tag_name)
                    )
                else:
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


def sync_base_categories_from_extended() -> Dict:
    """
    Update all tags' base categories based on their extended categories.
    This only affects tags with base category 'general' or 'meta'.
    Character, artist, copyright, and species tags are not modified.

    Also cleans up extended_category from artist/character/copyright/species tags
    since they don't need extended categorization.

    Returns:
        Dict with statistics about the update
    """
    with get_db_connection() as conn:
        cur = conn.cursor()

        # First, clean up extended_category from artist/character/copyright/species tags
        cur.execute("""
            UPDATE tags
            SET extended_category = NULL
            WHERE category IN ('artist', 'character', 'copyright', 'species')
            AND extended_category IS NOT NULL
        """)
        cleaned = cur.rowcount

        # Get all tags with extended categories (only general and meta now)
        cur.execute("""
            SELECT id, name, category, extended_category
            FROM tags
            WHERE extended_category IS NOT NULL
            AND category IN ('general', 'meta')
        """)

        tags = cur.fetchall()
        updated = 0

        for tag in tags:
            tag_id = tag['id']
            current_base = tag['category']
            extended_cat = tag['extended_category']

            # Get the correct base category from extended category
            new_base = get_base_category_from_extended(extended_cat)

            # Only update if it changed
            if new_base != current_base:
                cur.execute(
                    "UPDATE tags SET category = ? WHERE id = ?",
                    (new_base, tag_id)
                )
                updated += 1

        conn.commit()

        return {
            'total_checked': len(tags),
            'updated': updated,
            'unchanged': len(tags) - updated,
            'cleaned': cleaned
        }

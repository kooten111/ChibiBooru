"""
Centralized tag extraction utilities.
All tag extraction from booru sources should use these functions.
"""

from typing import Dict, Tuple, Optional, List

# Standard tag categories used throughout the application
TAG_CATEGORIES = ['character', 'copyright', 'artist', 'species', 'meta', 'general']

# Mapping from category names to database column names
TAG_COLUMN_MAP = {
    'character': 'tags_character',
    'copyright': 'tags_copyright',
    'artist': 'tags_artist',
    'species': 'tags_species',
    'meta': 'tags_meta',
    'general': 'tags_general'
}

# Rating constants
RATING_CATEGORY = 'rating'
RATING_TAGS = ['rating:general', 'rating:sensitive', 'rating:questionable', 'rating:explicit']
RATING_MAP = {
    'g': 'rating:general',
    's': 'rating:sensitive',
    'q': 'rating:questionable',
    'e': 'rating:explicit'
}


def extract_tags_from_source(source_data: dict, source_name: str) -> dict:
    """
    Extract categorized tags from any booru source data.

    This is THE SINGLE SOURCE OF TRUTH for tag extraction.
    All services should use this function instead of inline extraction.

    Args:
        source_data: Raw metadata dict from the booru source
        source_name: Name of the source ('danbooru', 'e621', 'pixiv', 'local_tagger', etc.)

    Returns:
        dict with keys: tags_character, tags_copyright, tags_artist,
                       tags_species, tags_meta, tags_general
        All values are space-separated strings.
    """
    if source_name == 'danbooru':
        return _extract_danbooru_tags(source_data)
    elif source_name == 'e621':
        return _extract_e621_tags(source_data)
    elif source_name in ['local_tagger', 'camie_tagger']:
        return _extract_local_tagger_tags(source_data)
    elif source_name == 'pixiv':
        return _extract_pixiv_tags(source_data)
    elif source_name in ['gelbooru', 'yandere']:
        return _extract_gelbooru_tags(source_data)
    else:
        # Unknown source - try generic extraction
        return _extract_generic_tags(source_data)


def _extract_danbooru_tags(source_data: dict) -> dict:
    """Extract tags from Danbooru format."""
    return {
        'tags_character': source_data.get("tag_string_character", ""),
        'tags_copyright': source_data.get("tag_string_copyright", ""),
        'tags_artist': source_data.get("tag_string_artist", ""),
        'tags_species': "",  # Danbooru doesn't have species
        'tags_meta': source_data.get("tag_string_meta", ""),
        'tags_general': source_data.get("tag_string_general", ""),
    }


def _extract_e621_tags(source_data: dict) -> dict:
    """Extract tags from e621 format."""
    tags = source_data.get("tags", {})
    return {
        'tags_character': " ".join(tags.get("character", [])),
        'tags_copyright': " ".join(tags.get("copyright", [])),
        'tags_artist': " ".join(tags.get("artist", [])),
        'tags_species': " ".join(tags.get("species", [])),
        'tags_meta': " ".join(tags.get("meta", [])),
        'tags_general': " ".join(tags.get("general", [])),
    }


def _extract_local_tagger_tags(source_data: dict) -> dict:
    """Extract tags from local tagger format (same as e621)."""
    return _extract_e621_tags(source_data)


def _extract_pixiv_tags(source_data: dict) -> dict:
    """Extract tags from Pixiv format."""
    return _extract_e621_tags(source_data)


def _extract_gelbooru_tags(source_data: dict) -> dict:
    """Extract tags from Gelbooru/Yandere format (tags only, no categories)."""
    all_tags = source_data.get("tags", "")
    if isinstance(all_tags, list):
        all_tags = " ".join(all_tags)

    return {
        'tags_character': "",
        'tags_copyright': "",
        'tags_artist': "",
        'tags_species': "",
        'tags_meta': "",
        'tags_general': all_tags,
    }


def _extract_generic_tags(source_data: dict) -> dict:
    """Fallback extraction for unknown sources."""
    # Try e621-style first
    if "tags" in source_data and isinstance(source_data["tags"], dict):
        return _extract_e621_tags(source_data)

    # Try danbooru-style
    if "tag_string_general" in source_data:
        return _extract_danbooru_tags(source_data)

    # Give up - return empty
    return {f'tags_{cat}': '' for cat in TAG_CATEGORIES}


def extract_rating_from_source(source_data: dict, source_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract rating information from source data.

    Args:
        source_data: Raw metadata dict
        source_name: Name of the source

    Returns:
        tuple: (rating_tag, rating_source) or (None, None)
        rating_tag is like 'rating:general', 'rating:explicit', etc.
        rating_source is 'original' or 'ai_inference'
    """
    rating_char = source_data.get('rating', '').lower()
    rating_tag = RATING_MAP.get(rating_char)

    if not rating_tag:
        return None, None

    # Determine trust level
    if source_name in ['danbooru', 'e621']:
        rating_source = 'original'
    elif source_name in ['local_tagger', 'camie_tagger']:
        rating_source = 'ai_inference'
    else:
        rating_source = 'original'

    return rating_tag, rating_source


def merge_tag_sources(primary_tags: dict, secondary_tags: dict,
                      merge_categories: List[str] = None) -> dict:
    """
    Merge tags from two sources, with primary taking precedence.

    Args:
        primary_tags: Tags from primary source (takes precedence)
        secondary_tags: Tags from secondary source (fills gaps)
        merge_categories: List of categories to merge (default: all except artist)

    Returns:
        Merged categorized tags dict
    """
    if merge_categories is None:
        merge_categories = ['character', 'copyright', 'species', 'meta', 'general']

    merged = dict(primary_tags)

    for category in merge_categories:
        key = f'tags_{category}'
        primary_set = set(primary_tags.get(key, '').split())
        secondary_set = set(secondary_tags.get(key, '').split())

        # Add secondary tags that aren't in primary
        combined = primary_set | secondary_set
        merged[key] = ' '.join(sorted(combined))

    return merged


def deduplicate_categorized_tags(categorized_tags: dict) -> dict:
    """
    Remove duplicate tags across categories.

    Tags in specific categories (character, copyright, artist, species, meta)
    are removed from the general category if they appear there.

    Args:
        categorized_tags: Dict with keys like 'tags_general', 'tags_character', etc.

    Returns:
        Deduplicated categorized tags dict
    """
    sets = {}
    for cat in TAG_CATEGORIES:
        key = f'tags_{cat}'
        tags_str = categorized_tags.get(key, '') or ''
        sets[cat] = set(tag.strip() for tag in tags_str.split() if tag.strip())

    # Remove from general anything that's in other categories
    non_general = (
        sets['character'] |
        sets['copyright'] |
        sets['artist'] |
        sets['meta'] |
        sets['species']
    )
    sets['general'] -= non_general

    # Rebuild the dict
    return {f'tags_{cat}': ' '.join(sorted(s)) for cat, s in sets.items()}


def is_rating_tag(tag_name: str) -> bool:
    """Check if a tag is a rating tag."""
    return tag_name in RATING_TAGS or tag_name.startswith('rating:')


def get_tag_category(tag_name: str, default: str = 'general') -> str:
    """
    Determine the correct category for a tag.

    Handles special cases like rating tags.
    """
    if is_rating_tag(tag_name):
        return RATING_CATEGORY
    return default

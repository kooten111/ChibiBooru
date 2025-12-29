"""
Tag Implication Service
Handles automatic pattern detection and suggestion generation for tag implications.
"""
import re
from database import get_db_connection
from typing import List, Dict, Tuple, Set
from repositories.tag_repository import apply_implications_for_image


class ImplicationSuggestion:
    """Represents a suggested tag implication."""
    def __init__(self, source_tag: str, implied_tag: str, confidence: float,
                 pattern_type: str, reason: str, affected_images: int = 0,
                 sample_size: int = 0,
                 source_category: str = 'general', implied_category: str = 'general'):
        self.source_tag = source_tag
        self.implied_tag = implied_tag
        self.confidence = confidence
        self.pattern_type = pattern_type
        self.reason = reason
        self.affected_images = affected_images
        self.sample_size = sample_size
        self.source_category = source_category
        self.implied_category = implied_category

    def to_dict(self):
        return {
            'source_tag': self.source_tag,
            'implied_tag': self.implied_tag,
            'confidence': self.confidence,
            'pattern_type': self.pattern_type,
            'reason': self.reason,
            'affected_images': self.affected_images,
            'sample_size': self.sample_size,
            'source_category': self.source_category,
            'implied_category': self.implied_category
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
                            affected_images=char_count - co_occurrence,  # Images that will gain the tag
                            sample_size=co_occurrence,  # How many images have both tags (for statistical significance)
                            source_category='character',
                            implied_category=corr_category
                        ))

    return suggestions


def get_all_suggestions() -> Dict[str, List[Dict]]:
    """
    Get all auto-detected implication suggestions grouped by pattern type.
    Uses caching to avoid re-running expensive queries.
    """
    suggestions = _get_cached_suggestions()
    
    naming = [s for s in suggestions if s.get('pattern_type') == 'naming_pattern']
    correlation = [s for s in suggestions if s.get('pattern_type') == 'correlation']
    
    return {
        'naming': naming,
        'correlation': correlation,
        'summary': {
            'total': len(suggestions),
            'naming_count': len(naming),
            'correlation_count': len(correlation)
        }
    }


# Cache for suggestions to avoid expensive re-computation
_suggestion_cache = {
    'suggestions': None,
    'timestamp': 0
}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached_suggestions() -> List[Dict]:
    """Get suggestions from cache or regenerate if stale."""
    import time
    
    current_time = time.time()
    if (_suggestion_cache['suggestions'] is not None and 
        current_time - _suggestion_cache['timestamp'] < _CACHE_TTL_SECONDS):
        return _suggestion_cache['suggestions']
    
    # Regenerate suggestions
    naming_suggestions = detect_substring_implications()
    correlation_suggestions = detect_tag_correlations(min_confidence=0.85, min_co_occurrence=3)
    
    all_suggestions = (
        [s.to_dict() for s in naming_suggestions] +
        [s.to_dict() for s in correlation_suggestions]
    )
    
    _suggestion_cache['suggestions'] = all_suggestions
    _suggestion_cache['timestamp'] = current_time
    
    return all_suggestions


def invalidate_suggestion_cache():
    """Clear the suggestion cache (call after approving/rejecting suggestions)."""
    _suggestion_cache['suggestions'] = None
    _suggestion_cache['timestamp'] = 0


def get_paginated_suggestions(page: int = 1, limit: int = 50, 
                               pattern_type: str = None,
                               source_categories: List[str] = None,
                               implied_categories: List[str] = None) -> Dict:
    """
    Get paginated suggestions with optional filtering.
    
    Args:
        page: Page number (1-indexed)
        limit: Items per page
        pattern_type: Optional filter ('naming_pattern' or 'correlation')
        source_categories: List of categories to include/exclude
        implied_categories: List of categories to include/exclude
    
    Returns:
        Dict with paginated results and metadata
    """
    all_suggestions = _get_cached_suggestions()
    
    # Apply filters
    filtered_suggestions = _filter_suggestions(
        all_suggestions, 
        pattern_type, 
        source_categories, 
        implied_categories
    )
    
    total = len(filtered_suggestions)
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    
    # Calculate slice indices
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    
    # Get the slice
    page_suggestions = filtered_suggestions[start_idx:end_idx]
    
    # Count by type for the full dataset (unfiltered counts usually desired for badges, 
    # but here we might want filtered counts? Let's keep total available counts for now)
    # actually, usually UI badges want "total available" not "current view"
    naming_count = sum(1 for s in _get_cached_suggestions() if s.get('pattern_type') == 'naming_pattern')
    correlation_count = sum(1 for s in _get_cached_suggestions() if s.get('pattern_type') == 'correlation')
    
    return {
        'suggestions': page_suggestions,
        'page': page,
        'limit': limit,
        'total': total,
        'total_pages': total_pages,
        'has_more': page < total_pages,
        'summary': {
            'total': len(_get_cached_suggestions()),
            'naming_count': naming_count,
            'correlation_count': correlation_count
        }
    }


def _filter_suggestions(suggestions: List[Dict], pattern_type: str = None,
                        source_categories: List[str] = None,
                        implied_categories: List[str] = None) -> List[Dict]:
    """Helper to filter detailed suggestions list."""
    filtered = suggestions
    
    # Pattern type filter
    if pattern_type and pattern_type != 'all':
        filtered = [s for s in filtered if s.get('pattern_type') == pattern_type]
        
    # Source category filter
    if source_categories and 'all' not in source_categories:
        # Separate inclusions and exclusions
        exclusions = [c[1:] for c in source_categories if c.startswith('!')]
        inclusions = [c for c in source_categories if not c.startswith('!')]
        
        filtered = [
            s for s in filtered
            if (not inclusions or s.get('source_category', 'general') in inclusions)
            and (not exclusions or s.get('source_category', 'general') not in exclusions)
        ]
        
    # Implied category filter
    if implied_categories and 'all' not in implied_categories:
        # Separate inclusions and exclusions
        exclusions = [c[1:] for c in implied_categories if c.startswith('!')]
        inclusions = [c for c in implied_categories if not c.startswith('!')]
        
        filtered = [
            s for s in filtered
            if (not inclusions or s.get('implied_category', 'general') in inclusions)
            and (not exclusions or s.get('implied_category', 'general') not in exclusions)
        ]
        
    return filtered


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

            if apply_implications_for_image(image_id):
                count += 1

    return count


def apply_single_implication_to_images(source_tag: str, implied_tag: str) -> int:
    """
    Apply a single implication rule to all images that have the source tag.
    This is called when a new rule is approved with apply_now=True.
    
    Returns count of images where the implied tag was added.
    """
    count = 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get images that have the source tag but not the implied tag
        cursor.execute("""
            SELECT DISTINCT it.image_id
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE t.name = ?
            AND it.image_id NOT IN (
                SELECT it2.image_id
                FROM image_tags it2
                JOIN tags t2 ON it2.tag_id = t2.id
                WHERE t2.name = ?
            )
        """, (source_tag, implied_tag))
        
        images_to_update = cursor.fetchall()
        
        # Get the implied tag ID
        cursor.execute("SELECT id, category FROM tags WHERE name = ?", (implied_tag,))
        implied_tag_result = cursor.fetchone()
        
        if not implied_tag_result:
            return 0
        
        implied_tag_id = implied_tag_result['id']
        
        # Add the implied tag to each image
        for img_row in images_to_update:
            image_id = img_row['image_id']
            
            # Insert with source='implication' to track that this was added via implications
            cursor.execute("""
                INSERT OR IGNORE INTO image_tags (image_id, tag_id, source)
                VALUES (?, ?, 'implication')
            """, (image_id, implied_tag_id))
            
            if cursor.rowcount > 0:
                count += 1
        
        conn.commit()
    
    return count


def clear_and_reapply_all_implications() -> dict:
    """
    Clear all implied tags (source='implication') and reapply all active implications.
    This is a debug operation that ensures consistency.
    Uses a single database connection for efficiency.
    
    Returns dict with counts of tags cleared and images updated.
    """
    from services import monitor_service
    
    monitor_service.add_log("Starting implication reapplication...", "info")
    
    cleared_count = 0
    tags_added = 0
    rules_count = 0
    images_updated = 0
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Phase 1: Clear existing implied tags
        cursor.execute("SELECT COUNT(*) as count FROM image_tags WHERE source = 'implication'")
        cleared_count = cursor.fetchone()['count']
        
        monitor_service.add_log(f"Clearing {cleared_count} existing implied tags...", "info")
        cursor.execute("DELETE FROM image_tags WHERE source = 'implication'")
        conn.commit()
        
        # Phase 2: Load all implication rules into memory (source_tag -> [implied_tags])
        cursor.execute("""
            SELECT t_source.name as source_tag, t_implied.name as implied_tag, t_implied.id as implied_tag_id
            FROM tag_implications ti
            JOIN tags t_source ON ti.source_tag_id = t_source.id
            JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
            WHERE ti.status = 'active'
        """)
        
        implication_rules = {}
        tag_name_to_id = {}
        for row in cursor.fetchall():
            source = row['source_tag']
            implied = row['implied_tag']
            implied_id = row['implied_tag_id']
            if source not in implication_rules:
                implication_rules[source] = []
            implication_rules[source].append(implied)
            tag_name_to_id[implied] = implied_id
        
        rules_count = len(implication_rules)
        monitor_service.add_log(f"Loaded {rules_count} implication rules...", "info")
        
        # Phase 3: Get all images with their tags
        cursor.execute("SELECT id FROM images")
        image_ids = [row['id'] for row in cursor.fetchall()]
        
        monitor_service.add_log(f"Applying rules to {len(image_ids)} images...", "info")
        
        # Phase 4: Apply implications to each image using cached rules
        for image_id in image_ids:
            # Get current tags for this image
            cursor.execute("""
                SELECT t.name FROM tags t 
                JOIN image_tags it ON t.id = it.tag_id 
                WHERE it.image_id = ?
            """, (image_id,))
            current_tags = {row['name'] for row in cursor.fetchall()}
            
            # Calculate implied tags (handling chains)
            tags_to_add = set()
            tags_to_check = set(current_tags)
            checked = set()
            
            while tags_to_check:
                tag = tags_to_check.pop()
                if tag in checked:
                    continue
                checked.add(tag)
                
                if tag in implication_rules:
                    for implied in implication_rules[tag]:
                        if implied not in current_tags and implied not in tags_to_add:
                            tags_to_add.add(implied)
                            tags_to_check.add(implied)  # Check for chained implications
            
            # Add implied tags
            if tags_to_add:
                images_updated += 1
                for tag_name in tags_to_add:
                    tag_id = tag_name_to_id.get(tag_name)
                    if tag_id:
                        cursor.execute("""
                            INSERT OR IGNORE INTO image_tags (image_id, tag_id, source) 
                            VALUES (?, ?, 'implication')
                        """, (image_id, tag_id))
                        tags_added += 1
        
        conn.commit()
    
    monitor_service.add_log(f"✓ {rules_count} rules applied, {tags_added} tags added to {images_updated} images", "success")
    
    return {
        'cleared_tags': cleared_count,
        'rules_applied': rules_count,
        'tags_added': tags_added,
        'images_updated': images_updated,
        'message': f'Cleared {cleared_count} implied tags, applied {rules_count} rules, added {tags_added} tags to {images_updated} images'
    }


def clear_implied_tags() -> int:
    """
    Clear ALL tags that were added via implications (source='implication').
    This does NOT reapply them. It is a debug/cleanup operation.
    
    Returns count of tags removed.
    """
    from services import monitor_service
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as count FROM image_tags WHERE source = 'implication'")
        count = cursor.fetchone()['count']
        
        if count > 0:
            monitor_service.add_log(f"Clearing {count} implied tags...", "warning")
            cursor.execute("DELETE FROM image_tags WHERE source = 'implication'")
            conn.commit()
            monitor_service.add_log(f"✓ Cleared {count} implied tags", "success")
            
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


def get_implications_for_tag(tag_name: str) -> Dict:
    """
    Get all implications related to a specific tag (tag-centric view).
    Returns implications where this tag is the source OR target, plus suggestions.
    """
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
        
        # Get implications where this tag is the source (what it implies)
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
        
        # Get implications where this tag is the target (what implies it)
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


def auto_approve_naming_pattern_suggestions() -> Dict:
    """
    Auto-approve all naming pattern suggestions.
    These are character_(copyright) → copyright patterns with high reliability.
    
    Returns:
        Dict with success count and any errors
    """
    suggestions = _get_cached_suggestions()
    
    # Filter to only naming pattern suggestions
    naming_suggestions = [s for s in suggestions if s.get('pattern_type') == 'naming_pattern']
    
    success_count = 0
    errors = []
    
    for suggestion in naming_suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        confidence = suggestion.get('confidence', 0.92)
        
        if not source_tag or not implied_tag:
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, 'naming_pattern', confidence)
            if success:
                success_count += 1
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    # Invalidate cache after bulk operation
    invalidate_suggestion_cache()
    
    return {
        'success_count': success_count,
        'total': len(naming_suggestions),
        'errors': errors,
        'pattern_type': 'naming_pattern'
    }


def auto_approve_high_confidence_suggestions(min_confidence: float = 0.95, 
                                              min_sample_size: int = 10,
                                              source_categories: List[str] = None,
                                              implied_categories: List[str] = None,
                                              apply_now: bool = False) -> Dict:
    """
    Auto-approve correlation suggestions that meet confidence and sample size thresholds.
    This ensures statistical significance before auto-approving.
    
    Args:
        min_confidence: Minimum confidence threshold (default 95%)
        min_sample_size: Minimum number of affected images for statistical significance
        source_categories: Optional list of source categories to filter by (supports ! prefix for exclusion)
        implied_categories: Optional list of implied categories to filter by (supports ! prefix for exclusion)
        apply_now: If True, apply the implications to existing images after approval
    
    Returns:
        Dict with success count and any errors
    """
    suggestions = _get_cached_suggestions()
    
    # Apply category filters if provided
    if source_categories or implied_categories:
        suggestions = _filter_suggestions(
            suggestions, 
            pattern_type=None,
            source_categories=source_categories,
            implied_categories=implied_categories
        )
    
    # Filter to correlation suggestions meeting thresholds
    # Note: sample_size is co-occurrence count (how many images have both tags)
    # This is what determines statistical significance, not affected_images
    eligible_suggestions = [
        s for s in suggestions 
        if s.get('pattern_type') == 'correlation'
        and s.get('confidence', 0) >= min_confidence
        and s.get('sample_size', s.get('affected_images', 0)) >= min_sample_size
    ]
    
    success_count = 0
    errors = []
    tags_applied = 0
    
    for suggestion in eligible_suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        confidence = suggestion.get('confidence', min_confidence)
        
        if not source_tag or not implied_tag:
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, 'correlation', confidence)
            if success:
                success_count += 1
                # Apply to images if requested
                if apply_now:
                    tags_applied += apply_single_implication_to_images(source_tag, implied_tag)
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    # Invalidate cache after bulk operation
    invalidate_suggestion_cache()
    
    return {
        'success_count': success_count,
        'total': len(eligible_suggestions),
        'errors': errors,
        'tags_applied': tags_applied,
        'pattern_type': 'correlation',
        'thresholds': {
            'min_confidence': min_confidence,
            'min_sample_size': min_sample_size
        }
    }


def bulk_approve_implications(suggestions: List[Dict]) -> Dict:
    """
    Approve multiple suggestions at once.
    
    Args:
        suggestions: List of dicts with 'source_tag', 'implied_tag', 'inference_type', 'confidence'
    
    Returns:
        Dict with success count and any errors
    """
    success_count = 0
    errors = []
    
    for suggestion in suggestions:
        source_tag = suggestion.get('source_tag')
        implied_tag = suggestion.get('implied_tag')
        inference_type = suggestion.get('inference_type', 'manual')
        confidence = suggestion.get('confidence', 1.0)
        
        if not source_tag or not implied_tag:
            errors.append(f"Missing source_tag or implied_tag in suggestion")
            continue
        
        try:
            success = approve_suggestion(source_tag, implied_tag, inference_type, confidence)
            if success:
                success_count += 1
            else:
                errors.append(f"Failed to approve {source_tag} → {implied_tag}")
        except Exception as e:
            errors.append(f"Error approving {source_tag} → {implied_tag}: {str(e)}")
    
    return {
        'success_count': success_count,
        'total': len(suggestions),
        'errors': errors
    }

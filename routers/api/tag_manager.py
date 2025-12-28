from quart import request, jsonify
from . import api_blueprint
from database import models, get_db_connection
from utils import api_handler
import json

# Constants
DEFAULT_TAG_CATEGORY = 'general'
SAMPLE_IMAGE_LIMIT = 6

def reload_cache():
    """Reload data cache after modifications. Can be optimized in the future."""
    reload_cache()

@api_blueprint.route('/tags/browse')
@api_handler()
async def browse_tags():
    """Browse tags with advanced filtering and sorting."""
    search = request.args.get('search', '').lower().strip()
    status = request.args.get('status', 'all')
    base_category = request.args.get('base_category', '')
    extended_category = request.args.get('extended_category', '')
    sort = request.args.get('sort', 'count_desc')
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 50))
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Build query based on filters
        # Note: tags table doesn't have a count column, we compute it from image_tags
        query = """
            SELECT t.id, t.name, t.category as base_category, t.extended_category, 
                   COUNT(DISTINCT it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE 1=1
        """
        params = []
        
        # Search filter
        if search:
            query += " AND t.name LIKE ?"
            params.append(f"%{search}%")
        
        # Status filters
        if status == 'uncategorized':
            query += " AND (t.extended_category IS NULL OR t.extended_category = '')"
        elif status == 'needs_extended':
            query += " AND t.category != 'general' AND (t.extended_category IS NULL OR t.extended_category = '')"
        elif status == 'orphaned':
            # Will be filtered after GROUP BY using HAVING
            pass
        elif status == 'low_usage':
            # Will be filtered after GROUP BY using HAVING
            pass
        
        # Base category filter
        if base_category:
            query += " AND t.category = ?"
            params.append(base_category)
        
        # Extended category filter
        if extended_category:
            query += " AND t.extended_category = ?"
            params.append(extended_category)
        
        # Group by tag to compute counts
        query += " GROUP BY t.id, t.name, t.category, t.extended_category"
        
        # HAVING clause for count-based filters
        if status == 'orphaned':
            query += " HAVING count = 0"
        elif status == 'low_usage':
            query += " HAVING count > 0 AND count < 5"
        
        # Sorting
        if sort == 'count_desc':
            query += " ORDER BY count DESC, t.name ASC"
        elif sort == 'count_asc':
            query += " ORDER BY count ASC, t.name ASC"
        elif sort == 'alpha_asc':
            query += " ORDER BY t.name ASC"
        elif sort == 'alpha_desc':
            query += " ORDER BY t.name DESC"
        
        # Get total count first
        count_query = f"SELECT COUNT(*) FROM ({query}) AS filtered"
        cur.execute(count_query, params)
        total = cur.fetchone()[0]
        
        # Add pagination
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(query, params)
        tags = [dict(row) for row in cur.fetchall()]
    
    return {
        'tags': tags,
        'total': total,
        'offset': offset,
        'limit': limit,
        'hasMore': offset + limit < total
    }

@api_blueprint.route('/tags/<tag_name>/detail')
@api_handler()
async def tag_detail(tag_name):
    """Get detailed information about a tag including sample images."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get tag info with computed count
        cur.execute("""
            SELECT t.id, t.name, t.category as base_category, t.extended_category,
                   COUNT(DISTINCT it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE t.name = ?
            GROUP BY t.id, t.name, t.category, t.extended_category
        """, (tag_name,))
        tag = cur.fetchone()
        
        if not tag:
            return {'error': 'Tag not found'}, 404
        
        tag_dict = dict(tag)
        tag_id = tag_dict['id']
        
        # Get sample images (up to limit, using more efficient method than RANDOM)
        # For better performance, we get the first N images ordered by ID
        cur.execute("""
            SELECT i.filepath
            FROM images i
            JOIN image_tags it ON i.id = it.image_id
            WHERE it.tag_id = ?
            ORDER BY i.id DESC
            LIMIT ?
        """, (tag_id, SAMPLE_IMAGE_LIMIT))
        samples = [dict(row) for row in cur.fetchall()]
        
        # Get implications (tags that this tag implies - i.e., this tag is the source)
        cur.execute("""
            SELECT t.name
            FROM tag_implications ti
            JOIN tags t ON ti.implied_tag_id = t.id
            WHERE ti.source_tag_id = ?
        """, (tag_id,))
        children = [row['name'] for row in cur.fetchall()]
        
        # Get implied by (tags that imply this tag - i.e., this tag is the implied)
        cur.execute("""
            SELECT t.name
            FROM tag_implications ti
            JOIN tags t ON ti.source_tag_id = t.id
            WHERE ti.implied_tag_id = ?
        """, (tag_id,))
        parents = [row['name'] for row in cur.fetchall()]
        
        # Get aliases (if any exist in your schema)
        # For now, returning empty list
        aliases = []
        
        return {
            'tag': tag_dict,
            'sample_images': samples,
            'implications': {
                'parents': parents,
                'children': children
            },
            'aliases': aliases
        }

@api_blueprint.route('/tags/rename', methods=['POST'])
@api_handler()
async def rename_tag():
    """Rename a tag."""
    data = await request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    create_alias = data.get('create_alias', False)
    
    if not old_name or not new_name:
        return {'error': 'Both old_name and new_name are required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Check if old tag exists
        cur.execute("SELECT id FROM tags WHERE name = ?", (old_name,))
        old_tag = cur.fetchone()
        if not old_tag:
            return {'error': 'Tag not found'}, 404
        
        # Check if new name already exists
        cur.execute("SELECT id FROM tags WHERE name = ?", (new_name,))
        if cur.fetchone():
            return {'error': 'Tag with new name already exists'}, 400
        
        # Update tag name
        cur.execute("UPDATE tags SET name = ? WHERE name = ?", (new_name, old_name))
        
        # Update implications
        cur.execute("UPDATE tag_implications SET parent_tag = ? WHERE parent_tag = ?", (new_name, old_name))
        cur.execute("UPDATE tag_implications SET child_tag = ? WHERE child_tag = ?", (new_name, old_name))
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Tag renamed from {old_name} to {new_name}'}

@api_blueprint.route('/tags/merge', methods=['POST'])
@api_handler()
async def merge_tags():
    """Merge multiple tags into one target tag."""
    data = await request.get_json()
    source_tags = data.get('source_tags', [])
    target_tag = data.get('target_tag', '').strip()
    create_aliases = data.get('create_aliases', False)
    
    if not source_tags or not target_tag:
        return {'error': 'source_tags and target_tag are required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get target tag ID
        cur.execute("SELECT id, category, extended_category FROM tags WHERE name = ?", (target_tag,))
        target = cur.fetchone()
        if not target:
            return {'error': 'Target tag not found'}, 404
        
        target_id = target['id']
        target_category = target['category']
        target_extended = target['extended_category']
        
        # Process each source tag
        for source_tag in source_tags:
            if source_tag == target_tag:
                continue
            
            cur.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
            source = cur.fetchone()
            if not source:
                continue
            
            source_id = source['id']
            
            # Update image_tags to point to target tag
            # Use INSERT OR IGNORE to avoid duplicates
            cur.execute("""
                INSERT OR IGNORE INTO image_tags (image_id, tag_id)
                SELECT image_id, ?
                FROM image_tags
                WHERE tag_id = ?
            """, (target_id, source_id))
            
            # Delete old image_tag entries
            cur.execute("DELETE FROM image_tags WHERE tag_id = ?", (source_id,))
            
            # Delete the source tag
            cur.execute("DELETE FROM tags WHERE id = ?", (source_id,))
        
        
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Merged {len(source_tags)} tags into {target_tag}'}

@api_blueprint.route('/tags/delete', methods=['POST'])
@api_handler()
async def delete_tags():
    """Delete one or more tags."""
    data = await request.get_json()
    tag_names = data.get('tag_names', [])
    remove_from_images = data.get('remove_from_images', True)
    
    if not tag_names:
        return {'error': 'tag_names is required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        for tag_name in tag_names:
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag = cur.fetchone()
            if not tag:
                continue
            
            tag_id = tag['id']
            
            if remove_from_images:
                # Remove tag from all images
                cur.execute("DELETE FROM image_tags WHERE tag_id = ?", (tag_id,))
            
            # Delete implications
            cur.execute("DELETE FROM tag_implications WHERE parent_tag = ? OR child_tag = ?", (tag_name, tag_name))
            
            # Delete the tag
            cur.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Deleted {len(tag_names)} tag(s)'}

@api_blueprint.route('/tags/bulk_categorize', methods=['POST'])
@api_handler()
async def bulk_categorize():
    """Set category for multiple tags at once."""
    data = await request.get_json()
    tag_names = data.get('tag_names', [])
    base_category = data.get('base_category', '')
    extended_category = data.get('extended_category', '')
    
    if not tag_names:
        return {'error': 'tag_names is required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        for tag_name in tag_names:
            updates = []
            params = []
            
            if base_category:
                updates.append("category = ?")
                params.append(base_category)
            
            if extended_category is not None:  # Allow empty string to clear
                updates.append("extended_category = ?")
                params.append(extended_category)
            
            if updates:
                query = f"UPDATE tags SET {', '.join(updates)} WHERE name = ?"
                params.append(tag_name)
                cur.execute(query, params)
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Updated categories for {len(tag_names)} tag(s)'}

@api_blueprint.route('/tags/stats')
@api_handler()
async def tag_stats():
    """Get comprehensive tag statistics."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Overall stats
        cur.execute("SELECT COUNT(*) as total FROM tags")
        total_tags = cur.fetchone()['total']
        
        cur.execute("SELECT COUNT(*) as count FROM tags WHERE extended_category IS NOT NULL AND extended_category != ''")
        categorized = cur.fetchone()['count']
        
        # Count orphaned tags (tags with no images)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id
            HAVING COUNT(it.image_id) = 0
        """)
        orphaned = len(cur.fetchall())  # Count the number of rows returned
        
        # Count low usage tags (1-4 images)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM (
                SELECT t.id
                FROM tags t
                LEFT JOIN image_tags it ON t.id = it.tag_id
                GROUP BY t.id
                HAVING COUNT(it.image_id) > 0 AND COUNT(it.image_id) < 5
            )
        """)
        low_usage = cur.fetchone()['count']
        
        cur.execute("SELECT COUNT(DISTINCT i.id) as count FROM images i")
        total_images = cur.fetchone()['count']
        
        # Total tag uses (count all image_tags relationships)
        cur.execute("SELECT COUNT(*) as total FROM image_tags")
        total_uses = cur.fetchone()['total'] or 0
        
        avg_tags = total_uses / total_images if total_images > 0 else 0
        
        # Base category breakdown
        cur.execute("""
            SELECT category, COUNT(*) as count
            FROM tags
            GROUP BY category
        """)
        by_base_category = {row['category']: row['count'] for row in cur.fetchall()}
        
        # Extended category coverage
        cur.execute("""
            SELECT extended_category, COUNT(*) as count
            FROM tags
            WHERE extended_category IS NOT NULL AND extended_category != ''
            GROUP BY extended_category
        """)
        by_extended_category = {row['extended_category']: row['count'] for row in cur.fetchall()}
        
        # Top tags
        cur.execute("""
            SELECT t.name, COUNT(DISTINCT it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id, t.name
            ORDER BY count DESC
            LIMIT 10
        """)
        top_by_usage = [dict(row) for row in cur.fetchall()]
        
        # Problem tags
        cur.execute("""
            SELECT t.name, COUNT(DISTINCT it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE (t.extended_category IS NULL OR t.extended_category = '')
            GROUP BY t.id, t.name
            HAVING count > 100
            ORDER BY count DESC
            LIMIT 10
        """)
        uncategorized_high_usage = [dict(row) for row in cur.fetchall()]
        
        cur.execute("""
            SELECT t.name
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id, t.name
            HAVING COUNT(DISTINCT it.image_id) = 0
            LIMIT 20
        """)
        orphaned_tags = [row['name'] for row in cur.fetchall()]
    
    return {
        'overview': {
            'total_tags': total_tags,
            'total_images': total_images,
            'categorized': categorized,
            'uncategorized': total_tags - categorized,
            'categorized_percentage': round(categorized / total_tags * 100, 1) if total_tags > 0 else 0,
            'tag_uses': total_uses,
            'avg_tags_per_image': round(avg_tags, 2),
            'orphaned': orphaned,
            'low_usage': low_usage
        },
        'by_base_category': by_base_category,
        'by_extended_category': by_extended_category,
        'top_tags': top_by_usage,
        'problem_tags': {
            'uncategorized_high_usage': uncategorized_high_usage,
            'orphaned': orphaned_tags
        }
    }

@api_blueprint.route('/images/bulk_add_tags', methods=['POST'])
@api_handler()
async def bulk_add_tags():
    """Add tags to multiple images."""
    data = await request.get_json()
    filepaths = data.get('filepaths', [])
    tags_to_add = data.get('tags', [])
    
    if not filepaths or not tags_to_add:
        return {'error': 'filepaths and tags are required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get or create tags
        tag_ids = {}
        for tag_name in tags_to_add:
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_row = cur.fetchone()
            if tag_row:
                tag_ids[tag_name] = tag_row['id']
            else:
                # Create new tag with default category (no count column in schema)
                cur.execute("INSERT INTO tags (name, category) VALUES (?, ?)", (tag_name, DEFAULT_TAG_CATEGORY))
                tag_ids[tag_name] = cur.lastrowid
        
        # Add tags to images
        for filepath in filepaths:
            cur.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            image = cur.fetchone()
            if not image:
                continue
            
            image_id = image['id']
            
            for tag_name, tag_id in tag_ids.items():
                cur.execute("""
                    INSERT OR IGNORE INTO image_tags (image_id, tag_id)
                    VALUES (?, ?)
                """, (image_id, tag_id))
        
        # Tag counts are computed dynamically, no need to update
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Added {len(tags_to_add)} tag(s) to {len(filepaths)} image(s)'}

@api_blueprint.route('/images/bulk_remove_tags', methods=['POST'])
@api_handler()
async def bulk_remove_tags():
    """Remove tags from multiple images."""
    data = await request.get_json()
    filepaths = data.get('filepaths', [])
    tags_to_remove = data.get('tags', [])
    
    if not filepaths or not tags_to_remove:
        return {'error': 'filepaths and tags are required'}, 400
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get tag IDs
        tag_ids = []
        for tag_name in tags_to_remove:
            cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_row = cur.fetchone()
            if tag_row:
                tag_ids.append(tag_row['id'])
        
        # Remove tags from images
        for filepath in filepaths:
            cur.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            image = cur.fetchone()
            if not image:
                continue
            
            image_id = image['id']
            
            for tag_id in tag_ids:
                cur.execute("""
                    DELETE FROM image_tags
                    WHERE image_id = ? AND tag_id = ?
                """, (image_id, tag_id))
        
        # Tag counts are computed dynamically, no need to update
        
        conn.commit()
        
        # Reload cache
        reload_cache()
    
    return {'success': True, 'message': f'Removed {len(tags_to_remove)} tag(s) from {len(filepaths)} image(s)'}

@api_blueprint.route('/images/common_tags')
@api_handler()
async def get_common_tags():
    """Get tags common to a set of images."""
    filepaths_str = request.args.get('filepaths', '')
    filepaths = [fp.strip() for fp in filepaths_str.split(',') if fp.strip()]
    
    if not filepaths:
        return {'all': [], 'some': []}
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Get image IDs
        placeholders = ','.join(['?' for _ in filepaths])
        cur.execute(f"""
            SELECT id, filepath FROM images
            WHERE filepath IN ({placeholders})
        """, filepaths)
        images = {row['filepath']: row['id'] for row in cur.fetchall()}
        
        if not images:
            return {'all': [], 'some': []}
        
        image_ids = list(images.values())
        total_images = len(image_ids)
        
        # Get tags for all these images
        placeholders = ','.join(['?' for _ in image_ids])
        cur.execute(f"""
            SELECT t.name, COUNT(DISTINCT it.image_id) as image_count
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE it.image_id IN ({placeholders})
            GROUP BY t.id, t.name
        """, image_ids)
        
        tag_counts = {}
        for row in cur.fetchall():
            tag_counts[row['name']] = row['image_count']
        
        # Separate into 'all' and 'some'
        all_tags = [tag for tag, count in tag_counts.items() if count == total_images]
        some_tags = [
            {
                'tag': tag,
                'count': count,
                'percentage': round(count / total_images * 100, 1)
            }
            for tag, count in tag_counts.items()
            if count < total_images
        ]
        
        # Sort 'some' by count descending
        some_tags.sort(key=lambda x: x['count'], reverse=True)
    
    return {
        'all': sorted(all_tags),
        'some': some_tags
    }

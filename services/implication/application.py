"""Apply implications to database images."""

from typing import Dict

from database import get_db_connection
from repositories.tag_repository import apply_implications_for_image
from services import monitor_service


def batch_apply_implications_to_all_images() -> int:
    """Apply all active implications to all existing images."""
    count = 0

    with get_db_connection() as conn:
        cursor = conn.cursor()

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
    Uses a single database connection for efficiency.
    Returns dict with counts of tags cleared and images updated.
    """
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
        
        # Phase 2: Load all implication rules into memory
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
        
        # Phase 4: Apply implications to each image
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
                            tags_to_check.add(implied)
            
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
    """Clear ALL tags that were added via implications (source='implication')."""
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

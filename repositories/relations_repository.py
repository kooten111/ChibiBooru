"""
Repository for image relations (duplicates, parent/child, siblings, non-duplicates).

Ordering convention:
- parent_child: image_id_a = parent, image_id_b = child (directional)
- sibling, non_duplicate: (min(id), max(id)) for consistency
"""

from database import get_db_connection
from typing import List, Dict, Optional, Set, Tuple


def _normalize_pair(id_a: int, id_b: int, relation_type: str = '') -> Tuple[int, int]:
    """
    Ensure consistent ordering for a pair.
    
    For 'parent_child': id_a = parent, id_b = child (preserves direction).
    For all other types: lower id first.
    """
    if relation_type == 'parent_child':
        return (id_a, id_b)
    return (min(id_a, id_b), max(id_a, id_b))


def add_relation(id_a: int, id_b: int, relation_type: str, source: str = 'manual') -> bool:
    """
    Add a relation between two images.
    
    Args:
        id_a: First image ID
        id_b: Second image ID
        relation_type: One of 'non_duplicate', 'parent_child', 'sibling'
        source: Origin of the relation ('manual', 'ingested', 'duplicate_review')
    
    Returns:
        True if inserted, False if already exists
    """
    norm_a, norm_b = _normalize_pair(id_a, id_b, relation_type)
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO image_relations (image_id_a, image_id_b, relation_type, source)
                VALUES (?, ?, ?, ?)
            """, (norm_a, norm_b, relation_type, source))
            conn.commit()
            return True
        except Exception:
            # Unique constraint violation — already exists
            return False


def bulk_add_relations(relations: List[Dict]) -> Tuple[int, int]:
    """
    Add multiple relations in a single transaction.
    
    Args:
        relations: List of dicts with keys: image_id_a, image_id_b, relation_type, source
    
    Returns:
        Tuple of (success_count, skip_count)
    """
    success = 0
    skipped = 0
    with get_db_connection() as conn:
        cur = conn.cursor()
        for rel in relations:
            rtype = rel['relation_type']
            norm_a, norm_b = _normalize_pair(rel['image_id_a'], rel['image_id_b'], rtype)
            try:
                cur.execute("""
                    INSERT INTO image_relations (image_id_a, image_id_b, relation_type, source)
                    VALUES (?, ?, ?, ?)
                """, (norm_a, norm_b, rtype, rel.get('source', 'manual')))
                success += 1
            except Exception:
                skipped += 1
        conn.commit()
    return success, skipped


def has_any_relation(id_a: int, id_b: int) -> bool:
    """Check if any relation exists between two images (checks both orderings)."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM image_relations
            WHERE (image_id_a = ? AND image_id_b = ?)
               OR (image_id_a = ? AND image_id_b = ?)
            LIMIT 1
        """, (id_a, id_b, id_b, id_a))
        return cur.fetchone() is not None


def get_all_reviewed_pairs() -> Set[Tuple[int, int]]:
    """Return all reviewed pairs as (min_id, max_id) tuples for duplicate queue filtering."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT image_id_a, image_id_b FROM image_relations")
        pairs = set()
        for row in cur.fetchall():
            # Always add the min/max normalized form so duplicate_pairs filtering works
            a, b = row['image_id_a'], row['image_id_b']
            pairs.add((min(a, b), max(a, b)))
        return pairs


def get_relations_for_image(image_id: int) -> List[Dict]:
    """Get all relations involving a specific image (checks both column positions)."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ir.*, 
                   ia.filepath as filepath_a, 
                   ib.filepath as filepath_b
            FROM image_relations ir
            JOIN images ia ON ia.id = ir.image_id_a
            JOIN images ib ON ib.id = ir.image_id_b
            WHERE ir.image_id_a = ? OR ir.image_id_b = ?
            ORDER BY ir.created_at DESC
        """, (image_id, image_id))
        return [dict(row) for row in cur.fetchall()]


def delete_relation(id_a: int, id_b: int, relation_type: Optional[str] = None) -> bool:
    """
    Delete a relation between two images.
    If relation_type is None, deletes all relations between the pair.
    Checks both orderings for parent_child relations.
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        if relation_type:
            cur.execute("""
                DELETE FROM image_relations
                WHERE ((image_id_a = ? AND image_id_b = ?)
                    OR (image_id_a = ? AND image_id_b = ?))
                  AND relation_type = ?
            """, (id_a, id_b, id_b, id_a, relation_type))
        else:
            cur.execute("""
                DELETE FROM image_relations
                WHERE (image_id_a = ? AND image_id_b = ?)
                   OR (image_id_a = ? AND image_id_b = ?)
            """, (id_a, id_b, id_b, id_a))
        conn.commit()
        return cur.rowcount > 0


def get_related_images_from_relations(image_id: int) -> List[Dict]:
    """
    Get parent/child/sibling images for an image from the image_relations table.
    
    For parent_child: image_id_a is always the parent, image_id_b the child.
    
    Returns:
        List of dicts with keys: path, type ('parent', 'child', 'sibling')
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ir.image_id_a, ir.image_id_b, ir.relation_type,
                   ia.filepath as filepath_a,
                   ib.filepath as filepath_b
            FROM image_relations ir
            JOIN images ia ON ia.id = ir.image_id_a
            JOIN images ib ON ib.id = ir.image_id_b
            WHERE (ir.image_id_a = ? OR ir.image_id_b = ?)
              AND ir.relation_type IN ('parent_child', 'sibling')
            ORDER BY ir.relation_type, ir.created_at
        """, (image_id, image_id))
        
        results = []
        for row in cur.fetchall():
            rtype = row['relation_type']
            if rtype == 'parent_child':
                if row['image_id_b'] == image_id:
                    # This image is the child → the other is the parent
                    results.append({
                        'path': f"images/{row['filepath_a']}",
                        'type': 'parent'
                    })
                else:
                    # This image is the parent → the other is the child
                    results.append({
                        'path': f"images/{row['filepath_b']}",
                        'type': 'child'
                    })
            elif rtype == 'sibling':
                other_fp = row['filepath_b'] if row['image_id_a'] == image_id else row['filepath_a']
                results.append({
                    'path': f"images/{other_fp}",
                    'type': 'sibling'
                })
        
        return results


def create_relations_on_ingest(new_image_id: int, parent_id: int = None, post_id: int = None) -> Dict:
    """
    Automatically create image_relations entries when ingesting a new image.
    
    Resolves booru parent_id/post_id to local image IDs and creates
    parent_child and sibling relations.
    
    Args:
        new_image_id: The newly ingested image's database ID
        parent_id: Booru parent post ID (from source metadata)
        post_id: Booru post ID of the new image
    
    Returns:
        Dict with counts: parent_found, children_found, siblings_created
    """
    stats = {'parent_found': 0, 'children_found': 0, 'siblings_created': 0}
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # 1. If this image has a parent_id, find the parent locally
        if parent_id:
            cur.execute("SELECT id FROM images WHERE post_id = ? AND id != ?", (parent_id, new_image_id))
            parent_row = cur.fetchone()
            if parent_row:
                parent_local_id = parent_row['id']
                added = add_relation(parent_local_id, new_image_id, 'parent_child', 'ingested')
                if added:
                    stats['parent_found'] = 1
                
                # Find existing children of this parent to create sibling relations
                existing_children = cur.execute("""
                    SELECT image_id_b FROM image_relations
                    WHERE image_id_a = ? AND relation_type = 'parent_child'
                      AND image_id_b != ?
                """, (parent_local_id, new_image_id)).fetchall()
                
                for child_row in existing_children:
                    sibling_id = child_row['image_id_b']
                    if add_relation(new_image_id, sibling_id, 'sibling', 'ingested'):
                        stats['siblings_created'] += 1
        
        # 2. If this image has a post_id, check if other images reference it as parent
        if post_id:
            cur.execute("SELECT id FROM images WHERE parent_id = ? AND id != ?", (post_id, new_image_id))
            children = cur.fetchall()
            for child_row in children:
                child_id = child_row['id']
                if add_relation(new_image_id, child_id, 'parent_child', 'ingested'):
                    stats['children_found'] += 1
    
    return stats

"""
Repository for image relations (duplicates, parent/child, siblings, non-duplicates).

Ordering convention:
- parent_child: image_id_a = parent, image_id_b = child (directional)
- sibling, non_duplicate: (min(id), max(id)) for consistency
"""

import sqlite3
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


def get_relation_for_image(relation_id: int, image_id: int) -> Optional[Dict]:
    """Get a single relation involving a specific image."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ir.*,
                   ia.filepath as filepath_a,
                   ib.filepath as filepath_b
            FROM image_relations ir
            JOIN images ia ON ia.id = ir.image_id_a
            JOIN images ib ON ib.id = ir.image_id_b
            WHERE ir.id = ?
              AND (ir.image_id_a = ? OR ir.image_id_b = ?)
            LIMIT 1
        """, (relation_id, image_id, image_id))
        row = cur.fetchone()
        return dict(row) if row else None


def get_image_by_id(image_id: int) -> Optional[Dict]:
    """Get minimal image metadata by local image ID."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, filepath
            FROM images
            WHERE id = ?
            LIMIT 1
        """, (image_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_editable_relations_for_image(image_id: int) -> List[Dict]:
    """Get relations formatted for editing from the perspective of one image."""
    relations = [
        relation for relation in get_relations_for_image(image_id)
        if relation['relation_type'] in {'parent_child', 'sibling'}
    ]
    editable = []

    for relation in relations:
        if relation['relation_type'] == 'parent_child':
            if relation['image_id_a'] == image_id:
                other_image_id = relation['image_id_b']
                other_filepath = relation['filepath_b']
                display_type = 'child'
            else:
                other_image_id = relation['image_id_a']
                other_filepath = relation['filepath_a']
                display_type = 'parent'
        else:
            other_image_id = relation['image_id_b'] if relation['image_id_a'] == image_id else relation['image_id_a']
            other_filepath = relation['filepath_b'] if relation['image_id_a'] == image_id else relation['filepath_a']
            display_type = relation['relation_type']

        editable.append({
            'id': relation['id'],
            'source': relation['source'],
            'created_at': relation['created_at'],
            'relation_type': relation['relation_type'],
            'display_type': display_type,
            'other_image_id': other_image_id,
            'other_filepath': other_filepath,
        })

    return editable


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


def delete_relation_by_id(relation_id: int) -> Optional[Dict]:
    """Delete a relation by ID and return the deleted row metadata if found."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ir.id, ir.image_id_a, ir.image_id_b, ir.relation_type,
                   ia.filepath as filepath_a,
                   ib.filepath as filepath_b
            FROM image_relations ir
            JOIN images ia ON ia.id = ir.image_id_a
            JOIN images ib ON ib.id = ir.image_id_b
            WHERE ir.id = ?
            LIMIT 1
        """, (relation_id,))
        row = cur.fetchone()
        if not row:
            return None

        cur.execute("DELETE FROM image_relations WHERE id = ?", (relation_id,))
        conn.commit()
        return dict(row)


def _manual_parent_child_exists(parent_id: int, child_id: int, exclude_relation_id: Optional[int] = None) -> bool:
    """Check whether a specific parent -> child edge already exists."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        if exclude_relation_id is None:
            cur.execute("""
                SELECT 1
                FROM image_relations
                WHERE relation_type = 'parent_child'
                  AND image_id_a = ?
                  AND image_id_b = ?
                LIMIT 1
            """, (parent_id, child_id))
        else:
            cur.execute("""
                SELECT 1
                FROM image_relations
                WHERE relation_type = 'parent_child'
                  AND image_id_a = ?
                  AND image_id_b = ?
                  AND id != ?
                LIMIT 1
            """, (parent_id, child_id, exclude_relation_id))
        return cur.fetchone() is not None


def _manual_parent_child_would_create_cycle(
    parent_id: int,
    child_id: int,
    exclude_relation_id: Optional[int] = None,
) -> bool:
    """Check if adding parent -> child would create a cycle in the current graph."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        params = [child_id]
        exclude_filter_root = ""
        exclude_filter_recursive = ""
        if exclude_relation_id is not None:
            exclude_filter_root = "AND id != ?"
            exclude_filter_recursive = "AND ir.id != ?"
            params.append(exclude_relation_id)
            params.append(exclude_relation_id)
        params.append(parent_id)

        cur.execute(f"""
            WITH RECURSIVE descendants(id) AS (
                SELECT image_id_b
                FROM image_relations
                WHERE relation_type = 'parent_child'
                  AND image_id_a = ?
                  {exclude_filter_root}
                UNION
                SELECT ir.image_id_b
                FROM image_relations ir
                JOIN descendants d ON ir.image_id_a = d.id
                WHERE ir.relation_type = 'parent_child'
                  {exclude_filter_recursive}
            )
            SELECT 1
            FROM descendants
            WHERE id = ?
            LIMIT 1
        """, params)
        return cur.fetchone() is not None


def validate_manual_parent_child(
    parent_id: int,
    child_id: int,
    exclude_relation_id: Optional[int] = None,
) -> None:
    """Validate a manual parent -> child mutation against graph rules."""
    if parent_id == child_id:
        raise ValueError("An image cannot be its own parent")

    parent_image = get_image_by_id(parent_id)
    child_image = get_image_by_id(child_id)
    if not parent_image or not child_image:
        raise ValueError("One or both image IDs do not exist")

    if _manual_parent_child_exists(parent_id, child_id, exclude_relation_id=exclude_relation_id):
        raise ValueError("That parent/child relation already exists")

    if _manual_parent_child_exists(child_id, parent_id, exclude_relation_id=exclude_relation_id):
        raise ValueError("Cannot set both images as parent of each other")

    if _manual_parent_child_would_create_cycle(parent_id, child_id, exclude_relation_id=exclude_relation_id):
        raise ValueError("That parent/child relation would create a cycle")


def _validate_manual_relation_target(image_id: int, other_image_id: int) -> None:
    """Shared validation for manual relation writes."""
    if image_id == other_image_id:
        raise ValueError("An image cannot have a relation to itself")

    if not get_image_by_id(image_id) or not get_image_by_id(other_image_id):
        raise ValueError("One or both image IDs do not exist")


def create_manual_relation(image_id: int, other_image_id: int, display_type: str) -> Dict:
    """Create a manual relation from the perspective of one image."""
    _validate_manual_relation_target(image_id, other_image_id)

    if display_type == 'parent':
        parent_id, child_id = other_image_id, image_id
        validate_manual_parent_child(parent_id, child_id)
        added = add_relation(parent_id, child_id, 'parent_child', 'manual')
    elif display_type == 'child':
        parent_id, child_id = image_id, other_image_id
        validate_manual_parent_child(parent_id, child_id)
        added = add_relation(parent_id, child_id, 'parent_child', 'manual')
    elif display_type == 'sibling':
        added = add_relation(image_id, other_image_id, 'sibling', 'manual')
    else:
        raise ValueError("display_type must be one of: parent, child, sibling")

    if not added:
        raise ValueError("That relation already exists")

    relation = get_latest_relation_between(image_id, other_image_id)
    if not relation:
        raise ValueError("Relation was created but could not be loaded")
    return relation


def update_manual_relation(relation_id: int, image_id: int, other_image_id: int, display_type: str) -> Dict:
    """Update a relation and mark the result as manual."""
    existing = get_relation_for_image(relation_id, image_id)
    if not existing:
        raise ValueError("Relation not found")

    _validate_manual_relation_target(image_id, other_image_id)

    new_relation_type = 'parent_child' if display_type in {'parent', 'child'} else 'sibling' if display_type == 'sibling' else None
    if not new_relation_type:
        raise ValueError("display_type must be one of: parent, child, sibling")

    if display_type == 'parent':
        new_a, new_b = other_image_id, image_id
        validate_manual_parent_child(new_a, new_b, exclude_relation_id=relation_id)
    elif display_type == 'child':
        new_a, new_b = image_id, other_image_id
        validate_manual_parent_child(new_a, new_b, exclude_relation_id=relation_id)
    else:
        new_a, new_b = _normalize_pair(image_id, other_image_id, 'sibling')

    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE image_relations
                SET image_id_a = ?, image_id_b = ?, relation_type = ?, source = 'manual'
                WHERE id = ?
            """, (new_a, new_b, new_relation_type, relation_id))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError("That relation already exists") from exc

    updated = get_relation_for_image(relation_id, image_id)
    if not updated:
        raise ValueError("Updated relation could not be loaded")
    return updated


def get_latest_relation_between(image_id: int, other_image_id: int) -> Optional[Dict]:
    """Load the latest relation between two images for refresh after mutation."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT ir.*,
                   ia.filepath as filepath_a,
                   ib.filepath as filepath_b
            FROM image_relations ir
            JOIN images ia ON ia.id = ir.image_id_a
            JOIN images ib ON ib.id = ir.image_id_b
            WHERE (ir.image_id_a = ? AND ir.image_id_b = ?)
               OR (ir.image_id_a = ? AND ir.image_id_b = ?)
            ORDER BY ir.created_at DESC, ir.id DESC
            LIMIT 1
        """, (image_id, other_image_id, other_image_id, image_id))
        row = cur.fetchone()
        return dict(row) if row else None


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

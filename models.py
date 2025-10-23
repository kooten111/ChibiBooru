# models.py
import threading
import os
import json
import sqlite3
from tqdm import tqdm
from database import get_db_connection

# --- In-memory Caches ---
tag_counts = {}
image_data = []
post_id_to_md5 = {}
data_lock = threading.Lock()


def md5_exists(md5):
    """Check if an MD5 hash already exists in the images table."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM images WHERE md5 = ?", (md5,))
        return cursor.fetchone() is not None
        
def load_data_from_db():
    """Load or reload data from the database into the in-memory caches."""
    global tag_counts, image_data, post_id_to_md5
    print("Loading data from database...")
    with data_lock:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='images';")
            if cursor.fetchone() is None:
                print("Warning: Database tables not found. Skipping data load.")
                tag_counts = {}
                image_data = []
                post_id_to_md5 = {}
                return False

            tag_counts_query = "SELECT name, COUNT(image_id) FROM tags JOIN image_tags ON tags.id = image_tags.tag_id GROUP BY name"
            tag_counts = {row['name']: row['COUNT(image_id)'] for row in conn.execute(tag_counts_query).fetchall()}

            image_data_query = """
            SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            GROUP BY i.id
            """
            image_data = [dict(row) for row in conn.execute(image_data_query).fetchall()]

            # Build post_id → MD5 mapping for ALL sources
            print("Building cross-source post_id index...")
            post_id_to_md5 = {}
            cursor.execute("""
                SELECT i.md5, rm.data 
                FROM images i 
                JOIN raw_metadata rm ON i.id = rm.image_id 
                WHERE rm.data IS NOT NULL
            """)
            for row in cursor.fetchall():
                try:
                    metadata = json.loads(row['data'])
                    md5 = row['md5']
                    for source, data in metadata.get('sources', {}).items():
                        if source in ['danbooru', 'e621', 'gelbooru', 'yandere']:
                            post_id = data.get('id')
                            if post_id:
                                post_id_to_md5[post_id] = md5
                except:
                    continue

    print(f"Loaded {len(image_data)} images, {len(tag_counts)} unique tags, {len(post_id_to_md5)} cross-source post_ids.")
    return True

# --- Cache Access Functions ---
def get_tag_counts():
    with data_lock:
        return tag_counts

def get_image_data():
    with data_lock:
        return image_data

def get_all_tags_sorted():
    """Get all tags with their counts, sorted alphabetically by name."""
    with get_db_connection() as conn:
        query = """
        SELECT t.name, t.category, COUNT(it.image_id) as count
        FROM tags t
        LEFT JOIN image_tags it ON t.id = it.tag_id
        GROUP BY t.id
        ORDER BY t.name ASC
        """
        return [dict(row) for row in conn.execute(query).fetchall()]

def recategorize_misplaced_tags():
    """
    Check all general tags and move them to correct categories if they exist 
    as categorized tags elsewhere in the database.
    """
    print("Recategorizing misplaced tags...")
    
    # Build lookup from all known categorized tags
    known_categorized = {
        'artist': set(),
        'copyright': set(),
        'character': set(),
        'species': set(),
        'meta': set()
    }
    
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Build lookup from existing categorized tags
        for category in known_categorized.keys():
            cur.execute("SELECT DISTINCT name FROM tags WHERE category = ?", (category,))
            known_categorized[category].update(row['name'] for row in cur.fetchall())
        
        # Find all general tags that should be recategorized
        cur.execute("SELECT DISTINCT name FROM tags WHERE category = 'general'")
        general_tags = [row['name'] for row in cur.fetchall()]
        
        changes = 0
        for tag_name in tqdm(general_tags, desc="Checking tags"):
            for category, tag_set in known_categorized.items():
                if tag_name in tag_set:
                    # Found a match - update this tag's category
                    cur.execute("UPDATE tags SET category = ? WHERE name = ? AND category = 'general'", 
                               (category, tag_name))
                    changes += 1
                    break
        
        conn.commit()
    
    print(f"Recategorized {changes} tags")
    return changes

def rebuild_categorized_tags_from_relations():
    """
    Back-fills the categorized tag columns in the 'images' table based on
    the existing data in the 'image_tags' and 'tags' tables.
    This is a data migration step.
    """
    print("Rebuilding categorized tag columns...")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get all images
        cursor.execute("SELECT id FROM images")
        images = cursor.fetchall()
        
        updated_count = 0
        for image_row in tqdm(images, desc="Updating Images"):
            image_id = image_row['id']
            
            # Fetch all tags for this image, grouped by category
            query = """
            SELECT category, GROUP_CONCAT(name, ' ') as tags
            FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE it.image_id = ?
            GROUP BY t.category
            """
            cursor.execute(query, (image_id,))
            
            categorized_tags = {row['category']: row['tags'] for row in cursor.fetchall()}
            
            # Update the images table
            update_query = """
            UPDATE images SET
                tags_character = ?,
                tags_copyright = ?,
                tags_artist = ?,
                tags_species = ?,
                tags_meta = ?,
                tags_general = ?
            WHERE id = ?
            """
            cursor.execute(update_query, (
                categorized_tags.get('character'),
                categorized_tags.get('copyright'),
                categorized_tags.get('artist'),
                categorized_tags.get('species'),
                categorized_tags.get('meta'),
                categorized_tags.get('general'),
                image_id
            ))
            updated_count += 1
            
        conn.commit()
    
    print(f"Successfully updated categorized tags for {updated_count} images.")
    return updated_count

def repopulate_from_database():
    """Rebuilds the tag and source relationships by reading from the raw_metadata table."""
    # Import config here to ensure it's loaded within the application context
    import config

    print("Repopulating database from 'raw_metadata' table...")
    with get_db_connection() as con:
        cur = con.cursor()

        # Clear existing tag and source relationships
        cur.execute("DELETE FROM image_tags")
        cur.execute("DELETE FROM image_sources")
        cur.execute("DELETE FROM tags")
        cur.execute("DELETE FROM sources")

        source_map = {}
        known_sources = ["danbooru", "e621", "gelbooru", "yandere", "local_tagger"]
        for source_name in known_sources:
            cur.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (source_name,))
            cur.execute("SELECT id FROM sources WHERE name = ?", (source_name,))
            source_map[source_name] = cur.fetchone()[0]

        # Get all raw metadata
        cur.execute("SELECT image_id, data FROM raw_metadata")
        all_metadata = cur.fetchall()

        for row in tqdm(all_metadata, desc="Rebuilding from DB Metadata"):
            image_id = row['image_id']
            try:
                metadata = json.loads(row['data'])
            except (json.JSONDecodeError, TypeError):
                continue

            primary_source_data = None
            source_name = None
            available_sources = metadata.get('sources', {})

            # *** CORRECTED LOGIC: Use BOORU_PRIORITY from config ***
            for src in config.BOORU_PRIORITY:
                if src in available_sources:
                    primary_source_data = available_sources[src]
                    source_name = src
                    break
            
            # Fallback if no priority source is found
            if not source_name and available_sources:
                source_name = next(iter(available_sources.keys()), None)
                primary_source_data = next(iter(available_sources.values()), {})


            if not primary_source_data:
                continue

            parent_id = primary_source_data.get('parent_id')
            if source_name == 'e621':
                parent_id = primary_source_data.get('relationships', {}).get('parent_id')

            cur.execute("""
                UPDATE images
                SET post_id = ?, parent_id = ?, has_children = ?, active_source = ?
                WHERE id = ?
            """, (
                primary_source_data.get("id"),
                parent_id,
                primary_source_data.get("has_children", False),
                source_name,
                image_id
            ))

            for src in metadata.get('sources', {}).keys():
                if src in source_map:
                    cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_map[src]))

            categorized_tags = {}
            if source_name == 'danbooru':
                categorized_tags = {
                    'character': primary_source_data.get("tag_string_character", "").split(),
                    'copyright': primary_source_data.get("tag_string_copyright", "").split(),
                    'artist': primary_source_data.get("tag_string_artist", "").split(),
                    'meta': primary_source_data.get("tag_string_meta", "").split(),
                    'general': primary_source_data.get("tag_string_general", "").split(),
                }
            elif source_name == 'e621':
                tags = primary_source_data.get("tags", {})
                categorized_tags = {
                    'character': tags.get("character", []), 'copyright': tags.get("copyright", []),
                    'artist': tags.get("artist", []), 'species': tags.get("species", []),
                    'meta': tags.get("meta", []), 'general': tags.get("general", [])
                }
            elif source_name == 'local_tagger' or source_name == 'camie_tagger':
                tags = primary_source_data.get("tags", {})
                categorized_tags = {
                    'character': tags.get("character", []),
                    'copyright': tags.get("copyright", []),
                    'artist': tags.get("artist", []),
                    'meta': tags.get("meta", []),
                    'general': tags.get("general", [])
                }

            for category, tags_list in categorized_tags.items():
                for tag_name in tags_list:
                    if not tag_name: continue
                    cur.execute("INSERT INTO tags (name, category) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET category=excluded.category", (tag_name, category))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cur.fetchone()['id']
                    cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
        con.commit()

    print("Repopulation complete.")
    recategorize_misplaced_tags()
    rebuild_categorized_tags_from_relations()
    print("Database rebuild complete.")
    
# --- Direct Database Query Functions ---

def get_image_count():
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(id) FROM images").fetchone()[0]

def get_avg_tags_per_image():
    with get_db_connection() as conn:
        result = conn.execute("SELECT AVG(tag_count) FROM (SELECT COUNT(tag_id) as tag_count FROM image_tags GROUP BY image_id)").fetchone()
        return round(result[0], 1) if result and result[0] is not None else 0

def get_source_breakdown():
    query = """
    SELECT s.name, COUNT(ims.image_id)
    FROM sources s
    JOIN image_sources ims ON s.id = ims.source_id
    GROUP BY s.name
    """
    with get_db_connection() as conn:
        return {row['name']: row['COUNT(ims.image_id)'] for row in conn.execute(query).fetchall()}

def get_category_counts():
    query = "SELECT category, COUNT(id) FROM tags WHERE category IS NOT NULL GROUP BY category"
    with get_db_connection() as conn:
        return {row['category']: row['COUNT(id)'] for row in conn.execute(query).fetchall()}

def get_saucenao_lookup_count():
    with get_db_connection() as conn:
        return conn.execute("SELECT COUNT(id) FROM images WHERE saucenao_lookup = 1").fetchone()[0]

def get_all_images_with_tags():
    with get_db_connection() as conn:
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        GROUP BY i.id
        """
        return [dict(row) for row in conn.execute(query).fetchall()]

def get_all_filepaths():
    """Returns a set of all filepaths in the database."""
    with get_db_connection() as conn:
        return {row['filepath'] for row in conn.execute("SELECT filepath FROM images").fetchall()}

def get_related_images(post_id, parent_id):
    """Find parent and child images using pre-computed cross-source mapping."""
    related = []
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Find parent using the mapping
        if parent_id and parent_id in post_id_to_md5:
            parent_md5 = post_id_to_md5[parent_id]
            parent = cursor.execute("SELECT filepath FROM images WHERE md5 = ?", (parent_md5,)).fetchone()
            if parent:
                related.append({
                    "path": f"images/{parent['filepath']}",
                    "type": "parent"
                })
        
        # Find children - check ALL parent_ids from ALL sources in raw metadata
        if post_id:
            current_md5 = post_id_to_md5.get(post_id)
            if current_md5:
                # Get all images with raw metadata
                cursor.execute("""
                    SELECT i.filepath, rm.data 
                    FROM images i 
                    JOIN raw_metadata rm ON i.id = rm.image_id 
                    WHERE rm.data IS NOT NULL
                """)
                
                for row in cursor.fetchall():
                    try:
                        metadata = json.loads(row['data'])
                        # Check parent_id from ALL sources
                        for source, data in metadata.get('sources', {}).items():
                            if source == 'danbooru':
                                check_parent = data.get('parent_id')
                            elif source == 'e621':
                                check_parent = data.get('relationships', {}).get('parent_id')
                            else:
                                check_parent = data.get('parent_id')
                            
                            # If this image's parent matches our MD5, it's our child
                            if check_parent and check_parent in post_id_to_md5:
                                if post_id_to_md5[check_parent] == current_md5:
                                    related.append({
                                        "path": f"images/{row['filepath']}",
                                        "type": "child"
                                    })
                                    break  # Don't add same child twice
                    except:
                        continue
    
    return related

def search_images_by_tags(tags_list):
    with get_db_connection() as conn:
        base_query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        JOIN image_tags it ON i.id = it.image_id
        JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT it_inner.image_id
            FROM image_tags it_inner
            JOIN tags t_inner ON it_inner.tag_id = t_inner.id
            WHERE t_inner.name IN ({placeholders})
            GROUP BY it_inner.image_id
            HAVING COUNT(DISTINCT t_inner.name) = ?
        )
        GROUP BY i.id
        """
        placeholders = ','.join('?' for _ in tags_list)
        query = base_query.format(placeholders=placeholders)
        params = tags_list + [len(tags_list)]
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def search_images_by_source(source_name):
    with get_db_connection() as conn:
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT ims.image_id
            FROM image_sources ims
            JOIN sources s ON ims.source_id = s.id
            WHERE s.name = ?
        )
        GROUP BY i.id
        """
        return [dict(row) for row in conn.execute(query, (source_name,)).fetchall()]

def get_image_details(filepath):
    with get_db_connection() as conn:
        query = """
        SELECT
            i.*,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id) as all_tags,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'character') as tags_character,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'copyright') as tags_copyright,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'artist') as tags_artist,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'species') as tags_species,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'meta') as tags_meta,
            (SELECT GROUP_CONCAT(t.name, ' ') FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = i.id AND t.category = 'general') as tags_general,
            rm.data as raw_metadata
        FROM images i
        LEFT JOIN raw_metadata rm ON i.id = rm.image_id
        WHERE i.filepath = ?
        """
        details = conn.execute(query, (filepath,)).fetchone()
        if not details:
            return None
        
        details_dict = dict(details)
        if details_dict.get('raw_metadata'):
            details_dict['raw_metadata'] = json.loads(details_dict['raw_metadata'])
        
        # If no active_source set but we have metadata, determine it
        if not details_dict.get('active_source') and details_dict.get('raw_metadata'):
            metadata = details_dict['raw_metadata']
            sources = metadata.get('sources', {})
            if 'danbooru' in sources:
                details_dict['active_source'] = 'danbooru'
            elif 'e621' in sources:
                details_dict['active_source'] = 'e621'
            elif sources:
                details_dict['active_source'] = list(sources.keys())[0]
        
        return details_dict

def delete_image(filepath):
    """Delete an image and all its related data from the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM images WHERE filepath = ?", (filepath,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"Database error deleting {filepath}: {e}")
        return False

def update_image_tags(filepath, new_tags_str):
    """Update the tags for a specific image."""
    new_tags = set(tag.strip() for tag in new_tags_str.lower().split())
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            if not result:
                return False
            image_id = result['id']
            
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            
            for tag_name in new_tags:
                if not tag_name: continue
                
                cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, 'general'))
                
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_id_result = cursor.fetchone()
                if not tag_id_result:
                    print(f"Failed to get or create tag_id for: {tag_name}")
                    continue
                tag_id = tag_id_result['id']
                
                cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))
                
            conn.commit()
            return True
    except Exception as e:
        print(f"Database error updating tags for {filepath}: {e}")
        conn.rollback()
        return False

def update_image_tags_categorized(filepath, categorized_tags):
    """Update image tags by category in the database."""
    from database import get_db_connection
    
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    elif filepath.startswith('static/images/'):
        filepath = filepath[14:]
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get image_id
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            if not result:
                print(f"Image not found: {filepath}")
                return False
            
            image_id = result['id']
            
            # Update the categorized tag columns in images table
            cursor.execute("""
                UPDATE images 
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?
                WHERE id = ?
            """, (
                categorized_tags.get('tags_character', ''),
                categorized_tags.get('tags_copyright', ''),
                categorized_tags.get('tags_artist', ''),
                categorized_tags.get('tags_species', ''),
                categorized_tags.get('tags_meta', ''),
                categorized_tags.get('tags_general', ''),
                image_id
            ))
            
            # Delete old image_tags entries
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            
            # Insert new tags for each category
            for category_key, tags_str in categorized_tags.items():
                if not tags_str or not tags_str.strip():
                    continue
                    
                # Remove 'tags_' prefix from category name
                category_name = category_key.replace('tags_', '')
                
                tags = [t.strip() for t in tags_str.split() if t.strip()]
                for tag_name in tags:
                    # Get or create tag with proper category
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_result = cursor.fetchone()
                    
                    if tag_result:
                        tag_id = tag_result['id']
                        # Update category if tag exists
                        cursor.execute("UPDATE tags SET category = ? WHERE id = ?", (category_name, tag_id))
                    else:
                        # Insert new tag with category
                        cursor.execute(
                            "INSERT INTO tags (name, category) VALUES (?, ?)",
                            (tag_name, category_name)
                        )
                        tag_id = cursor.lastrowid
                    
                    # Link tag to image
                    cursor.execute(
                        "INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                        (image_id, tag_id)
                    )
            
            conn.commit()
            print(f"Successfully updated tags for {filepath}")
            return True
            
    except Exception as e:
        print(f"Error updating categorized tags for {filepath}: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.rollback()
        return False
        
def add_image_with_metadata(image_info, source_names, categorized_tags, raw_metadata_dict):
    """
    Adds a new image and all its metadata to the database in a single transaction.
    Returns True on success, False on failure (including duplicate MD5 race condition).
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 1. Insert the image record
            cursor.execute("""
                INSERT INTO images (filepath, md5, post_id, parent_id, has_children, saucenao_lookup)
                VALUES (:filepath, :md5, :post_id, :parent_id, :has_children, :saucenao_lookup)
            """, image_info)
            image_id = cursor.lastrowid

            # 2. Link sources
            for name in source_names:
                cursor.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (name,))
                cursor.execute("SELECT id FROM sources WHERE name = ?", (name,))
                source_id = cursor.fetchone()['id']
                cursor.execute("INSERT INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_id))

            # 3. Insert and link tags
            for category, tags_list in categorized_tags.items():
                for tag_name in tags_list:
                    if not tag_name: continue
                    cursor.execute("""
    INSERT INTO tags (name, category) VALUES (?, ?)
    ON CONFLICT(name) DO UPDATE SET category = excluded.category
""", (tag_name, category))
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cursor.fetchone()['id']
                    cursor.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

            # 4. Insert raw metadata
            cursor.execute(
                "INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)",
                (image_id, json.dumps(raw_metadata_dict))
            )
            # 5. Populate categorized tag columns in images table
            tag_columns = {
                'character': 'tags_character',
                'copyright': 'tags_copyright', 
                'artist': 'tags_artist',
                'species': 'tags_species',
                'meta': 'tags_meta',
                'general': 'tags_general'
            }

            update_values = {}
            for category, tags_list in categorized_tags.items():
                col_name = tag_columns.get(category)
                if col_name:
                    update_values[col_name] = ' '.join(tags_list) if tags_list else None

            cursor.execute("""
                UPDATE images 
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?
                WHERE id = ?
            """, (
                update_values.get('tags_character'),
                update_values.get('tags_copyright'),
                update_values.get('tags_artist'),
                update_values.get('tags_species'),
                update_values.get('tags_meta'),
                update_values.get('tags_general'),
                image_id
            ))

            conn.commit()
            return True
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: images.md5" in str(e):
            print(f"Race condition: MD5 {image_info['md5']} was inserted by another process. Treating as duplicate.")
            return False
        else:
            print(f"Database integrity error adding image {image_info['filepath']}: {e}")
            return False
    except Exception as e:
        print(f"Database error adding image {image_info['filepath']}: {e}")
        return False

def search_images_by_multiple_sources(source_names):
    """
    Search for images that have ALL specified sources (AND logic).
    Returns images only if they exist in every source in source_names list.
    """
    with get_db_connection() as conn:
        # Build a query that requires the image to have ALL sources
        # Using HAVING COUNT(DISTINCT s.name) = number_of_sources ensures AND logic
        query = """
        SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
        FROM images i
        LEFT JOIN image_tags it ON i.id = it.image_id
        LEFT JOIN tags t ON it.tag_id = t.id
        WHERE i.id IN (
            SELECT ims.image_id
            FROM image_sources ims
            JOIN sources s ON ims.source_id = s.id
            WHERE s.name IN ({placeholders})
            GROUP BY ims.image_id
            HAVING COUNT(DISTINCT s.name) = ?
        )
        GROUP BY i.id
        """
        placeholders = ','.join('?' for _ in source_names)
        query = query.format(placeholders=placeholders)
        params = source_names + [len(source_names)]
        return [dict(row) for row in conn.execute(query, params).fetchall()]

def search_images_by_relationship(relationship_type):
    """
    Search for images by relationship type.
    relationship_type: 'parent', 'child', or 'any'
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        matching_filepaths = set()
        
        # Get all images with raw metadata
        cursor.execute("SELECT i.id, i.filepath, rm.data FROM images i LEFT JOIN raw_metadata rm ON i.id = rm.image_id WHERE rm.data IS NOT NULL")
        
        for row in cursor.fetchall():
            try:
                metadata = json.loads(row['data'])
                image_id = row['id']
                filepath = row['filepath']
                
                has_parent = False
                has_child = False
                
                # Extract all post_ids and parent_ids for this image
                post_ids = set()
                parent_ids = set()
                
                for source, data in metadata.get('sources', {}).items():
                    if source == 'danbooru':
                        pid = data.get('id')
                        ppid = data.get('parent_id')
                    elif source == 'e621':
                        pid = data.get('id')
                        ppid = data.get('relationships', {}).get('parent_id')
                    else:
                        pid = data.get('id')
                        ppid = data.get('parent_id')
                    
                    if pid:
                        post_ids.add(pid)
                    if ppid:
                        parent_ids.add(ppid)
                
                # Check if has parent
                if parent_ids:
                    has_parent = True
                
                # Check if has children (are we a parent to anyone?)
                if post_ids and relationship_type in ['child', 'any']:
                    # Quick check: see if any other image references us as parent
                    cursor2 = conn.cursor()
                    cursor2.execute("SELECT rm2.data FROM raw_metadata rm2 WHERE rm2.image_id != ?", (image_id,))
                    for other_row in cursor2.fetchall():
                        try:
                            other_metadata = json.loads(other_row['data'])
                            for other_source, other_data in other_metadata.get('sources', {}).items():
                                if other_source == 'danbooru':
                                    other_parent = other_data.get('parent_id')
                                elif other_source == 'e621':
                                    other_parent = other_data.get('relationships', {}).get('parent_id')
                                else:
                                    other_parent = other_data.get('parent_id')
                                
                                if other_parent and other_parent in post_ids:
                                    has_child = True
                                    break
                            if has_child:
                                break
                        except:
                            continue
                
                # Add to results based on type
                if relationship_type == 'parent' and has_parent:
                    matching_filepaths.add(filepath)
                elif relationship_type == 'child' and has_child:
                    matching_filepaths.add(filepath)
                elif relationship_type == 'any' and (has_parent or has_child):
                    matching_filepaths.add(filepath)
                    
            except:
                continue
        
        # Get full image data with tags
        if matching_filepaths:
            placeholders = ','.join('?' for _ in matching_filepaths)
            query = f"""
            SELECT i.filepath, GROUP_CONCAT(t.name, ' ') as tags
            FROM images i
            LEFT JOIN image_tags it ON i.id = it.image_id
            LEFT JOIN tags t ON it.tag_id = t.id
            WHERE i.filepath IN ({placeholders})
            GROUP BY i.id
            """
            return [dict(row) for row in conn.execute(query, list(matching_filepaths)).fetchall()]
        
        return []

# --- NEW: Pool Management Functions ---

def create_pool(name, description=""):
    """Create a new pool."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO pools (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
        return cursor.lastrowid

def get_all_pools():
    """Get a list of all pools."""
    with get_db_connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM pools ORDER BY name ASC").fetchall()]

def get_pool_details(pool_id):
    """Get details for a single pool and its images."""
    with get_db_connection() as conn:
        pool = conn.execute("SELECT * FROM pools WHERE id = ?", (pool_id,)).fetchone()
        if not pool:
            return None
        
        images_query = """
        SELECT i.filepath, pi.sort_order
        FROM images i
        JOIN pool_images pi ON i.id = pi.image_id
        WHERE pi.pool_id = ?
        ORDER BY pi.sort_order ASC
        """
        images = [dict(row) for row in conn.execute(images_query, (pool_id,)).fetchall()]
        return {"pool": dict(pool), "images": images}

def add_image_to_pool(pool_id, image_id):
    """Add an image to a pool."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get the next sort order
        cursor.execute("SELECT MAX(sort_order) FROM pool_images WHERE pool_id = ?", (pool_id,))
        max_order = cursor.fetchone()[0]
        next_order = (max_order or 0) + 1
        
        cursor.execute("INSERT OR IGNORE INTO pool_images (pool_id, image_id, sort_order) VALUES (?, ?, ?)",
                       (pool_id, image_id, next_order))
        conn.commit()

# --- NEW: Tag Implication Functions ---

def add_implication(source_tag_name, implied_tag_name):
    """Create an implication from a source tag to an implied tag."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get tag IDs
        cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag_name,))
        source_id = cursor.fetchone()
        cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag_name,))
        implied_id = cursor.fetchone()
        
        if source_id and implied_id:
            cursor.execute("INSERT OR IGNORE INTO tag_implications (source_tag_id, implied_tag_id) VALUES (?, ?)",
                           (source_id['id'], implied_id['id']))
            conn.commit()
            return True
        return False

def get_implications_for_tag(tag_name):
    """Get all tags implied by a given source tag."""
    with get_db_connection() as conn:
        query = """
        SELECT t_implied.name
        FROM tags t_source
        JOIN tag_implications ti ON t_source.id = ti.source_tag_id
        JOIN tags t_implied ON ti.implied_tag_id = t_implied.id
        WHERE t_source.name = ?
        """
        return [row['name'] for row in conn.execute(query, (tag_name,)).fetchall()]

def apply_implications_for_image(image_id):
    """Apply all tag implications for a given image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Get all current tags for the image
        cursor.execute("SELECT t.name FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = ?", (image_id,))
        current_tags = {row['name'] for row in cursor.fetchall()}
        
        tags_to_add = set()
        
        # Use a loop to handle chained implications (A->B, B->C)
        newly_added_tags_this_iteration = set(current_tags)
        while newly_added_tags_this_iteration:
            tags_to_check = newly_added_tags_this_iteration
            newly_added_tags_this_iteration = set()
            
            for tag_name in tags_to_check:
                implied_tags = get_implications_for_tag(tag_name)
                for implied_tag in implied_tags:
                    if implied_tag not in current_tags and implied_tag not in tags_to_add:
                        tags_to_add.add(implied_tag)
                        newly_added_tags_this_iteration.add(implied_tag)

        # Add the new tags to the database
        for tag_name in tags_to_add:
            cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, 'general'))
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cursor.fetchone()['id']
            cursor.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

        conn.commit()
        return len(tags_to_add) > 0
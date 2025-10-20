import json
from database import get_db_connection

def extract_tags_from_source(source_data, source_name):
    """Extract tag data from a specific source"""
    if not source_data or not isinstance(source_data, dict):
        return None
    
    tags_dict = {
        "character": "",
        "copyright": "",
        "artist": "",
        "species": "",
        "meta": "",
        "general": ""
    }
    
    all_tags = set()
    parent_id = source_data.get("parent_id")
    if source_name == 'e621':
        parent_id = source_data.get('relationships', {}).get('parent_id')
    has_children = source_data.get("has_children", False)
    post_id = source_data.get("id")
    
    if source_name == "danbooru":
        tags_dict["character"] = source_data.get("tag_string_character", "")
        tags_dict["copyright"] = source_data.get("tag_string_copyright", "")
        tags_dict["artist"] = source_data.get("tag_string_artist", "")
        tags_dict["meta"] = source_data.get("tag_string_meta", "")
        tags_dict["general"] = source_data.get("tag_string_general", "")
        
    elif source_name == "e621":
        tags = source_data.get("tags", {})
        if isinstance(tags, dict):
            tags_dict["character"] = " ".join(tags.get("character", []))
            tags_dict["copyright"] = " ".join(tags.get("copyright", []))
            tags_dict["artist"] = " ".join(tags.get("artist", []))
            tags_dict["species"] = " ".join(tags.get("species", []))
            tags_dict["meta"] = " ".join(tags.get("meta", []))
            tags_dict["general"] = " ".join(tags.get("general", []))
            
    elif source_name == "camie_tagger":
        tags_dict["character"] = source_data.get("tags_character", "")
        tags_dict["copyright"] = source_data.get("tags_copyright", "")
        tags_dict["artist"] = source_data.get("tags_artist", "")
        tags_dict["general"] = source_data.get("tags_general", "")
        
    else:
        # Gelbooru, Yandere, etc - general tags only
        tags_str = source_data.get("tags", "")
        if isinstance(tags_str, list):
            tags_str = " ".join(tags_str)
        tags_dict["general"] = tags_str
    
    # Collect all tags
    for category_tags in tags_dict.values():
        if category_tags:
            all_tags.update(category_tags.split())
    
    return {
        "tags": " ".join(sorted(all_tags)),
        "tags_character": tags_dict["character"],
        "tags_copyright": tags_dict["copyright"],
        "tags_artist": tags_dict["artist"],
        "tags_species": tags_dict["species"],
        "tags_meta": tags_dict["meta"],
        "tags_general": tags_dict["general"],
        "id": post_id,
        "parent_id": parent_id,
        "has_children": has_children,
        "active_source": source_name
    }

def switch_metadata_source_db(filepath, source_name):
    """Switch the active metadata source for an image using database"""
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]  # Remove 'images/' prefix
    elif filepath.startswith('static/images/'):
        filepath = filepath[14:]  # Remove 'static/images/' prefix
    
    with get_db_connection() as conn:
        # Get image data
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.id, i.md5, rm.data as raw_metadata
            FROM images i
            LEFT JOIN raw_metadata rm ON i.id = rm.image_id
            WHERE i.filepath = ?
        """, (filepath,))
        
        result = cursor.fetchone()
        if not result:
            return {"error": "Image not found in database"}
        
        if not result['raw_metadata']:
            return {"error": "No metadata found for this image"}
        
        image_id = result['id']
        metadata = json.loads(result['raw_metadata'])
        
        # Check if source exists in metadata
        if not metadata.get("sources") or source_name not in metadata["sources"]:
            available = list(metadata.get("sources", {}).keys()) if metadata.get("sources") else []
            return {
                "error": f"Source '{source_name}' not found. Available sources: {', '.join(available)}"
            }
        
        # Extract tags from the selected source
        source_data = metadata["sources"][source_name]
        tag_data = extract_tags_from_source(source_data, source_name)
        
        if not tag_data:
            return {"error": f"Could not extract tags from source '{source_name}'"}
        
        # Update database - delete old tags and insert new ones
        try:
            # Delete old image_tags
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            
            # Insert new tags with categories
            tag_categories = {
                "tags_character": "character",
                "tags_copyright": "copyright",
                "tags_artist": "artist",
                "tags_species": "species",
                "tags_meta": "meta",
                "tags_general": "general"
            }
            
            for tag_field, category in tag_categories.items():
                tags_str = tag_data.get(tag_field, "")
                if tags_str:
                    for tag_name in tags_str.split():
                        if not tag_name:
                            continue
                        
                        # Insert or update tag
                        cursor.execute("""
                            INSERT INTO tags (name, category) VALUES (?, ?)
                            ON CONFLICT(name) DO UPDATE SET category = excluded.category
                        """, (tag_name, category))
                        
                        # Get tag ID
                        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                        tag_id = cursor.fetchone()['id']
                        
                        # Link tag to image
                        cursor.execute("""
                            INSERT OR IGNORE INTO image_tags (image_id, tag_id) 
                            VALUES (?, ?)
                        """, (image_id, tag_id))
            
            # *** FIX: Update the cached tag columns in the images table ***
            cursor.execute("""
                UPDATE images 
                SET post_id = ?, parent_id = ?, has_children = ?, active_source = ?,
                    tags_character = ?, tags_copyright = ?, tags_artist = ?, 
                    tags_species = ?, tags_meta = ?, tags_general = ?
                WHERE id = ?
            """, (tag_data.get("id"), tag_data.get("parent_id"), 
                tag_data.get("has_children", False), source_name,
                tag_data.get("tags_character"), tag_data.get("tags_copyright"),
                tag_data.get("tags_artist"), tag_data.get("tags_species"),
                tag_data.get("tags_meta"), tag_data.get("tags_general"),
                image_id))
            
            conn.commit()
            
            return {
                "status": "success",
                "message": f"Switched to {source_name}",
                "source": source_name,
                "tag_count": len(tag_data["tags"].split())
            }
            
        except Exception as e:
            conn.rollback()
            return {"error": f"Database error: {str(e)}"}
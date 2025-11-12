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

    # Extract rating if present (danbooru, e621, etc.)
    rating = None
    rating_source = None
    if 'rating' in source_data:
        rating_char = source_data.get('rating', '').lower()
        # Map single-letter ratings to full tag names
        rating_map = {
            'g': 'rating:general',
            's': 'rating:sensitive',
            'q': 'rating:questionable',
            'e': 'rating:explicit'
        }
        rating = rating_map.get(rating_char)

        # Determine source trust level
        # danbooru and e621 are authoritative (original)
        # local_tagger is 50/50 (treat as ai_inference)
        # others default to original
        if source_name in ['danbooru', 'e621']:
            rating_source = 'original'  # Trusted source
        elif source_name in ['local_tagger', 'camie_tagger']:
            rating_source = 'ai_inference'  # Less trusted
        else:
            rating_source = 'original'  # Default to original for other sources
    
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
            
    elif source_name == "local_tagger" or source_name == "camie_tagger":
        # Handle both old 'camie_tagger' and new 'local_tagger' format
        tags = source_data.get("tags", {})
        if isinstance(tags, dict):
            tags_dict["character"] = " ".join(tags.get("character", []))
            tags_dict["copyright"] = " ".join(tags.get("copyright", []))
            tags_dict["artist"] = " ".join(tags.get("artist", []))
            tags_dict["meta"] = " ".join(tags.get("meta", []))
            tags_dict["general"] = " ".join(tags.get("general", []))
        else:
            # Fallback for old format
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

    result = {
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

    # Add rating information if extracted
    if rating:
        result["rating"] = rating
        result["rating_source"] = rating_source

    return result

def merge_all_sources(filepath):
    """Merge tags from all available sources for an image"""
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]  # Remove 'images/' prefix
    elif filepath.startswith('static/images/'):
        filepath = filepath[14:]  # Remove 'static/images/' prefix

    with get_db_connection() as conn:
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

        if not metadata.get("sources"):
            return {"error": "No sources found in metadata"}

        # Category priority: more specific categories take precedence
        # character > species > copyright > artist > meta > general
        category_priority = {
            "character": 6,
            "species": 5,
            "copyright": 4,
            "artist": 3,
            "meta": 2,
            "general": 1
        }

        # Collect all tags from all sources with their categories
        # tag_name -> {category, sources[]}
        merged_tags = {}
        all_post_ids = []
        all_parent_ids = []
        has_any_children = False

        for source_name, source_data in metadata["sources"].items():
            tag_data = extract_tags_from_source(source_data, source_name)
            if not tag_data:
                continue

            # Track post IDs and parent relationships
            if tag_data.get("id"):
                all_post_ids.append(f"{source_name}:{tag_data['id']}")
            if tag_data.get("parent_id"):
                all_parent_ids.append(f"{source_name}:{tag_data['parent_id']}")
            if tag_data.get("has_children"):
                has_any_children = True

            # Process each category of tags
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

                        if tag_name not in merged_tags:
                            merged_tags[tag_name] = {
                                "category": category,
                                "sources": [source_name]
                            }
                        else:
                            # Tag exists from another source
                            # Use higher priority category if different
                            existing_priority = category_priority.get(merged_tags[tag_name]["category"], 0)
                            new_priority = category_priority.get(category, 0)

                            if new_priority > existing_priority:
                                merged_tags[tag_name]["category"] = category

                            # Add source to list
                            if source_name not in merged_tags[tag_name]["sources"]:
                                merged_tags[tag_name]["sources"].append(source_name)

        if not merged_tags:
            return {"error": "No tags found in any source"}

        # Build categorized tag strings for cached columns
        categorized_tags = {
            "character": [],
            "copyright": [],
            "artist": [],
            "species": [],
            "meta": [],
            "general": []
        }

        for tag_name, tag_info in merged_tags.items():
            category = tag_info["category"]
            categorized_tags[category].append(tag_name)

        # Convert to space-separated strings
        tags_character = " ".join(sorted(categorized_tags["character"]))
        tags_copyright = " ".join(sorted(categorized_tags["copyright"]))
        tags_artist = " ".join(sorted(categorized_tags["artist"]))
        tags_species = " ".join(sorted(categorized_tags["species"]))
        tags_meta = " ".join(sorted(categorized_tags["meta"]))
        tags_general = " ".join(sorted(categorized_tags["general"]))

        # Update database
        try:
            # Delete old image_tags
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))

            # Insert merged tags
            for tag_name, tag_info in merged_tags.items():
                category = tag_info["category"]

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
                    INSERT OR IGNORE INTO image_tags (image_id, tag_id, source)
                    VALUES (?, ?, ?)
                """, (image_id, tag_id, 'merged'))

            # Update images table with merged data
            # Use first post_id/parent_id if available
            post_id_str = all_post_ids[0] if all_post_ids else None
            parent_id_str = all_parent_ids[0] if all_parent_ids else None

            cursor.execute("""
                UPDATE images
                SET post_id = ?, parent_id = ?, has_children = ?, active_source = 'merged',
                    tags_character = ?, tags_copyright = ?, tags_artist = ?,
                    tags_species = ?, tags_meta = ?, tags_general = ?
                WHERE id = ?
            """, (post_id_str, parent_id_str, has_any_children,
                tags_character, tags_copyright, tags_artist,
                tags_species, tags_meta, tags_general,
                image_id))

            conn.commit()

            return {
                "status": "success",
                "message": "Merged all sources",
                "source": "merged",
                "tag_count": len(merged_tags),
                "sources_merged": list(metadata["sources"].keys()),
                "merged_tags": merged_tags  # Include tag-to-sources mapping
            }

        except Exception as e:
            conn.rollback()
            return {"error": f"Database error: {str(e)}"}

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

            # Insert rating tag if present
            if tag_data.get("rating"):
                rating_tag = tag_data["rating"]
                rating_source = tag_data.get("rating_source", "original")

                # Insert or update rating tag
                cursor.execute("""
                    INSERT INTO tags (name, category) VALUES (?, 'meta')
                    ON CONFLICT(name) DO UPDATE SET category = 'meta'
                """, (rating_tag,))

                # Get tag ID
                cursor.execute("SELECT id FROM tags WHERE name = ?", (rating_tag,))
                tag_id = cursor.fetchone()['id']

                # Link rating tag to image with appropriate source
                cursor.execute("""
                    INSERT OR REPLACE INTO image_tags (image_id, tag_id, source)
                    VALUES (?, ?, ?)
                """, (image_id, tag_id, rating_source))

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

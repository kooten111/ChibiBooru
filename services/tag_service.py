from quart import request, jsonify
from database import models
from database import get_db_connection
import traceback

def update_image_tags_categorized(filepath, categorized_tags):
    """Update image tags by category in the database."""
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
        traceback.print_exc()
        if 'conn' in locals():
            conn.rollback()
        return False

async def edit_tags_service():
    """Service to update tags for an image with category support."""
    data = await request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    
    # Check if we have categorized tags (new format) or plain tags (old format)
    categorized_tags = data.get('categorized_tags')
    
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        if categorized_tags:
            # New categorized format
            success = update_image_tags_categorized(filepath, categorized_tags)
        else:
            # Old format for backwards compatibility
            new_tags_str = data.get('tags', '').strip()
            success = models.update_image_tags(filepath, new_tags_str)

        if success:
            # Selective reload: only update this image and tag counts
            models.reload_single_image(filepath)
            models.reload_tag_counts()
            from repositories.data_access import get_image_details
            get_image_details.cache_clear()
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Failed to update tags in the database"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def autocomplete():
    """Enhanced autocomplete with grouped suggestions by type and category."""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify({"groups": []})

    last_token = query.split()[-1].lower()

    # Strip the '-' prefix for negative searches so autocomplete works
    is_negative_search = last_token.startswith('-')
    search_token = last_token[1:] if is_negative_search else last_token

    # Need at least 2 characters for the actual search term
    if len(search_token) < 2:
        return jsonify({"groups": []})

    # Initialize groups
    groups = {
        "Filters": [],
        "Tags": [],
        "Files": []
    }

    # File extension search (only if not a negative search)
    if not is_negative_search and search_token.startswith('.'):
        ext = search_token[1:]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']:
            groups["Filters"].append({
                "tag": search_token,
                "display": f"All {search_token} files",
                "count": None,
                "type": "extension"
            })

    # Special filter suggestions (only if not a negative search)
    if not is_negative_search:
        filters = [
            ("source:danbooru", "Danbooru images", "danbooru"),
            ("source:e621", "E621 images", "e621"),
            ("source:gelbooru", "Gelbooru images", "gelbooru"),
            ("source:yandere", "Yandere images", "yandere"),
            ("source:pixiv", "Pixiv images", "pixiv"),
            ("source:local_tagger", "Locally tagged images", "local"),
            ("has:parent", "Images with parent", "parent"),
            ("has:child", "Images with children", "child"),
            ("pool:", "Search pools", "pool"),
            ("order:new", "Newest first", "order"),
            ("order:newest", "Newest first", "newest"),
            ("order:old", "Oldest first", "old"),
            ("order:oldest", "Oldest first", "oldest")
        ]

        for tag, display, keyword in filters:
            # Match if: keyword matches search, OR search matches keyword, OR search matches start of tag
            if keyword in search_token or search_token in keyword or tag.startswith(search_token):
                groups["Filters"].append({
                    "tag": tag,
                    "display": display,
                    "count": None,
                    "type": "filter"
                })

    # Get tag categories from database
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT t.name, t.category, COUNT(DISTINCT it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE LOWER(t.name) LIKE ?
            GROUP BY t.name, t.category
            ORDER BY count DESC
            LIMIT 20
        """, (f"%{search_token}%",))
        tag_results = cursor.fetchall()

    # Group tags by category
    tag_categories = {}
    for row in tag_results:
        tag_name = row['name']
        category = row['category'] or 'general'
        count = row['count']

        if category not in tag_categories:
            tag_categories[category] = []

        tag_lower = tag_name.lower()
        is_prefix = tag_lower.startswith(search_token)

        # If this was a negative search, prepend '-' to the tag and don't use category
        if is_negative_search:
            final_tag = f"-{tag_name}"
            final_display = f"-{tag_name}"
            final_category = None  # Don't use category prefix for negative tags
        else:
            final_tag = tag_name
            final_display = tag_name
            final_category = category

        tag_categories[category].append({
            "tag": final_tag,
            "display": final_display,
            "count": count,
            "category": final_category,
            "type": "tag",
            "is_prefix": is_prefix
        })

    # Sort categories by priority and build tag groups
    category_priority = ['character', 'copyright', 'artist', 'species', 'general', 'meta']

    for category in category_priority:
        if category not in tag_categories:
            continue

        # Sort: prefix matches first, then by count
        sorted_tags = sorted(
            tag_categories[category],
            key=lambda x: (not x['is_prefix'], -x['count'])
        )

        groups["Tags"].extend(sorted_tags[:5])

    # Build response with only non-empty groups
    response_groups = []
    for group_name, items in groups.items():
        if items:
            response_groups.append({
                "name": group_name,
                "items": items[:10]
            })

    return jsonify({"groups": response_groups})

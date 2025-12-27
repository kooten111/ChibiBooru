from quart import request, jsonify
from database import models
from database import get_db_connection
from utils.file_utils import normalize_image_path
import traceback

async def edit_tags_service():
    """Service to update tags for an image with category support.

    This is for MANUAL USER EDITS only and records deltas for preservation
    across database rebuilds.
    """
    data = await request.json
    filepath = normalize_image_path(data.get('filepath', ''))

    # Check if we have categorized tags (new format) or plain tags (old format)
    categorized_tags = data.get('categorized_tags')

    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        if categorized_tags:
            # New categorized format - THIS IS A MANUAL USER EDIT, record deltas
            success = models.update_image_tags_categorized(
                filepath,
                categorized_tags,
                record_deltas=True  # Record manual user modifications
            )
        else:
            # Old format for backwards compatibility - THIS IS A MANUAL USER EDIT, record deltas
            new_tags_str = data.get('tags', '').strip()
            success = models.update_image_tags(
                filepath,
                new_tags_str,
                record_deltas=True  # Record manual user modifications
            )

        if success:
            # Selective reload: only update this image and tag counts
            from core.cache_manager import invalidate_image_cache
            invalidate_image_cache(filepath)
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
            ("is:favourite", "Favourited images", "favourite"),
            ("is:favourite", "Favourited images", "fav"),
            ("pool:", "Search pools", "pool"),
            ("order:new", "Newest first", "order"),
            ("order:newest", "Newest first", "newest"),
            ("order:old", "Oldest first", "old"),
            ("order:oldest", "Oldest first", "oldest"),
            ("order:score", "Highest score first", "score"),
            ("order:score_desc", "Highest score first", "score"),
            ("order:score_asc", "Lowest score first", "score"),
            ("order:fav", "Most favorited first", "fav"),
            ("order:fav_desc", "Most favorited first", "fav"),
            ("order:fav_asc", "Least favorited first", "fav")
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

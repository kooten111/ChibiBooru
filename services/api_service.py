# services/api_service.py
from flask import request, jsonify, url_for
import models
import random
import sys
import os
import requests
from urllib.parse import urlparse
from utils import get_thumbnail_path
import processing
from database import get_db_connection

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')


def get_images_for_api():
    """Service for the infinite scroll API."""
    from services import query_service  # Import here to avoid circular import
    
    search_query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    seed = request.args.get('seed', default=None, type=int)

    # Use the same search logic as the main page for consistency
    search_results, should_shuffle = query_service.perform_search(search_query)

    if should_shuffle and seed is not None:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    total_pages = (total_results + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    images_page = [
        {"path": f"images/{img['filepath']}", "thumb": get_thumbnail_path(f"images/{img['filepath']}"), "tags": img.get('tags', '')}
        for img in search_results[start_idx:end_idx]
    ]

    return jsonify({
        "images": images_page,
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results,
        "has_more": page < total_pages
    })


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
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.rollback()
        return False

def edit_tags_service():
    """Service to update tags for an image with category support."""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    
    # Check if we have categorized tags (new format) or plain tags (old format)
    categorized_tags = data.get('categorized_tags')
    
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        if categorized_tags:
            # New categorized format
            success = models.update_image_tags_categorized(filepath, categorized_tags)
        else:
            # Old format for backwards compatibility
            new_tags_str = data.get('tags', '').strip()
            success = models.update_image_tags(filepath, new_tags_str)

        if success:
            models.load_data_from_db()
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Failed to update tags in the database"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def delete_image_service():
    """Service to delete an image and its data."""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)

    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        db_success = models.delete_image(filepath)
        if not db_success:
            print(f"Info: delete_image_service called for {filepath}, but it was not in the database.")

        full_image_path = os.path.join("static/images", filepath)
        full_thumb_path = os.path.join("static", get_thumbnail_path(f"images/{filepath}"))

        if os.path.exists(full_image_path):
            os.remove(full_image_path)
        if os.path.exists(full_thumb_path):
            os.remove(full_thumb_path)
        
        models.load_data_from_db()

        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Error deleting image {filepath}: {e}")
        return jsonify({"error": "An unexpected error occurred during deletion."}), 500

# --- THIS IS THE CORRECTED SAUCENAO BLOCK ---

def saucenao_search_service():
    """Service to search SauceNao for an image."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    filepath = data.get('filepath', '')
    if not filepath:
        return jsonify({"error": "No filepath provided"}), 400

    full_path = os.path.join("static", filepath)
    if not os.path.exists(full_path):
        return jsonify({"error": "Image file not found"}), 404
    
    try:
        saucenao_response = processing.search_saucenao(full_path)
        if not saucenao_response or 'results' not in saucenao_response:
            return jsonify({"status": "success", "found": False, "message": "No results found"})

        results = []
        for result in saucenao_response.get('results', []):
            similarity = float(result['header']['similarity'])
            if similarity < 60: continue

            result_data = {"similarity": similarity, "thumbnail": result['header'].get('thumbnail'), "sources": []}
            for url in result['data'].get('ext_urls', []):
                source_info = None
                # Restore robust URL parsing for all boorus
                if 'danbooru.donmai.us' in url:
                    post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0] if '/posts/' in url else url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "danbooru", "url": url, "post_id": post_id}
                elif 'e621.net' in url:
                    post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0] if '/posts/' in url else url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "e621", "url": url, "post_id": post_id}
                elif 'gelbooru.com' in url and 'id=' in url:
                    source_info = {"type": "gelbooru", "url": url, "post_id": url.split('id=')[-1].split('&')[0]}
                elif 'yande.re' in url:
                    post_id = url.split('/post/show/')[-1].split('?')[0].split('/')[0] if '/post/show/' in url else url.split('/post/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "yandere", "url": url, "post_id": post_id}
                
                if source_info:
                    result_data["sources"].append(source_info)

            if result_data["sources"]:
                results.append(result_data)

        return jsonify({"status": "success", "found": len(results) > 0, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def saucenao_fetch_metadata_service():
    """Service to fetch full metadata from a booru source."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    source, post_id = data.get('source'), data.get('post_id')
    if not source or not post_id:
        return jsonify({"error": "Missing source or post_id"}), 400

    try:
        result = processing.fetch_by_post_id(source, post_id)
        if not result or 'data' not in result:
            return jsonify({"error": f"Failed to fetch metadata from {source}"}), 404

        full_data = result['data']
        tags_data = processing.extract_tag_data(full_data, source)

        return jsonify({
            "status": "success",
            "source": source,
            "tags": tags_data['tags'],
            "image_url": tags_data.get('image_url'),
            "preview_url": tags_data.get('preview_url'),
            "width": tags_data.get('width'),
            "height": tags_data.get('height'),
            "file_size": tags_data.get('file_size'),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def autocomplete():
    """Enhanced autocomplete with fuzzy matching, sources, filenames, and extensions."""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])

    tag_counts = models.get_tag_counts()
    last_token = query.split()[-1].lower()
    
    suggestions = []
    
    # File extension search
    if last_token.startswith('.'):
        ext = last_token[1:]  # Remove the dot
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']:
            suggestions.append({
                "tag": last_token,
                "display": f"All {last_token} files",
                "count": None,
                "type": "extension",
                "icon": "📁"
            })
    
    # Source suggestions
    sources = ['danbooru', 'e621', 'gelbooru', 'yandere', 'camie_tagger']
    for source in sources:
        if last_token in source or source.startswith(last_token):
            suggestions.append({
                "tag": f"source:{source}",
                "display": f"{source.title()} images",
                "count": None,
                "type": "source",
                "icon": "🌐"
            })
    
    # Tag matching - both prefix and substring
    prefix_matches = []
    substring_matches = []
    
    for tag, count in tag_counts.items():
        tag_lower = tag.lower()
        
        # Exact prefix match (highest priority)
        if tag_lower.startswith(last_token):
            prefix_matches.append({
                "tag": tag,
                "display": tag,
                "count": count,
                "type": "tag",
                "icon": "🏷️"
            })
        # Substring match (fuzzy matching)
        elif last_token in tag_lower:
            substring_matches.append({
                "tag": tag,
                "display": tag,
                "count": count,
                "type": "tag",
                "icon": "🏷️"
            })
    
    # Sort by count
    prefix_matches.sort(key=lambda x: x['count'], reverse=True)
    substring_matches.sort(key=lambda x: x['count'], reverse=True)
    
    # Combine: extension/source suggestions first, then prefix matches, then substring
    suggestions.extend(prefix_matches[:8])
    suggestions.extend(substring_matches[:5])
    
    return jsonify(suggestions[:15])


def saucenao_apply_service():
    """Service to apply selected metadata and download the new image."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    original_filepath = data.get('filepath', '').replace('images/', '', 1)
    source = data.get('source')
    post_id = data.get('post_id')
    download_image = data.get('download_image', False)
    image_url = data.get('image_url')

    if not all([original_filepath, source, post_id]):
        return jsonify({"error": "Missing required parameters"}), 400

    new_full_path = None
    redirect_url = None
    
    try:
        # Step 1: Delete the old database entry
        models.delete_image(original_filepath)
        
        # Step 2: Handle the image file
        old_full_path = os.path.join("static/images", original_filepath)
        
        if download_image and image_url:
            # Download new image to a new path
            new_filename = os.path.basename(urlparse(image_url).path)
            new_full_path = os.path.join("static/images", new_filename)
            
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(new_full_path, 'wb') as f:
                f.write(response.content)

            # If download is successful, remove the old file and its thumbnail
            if os.path.exists(old_full_path):
                os.remove(old_full_path)
            old_thumb_path = os.path.join("static", get_thumbnail_path(f"images/{original_filepath}"))
            if os.path.exists(old_thumb_path):
                os.remove(old_thumb_path)
            
            # Set the path to be processed to the new file
            path_to_process = new_full_path
            redirect_url = url_for('main.show_image', filepath=os.path.join("images", new_filename))

        else:
            # Use the existing file
            path_to_process = old_full_path
            redirect_url = url_for('main.show_image', filepath=os.path.join("images", original_filepath))

        # Step 3: Process the image file (either the new one or the old one)
        if processing.process_image_file(path_to_process):
            models.load_data_from_db()
            return jsonify({
                "status": "success",
                "redirect_url": redirect_url
            })
        else:
            raise Exception("Failed to process and save the new image to the database.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Clean up downloaded file on failure
        if new_full_path and os.path.exists(new_full_path):
            os.remove(new_full_path)
        return jsonify({"error": str(e)}), 500
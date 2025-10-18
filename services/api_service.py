# services/api_service.py
from flask import request, jsonify, url_for
import models
import random
import os
import requests
from urllib.parse import urlparse
from utils import get_thumbnail_path
import processing

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

def get_images_for_api():
    """Service for the infinite scroll API."""
    search_query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    seed = request.args.get('seed', default=None, type=int)

    if search_query:
        search_results = models.search_images_by_tags(search_query.split())
        should_shuffle = True
    else:
        search_results = models.get_all_images_with_tags()
        should_shuffle = True

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

def autocomplete():
    """Service for tag autocomplete suggestions."""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])

    tag_counts = models.get_tag_counts()
    last_token = query.split()[-1]
    
    matches = [
        {"tag": tag, "count": count}
        for tag, count in tag_counts.items()
        if tag.startswith(last_token)
    ]
    matches.sort(key=lambda x: x['count'], reverse=True)
    return jsonify(matches[:10])

def edit_tags_service():
    """Service to update tags for an image."""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    new_tags_str = data.get('tags', '').strip()

    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    success = models.update_image_tags(filepath, new_tags_str)

    if success:
        models.load_data_from_db()
        return jsonify({"status": "success"})
    else:
        return jsonify({"error": "Failed to update tags in the database"}), 500

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
        full_data = processing.fetch_by_post_id(source, post_id)
        if not full_data:
            return jsonify({"error": f"Failed to fetch metadata from {source}"}), 404
        
        image_url, preview_url, tags_str = None, None, ""
        if source == 'danbooru':
            image_url = full_data.get('file_url') or full_data.get('large_file_url')
            preview_url = full_data.get('preview_file_url')
            tags_str = full_data.get("tag_string", "")
        elif source == 'e621':
            image_url = full_data.get('file', {}).get('url')
            preview_url = full_data.get('preview', {}).get('url')
            tags = full_data.get("tags", {})
            tags_str = " ".join([tag for cat in tags.values() for tag in cat])
        
        return jsonify({
            "status": "success", "tags": {"all": tags_str},
            "image_url": image_url, "preview_url": preview_url
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def saucenao_apply_service():
    """Service to apply selected metadata and download the new image."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    original_filepath = data.get('filepath', '').replace('images/', '', 1)
    source, post_id = data.get('source'), data.get('post_id')

    if not all([original_filepath, source, post_id]):
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        # Step 1: Delete the old placeholder entry and files directly
        models.delete_image(original_filepath)
        old_full_path = os.path.join("static/images", original_filepath)
        if os.path.exists(old_full_path):
            os.remove(old_full_path)
        old_thumb_path = os.path.join("static", get_thumbnail_path(f"images/{original_filepath}"))
        if os.path.exists(old_thumb_path):
            os.remove(old_thumb_path)

        # Step 2: Fetch the new metadata
        full_data = processing.fetch_by_post_id(source, post_id)
        if not full_data:
            raise Exception("Failed to fetch metadata for the new image.")

        # Step 3: Download the new image file
        image_url = (full_data.get('file_url') or 
                     full_data.get('large_file_url') or 
                     full_data.get('file', {}).get('url'))
        if not image_url:
            raise Exception("Could not find a valid image URL in the metadata.")

        new_filename = os.path.basename(urlparse(image_url).path)
        new_full_path = os.path.join("static/images", new_filename)
        
        response = requests.get(image_url, timeout=60)
        response.raise_for_status()
        with open(new_full_path, 'wb') as f:
            f.write(response.content)

        # Step 4: Process the new file directly
        if processing.process_image_file(new_full_path):
            models.load_data_from_db()
            return jsonify({
                "status": "success",
                "redirect_url": url_for('main.show_image', filepath=f"images/{new_filename}")
            })
        else:
            raise Exception("Failed to process and save the new image to the database.")

    except Exception as e:
        if 'new_full_path' in locals() and os.path.exists(new_full_path):
            os.remove(new_full_path)
        return jsonify({"error": str(e)}), 500

# --- END OF SAUCENAO BLOCK ---
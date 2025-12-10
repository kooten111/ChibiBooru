from quart import request, jsonify, url_for
from database import models
from services import processing_service as processing
from utils import get_thumbnail_path
import os
import requests
from urllib.parse import urlparse
import traceback

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

async def saucenao_search_service():
    """Service to search SauceNao for an image."""
    data = await request.json
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


async def saucenao_fetch_metadata_service():
    """Service to fetch full metadata from a booru source."""
    data = await request.json
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
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


async def saucenao_apply_service():
    """Service to apply selected metadata and download the new image."""
    data = await request.json
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
            # Selective reload: only update this image and tag counts
            rel_path = os.path.relpath(path_to_process, "static/images").replace('\\', '/')
            from core.cache_manager import invalidate_image_cache
            invalidate_image_cache(rel_path)
            return jsonify({
                "status": "success",
                "redirect_url": redirect_url
            })
        else:
            raise Exception("Failed to process and save the new image to the database.")

    except Exception as e:
        traceback.print_exc()
        # Clean up downloaded file on failure
        if new_full_path and os.path.exists(new_full_path):
            os.remove(new_full_path)
        return jsonify({"error": str(e)}), 500

from database import models
from services import processing
from utils import get_thumbnail_path
from utils.file_utils import normalize_image_path
import os
import requests
from urllib.parse import urlparse
import traceback


def saucenao_search(data: dict) -> dict:
    """Search SauceNao for an image. Takes data dict; returns result dict or raises."""
    filepath = data.get('filepath', '')
    if not filepath:
        raise ValueError("No filepath provided")

    full_path = os.path.join("static", filepath)
    if not os.path.exists(full_path):
        raise FileNotFoundError("Image file not found")

    saucenao_response = processing.search_saucenao(full_path)
    if not saucenao_response or 'results' not in saucenao_response:
        return {"status": "success", "found": False, "message": "No results found"}

    results = []
    for result in saucenao_response.get('results', []):
        similarity = float(result['header']['similarity'])
        if similarity < 60:
            continue

        result_data = {"similarity": similarity, "thumbnail": result['header'].get('thumbnail'), "sources": []}
        for url in result['data'].get('ext_urls', []):
            source_info = None
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

    return {"status": "success", "found": len(results) > 0, "results": results}


def saucenao_fetch_metadata(data: dict) -> dict:
    """Fetch full metadata from a booru source. Takes data dict; returns result dict or raises."""
    source, post_id = data.get('source'), data.get('post_id')
    if not source or not post_id:
        raise ValueError("Missing source or post_id")

    result = processing.fetch_by_post_id(source, post_id)
    if not result or 'data' not in result:
        raise FileNotFoundError(f"Failed to fetch metadata from {source}")

    full_data = result['data']
    tags_data = processing.extract_tag_data(full_data, source)

    return {
        "status": "success",
        "source": source,
        "tags": tags_data['tags'],
        "image_url": tags_data.get('image_url'),
        "preview_url": tags_data.get('preview_url'),
        "width": tags_data.get('width'),
        "height": tags_data.get('height'),
        "file_size": tags_data.get('file_size'),
    }


def saucenao_apply(data: dict) -> dict:
    """Apply selected metadata and optionally download the new image. Returns dict with status and redirect_path."""
    original_filepath = normalize_image_path(data.get('filepath', ''))
    source = data.get('source')
    post_id = data.get('post_id')
    download_image = data.get('download_image', False)
    image_url = data.get('image_url')

    if not all([original_filepath, source, post_id]):
        raise ValueError("Missing required parameters")

    new_full_path = None
    try:
        # Step 1: Delete the old database entry
        models.delete_image(original_filepath)

        # Step 2: Handle the image file
        old_full_path = os.path.join("static/images", original_filepath)

        if download_image and image_url:
            new_filename = os.path.basename(urlparse(image_url).path)
            new_full_path = os.path.join("static/images", new_filename)

            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(new_full_path, 'wb') as f:
                f.write(response.content)

            if os.path.exists(old_full_path):
                os.remove(old_full_path)
            old_thumb_path = os.path.join("static", get_thumbnail_path(f"images/{original_filepath}"))
            if os.path.exists(old_thumb_path):
                os.remove(old_thumb_path)

            path_to_process = new_full_path
            redirect_path = os.path.join("images", new_filename)
        else:
            path_to_process = old_full_path
            redirect_path = os.path.join("images", original_filepath)

        # Step 3: Process the image file
        success, msg, *_ = processing.process_image_file(path_to_process)
        if not success:
            raise RuntimeError(f"Failed to process and save the new image: {msg}")

        rel_path = os.path.relpath(path_to_process, "static/images").replace('\\', '/')
        from core.cache_manager import invalidate_image_cache
        invalidate_image_cache(rel_path)

        return {"status": "success", "redirect_path": redirect_path}
    except Exception:
        if new_full_path and os.path.exists(new_full_path):
            try:
                os.remove(new_full_path)
            except OSError:
                pass
        raise

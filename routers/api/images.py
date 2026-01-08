from quart import request, jsonify, send_file
from . import api_blueprint
from services import image_service, tag_service
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
from database import models
from utils import api_handler
from utils.file_utils import normalize_image_path
import asyncio

@api_blueprint.route('/images')
@api_handler()
async def get_images():
    """Get paginated images for infinite scroll."""
    query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    seed = request.args.get('seed', default=None, type=int)
    
    data = await asyncio.to_thread(image_service.get_images_for_api, query, page, seed)
    return jsonify(data)

@api_blueprint.route('/edit_tags', methods=['POST'])
@api_handler()
async def edit_tags():
    """Edit tags for an image with category support."""
    data = await request.json
    return await asyncio.to_thread(tag_service.edit_tags_service, data)

@api_blueprint.route('/delete_image', methods=['POST'])
@api_handler()
async def delete_image():
    """Delete an image and its associated data."""
    data = await request.json
    return await asyncio.to_thread(image_service.delete_image_service, data)

@api_blueprint.route('/delete_images_bulk', methods=['POST'])
@api_handler()
async def delete_images_bulk():
    """Delete multiple images in bulk."""
    data = await request.json
    return await asyncio.to_thread(image_service.delete_images_bulk_service, data)

@api_blueprint.route('/download_images_bulk', methods=['POST'])
@api_handler()
async def download_images_bulk():
    """Download multiple images as a zip file."""
    data = await request.json
    result = await asyncio.to_thread(image_service.prepare_bulk_download, data)
    
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
        
    return await send_file(
        result,
        mimetype='application/zip',
        as_attachment=True,
        attachment_filename='images.zip'
    )

@api_blueprint.route('/retry_tagging', methods=['POST'])
@api_handler()
async def retry_tagging():
    """Retry tagging for a single image."""
    data = await request.json
    return await asyncio.to_thread(image_service.retry_tagging_service, data)

@api_blueprint.route('/bulk_retry_tagging', methods=['POST'])
@api_handler()
async def bulk_retry_tagging():
    """Retry tagging for multiple images in bulk."""
    return await image_service.bulk_retry_tagging_service()

@api_blueprint.route('/switch_source', methods=['POST'])
@api_handler()
async def switch_source():
    data = await request.json
    filepath = data.get('filepath')
    source = data.get('source')

    if not filepath or not source:
        raise ValueError("Missing filepath or source")

    # Handle special "merged" source
    if source == 'merged':
        result = merge_all_sources(filepath)
    else:
        result = switch_metadata_source_db(filepath, source)

    if "error" in result:
        raise ValueError(result["error"])

    # Selective reload: only update this image
    from core.cache_manager import invalidate_image_cache
    invalidate_image_cache(normalize_image_path(filepath))

    return result

@api_blueprint.route('/clear_deltas', methods=['POST'])
@api_handler()
async def clear_deltas():
    """Clear tag deltas for a specific image."""
    data = await request.json
    filepath = data.get('filepath')

    if not filepath:
        raise ValueError("Missing filepath")

    # Normalize filepath
    filepath = normalize_image_path(filepath)

    # Clear deltas for this image
    count = models.clear_deltas_for_image(filepath)

    return {
        "status": "success",
        "message": f"Cleared {count} delta(s) for this image",
        "count": count
    }

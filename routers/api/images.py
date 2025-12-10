from quart import request, jsonify
from . import api_blueprint
from services import image_service, tag_service
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
from database import models
from utils import api_handler
import asyncio

@api_blueprint.route('/images')
@api_handler()
async def get_images():
    """Get paginated images for infinite scroll."""
    return image_service.get_images_for_api()

@api_blueprint.route('/edit_tags', methods=['POST'])
@api_handler()
async def edit_tags():
    """Edit tags for an image with category support."""
    return await tag_service.edit_tags_service()

@api_blueprint.route('/delete_image', methods=['POST'])
@api_handler()
async def delete_image():
    """Delete an image and its associated data."""
    return await image_service.delete_image_service()

@api_blueprint.route('/delete_images_bulk', methods=['POST'])
@api_handler()
async def delete_images_bulk():
    """Delete multiple images in bulk."""
    return await image_service.delete_images_bulk_service()

@api_blueprint.route('/download_images_bulk', methods=['POST'])
@api_handler()
async def download_images_bulk():
    """Download multiple images as a zip file."""
    return await image_service.download_images_bulk_service()

@api_blueprint.route('/retry_tagging', methods=['POST'])
@api_handler()
async def retry_tagging():
    """Retry tagging for a single image."""
    return await image_service.retry_tagging_service()

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
    invalidate_image_cache(filepath.replace('images/', '', 1))

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
    filepath = filepath.replace('images/', '', 1)

    # Clear deltas for this image
    count = models.clear_deltas_for_image(filepath)

    return {
        "message": f"Cleared {count} delta(s) for this image",
        "count": count
    }

from quart import request, jsonify, send_file, make_response
from . import api_blueprint
from services import image_service, tag_service
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
from database import models
import config
from utils import api_handler
from utils.file_utils import normalize_image_path
from utils.request_helpers import require_json_body
from utils.validation import validate_string, validate_positive_integer, validate_enum
import asyncio


def _no_cache(response):
    """Mark a response as uncacheable so browsers always fetch fresh data."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@api_blueprint.route('/images')
@api_handler()
async def get_images():
    """Get paginated images for infinite scroll."""
    query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', config.IMAGES_PER_PAGE, type=int)

    page = max(page or 1, 1)
    per_page = max(1, min(per_page or config.IMAGES_PER_PAGE, 500))
    
    data = await asyncio.to_thread(image_service.get_images_for_api, query, page, per_page)
    return jsonify(data)

@api_blueprint.route('/edit_tags', methods=['POST'])
@api_handler()
async def edit_tags():
    """Edit tags for an image with category support."""
    data = await require_json_body(request)
    return await asyncio.to_thread(tag_service.edit_tags_service, data)

@api_blueprint.route('/delete_image', methods=['POST'])
@api_handler()
async def delete_image():
    """Delete an image and its associated data."""
    data = await require_json_body(request)
    return await asyncio.to_thread(image_service.delete_image_service, data)

@api_blueprint.route('/delete_images_bulk', methods=['POST'])
@api_handler()
async def delete_images_bulk():
    """Delete multiple images in bulk."""
    data = await require_json_body(request)
    return await asyncio.to_thread(image_service.delete_images_bulk_service, data)

@api_blueprint.route('/download_images_bulk', methods=['POST'])
@api_handler()
async def download_images_bulk():
    """Download multiple images as a zip file."""
    data = await require_json_body(request)
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
    data = await require_json_body(request)
    return await asyncio.to_thread(image_service.retry_tagging_service, data)

@api_blueprint.route('/bulk_retry_tagging', methods=['POST'])
@api_handler()
async def bulk_retry_tagging():
    """Retry tagging for multiple images in bulk."""
    data = (await request.get_json(silent=True)) or {}
    return await image_service.start_bulk_retry_tagging(data)

@api_blueprint.route('/switch_source', methods=['POST'])
@api_handler()
async def switch_source():
    data = await require_json_body(request)
    filepath = validate_string(data.get('filepath'), 'filepath', min_length=1)
    source = validate_string(data.get('source'), 'source', min_length=1)

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
    data = await require_json_body(request)
    filepath = validate_string(data.get('filepath'), 'filepath', min_length=1)
    filepath = normalize_image_path(filepath)

    # Clear deltas for this image
    count = models.clear_deltas_for_image(filepath)

    return {
        "status": "success",
        "message": f"Cleared {count} delta(s) for this image",
        "count": count
    }

@api_blueprint.route('/image/<path:filepath>/stats')
@api_handler()
async def get_image_stats(filepath):
    """Get enhanced stats for image detail page (lazy-loaded)."""
    from services import query_service
    stats = await asyncio.to_thread(query_service.get_enhanced_stats)
    return jsonify(stats)

@api_blueprint.route('/image/<path:filepath>/deltas')
@api_handler()
async def get_image_deltas(filepath):
    """Get tag deltas for a specific image (lazy-loaded)."""
    lookup_path = normalize_image_path(filepath)
    tag_deltas = await asyncio.to_thread(models.get_image_deltas, lookup_path)
    return _no_cache(await make_response(jsonify(tag_deltas or [])))

@api_blueprint.route('/image/<path:filepath>/pools')
@api_handler()
async def get_image_pools(filepath):
    """Get pools for a specific image (lazy-loaded)."""
    from repositories.data_access import get_image_details
    lookup_path = normalize_image_path(filepath)
    data = await asyncio.to_thread(get_image_details, lookup_path)
    if not data or not data.get('id'):
        return _no_cache(await make_response(jsonify([])))
    pools = await asyncio.to_thread(models.get_pools_for_image, data['id'])
    return _no_cache(await make_response(jsonify(pools or [])))

@api_blueprint.route('/image/<path:filepath>/similar')
@api_handler()
async def get_image_similar(filepath):
    """Get similar images for a specific image (lazy-loaded)."""
    from services import query_service
    from utils import get_thumbnail_path
    from repositories.data_access import get_image_details_with_merged_tags
    from repositories import relations_repository
    
    lookup_path = normalize_image_path(filepath)
    
    # Get image data for family filtering
    data = await asyncio.to_thread(get_image_details_with_merged_tags, lookup_path)
    if not data:
        return _no_cache(await make_response(jsonify({'parent_child_images': [], 'similar_images': []})))
    
    image_id = data.get('id')
    
    # Fetch family images from image_relations table (canonical source)
    parent_child_images = await asyncio.to_thread(
        relations_repository.get_related_images_from_relations,
        image_id
    ) if image_id else []
    
    parent_child_paths = set()
    for img in parent_child_images:
        img['match_type'] = img['type']  # 'parent', 'child', or 'sibling'
        img['thumb'] = get_thumbnail_path(img['path'])
        
        parent_child_paths.add(normalize_image_path(img['path']))
    
    # Get similar images - tag-based results
    similar_images = await asyncio.to_thread(
        query_service.find_related_by_tags,
        filepath,
        limit=40
    )
    
    # Filter out self-match and family
    similar_images = [
        img for img in similar_images
        if normalize_image_path(img['path']) != lookup_path
        and normalize_image_path(img['path']) not in parent_child_paths
    ]
    
    # Tag-only results - ensure correct labeling
    for img in similar_images:
        img['primary_source'] = 'tag'
    
    return _no_cache(await make_response(jsonify({
        'parent_child_images': parent_child_images,
        'similar_images': similar_images
    })))


@api_blueprint.route('/image/<path:filepath>/relations')
@api_handler()
async def get_image_relations(filepath):
    """Get editable relations for a specific image."""
    from repositories.data_access import get_image_details
    from repositories import relations_repository

    lookup_path = normalize_image_path(filepath)
    data = await asyncio.to_thread(get_image_details, lookup_path)
    if not data or not data.get('id'):
        raise FileNotFoundError("Image not found")

    relations = await asyncio.to_thread(
        relations_repository.get_editable_relations_for_image,
        data['id']
    )
    return _no_cache(await make_response(jsonify({
        'image_id': data['id'],
        'relations': relations,
    })))


@api_blueprint.route('/image-relations', methods=['POST'])
@api_handler()
async def create_image_relation():
    """Create a manual image relation."""
    data = await require_json_body(request)
    image_id = validate_positive_integer(data.get('image_id'), 'image_id')
    other_image_id = validate_positive_integer(data.get('other_image_id'), 'other_image_id')
    display_type = validate_enum(data.get('display_type'), 'display_type', ['parent', 'child', 'sibling'])

    from repositories import relations_repository
    from core.cache_manager import invalidate_image_cache

    created = await asyncio.to_thread(
        relations_repository.create_manual_relation,
        image_id,
        other_image_id,
        display_type,
    )

    invalidate_image_cache(created['filepath_a'])
    invalidate_image_cache(created['filepath_b'])

    return {
        'status': 'success',
        'message': 'Relation created',
    }


@api_blueprint.route('/image-relations/<int:relation_id>', methods=['PUT'])
@api_handler()
async def update_image_relation(relation_id):
    """Update an existing relation as a manual edit."""
    data = await require_json_body(request)
    image_id = validate_positive_integer(data.get('image_id'), 'image_id')
    other_image_id = validate_positive_integer(data.get('other_image_id'), 'other_image_id')
    display_type = validate_enum(data.get('display_type'), 'display_type', ['parent', 'child', 'sibling'])

    from repositories import relations_repository
    from core.cache_manager import invalidate_image_cache

    before = await asyncio.to_thread(
        relations_repository.get_relation_for_image,
        relation_id,
        image_id,
    )
    if not before:
        raise FileNotFoundError("Relation not found")

    updated = await asyncio.to_thread(
        relations_repository.update_manual_relation,
        relation_id,
        image_id,
        other_image_id,
        display_type,
    )

    invalidate_image_cache(before['filepath_a'])
    invalidate_image_cache(before['filepath_b'])
    invalidate_image_cache(updated['filepath_a'])
    invalidate_image_cache(updated['filepath_b'])

    return {
        'status': 'success',
        'message': 'Relation updated',
    }


@api_blueprint.route('/image-relations/<int:relation_id>', methods=['DELETE'])
@api_handler()
async def delete_image_relation(relation_id):
    """Delete a relation by ID."""
    from repositories import relations_repository
    from core.cache_manager import invalidate_image_cache

    deleted = await asyncio.to_thread(relations_repository.delete_relation_by_id, relation_id)
    if not deleted:
        raise FileNotFoundError("Relation not found")

    invalidate_image_cache(deleted['filepath_a'])
    invalidate_image_cache(deleted['filepath_b'])

    return {
        'status': 'success',
        'message': 'Relation removed',
    }

from quart import request, jsonify
from . import api_blueprint
from services import api_service
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
from database import models
import asyncio

@api_blueprint.route('/images')
async def get_images():
    return api_service.get_images_for_api()

@api_blueprint.route('/edit_tags', methods=['POST'])
async def edit_tags():
    return await api_service.edit_tags_service()

@api_blueprint.route('/delete_image', methods=['POST'])
async def delete_image():
    return await api_service.delete_image_service()

@api_blueprint.route('/delete_images_bulk', methods=['POST'])
async def delete_images_bulk():
    return await api_service.delete_images_bulk_service()

@api_blueprint.route('/retry_tagging', methods=['POST'])
async def retry_tagging():
    return await api_service.retry_tagging_service()

@api_blueprint.route('/bulk_retry_tagging', methods=['POST'])
async def bulk_retry_tagging():
    return await api_service.bulk_retry_tagging_service()

@api_blueprint.route('/switch_source', methods=['POST'])
async def switch_source():
    try:
        data = await request.json
        filepath = data.get('filepath')
        source = data.get('source')

        if not filepath or not source:
            return jsonify({"error": "Missing filepath or source"}), 400

        # Handle special "merged" source
        if source == 'merged':
            result = merge_all_sources(filepath)
        else:
            result = switch_metadata_source_db(filepath, source)

        if "error" in result:
            return jsonify(result), 400

        # Selective reload: only update this image
        models.reload_single_image(filepath.replace('images/', '', 1))

        return jsonify(result), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

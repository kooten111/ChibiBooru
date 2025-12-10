from quart import request, jsonify
from . import api_blueprint
from database import models
from utils.api_responses import success_response, error_response, not_found_response, server_error_response

@api_blueprint.route('/pools/create', methods=['POST'])
async def create_pool():
    try:
        data = await request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return error_response("Pool name is required", 400)

        pool_id = models.create_pool(name, description)
        return success_response(
            data={"pool_id": pool_id},
            message=f"Pool '{name}' created successfully."
        )

    except Exception as e:
        return server_error_response(e)

@api_blueprint.route('/pools/<int:pool_id>/update', methods=['POST'])
async def update_pool(pool_id):
    try:
        data = await request.json
        name = data.get('name')
        description = data.get('description')

        if not name and not description:
            return error_response("At least one field (name or description) is required", 400)

        models.update_pool(pool_id, name, description)
        return success_response(message="Pool updated successfully.")

    except Exception as e:
        return server_error_response(e)

@api_blueprint.route('/pools/<int:pool_id>/delete', methods=['POST'])
async def delete_pool(pool_id):
    try:
        models.delete_pool(pool_id)
        return jsonify({"status": "success", "message": "Pool deleted successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/add_image', methods=['POST'])
async def add_image_to_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return not_found_response("Image not found")

        image_id = image_data['id']
        models.add_image_to_pool(pool_id, image_id)
        return success_response(message="Image added to pool.")

    except Exception as e:
        return server_error_response(e)

@api_blueprint.route('/pools/<int:pool_id>/remove_image', methods=['POST'])
async def remove_image_from_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.remove_image_from_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image removed from pool."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/reorder', methods=['POST'])
async def reorder_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)
        new_position = data.get('position')

        if new_position is None:
            return jsonify({"error": "Position is required"}), 400

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.reorder_pool_images(pool_id, image_id, new_position)
        return jsonify({"status": "success", "message": "Pool reordered successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/for_image', methods=['GET'])
async def get_pools_for_image():
    try:
        filepath = request.args.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        pools = models.get_pools_for_image(image_id)
        return jsonify({"pools": pools})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/all', methods=['GET'])
async def get_all_pools():
    try:
        pools = models.get_all_pools()
        # Add image counts
        for pool in pools:
            pool_details = models.get_pool_details(pool['id'])
            pool['image_count'] = len(pool_details['images']) if pool_details else 0
        return jsonify({"pools": pools})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

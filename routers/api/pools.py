from quart import request, jsonify
from . import api_blueprint
from database import models
from utils import api_handler
from utils.file_utils import normalize_image_path
from utils.validation import validate_string

@api_blueprint.route('/pools/create', methods=['POST'])
@api_handler()
async def create_pool():
    """Create a new pool."""
    data = await request.json
    if not data:
        raise ValueError("Request body is required")
    
    name = validate_string(data.get('name', ''), 'name', min_length=1, max_length=200)
    description = data.get('description', '').strip() if data.get('description') else ''
    if description:
        description = validate_string(description, 'description', max_length=1000, allow_empty=True)

    pool_id = models.create_pool(name, description)
    return {
        "pool_id": pool_id,
        "message": f"Pool '{name}' created successfully."
    }

@api_blueprint.route('/pools/<int:pool_id>/update', methods=['POST'])
@api_handler()
async def update_pool(pool_id: int):
    """Update a pool's name or description."""
    from utils.validation import validate_integer
    
    validate_integer(pool_id, 'pool_id', min_value=1)
    
    data = await request.json
    if not data:
        raise ValueError("Request body is required")
    
    name = data.get('name')
    description = data.get('description')

    if not name and not description:
        raise ValueError("At least one field (name or description) is required")
    
    if name:
        name = validate_string(name, 'name', min_length=1, max_length=200)
    if description is not None:
        description = validate_string(description, 'description', max_length=1000, allow_empty=True)

    models.update_pool(pool_id, name, description)
    return {"message": "Pool updated successfully."}

@api_blueprint.route('/pools/<int:pool_id>/delete', methods=['POST'])
@api_handler()
async def delete_pool(pool_id):
    """Delete a pool."""
    models.delete_pool(pool_id)
    return {"message": "Pool deleted successfully."}

@api_blueprint.route('/pools/<int:pool_id>/add_image', methods=['POST'])
@api_handler()
async def add_image_to_pool(pool_id: int):
    """Add an image to a pool."""
    from utils.validation import validate_integer, validate_string
    
    validate_integer(pool_id, 'pool_id', min_value=1)
    
    data = await request.json
    if not data:
        raise ValueError("Request body is required")
    
    filepath = validate_string(data.get('filepath', ''), 'filepath', min_length=1)
    filepath = normalize_image_path(filepath)

    # Get image ID from filepath
    image_data = models.get_image_details(filepath)
    if not image_data:
        raise FileNotFoundError("Image not found")

    image_id = image_data['id']
    models.add_image_to_pool(pool_id, image_id)
    return {"message": "Image added to pool."}

@api_blueprint.route('/pools/<int:pool_id>/remove_image', methods=['POST'])
@api_handler()
async def remove_image_from_pool(pool_id):
    """Remove an image from a pool."""
    data = await request.json
    filepath = normalize_image_path(data.get('filepath', ''))

    # Get image ID from filepath
    image_data = models.get_image_details(filepath)
    if not image_data:
        raise FileNotFoundError("Image not found")

    image_id = image_data['id']
    models.remove_image_from_pool(pool_id, image_id)
    return {"message": "Image removed from pool."}

@api_blueprint.route('/pools/<int:pool_id>/reorder', methods=['POST'])
@api_handler()
async def reorder_pool(pool_id):
    """Reorder images in a pool."""
    data = await request.json
    filepath = normalize_image_path(data.get('filepath', ''))
    new_position = data.get('position')

    if new_position is None:
        raise ValueError("Position is required")

    # Get image ID from filepath
    image_data = models.get_image_details(filepath)
    if not image_data:
        raise FileNotFoundError("Image not found")

    image_id = image_data['id']
    models.reorder_pool_images(pool_id, image_id, new_position)
    return {"message": "Pool reordered successfully."}

@api_blueprint.route('/pools/for_image', methods=['GET'])
@api_handler()
async def get_pools_for_image():
    """Get all pools containing a specific image."""
    filepath = normalize_image_path(request.args.get('filepath', ''))

    # Get image ID from filepath
    image_data = models.get_image_details(filepath)
    if not image_data:
        raise FileNotFoundError("Image not found")

    image_id = image_data['id']
    pools = models.get_pools_for_image(image_id)
    return {"pools": pools}

@api_blueprint.route('/pools/all', methods=['GET'])
@api_handler()
async def get_all_pools():
    """Get all pools with image counts."""
    pools = models.get_all_pools()
    # Add image counts
    for pool in pools:
        pool_details = models.get_pool_details(pool['id'])
        pool['image_count'] = len(pool_details['images']) if pool_details else 0
    return {"pools": pools}

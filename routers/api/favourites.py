"""
Favourites API Routes

API endpoints for managing user favourites.
"""

from quart import request
from . import api_blueprint
from database import models
from repositories import favourites_repository
from utils import api_handler


@api_blueprint.route('/favourites/toggle', methods=['POST'])
@api_handler()
async def toggle_favourite():
    """Toggle favourite status for an image."""
    data = await request.json
    filepath = data.get('filepath', '')
    
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    if not filepath:
        raise ValueError("Filepath is required")
    
    # Get image ID from filepath
    image_id = favourites_repository.get_image_id_by_filepath(filepath)
    if not image_id:
        raise FileNotFoundError("Image not found")
    
    # Toggle and return new state
    is_favourite = favourites_repository.toggle_favourite(image_id)
    
    return {
        "is_favourite": is_favourite,
        "message": "Added to favourites" if is_favourite else "Removed from favourites"
    }


@api_blueprint.route('/favourites/status', methods=['GET'])
@api_handler()
async def get_favourite_status():
    """Get favourite status for an image."""
    filepath = request.args.get('filepath', '')
    
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    if not filepath:
        raise ValueError("Filepath is required")
    
    is_favourite = favourites_repository.is_favourite_by_filepath(filepath)
    
    return {"is_favourite": is_favourite}


@api_blueprint.route('/favourites/count', methods=['GET'])
@api_handler()
async def get_favourites_count():
    """Get total count of favourited images."""
    count = favourites_repository.get_favourites_count()
    return {"count": count}

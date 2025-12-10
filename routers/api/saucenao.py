from quart import request, jsonify
from . import api_blueprint
from services import saucenao_service
from utils import api_handler

@api_blueprint.route('/saucenao/search', methods=['POST'])
@api_handler()
async def saucenao_search():
    """Search SauceNAO for similar images."""
    return await saucenao_service.saucenao_search_service()

@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
@api_handler()
async def saucenao_fetch_metadata():
    """Fetch metadata from SauceNAO search results."""
    return await saucenao_service.saucenao_fetch_metadata_service()

@api_blueprint.route('/saucenao/apply', methods=['POST'])
@api_handler()
async def saucenao_apply():
    """Apply SauceNAO metadata to an image."""
    return await saucenao_service.saucenao_apply_service()

from quart import request, jsonify
from . import api_blueprint
from services import api_service

@api_blueprint.route('/saucenao/search', methods=['POST'])
async def saucenao_search():
    return await api_service.saucenao_search_service()

@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
async def saucenao_fetch_metadata():
    return await api_service.saucenao_fetch_metadata_service()

@api_blueprint.route('/saucenao/apply', methods=['POST'])
async def saucenao_apply():
    return await api_service.saucenao_apply_service()

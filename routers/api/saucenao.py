from quart import request, jsonify, url_for
from . import api_blueprint
from services import saucenao_service
from utils import api_handler
from utils.request_helpers import require_json_body
import config
import asyncio

def _check_saucenao_secret(data: dict) -> None:
    """Raise PermissionError if secret is missing or invalid."""
    secret = data.get('secret', '')
    if secret != config.SYSTEM_API_SECRET:
        raise PermissionError("Unauthorized")


@api_blueprint.route('/saucenao/search', methods=['POST'])
@api_handler()
async def saucenao_search():
    """Search SauceNAO for similar images."""
    data = await require_json_body(request)
    _check_saucenao_secret(data)
    result = await asyncio.to_thread(saucenao_service.saucenao_search, data)
    return result


@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
@api_handler()
async def saucenao_fetch_metadata():
    """Fetch metadata from SauceNAO search results."""
    data = await require_json_body(request)
    _check_saucenao_secret(data)
    result = await asyncio.to_thread(saucenao_service.saucenao_fetch_metadata, data)
    return result


@api_blueprint.route('/saucenao/apply', methods=['POST'])
@api_handler()
async def saucenao_apply():
    """Apply SauceNAO metadata to an image."""
    data = await require_json_body(request)
    _check_saucenao_secret(data)
    result = await asyncio.to_thread(saucenao_service.saucenao_apply, data)
    if "redirect_path" in result:
        result["redirect_url"] = url_for("main.show_image", filepath=result.pop("redirect_path"))
    return result

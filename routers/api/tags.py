from quart import request, jsonify
from . import api_blueprint
from services import tag_service
from database import models

@api_blueprint.route('/tags/fetch')
async def fetch_tags():
    """API endpoint for fetching tags with pagination and filtering."""
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 100))
    search = request.args.get('search', '').lower().strip()
    category = request.args.get('category', 'all')

    # Use optimized SQL search
    tags_page, total = models.search_tags(search, category, limit, offset)

    return jsonify({
        'tags': tags_page,
        'total': total,
        'offset': offset,
        'limit': limit,
        'hasMore': offset + limit < total
    })

@api_blueprint.route('/autocomplete')
async def autocomplete():
    return tag_service.autocomplete()

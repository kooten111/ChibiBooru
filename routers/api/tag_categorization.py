from quart import request, jsonify, Response
from . import api_blueprint
from services import tag_categorization_service as tag_cat
from database import models, get_db_connection
from utils import api_handler
import json


@api_blueprint.route('/tag_categorize/stats', methods=['GET'])
@api_handler()
async def api_tag_categorization_stats():
    """Get statistics about tag categorization status."""
    # By default, skip the expensive "meaningful" stats for faster page load
    # Frontend can request full stats with ?full=true if needed
    include_meaningful = request.args.get('full', 'false').lower() == 'true'
    stats = tag_cat.get_categorization_stats(include_meaningful=include_meaningful)
    return stats


@api_blueprint.route('/tag_categorize/tags', methods=['GET'])
@api_handler()
async def api_get_uncategorized_tags():
    """Get uncategorized tags sorted by frequency for categorization interface."""
    limit = request.args.get('limit', 100, type=int)
    tags = tag_cat.get_uncategorized_tags_by_frequency(limit)

    return {
        'tags': tags,
        'count': len(tags),
        'categories': tag_cat.TAG_CATEGORIES,
        'extended_categories': tag_cat.EXTENDED_CATEGORIES
    }


@api_blueprint.route('/tag_categorize/set', methods=['POST'])
@api_handler()
async def api_set_tag_category():
    """Set category for a tag."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    tag_name = data.get('tag_name')
    category = data.get('category')

    if not tag_name:
        raise ValueError("tag_name is required")

    # Validate category if provided
    if category and category not in tag_cat.TAG_CATEGORIES:
        raise ValueError(f"Invalid category. Must be one of: {', '.join(tag_cat.TAG_CATEGORIES)}")

    result = tag_cat.set_tag_category(tag_name, category)

    # Reload data to update in-memory cache (async to avoid blocking)
    from core.cache_manager import trigger_cache_reload_async
    trigger_cache_reload_async()

    return result


@api_blueprint.route('/tag_categorize/tag_details', methods=['GET'])
@api_handler()
async def api_get_tag_details():
    """Get detailed information about a tag including suggestions."""
    tag_name = request.args.get('tag_name')

    if not tag_name:
        raise ValueError("tag_name parameter is required")

    details = tag_cat.get_tag_details(tag_name)
    return details


@api_blueprint.route('/tag_categorize/bulk', methods=['POST'])
@api_handler()
async def api_bulk_categorize():
    """Categorize multiple tags at once."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    categorizations = data.get('categorizations', [])

    if not categorizations:
        raise ValueError("categorizations array is required")

    # Convert to list of tuples
    cat_tuples = [(item['tag_name'], item['category']) for item in categorizations]

    result = tag_cat.bulk_categorize_tags(cat_tuples)

    # Reload data to update in-memory cache (async to avoid blocking)
    from core.cache_manager import trigger_cache_reload_async
    trigger_cache_reload_async()

    return result


@api_blueprint.route('/tag_categorize/suggest', methods=['GET'])
@api_handler()
async def api_suggest_category():
    """Suggest a category for a tag based on patterns and co-occurrence."""
    tag_name = request.args.get('tag_name')

    if not tag_name:
        raise ValueError("tag_name parameter is required")

    suggested = tag_cat.suggest_category_for_tag(tag_name)

    return {
        'tag_name': tag_name,
        'suggested_category': suggested
    }


@api_blueprint.route('/tag_categorize/export', methods=['GET'])
@api_handler()
async def api_export_categorizations():
    """Export tag categorizations as JSON."""
    categorized_only = request.args.get('categorized_only', 'false').lower() == 'true'
    export_data = tag_cat.export_tag_categorizations(categorized_only=categorized_only)

    response = Response(
        json.dumps(export_data, indent=2),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="tag_categorizations_{export_data["export_date"]}.json"'
        }
    )
    return response


@api_blueprint.route('/tag_categorize/import', methods=['POST'])
@api_handler()
async def api_import_categorizations():
    """Import tag categorizations from JSON."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    mode = request.args.get('mode', 'merge')
    if mode not in ['merge', 'overwrite', 'update']:
        raise ValueError("Invalid mode. Must be one of: merge, overwrite, update")

    stats = tag_cat.import_tag_categorizations(data, mode=mode)

    # Reload data to update in-memory cache (async to avoid blocking)
    from core.cache_manager import trigger_cache_reload_async
    trigger_cache_reload_async()

    return stats


@api_blueprint.route('/tag_categorize/sync_base_categories', methods=['POST'])
@api_handler()
async def api_sync_base_categories():
    """Sync base categories from extended categories."""
    stats = tag_cat.sync_base_categories_from_extended()

    # Reload data to update in-memory cache (async to avoid blocking)
    from core.cache_manager import trigger_cache_reload_async
    trigger_cache_reload_async()

    return stats


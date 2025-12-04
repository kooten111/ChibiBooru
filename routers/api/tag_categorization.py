from quart import request, jsonify
from . import api_blueprint
from services import tag_categorization_service as tag_cat
from database import models, get_db_connection


@api_blueprint.route('/tag_categorize/stats', methods=['GET'])
async def api_tag_categorization_stats():
    """Get statistics about tag categorization status."""
    try:
        stats = tag_cat.get_categorization_stats()
        return jsonify(stats)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@api_blueprint.route('/tag_categorize/tags', methods=['GET'])
async def api_get_uncategorized_tags():
    """Get uncategorized tags sorted by frequency for categorization interface."""
    try:
        limit = request.args.get('limit', 100, type=int)
        tags = tag_cat.get_uncategorized_tags_by_frequency(limit)

        return jsonify({
            'tags': tags,
            'count': len(tags),
            'categories': tag_cat.TAG_CATEGORIES,
            'extended_categories': tag_cat.EXTENDED_CATEGORIES
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@api_blueprint.route('/tag_categorize/set', methods=['POST'])
async def api_set_tag_category():
    """Set category for a tag."""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400

        tag_name = data.get('tag_name')
        category = data.get('category')

        if not tag_name:
            return jsonify({
                "success": False,
                "error": "tag_name is required"
            }), 400

        # Validate category if provided
        if category and category not in tag_cat.TAG_CATEGORIES:
            return jsonify({
                "success": False,
                "error": f"Invalid category. Must be one of: {', '.join(tag_cat.TAG_CATEGORIES)}"
            }), 400

        result = tag_cat.set_tag_category(tag_name, category)

        # Reload data to update in-memory cache
        models.load_data_from_db()

        return jsonify({
            "success": True,
            **result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/tag_categorize/tag_details', methods=['GET'])
async def api_get_tag_details():
    """Get detailed information about a tag including suggestions."""
    try:
        tag_name = request.args.get('tag_name')

        if not tag_name:
            return jsonify({
                "error": "tag_name parameter is required"
            }), 400

        details = tag_cat.get_tag_details(tag_name)
        return jsonify(details)
    except ValueError as e:
        return jsonify({
            "error": str(e)
        }), 404
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@api_blueprint.route('/tag_categorize/bulk', methods=['POST'])
async def api_bulk_categorize():
    """Categorize multiple tags at once."""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400

        categorizations = data.get('categorizations', [])

        if not categorizations:
            return jsonify({
                "success": False,
                "error": "categorizations array is required"
            }), 400

        # Convert to list of tuples
        cat_tuples = [(item['tag_name'], item['category']) for item in categorizations]

        result = tag_cat.bulk_categorize_tags(cat_tuples)

        # Reload data to update in-memory cache
        models.load_data_from_db()

        return jsonify({
            "success": True,
            **result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/tag_categorize/suggest', methods=['GET'])
async def api_suggest_category():
    """Suggest a category for a tag based on patterns and co-occurrence."""
    try:
        tag_name = request.args.get('tag_name')

        if not tag_name:
            return jsonify({
                "error": "tag_name parameter is required"
            }), 400

        suggested = tag_cat.suggest_category_for_tag(tag_name)

        return jsonify({
            'tag_name': tag_name,
            'suggested_category': suggested
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

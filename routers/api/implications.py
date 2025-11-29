from quart import request, jsonify
from . import api_blueprint

@api_blueprint.route('/implications/suggestions', methods=['GET'])
async def get_implication_suggestions():
    """Get all auto-detected implication suggestions."""
    try:
        from services import implication_service
        suggestions = implication_service.get_all_suggestions()
        return jsonify(suggestions)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/approve', methods=['POST'])
async def approve_implication():
    """Approve a suggestion and create the implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')
        inference_type = data.get('inference_type', 'manual')
        confidence = data.get('confidence', 1.0)

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.approve_suggestion(
            source_tag, implied_tag, inference_type, confidence
        )

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication created: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Failed to create implication"}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/create', methods=['POST'])
async def create_implication():
    """Create a manual implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.create_manual_implication(source_tag, implied_tag)

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication created: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Failed to create implication (tags may not exist)"}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/delete', methods=['POST'])
async def delete_implication():
    """Delete an implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.delete_implication(source_tag, implied_tag)

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication deleted: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Implication not found"}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/all', methods=['GET'])
async def get_all_implications():
    """Get all existing implications."""
    try:
        from services import implication_service
        implications = implication_service.get_all_implications()
        return jsonify({"implications": implications})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/chain/<tag_name>', methods=['GET'])
async def get_implication_chain(tag_name):
    """Get the full implication chain for a tag."""
    try:
        from services import implication_service
        chain = implication_service.get_implication_chain(tag_name)
        return jsonify(chain)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/preview', methods=['POST'])
async def preview_implication():
    """Preview the impact of creating an implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        impact = implication_service.preview_implication_impact(source_tag, implied_tag)
        return jsonify(impact)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/batch_apply', methods=['POST'])
async def batch_apply_implications():
    """Apply all implications to all existing images."""
    try:
        from services import implication_service
        count = implication_service.batch_apply_implications_to_all_images()
        return jsonify({
            "status": "success",
            "message": f"Applied implications to {count} images"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

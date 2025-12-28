from quart import request, jsonify
from . import api_blueprint
from utils import api_handler

@api_blueprint.route('/implications/suggestions', methods=['GET'])
@api_handler()
async def get_implication_suggestions():
    """Get paginated auto-detected implication suggestions."""
    from services import implication_service
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    pattern_type = request.args.get('type', None)
    
    # Clamp values to reasonable ranges
    page = max(1, page)
    limit = max(1, min(200, limit))
    
    return implication_service.get_paginated_suggestions(page, limit, pattern_type)


@api_blueprint.route('/implications/approve', methods=['POST'])
@api_handler()
async def approve_implication():
    """Approve a suggestion and create the implication."""
    from services import implication_service
    data = await request.json
    source_tag = data.get('source_tag')
    implied_tag = data.get('implied_tag')
    inference_type = data.get('inference_type', 'manual')
    confidence = data.get('confidence', 1.0)

    if not source_tag or not implied_tag:
        raise ValueError("Missing source_tag or implied_tag")

    success = implication_service.approve_suggestion(
        source_tag, implied_tag, inference_type, confidence
    )

    if not success:
        raise ValueError("Failed to create implication")

    # Invalidate cache so next fetch reflects the approval
    implication_service.invalidate_suggestion_cache()
    
    return {"message": f"Implication created: {source_tag} → {implied_tag}"}


@api_blueprint.route('/implications/create', methods=['POST'])
@api_handler()
async def create_implication():
    """Create a manual implication."""
    from services import implication_service
    data = await request.json
    source_tag = data.get('source_tag')
    implied_tag = data.get('implied_tag')

    if not source_tag or not implied_tag:
        raise ValueError("Missing source_tag or implied_tag")

    success = implication_service.create_manual_implication(source_tag, implied_tag)

    if not success:
        raise ValueError("Failed to create implication (tags may not exist)")

    return {"message": f"Implication created: {source_tag} → {implied_tag}"}


@api_blueprint.route('/implications/delete', methods=['POST'])
@api_handler()
async def delete_implication():
    """Delete an implication."""
    from services import implication_service
    data = await request.json
    source_tag = data.get('source_tag')
    implied_tag = data.get('implied_tag')

    if not source_tag or not implied_tag:
        raise ValueError("Missing source_tag or implied_tag")

    success = implication_service.delete_implication(source_tag, implied_tag)

    if not success:
        raise FileNotFoundError("Implication not found")

    return {"message": f"Implication deleted: {source_tag} → {implied_tag}"}


@api_blueprint.route('/implications/all', methods=['GET'])
@api_handler()
async def get_all_implications():
    """Get all existing implications."""
    from services import implication_service
    implications = implication_service.get_all_implications()
    return {"implications": implications}


@api_blueprint.route('/implications/chain/<tag_name>', methods=['GET'])
@api_handler()
async def get_implication_chain(tag_name):
    """Get the full implication chain for a tag."""
    from services import implication_service
    chain = implication_service.get_implication_chain(tag_name)
    return chain


@api_blueprint.route('/implications/preview', methods=['POST'])
@api_handler()
async def preview_implication():
    """Preview the impact of creating an implication."""
    from services import implication_service
    data = await request.json
    source_tag = data.get('source_tag')
    implied_tag = data.get('implied_tag')

    if not source_tag or not implied_tag:
        raise ValueError("Missing source_tag or implied_tag")

    impact = implication_service.preview_implication_impact(source_tag, implied_tag)
    return impact


@api_blueprint.route('/implications/batch_apply', methods=['POST'])
@api_handler()
async def batch_apply_implications():
    """Apply all implications to all existing images."""
    from services import implication_service
    count = implication_service.batch_apply_implications_to_all_images()
    return {"message": f"Applied implications to {count} images"}


@api_blueprint.route('/implications/for-tag/<tag_name>', methods=['GET'])
@api_handler()
async def get_implications_for_tag(tag_name):
    """Get all implications where this tag is source OR target, plus suggestions."""
    from services import implication_service
    result = implication_service.get_implications_for_tag(tag_name)
    return result


@api_blueprint.route('/implications/bulk-approve', methods=['POST'])
@api_handler()
async def bulk_approve_implications():
    """Approve multiple suggestions at once."""
    from services import implication_service
    data = await request.json
    suggestions = data.get('suggestions', [])
    
    if not suggestions:
        raise ValueError("No suggestions provided")
    
    result = implication_service.bulk_approve_implications(suggestions)
    
    # Invalidate cache so next fetch reflects the approvals
    implication_service.invalidate_suggestion_cache()
    
    return result

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
    
    # Robustly get list filters (check both with and without brackets)
    source_categories = request.args.getlist('source_categories[]')
    if not source_categories:
        source_categories = request.args.getlist('source_categories')
        
    implied_categories = request.args.getlist('implied_categories[]')
    if not implied_categories:
        implied_categories = request.args.getlist('implied_categories')
    
    # Also support comma-separated if passed as single string
    if not source_categories and request.args.get('source_categories'):
        val = request.args.get('source_categories')
        source_categories = val.split(',') if val else []
        
    if not implied_categories and request.args.get('implied_categories'):
        val = request.args.get('implied_categories')
        implied_categories = val.split(',') if val else []
    
    # Clean up empty strings if any
    source_categories = [c for c in source_categories if c]
    implied_categories = [c for c in implied_categories if c]
        
    # Clamp values to reasonable ranges
    page = max(1, page)
    limit = max(1, min(200, limit))
    
    return implication_service.get_paginated_suggestions(
        page, limit, pattern_type, source_categories, implied_categories
    )


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
    apply_now = data.get('apply_now', False)  # Option to apply to existing images

    if not source_tag or not implied_tag:
        raise ValueError("Missing source_tag or implied_tag")

    success = implication_service.approve_suggestion(
        source_tag, implied_tag, inference_type, confidence
    )

    if not success:
        raise ValueError("Failed to create implication")

    # Invalidate cache so next fetch reflects the approval
    implication_service.invalidate_suggestion_cache()
    
    # Apply to existing images if requested
    applied_count = 0
    if apply_now:
        applied_count = implication_service.apply_single_implication_to_images(source_tag, implied_tag)
    
    message = f"Implication created: {source_tag} → {implied_tag}"
    if apply_now:
        message += f" (applied to {applied_count} images)"
    
    return {"message": message, "applied_count": applied_count}


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


@api_blueprint.route('/implications/auto-approve-pattern', methods=['POST'])
@api_handler()
async def auto_approve_naming_patterns():
    """Auto-approve all naming pattern suggestions (character_(copyright) → copyright)."""
    from services import implication_service
    
    result = implication_service.auto_approve_naming_pattern_suggestions()
    
    return result


@api_blueprint.route('/implications/auto-approve-confident', methods=['POST'])
@api_handler()
async def auto_approve_high_confidence():
    """Auto-approve high-confidence correlation suggestions with statistical significance."""
    from services import implication_service
    data = await request.json or {}
    
    min_confidence = data.get('min_confidence', 0.95)
    min_sample_size = data.get('min_sample_size', 10)
    source_categories = data.get('source_categories')
    implied_categories = data.get('implied_categories')
    apply_now = data.get('apply_now', False)
    
    result = implication_service.auto_approve_high_confidence_suggestions(
        min_confidence=min_confidence,
        min_sample_size=min_sample_size,
        source_categories=source_categories,
        implied_categories=implied_categories,
        apply_now=apply_now
    )
    
    return result


@api_blueprint.route('/implications/clear-and-reapply', methods=['POST'])
@api_handler()
async def clear_and_reapply_implications():
    """Clear all implied tags and reapply all implications. Debug/maintenance operation."""
    from services import implication_service
    result = implication_service.clear_and_reapply_all_implications()
    return result


@api_blueprint.route('/implications/clear-tags', methods=['POST'])
@api_handler()
async def clear_implied_tags_only():
    """Just clear all implied tags without reapplying. Debug operation."""
    from services import implication_service
    count = implication_service.clear_implied_tags()
    return {"message": f"Cleared {count} implied tags", "count": count}

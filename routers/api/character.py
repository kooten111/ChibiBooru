from quart import request, jsonify
from . import api_blueprint
from services import character_service
from database import get_db_connection
from utils import api_handler, success_response, error_response
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Character Inference API Endpoints
# ============================================================================

@api_blueprint.route('/character/train', methods=['POST'])
@api_handler()
async def api_train_character_model():
    """Train the character inference model via ML Worker."""
    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        stats = client.train_character_model(timeout=600.0)
        return {"stats": stats, "source": "ml_worker"}
    except Exception as e:
        logger.warning(f"ML Worker unavailable, falling back to direct training: {e}")
        # Fallback to direct call if ML Worker unavailable
        stats = character_service.train_model()
        return {"stats": stats, "source": "direct", "warning": "ML Worker unavailable"}


@api_blueprint.route('/character/infer', methods=['POST'])
@api_handler()
async def api_infer_characters():
    """Run inference on untagged images or a specific image via ML Worker."""
    data = await request.get_json() or {}
    image_id = data.get('image_id')

    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        
        if image_id:
            # Infer single image
            result = client.infer_characters(image_ids=[image_id], timeout=60.0)
            return {"result": result, "source": "ml_worker"}
        else:
            # Infer all untagged images
            stats = client.infer_characters(image_ids=None, timeout=600.0)
            return {"stats": stats, "source": "ml_worker"}
    except Exception as e:
        logger.warning(f"ML Worker unavailable, falling back to direct inference: {e}")
        # Fallback to direct call if ML Worker unavailable
        if image_id:
            result = character_service.infer_character_for_image(image_id)
            return {"result": result, "source": "direct", "warning": "ML Worker unavailable"}
        else:
            stats = character_service.infer_all_untagged_images()
            return {"stats": stats, "source": "direct", "warning": "ML Worker unavailable"}


@api_blueprint.route('/character/infer/<int:image_id>', methods=['POST'])
@api_handler()
async def api_infer_character_single(image_id):
    """Run inference on a specific image."""
    result = character_service.infer_character_for_image(image_id)
    return {"result": result}


@api_blueprint.route('/character/predict/<int:image_id>', methods=['GET'])
@api_handler()
async def api_predict_character(image_id):
    """Get character predictions for an image without applying them."""
    # Get image tags (excluding existing character tags)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.name
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ?
              AND t.category != 'character'
        """, (image_id,))

        tags = [row['name'] for row in cur.fetchall()]

    if not tags:
        return {'predictions': [], 'tags': tags}

    # Predict characters
    predictions = character_service.predict_characters(tags)

    # Format predictions with detailed breakdown
    detailed_predictions = []
    tag_weights, pair_weights = character_service.load_weights()
    config = character_service.get_config()

    for character, confidence in predictions:
        # Get contributing tags
        contributing_tags = []
        for tag in tags:
            weight = tag_weights.get((tag, character), 0.0)
            if abs(weight) > 0.01:
                contributing_tags.append({
                    'tag': tag,
                    'weight': round(weight, 3)
                })
        
        contributing_tags.sort(key=lambda x: abs(x['weight']), reverse=True)

        detailed_predictions.append({
            'character': character,
            'confidence': round(confidence, 3),
            'contributing_tags': contributing_tags[:10]  # Top 10 contributing tags
        })

    return {
        'predictions': detailed_predictions,
        'tags': tags,
        'image_id': image_id
    }


@api_blueprint.route('/character/apply/<int:image_id>', methods=['POST'])
@api_handler()
async def api_apply_character(image_id):
    """Apply predicted character tags to an image."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    characters = data.get('characters', [])
    
    if not characters:
        raise ValueError("No characters provided")

    results = []
    for character in characters:
        result = character_service.set_image_character(
            image_id, 
            character, 
            source='user',  # User explicitly applying, so mark as user
            add=True
        )
        results.append(result)

    # Reload data to update in-memory cache
    from core.cache_manager import load_data_from_db_async
    load_data_from_db_async()

    return {'results': results}


@api_blueprint.route('/character/clear_ai', methods=['POST'])
@api_handler()
async def api_clear_ai_characters():
    """Remove all AI-inferred character tags."""
    deleted_count = character_service.clear_ai_inferred_characters()
    return {"deleted_count": deleted_count}


@api_blueprint.route('/character/retrain_all', methods=['POST'])
@api_handler()
async def api_retrain_all_characters():
    """Clear AI characters, retrain, and re-infer everything."""
    result = character_service.retrain_and_reapply_all()
    return result


@api_blueprint.route('/character/stats', methods=['GET'])
@api_handler()
async def api_character_stats():
    """Get model statistics and configuration."""
    stats = character_service.get_model_stats()
    return stats


@api_blueprint.route('/character/config', methods=['GET'])
@api_handler()
async def api_get_character_config():
    """Get current configuration."""
    config = character_service.get_config()
    return {"config": config}


@api_blueprint.route('/character/config', methods=['POST'])
@api_handler()
async def api_update_character_config():
    """Update inference configuration."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    updated = []
    for key, value in data.items():
        try:
            character_service.update_config(key, float(value))
            updated.append(key)
        except Exception as e:
            raise ValueError(f"Failed to update {key}: {str(e)}")

    return {"updated": updated}


@api_blueprint.route('/character/characters', methods=['GET'])
@api_handler()
async def api_get_all_characters():
    """Get list of all known characters with sample counts (with pagination support)."""
    # Get pagination parameters with safety limits
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 100, type=int), 200)  # Max 200 per page
    search = request.args.get('search', '').strip()
    
    # Use paginated query at database level (much more memory efficient!)
    characters_page, total_count = character_service.get_known_characters_paginated(
        page=page, 
        per_page=per_page, 
        search=search if search else None
    )
    
    # Only get distribution if explicitly requested (it can be slow on large databases)
    include_distribution = request.args.get('include_distribution', 'false').lower() == 'true'
    if include_distribution and characters_page:
        character_names = [c['name'] for c in characters_page]
        distribution = character_service.get_character_distribution_for_characters(character_names)
        
        # Merge the data
        for char_info in characters_page:
            char_name = char_info['name']
            if char_name in distribution:
                char_info.update(distribution[char_name])
            else:
                char_info.update({'total': 0, 'ai': 0, 'user': 0, 'original': 0})
    else:
        # Set defaults without querying
        for char_info in characters_page:
            char_info.update({'total': 0, 'ai': 0, 'user': 0, 'original': 0})
    
    return {
        "characters": characters_page,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_count,
            "pages": (total_count + per_page - 1) // per_page
        }
    }


@api_blueprint.route('/character/top_tags', methods=['GET'])
@api_handler()
async def api_top_weighted_tags_character():
    """Get highest-weighted tags for a character."""
    character = request.args.get('character')
    limit = request.args.get('limit', 50, type=int)

    if not character:
        raise ValueError("character parameter is required")

    result = character_service.get_top_weighted_tags(character, limit)
    return {
        "character": character,
        **result
    }


@api_blueprint.route('/character/precompute', methods=['POST'])
@api_handler()
async def api_precompute_predictions():
    """Pre-compute and store character predictions for untagged images (without applying them)."""
    import uuid
    import asyncio
    from services.background_tasks import task_manager
    from services import monitor_service
    
    data = await request.get_json() or {}
    limit = data.get('limit')  # Optional limit
    batch_size = data.get('batch_size', 500)  # Default batch size: 500 images per batch
    
    task_id = f"precompute_char_{uuid.uuid4().hex[:8]}"
    
    async def precompute_task(task_id, manager, limit, batch_size):
        """Background task for precomputing character predictions with progress updates."""
        from services import monitor_service as mon
        
        mon.add_log(f"Starting character prediction precomputation (batch size: {batch_size})...", "info")
        
        loop = asyncio.get_running_loop()
        
        import time
        last_update_time = 0
        
        def progress_callback(processed, total):
            nonlocal last_update_time
            current_time = time.time()
            
            # Throttle updates: only update if 0.1s passed OR it's the final update
            if (current_time - last_update_time > 0.1) or (processed >= total):
                last_update_time = current_time
                future = asyncio.run_coroutine_threadsafe(
                    manager.update_progress(
                        task_id, 
                        processed, 
                        total, 
                        f"Processing images... ({processed}/{total})"
                    ), 
                    loop
                )
                # We don't wait for the future
        
        try:
            # Run synchronous service function in thread
            stats = await asyncio.to_thread(
                character_service.precompute_predictions_for_untagged_images,
                limit=limit,
                progress_callback=progress_callback,
                batch_size=batch_size
            )
            
            processed = stats.get('processed', 0)
            total = stats.get('total', processed)  # Get total from stats, fallback to processed
            predictions_stored = stats.get('predictions_stored', 0)
            duration = stats.get('duration_seconds', 0)
            
            result_msg = f"✓ Precomputation complete: {processed} processed, {predictions_stored} predictions stored"
            if duration:
                result_msg += f" in {duration}s"
            mon.add_log(result_msg, "success")
            
            # Update task to 100%
            await manager.update_progress(task_id, total, total, "Complete")
            
            return {
                'processed': processed,
                'predictions_stored': predictions_stored,
                'skipped_no_tags': stats.get('skipped_no_tags', 0),
                'duration_seconds': duration,
                'message': f"Precomputed {predictions_stored} predictions for {processed} images"
            }
        except Exception as e:
            mon.add_log(f"Precomputation failed: {str(e)}", "error")
            raise
    
    # Start background task
    monitor_service.add_log("Character prediction precomputation task started...", "info")
    await task_manager.start_task(task_id, precompute_task, limit, batch_size)
    
    return {
        'status': 'started',
        'task_id': task_id,
        'message': 'Precomputation started in background'
    }


@api_blueprint.route('/character/images', methods=['GET'])
@api_handler()
async def api_get_images_for_character():
    """Get images for character review interface with predictions."""
    filter_type = request.args.get('filter', 'untagged')
    limit = request.args.get('limit', 50, type=int)
    include_predictions = request.args.get('include_predictions', 'true').lower() == 'true'

    with get_db_connection() as conn:
        cur = conn.cursor()

        if filter_type == 'untagged':
            # Get images without any character tag (from local_tagger)
            cur.execute("""
                SELECT i.id, i.filepath
                FROM images i
                WHERE i.active_source = 'local_tagger'
                  AND NOT EXISTS (
                      SELECT 1 FROM image_tags it
                      JOIN tags t ON it.tag_id = t.id
                      WHERE it.image_id = i.id
                        AND t.category = 'character'
                  )
                ORDER BY i.id
                LIMIT ?
            """, (limit,))

        elif filter_type == 'ai_predicted':
            # Get images with AI-predicted characters
            cur.execute("""
                SELECT DISTINCT i.id, i.filepath
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                WHERE t.category = 'character'
                  AND it.source = 'ai_inference'
                ORDER BY i.id
                LIMIT ?
            """, (limit,))

        else:  # 'all'
            # Get all images with any character tags
            cur.execute("""
                SELECT DISTINCT i.id, i.filepath
                FROM images i
                JOIN image_tags it ON i.id = it.image_id
                JOIN tags t ON it.tag_id = t.id
                WHERE t.category = 'character'
                ORDER BY i.id
                LIMIT ?
            """, (limit,))

        # Fetch all images first
        image_rows = cur.fetchall()
        image_ids = [row['id'] for row in image_rows]

        # Batch fetch all tags for all images in a single query
        tags_by_image = {}
        if image_ids:
            placeholders = ','.join('?' for _ in image_ids)
            cur.execute(f"""
                SELECT it.image_id, t.name, t.category, it.source
                FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id IN ({placeholders})
            """, image_ids)

            # Group tags by image_id
            for tag_row in cur.fetchall():
                img_id = tag_row['image_id']
                if img_id not in tags_by_image:
                    tags_by_image[img_id] = []
                tags_by_image[img_id].append({
                    'name': tag_row['name'],
                    'category': tag_row['category'],
                    'source': tag_row['source']
                })

        # Build images list with pre-fetched tags
        from utils.file_utils import get_thumbnail_path
        images = []
        
        # Load stored predictions if needed (much faster than computing on-the-fly)
        stored_predictions = {}
        if include_predictions and filter_type == 'untagged' and image_ids:
            try:
                from repositories.character_predictions_repository import get_predictions_for_images
                stored_predictions = get_predictions_for_images(image_ids)
            except Exception as e:
                logger.warning(f"Could not load stored predictions: {e}")
                stored_predictions = {}
        
        for row in image_rows:
            image_id = row['id']
            filepath = row['filepath']

            all_tags = tags_by_image.get(image_id, [])
            character_tags = [t for t in all_tags if t['category'] == 'character']
            other_tags = [t['name'] for t in all_tags if t['category'] != 'character']

            # Get character info
            characters = []
            ai_characters = []
            for ct in character_tags:
                char_info = {
                    'name': ct['name'],
                    'source': ct['source']
                }
                characters.append(char_info)
                if ct['source'] == 'ai_inference':
                    ai_characters.append(ct['name'])

            image_data = {
                'id': image_id,
                'filepath': filepath,
                'thumb': get_thumbnail_path(filepath),
                'characters': characters,
                'ai_characters': ai_characters,
                'tag_count': len(other_tags),
                'tags': other_tags
            }
            
            # Add stored predictions for untagged images (fast!)
            # DO NOT compute on-the-fly - it's too slow and causes memory issues
            if include_predictions and filter_type == 'untagged' and not characters:
                predictions = stored_predictions.get(image_id, [])
                # Only use stored predictions - never compute on-the-fly
                # Format predictions
                image_data['predictions'] = [
                    {
                        'character': pred['character'],
                        'confidence': round(pred['confidence'], 3)
                    }
                    for pred in predictions
                ]
            else:
                image_data['predictions'] = []

            images.append(image_data)

        return {
            'images': images,
            'count': len(images)
        }

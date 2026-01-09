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
    """Train the character inference model as a background task via subprocess (memory freed on exit)."""
    import uuid
    import asyncio
    import subprocess
    import json
    import os
    from services.background_tasks import task_manager
    from services import monitor_service
    
    task_id = f"train_char_{uuid.uuid4().hex[:8]}"
    
    async def train_task(task_id, manager):
        """Background task that runs the training worker and parses progress."""
        monitor_service.add_log("Starting character model training...", "info")
        await manager.update_progress(task_id, 0, 100, "Starting training...")
        
        worker_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'character_train_worker.py')
        python_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'venv', 'bin', 'python3')
        
        process = subprocess.Popen(
            [python_path, worker_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1, # Line buffered
            cwd=os.path.dirname(worker_script)
        )
        
        try:
            stats = {}
            # Read streaming output
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    line = line.strip()
                    if line.startswith('PROGRESS:'):
                        # Format: PROGRESS:percent:message
                        parts = line.split(':', 2)
                        if len(parts) >= 3:
                            percent = int(parts[1])
                            message = parts[2]
                            await manager.update_progress(task_id, percent, 100, message)
                    elif line.startswith('STATS_JSON:'):
                        try:
                            stats = json.loads(line[11:])
                        except:
                            pass
                    elif line.startswith('ERROR:'):
                         monitor_service.add_log(f"Training Worker Error: {line[6:]}", "error")

            # Check return code
            if process.poll() != 0:
                stderr = process.stderr.read()
                raise Exception(f"Training failed: {stderr}")
            
            # Use data from stats
            sample_count = stats.get('training_samples', 0)
            tag_count = stats.get('tag_weights_count', 0)
            pair_count = stats.get('pair_weights_count', 0)
            
            monitor_service.add_log(f"Training complete: {sample_count} samples, {tag_count} weights, {pair_count} pairs", "success")
            await manager.update_progress(task_id, 100, 100, "Training complete!")
            
            return {
                "success": True,
                "stats": stats
            }
            
        except Exception as e:
            process.kill()
            monitor_service.add_log(f"Training task crashed: {str(e)}", "error")
            raise e
            
    # Start the task
    await task_manager.start_task(task_id, train_task)
    
    return {"success": True, "task_id": task_id}


@api_blueprint.route('/character/infer', methods=['POST'])
@api_handler()
async def api_infer_characters():
    """Run inference as a subprocess (memory freed on exit)."""
    import asyncio
    import subprocess
    import json
    import os
    
    data = await request.get_json() or {}
    image_id = data.get('image_id')
    
    worker_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'character_infer_worker.py')
    python_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'venv', 'bin', 'python3')
    
    def run_inference():
        """Run inference in subprocess and parse results."""
        cmd = [python_path, worker_script]
        if image_id:
            cmd.extend(['--image-id', str(image_id)])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(worker_script)
        )
        
        # Parse output
        stats = {}
        inference_result = {}
        for line in result.stdout.split('\n'):
            if line.startswith('STATS_JSON:'):
                try:
                    stats = json.loads(line[11:])
                except:
                    pass
            elif line.startswith('RESULT_JSON:'):
                try:
                    inference_result = json.loads(line[12:])
                except:
                    pass
        
        if result.returncode != 0:
            raise Exception(f"Inference failed: {result.stderr}")
        
        return stats if not image_id else inference_result
    
    result_data = await asyncio.to_thread(run_inference)
    
    if image_id:
        return {"result": result_data, "source": "subprocess"}
    else:
        return {"stats": result_data, "source": "subprocess"}


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
    """Pre-compute and store character predictions using standalone workers."""
    import uuid
    import asyncio
    import subprocess
    import os
    from services.background_tasks import task_manager
    from services import monitor_service
    import config
    
    data = await request.get_json() or {}
    num_workers = data.get('num_workers', config.MAX_WORKERS)
    
    task_id = f"precompute_char_{uuid.uuid4().hex[:8]}"
    
    async def precompute_task(task_id, manager, num_workers):
        """Background task that launches and monitors worker processes."""
        from services import monitor_service as mon
        import time
        
        mon.add_log(f"Starting character prediction precomputation with {num_workers} workers...", "info")
        
        # Get total count for progress tracking
        total_count = character_service.get_untagged_character_images_count()
        await manager.update_progress(task_id, 0, total_count, f"Launching {num_workers} workers...")
        
        # Launch worker processes
        workers = []
        worker_script = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'character_worker.py')
        
        try:
            for i in range(num_workers):
                env = os.environ.copy()
                env['WORKER_ID'] = f'worker-{i+1}'
                env['API_BASE_URL'] = f'http://localhost:{config.FLASK_PORT}'
                env['BATCH_SIZE'] = '50'
                
                # Launch worker
                process = subprocess.Popen(
                    [os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'venv', 'bin', 'python3'), worker_script],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                workers.append(process)
                mon.add_log(f"Launched worker {i+1} (PID {process.pid})", "info")
            
            
            # Monitor progress by polling untagged count
            last_processed = 0
            start_time = time.time()
            
            while any(w.poll() is None for w in workers):
                await asyncio.sleep(1)
                
                # Check current progress from database
                current_untagged = character_service.get_untagged_character_images_count()
                current_processed = total_count - current_untagged
                
                if current_processed != last_processed:
                    last_processed = current_processed
                    elapsed = int(time.time() - start_time)
                    await manager.update_progress(
                        task_id, 
                        current_processed, 
                        total_count, 
                        f"Processing... ({current_processed}/{total_count}) - {elapsed}s elapsed"
                    )

                
            # Wait for all workers to complete
            for worker in workers:
                worker.wait()
                if worker.returncode != 0:
                    stderr = worker.stderr.read().decode() if worker.stderr else ""
                    mon.add_log(f"Worker {worker.pid} failed with code {worker.returncode}: {stderr[:200]}", "error")
            
            # Get final stats
            final_count = total_count - character_service.get_untagged_character_images_count()
            
            await manager.update_progress(task_id, total_count, total_count, "Complete")
            mon.add_log(f"✓ Precomputation complete: {final_count} images processed", "success")
            
            return {
                'processed': final_count,
                'num_workers': num_workers,
                'message': f'Processed {final_count} images with {num_workers} workers'
            }
            
        except Exception as e:
            # Clean up workers on error
            for worker in workers:
                if worker.poll() is None:
                    worker.terminate()
            mon.add_log(f"Precomputation failed: {str(e)}", "error")
            raise
    
    # Start background task
    monitor_service.add_log("Character prediction precomputation task started...", "info")
    await task_manager.start_task(task_id, precompute_task, num_workers)
    
    return {
        'status': 'started',
        'task_id': task_id,
        'message': f'Precomputation started with {num_workers} workers'
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

# ============================================================================
# Worker API Endpoints (for distributed processing)
# ============================================================================

@api_blueprint.route('/character/work', methods=['GET'])
@api_handler()
async def api_get_character_work():
    """
    Get a batch of work for character prediction workers.
    Workers pull batches dynamically to keep busy.
    """
    batch_size = int(request.args.get('batch_size', 50))
    worker_id = request.args.get('worker_id', 'unknown')
    
    import uuid
    from services import monitor_service
    
    # Get a batch of untagged images
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    
    try:
        images = character_service.get_untagged_character_images_batched(
            batch_size=batch_size,
            offset=0,  # Will track via session/state later if needed
            limit=batch_size
        )
        
        if not images:
            return {
                'images': [],
                'batch_id': None,
                'message': 'No more work available'
            }
        
        # Format for worker
        work_items = []
        for image_id, tags_with_extended in images:
            tag_names = [tag for tag, _ in tags_with_extended]
            work_items.append({
                'image_id': image_id,
                'tags': tag_names
            })
        
        monitor_service.add_log(f"Dispatched batch {batch_id} ({len(work_items)} images) to worker {worker_id}", "info")
        
        return {
            'images': work_items,
            'batch_id': batch_id,
            'count': len(work_items)
        }
        
    except Exception as e:
        logger.error(f"Error creating work batch: {e}", exc_info=True)
        return error_response(f"Failed to create work batch: {str(e)}")


@api_blueprint.route('/character/results', methods=['POST'])
@api_handler()
async def api_submit_character_results():
    """
    Accept processed results from a worker.
    Stores predictions in the database.
    """
    data = await request.get_json()
    batch_id = data.get('batch_id')
    worker_id = data.get('worker_id', 'unknown')
    results = data.get('results', {})
    
    from services import monitor_service
    from repositories.character_predictions_repository import store_predictions_batch
    
    try:
        predictions = results.get('predictions', {})
        stats = results.get('stats', {})
        
        if not predictions:
            monitor_service.add_log(f"Worker {worker_id} submitted batch {batch_id} with no predictions", "warning")
            return success_response("No predictions to store")
        
        # Store all predictions
        config = character_service.get_config()
        min_confidence = config.get('min_confidence', 0.3)
        
        # Convert string keys to int for image_id
        predictions_int_keys = {
            int(image_id): preds 
            for image_id, preds in predictions.items()
        }
        
        store_predictions_batch(predictions_int_keys, min_confidence=min_confidence)
        
        processed = stats.get('processed', 0)
        predictions_stored = stats.get('predictions_stored', 0)
        
        monitor_service.add_log(
            f"✓ Worker {worker_id} completed batch {batch_id}: {processed} processed, {predictions_stored} predictions stored",
            "success"
        )
        
        return success_response(f"Stored {predictions_stored} predictions from {processed} images")
        
    except Exception as e:
        logger.error(f"Error storing worker results: {e}", exc_info=True)
        return error_response(f"Failed to store results: {str(e)}")

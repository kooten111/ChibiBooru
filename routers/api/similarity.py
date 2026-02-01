"""
Similarity API Routes

Provides API endpoints for visual similarity operations using perceptual hashing.
"""
import asyncio
from quart import request, jsonify
from . import api_blueprint
from utils.decorators import api_handler, require_secret
from services import similarity_service
import config


@api_blueprint.route('/similar/<path:filepath>')
@api_handler()
async def get_similar_images(filepath):
    """
    Find visually similar images using perceptual hash.
    
    GET /api/similar/<filepath>?threshold=10&limit=50
    """
    # Clean filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    threshold = request.args.get('threshold', config.VISUAL_SIMILARITY_THRESHOLD, type=int)
    limit = request.args.get('limit', 50, type=int)
    exclude_family = request.args.get('exclude_family', 'false').lower() in ('true', '1', 'yes')
    color_weight = request.args.get('color_weight', 0.0, type=float)
    
    # Run in thread to not block
    similar = await asyncio.to_thread(
        similarity_service.find_similar_images,
        filepath,
        threshold=threshold,
        limit=limit,
        exclude_family=exclude_family,
        color_weight=color_weight
    )
    
    return {
        'similar': similar,
        'count': len(similar),
        'threshold': threshold,
        'exclude_family': exclude_family,
        'color_weight': color_weight,
        'reference': filepath
    }


@api_blueprint.route('/similar-blended/<path:filepath>')
@api_handler()
async def get_blended_similar(filepath):
    """
    Find similar images using both visual hash and tag similarity.
    
    GET /api/similar-blended/<filepath>?visual_weight=0.3&tag_weight=0.7&visual_threshold=15&tag_threshold=0.1&semantic_threshold=0.3&exclude_family=true
    """
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    visual_weight = request.args.get('visual_weight', 0.2, type=float)
    tag_weight = request.args.get('tag_weight', 0.2, type=float)
    semantic_weight = request.args.get('semantic_weight', 0.6, type=float)
    visual_threshold = request.args.get('visual_threshold', 15, type=int)
    tag_threshold = request.args.get('tag_threshold', 0.1, type=float)
    semantic_threshold = request.args.get('semantic_threshold', 0.3, type=float)
    exclude_family = request.args.get('exclude_family', 'false').lower() in ('true', '1', 'yes')
    
    similar = await asyncio.to_thread(
        similarity_service.find_blended_similar,
        filepath,
        visual_weight=visual_weight,
        tag_weight=tag_weight,
        semantic_weight=semantic_weight,
        visual_threshold=visual_threshold,
        tag_threshold=tag_threshold,
        semantic_threshold=semantic_threshold,
        exclude_family=exclude_family
    )
    
    return {
        'similar': similar,
        'count': len(similar),
        'visual_weight': visual_weight,
        'tag_weight': tag_weight,
        'semantic_weight': semantic_weight,
        'visual_threshold': visual_threshold,
        'tag_threshold': tag_threshold,
        'semantic_threshold': semantic_threshold,
        'exclude_family': exclude_family,
        'reference': filepath
    }


@api_blueprint.route('/similar-semantic/<path:filepath>')
@api_handler()
async def get_semantic_similar(filepath):
    """
    Find semantically similar images using FAISS index only.
    
    GET /api/similar-semantic/<filepath>?limit=40&exclude_family=true
    """
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    limit = request.args.get('limit', 40, type=int)
    exclude_family = request.args.get('exclude_family', 'false').lower() in ('true', '1', 'yes')
    
    # Run in thread to not block - service now handles all filtering
    similar = await asyncio.to_thread(
        similarity_service.find_semantic_similar,
        filepath,
        limit=limit,
        exclude_self=True,
        exclude_family=exclude_family
    )
    
    return {
        'similar': similar,
        'count': len(similar),
        'limit': limit,
        'exclude_family': exclude_family,
        'reference': filepath
    }


@api_blueprint.route('/duplicates')
@api_handler()
async def get_duplicate_groups():
    """
    Find all groups of visually similar/duplicate images.
    
    GET /api/duplicates?threshold=5
    """
    threshold = request.args.get('threshold', 5, type=int)
    
    groups = await asyncio.to_thread(
        similarity_service.find_all_duplicate_groups,
        threshold=threshold
    )
    
    return {
        'groups': groups,
        'group_count': len(groups),
        'total_duplicates': sum(len(g) for g in groups),
        'threshold': threshold
    }


@api_blueprint.route('/similarity/generate-hashes', methods=['POST'])
@api_handler()
@require_secret
async def generate_hashes():
    """
    Generate perceptual hashes for images that don't have one.
    
    POST /api/similarity/generate-hashes
    Requires secret authorization.
    Returns a task_id for polling progress.
    """
    import uuid
    from services.background_tasks import task_manager
    from services import monitor_service
    
    task_id = f"hash_gen_{uuid.uuid4().hex[:8]}"
    
    # Start background task using service layer function
    monitor_service.add_log("Hash generation task started...", "info")
    await task_manager.start_task(task_id, similarity_service.run_hash_generation_task)
    
    return {
        'status': 'started',
        'task_id': task_id,
        'message': 'Hash generation started in background'
    }


@api_blueprint.route('/similarity/stats')
@api_handler()
async def get_hash_stats():
    """
    Get statistics about perceptual hash coverage.
    
    GET /api/similarity/stats
    """
    stats = await asyncio.to_thread(similarity_service.get_hash_coverage_stats)
    
    return stats


@api_blueprint.route('/similarity/compute/<path:filepath>', methods=['POST'])
@api_handler()
@require_secret
async def compute_hash_for_image(filepath):
    """
    Compute and store perceptual hash for a specific image.
    
    POST /api/similarity/compute/<filepath>
    """
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    import os
    full_path = os.path.join("static/images", filepath)
    
    if not os.path.exists(full_path):
        return {'error': 'Image not found'}, 404
    
    # Get MD5 for zip animations
    from database import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT md5 FROM images WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        md5 = row['md5'] if row else None
    
    phash = await asyncio.to_thread(
        similarity_service.compute_phash_for_file,
        full_path,
        md5
    )
    
    if phash:
        similarity_service.update_image_phash(filepath, phash)
        return {
            'status': 'success',
            'filepath': filepath,
            'phash': phash
        }
    else:
        return {'error': 'Failed to compute hash'}, 500


@api_blueprint.route('/similarity/rebuild-cache', methods=['POST'])
@api_handler()
@require_secret
async def rebuild_similarity_cache():
    """
    Rebuild the pre-computed similarity cache for all images.
    
    POST /api/similarity/rebuild-cache
    Requires secret authorization.
    Returns a task_id for polling progress.
    """
    import uuid
    from services.background_tasks import task_manager
    from services import monitor_service, similarity_cache
    
    task_id = f"similarity_cache_{uuid.uuid4().hex[:8]}"
    
    async def rebuild_cache_task(task_id, manager):
        """Background task for rebuilding similarity cache via ML Worker."""
        from services import monitor_service as mon
        from ml_worker.client import get_ml_worker_client
        import time
        
        mon.add_log("Starting similarity cache rebuild via ML Worker...", "info")
        
        try:
            client = get_ml_worker_client()
            response = client.rebuild_cache(similarity_type='blended')
            worker_job_id = response['job_id']
            
            mon.add_log(f"Worker job started: {worker_job_id}", "info")
            
            # Poll for completion
            while True:
                job_status = client.get_job_status(worker_job_id)
                status = job_status.get('status')
                progress = job_status.get('progress', 0)
                message = job_status.get('message', 'Processing...')
                
                # Forward progress to frontend
                await manager.update_progress(task_id, progress, 100, message)
                
                if status == 'completed':
                    result = job_status.get('result', {})
                    success = result.get('success', 0)
                    failed = result.get('failed', 0)
                    total = result.get('total', 0)
                    
                    result_msg = f"✓ Similarity cache rebuild complete: {success} cached, {failed} failed"
                    mon.add_log(result_msg, "success")
                    
                    await manager.update_progress(task_id, 100, 100, "Complete")
                    
                    return {
                        'success': success,
                        'failed': failed,
                        'total': total,
                        'message': f"Cached {success} images ({failed} failed)"
                    }
                    
                elif status == 'failed':
                    error_msg = job_status.get('error', 'Unknown worker error')
                    mon.add_log(f"Worker job failed: {error_msg}", "error")
                    raise Exception(f"Worker job failed: {error_msg}")
                    
                await asyncio.sleep(1)
                
        except Exception as e:
            mon.add_log(f"Similarity cache rebuild failed: {e}", "error")
            raise e
    
    # Start background task
    monitor_service.add_log("Similarity cache rebuild task started...", "info")
    await task_manager.start_task(task_id, rebuild_cache_task)
    
    return {
        'status': 'started',
        'task_id': task_id,
        'message': 'Similarity cache rebuild started in background'
    }


@api_blueprint.route('/similarity/cache-stats')
@api_handler()
async def get_cache_stats():
    """
    Get statistics about similarity cache coverage.
    
    GET /api/similarity/cache-stats
    """
    from services import similarity_cache
    stats = await asyncio.to_thread(similarity_cache.get_cache_stats)
    
    return stats


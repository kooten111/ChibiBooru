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
    
    GET /api/similar-blended/<filepath>?visual_weight=0.3&tag_weight=0.7&threshold=15&limit=20&exclude_family=true
    """
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    
    visual_weight = request.args.get('visual_weight', 0.2, type=float)
    tag_weight = request.args.get('tag_weight', 0.2, type=float)
    semantic_weight = request.args.get('semantic_weight', 0.6, type=float)
    threshold = request.args.get('threshold', config.VISUAL_SIMILARITY_THRESHOLD, type=int)
    limit = request.args.get('limit', 20, type=int)
    exclude_family = request.args.get('exclude_family', 'false').lower() in ('true', '1', 'yes')
    
    similar = await asyncio.to_thread(
        similarity_service.find_blended_similar,
        filepath,
        visual_weight=visual_weight,
        tag_weight=tag_weight,
        semantic_weight=request.args.get('semantic_weight', 0.6, type=float),
        threshold=threshold,
        limit=limit,
        exclude_family=exclude_family
    )
    
    return {
        'similar': similar,
        'count': len(similar),
        'visual_weight': visual_weight,
        'tag_weight': tag_weight,
        'threshold': threshold,
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
    
    async def generate_hashes_task(task_id, manager):
        """Background task for generating hashes with progress updates."""
        from services import monitor_service as mon
        
        mon.add_log("Starting hash generation...", "info")
        
        loop = asyncio.get_running_loop()
        
        def progress_callback(current, total):
             future = asyncio.run_coroutine_threadsafe(
                 manager.update_progress(task_id, current, total, "Generating hashes..."), 
                 loop
             )
             # We don't wait for the future
        
        # Run synchronous service function in thread
        stats = await asyncio.to_thread(
            similarity_service.generate_missing_hashes, 
            batch_size=100, 
            progress_callback=progress_callback
        )
        
        success = stats['success']
        failed = stats['failed']
        total = stats['total']
        
        result_msg = f"✓ Hash generation complete: {success} generated, {failed} failed"
        mon.add_log(result_msg, "success")
        
        # Update task to 100%
        await manager.update_progress(task_id, total, total, "Complete")
        
        return {
            'success': success,
            'failed': failed,
            'total': total,
            'message': f"Generated {success} hashes ({failed} failed)"
        }
    
    # Start background task
    monitor_service.add_log("Hash generation task started...", "info")
    await task_manager.start_task(task_id, generate_hashes_task)
    
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


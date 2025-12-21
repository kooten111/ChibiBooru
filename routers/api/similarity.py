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
    
    # Run in thread to not block
    similar = await asyncio.to_thread(
        similarity_service.find_similar_images,
        filepath,
        threshold=threshold,
        limit=limit,
        exclude_family=exclude_family
    )
    
    return {
        'similar': similar,
        'count': len(similar),
        'threshold': threshold,
        'exclude_family': exclude_family,
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
    
    visual_weight = request.args.get('visual_weight', config.VISUAL_SIMILARITY_WEIGHT, type=float)
    tag_weight = request.args.get('tag_weight', config.TAG_SIMILARITY_WEIGHT, type=float)
    threshold = request.args.get('threshold', config.VISUAL_SIMILARITY_THRESHOLD, type=int)
    limit = request.args.get('limit', 20, type=int)
    exclude_family = request.args.get('exclude_family', 'false').lower() in ('true', '1', 'yes')
    
    similar = await asyncio.to_thread(
        similarity_service.find_blended_similar,
        filepath,
        visual_weight=visual_weight,
        tag_weight=tag_weight,
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
        from database import get_db_connection
        from services import monitor_service as mon
        import os
        
        # Get count of images missing hashes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filepath, md5 FROM images WHERE phash IS NULL")
            missing = cursor.fetchall()
        
        total = len(missing)
        if total == 0:
            mon.add_log("All images already have hashes", "info")
            return {'success': 0, 'failed': 0, 'total': 0, 'message': 'All images already have hashes'}
        
        mon.add_log(f"Starting hash generation for {total} images...", "info")
        await manager.update_progress(task_id, 0, total, f"Processing 0/{total} images...")
        
        success = 0
        failed = 0
        
        for i, row in enumerate(missing):
            filepath = row['filepath']
            md5 = row['md5']
            full_path = os.path.join("static/images", filepath)
            
            # Run blocking hash computation in thread to avoid freezing the event loop
            try:
                phash = await asyncio.to_thread(similarity_service.compute_phash_for_file, full_path, md5)
            except Exception as e:
                mon.add_log(f"Error processing {filepath}: {e}", "error")
                phash = None
            
            if phash:
                # DB updates are fast enough, but could also be threaded if needed
                similarity_service.update_image_phash(filepath, phash)
                success += 1
            else:
                failed += 1
            
            # Determine log interval: every 1% or every 10 images, whichever is larger, capped at 1000
            log_interval = max(10, int(total / 100))
            if log_interval > 1000:
                log_interval = 1000
            
            # Update progress
            if (i + 1) % log_interval == 0 or i == total - 1:
                progress_msg = f"Hash generation: {i + 1}/{total} ({success} success, {failed} failed)"
                mon.add_log(progress_msg, "info")
                await manager.update_progress(task_id, i + 1, total, progress_msg)
                
            # Yield control periodically to ensure server stays responsive
            if i % 10 == 0:
                await asyncio.sleep(0)
        
        result_msg = f"✓ Hash generation complete: {success} generated, {failed} failed"
        mon.add_log(result_msg, "success")
        
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


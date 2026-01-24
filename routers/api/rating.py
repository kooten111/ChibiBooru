from quart import request, jsonify
from . import api_blueprint
from services import rating_service as rating_inference
from database import models
from database import get_db_connection
from utils import api_handler, success_response, error_response
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Rating Inference API Endpoints
# ============================================================================

@api_blueprint.route('/rate/train', methods=['POST'])
@api_handler()
async def api_train_model():
    """Train the rating inference model via ML Worker."""
    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        # Returns job info now
        response = client.train_rating_model(timeout=30.0)
        return response
    except Exception as e:
        logger.warning(f"ML Worker unavailable, falling back to direct training: {e}")
        # Fallback to direct call if ML Worker unavailable
        stats = rating_inference.train_model()
        return {"stats": stats, "source": "direct", "warning": "ML Worker unavailable"}


@api_blueprint.route('/rate/infer', methods=['POST'])
@api_handler()
async def api_infer_ratings():
    """Run inference on unrated images or a specific image via ML Worker."""
    data = await request.get_json(silent=True) or {}
    image_id = data.get('image_id')

    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        
        # Returns job info now
        if image_id:
            # Infer single image
            response = client.infer_ratings(image_ids=[image_id], timeout=30.0)
        else:
            # Infer all unrated images
            response = client.infer_ratings(image_ids=None, timeout=30.0)
            
        return response
    except Exception as e:
        logger.warning(f"ML Worker unavailable, falling back to direct inference: {e}")
        # Fallback to direct call if ML Worker unavailable
        if image_id:
            result = rating_inference.infer_rating_for_image(image_id)
            return {"result": result, "source": "direct", "warning": "ML Worker unavailable"}
        else:
            stats = rating_inference.infer_all_unrated_images()
            return {"stats": stats, "source": "direct", "warning": "ML Worker unavailable"}


@api_blueprint.route('/rate/job/<job_id>', methods=['GET'])
@api_handler()
async def api_get_job_status(job_id):
    """Get status of an ML Worker job."""
    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        status = client.get_job_status(job_id)
        return status
    except Exception as e:
        # If ML worker is unavailable, return a response the frontend understands
        logger.warning(f"Failed to get job status for {job_id}: {e}")
        return {"found": False, "error": str(e)}


@api_blueprint.route('/rate/clear_ai', methods=['POST'])
@api_handler()
async def api_clear_ai_ratings():
    """Remove all AI-inferred ratings."""
    deleted_count = rating_inference.clear_ai_inferred_ratings()
    return {"deleted_count": deleted_count}


@api_blueprint.route('/rate/retrain_all', methods=['POST'])
@api_handler()
async def api_retrain_all():
    """Clear AI ratings, retrain, and re-infer everything."""
    result = rating_inference.retrain_and_reapply_all()
    return result


@api_blueprint.route('/rate/precompute', methods=['POST'])
@api_handler()
async def api_precompute_ratings():
    """Pre-compute and store rating predictions for unrated images using multiprocessing."""
    import uuid
    import asyncio
    from services.background_tasks import task_manager
    from services import monitor_service
    import config
    
    data = await request.get_json() or {}
    num_workers = data.get('num_workers', getattr(config, 'MAX_WORKERS', 2))
    batch_size = data.get('batch_size', 200)
    limit = data.get('limit', None)
    
    task_id = f"precompute_rating_{uuid.uuid4().hex[:8]}"
    
    async def precompute_task(task_id, manager, num_workers, batch_size, limit):
        """Background task that runs rating precomputation."""
        from services import monitor_service as mon
        import time
        
        mon.add_log(f"Starting rating prediction precomputation with {num_workers} workers...", "info")
        
        # Get total count for progress tracking
        total_count = rating_inference.get_unrated_images_count()
        if limit:
            total_count = min(total_count, limit)
        
        await manager.update_progress(task_id, 0, total_count, f"Starting with {num_workers} workers...")
        
        def progress_callback(processed, total):
            """Progress callback for precomputation."""
            asyncio.create_task(manager.update_progress(
                task_id,
                processed,
                total,
                f"Processing... ({processed}/{total})"
            ))
        
        try:
            # Run precomputation
            stats = rating_inference.precompute_ratings_for_unrated_images(
                limit=limit,
                progress_callback=progress_callback,
                batch_size=batch_size,
                num_workers=num_workers
            )
            
            await manager.update_progress(task_id, total_count, total_count, "Complete")
            mon.add_log(f"✓ Rating precomputation complete: {stats['rated']} images rated", "success")
            
            return {
                'processed': stats['processed'],
                'rated': stats['rated'],
                'skipped_low_confidence': stats['skipped_low_confidence'],
                'duration_seconds': stats.get('duration_seconds', 0),
                'num_workers': num_workers
            }
        except Exception as e:
            mon.add_log(f"Rating precomputation failed: {str(e)}", "error")
            raise
    
    # Start background task
    monitor_service.add_log("Rating prediction precomputation task started...", "info")
    await task_manager.start_task(task_id, precompute_task, num_workers, batch_size, limit)
    
    return {
        'status': 'started',
        'task_id': task_id,
        'message': f'Precomputation started with {num_workers} workers'
    }


@api_blueprint.route('/rate/stats', methods=['GET'])
@api_handler()
async def api_rating_stats():
    """Get model statistics and configuration."""
    stats = rating_inference.get_model_stats()
    return stats


@api_blueprint.route('/rate/set', methods=['POST'])
@api_blueprint.route('/rate/rate', methods=['POST'])  # Alias for frontend compatibility
@api_handler()
async def api_set_rating():
    """Set rating for an image (user correction)."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    image_id = data.get('image_id')
    rating = data.get('rating')  # Can be None to remove rating

    if image_id is None:
        raise ValueError("image_id is required")

    # Validate rating if provided
    if rating is not None and rating not in rating_inference.RATINGS:
        raise ValueError(f"Invalid rating. Must be one of: {', '.join(rating_inference.RATINGS)}")

    result = rating_inference.set_image_rating(image_id, rating, source='user')

    # Reload data to update in-memory cache (async to avoid blocking)
    from core.cache_manager import load_data_from_db_async
    load_data_from_db_async()

    return {
        'status': 'success',
        'old_rating': result.get('old_rating'),
        'new_rating': result.get('new_rating')
    }


@api_blueprint.route('/rate/top_tags', methods=['GET'])
@api_handler()
async def api_top_weighted_tags():
    """Get highest-weighted tags for a rating."""
    rating = request.args.get('rating')
    limit = request.args.get('limit', 50, type=int)

    if not rating:
        raise ValueError("rating parameter is required")

    if rating not in rating_inference.RATINGS:
        raise ValueError(f"Invalid rating. Must be one of: {', '.join(rating_inference.RATINGS)}")

    result = rating_inference.get_top_weighted_tags(rating, limit)
    return {
        "rating": rating,
        **result
    }


@api_blueprint.route('/rate/config', methods=['POST'])
@api_handler()
async def api_update_config():
    """Update inference configuration."""
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")

    updated = []
    for key, value in data.items():
        try:
            rating_inference.update_config(key, float(value))
            updated.append(key)
        except Exception as e:
            raise ValueError(f"Failed to update {key}: {str(e)}")

    return {"updated": updated}


@api_blueprint.route('/rate/images', methods=['GET'])
@api_handler()
async def api_get_images_for_rating():
    """Get images for rating review interface."""
    filter_type = request.args.get('filter', 'unrated')
    limit = request.args.get('limit', 100, type=int)
    after_id = request.args.get('after_id', type=int)

    with get_db_connection() as conn:
        cur = conn.cursor()

        if filter_type == 'unrated':
            # Get images without any rating tag
            if after_id:
                cur.execute(f"""
                    SELECT i.id, i.filepath
                    FROM images i
                    WHERE i.id > ?
                    AND NOT EXISTS (
                        SELECT 1 FROM image_tags it
                        JOIN tags t ON it.tag_id = t.id
                        WHERE it.image_id = i.id
                        AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                    )
                    ORDER BY i.id
                    LIMIT ?
                """, [after_id] + list(rating_inference.RATINGS) + [limit])
            else:
                cur.execute(f"""
                    SELECT i.id, i.filepath
                    FROM images i
                    WHERE NOT EXISTS (
                        SELECT 1 FROM image_tags it
                        JOIN tags t ON it.tag_id = t.id
                        WHERE it.image_id = i.id
                        AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                    )
                    ORDER BY i.id
                    LIMIT ?
                """, rating_inference.RATINGS + [limit])

        elif filter_type == 'ai_predicted':
            # Get images with AI-predicted ratings
            if after_id:
                cur.execute(f"""
                    SELECT DISTINCT i.id, i.filepath
                    FROM images i
                    JOIN image_tags it ON i.id = it.image_id
                    JOIN tags t ON it.tag_id = t.id
                    WHERE i.id > ?
                    AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                      AND it.source = 'ai_inference'
                    ORDER BY i.id
                    LIMIT ?
                """, [after_id] + list(rating_inference.RATINGS) + [limit])
            else:
                cur.execute(f"""
                    SELECT DISTINCT i.id, i.filepath
                    FROM images i
                    JOIN image_tags it ON i.id = it.image_id
                    JOIN tags t ON it.tag_id = t.id
                    WHERE t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                      AND it.source = 'ai_inference'
                    ORDER BY i.id
                    LIMIT ?
                """, rating_inference.RATINGS + [limit])

        else:  # 'all'
            # Get all images
            if after_id:
                cur.execute("SELECT id, filepath FROM images WHERE id > ? ORDER BY id LIMIT ?", (after_id, limit))
            else:
                cur.execute("SELECT id, filepath FROM images ORDER BY id LIMIT ?", (limit,))

        # Fetch all images first
        image_rows = cur.fetchall()
        image_ids = [row['id'] for row in image_rows]

        # Batch fetch all tags for all images in a single query
        tags_by_image = {}
        if image_ids:
            placeholders = ','.join('?' for _ in image_ids)
            cur.execute(f"""
                SELECT it.image_id, t.name, it.source
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
                    'source': tag_row['source']
                })

        # Build images list with pre-fetched tags
        from utils.file_utils import get_thumbnail_path
        images = []
        for row in image_rows:
            image_id = row['id']
            filepath = row['filepath']

            all_tags = tags_by_image.get(image_id, [])
            tags = [t['name'] for t in all_tags if not t['name'].startswith('rating:')]
            rating_tags = [t for t in all_tags if t['name'].startswith('rating:')]

            # Get rating info
            rating = None
            rating_source = None
            for rt in rating_tags:
                rating = rt['name']
                rating_source = rt['source']
                break

            # Remove 'images/' prefix if present (database stores paths relative to static/images/)
            normalized_filepath = filepath.replace('images/', '', 1) if filepath.startswith('images/') else filepath
            
            images.append({
                'id': image_id,
                'filepath': normalized_filepath,
                'thumb': get_thumbnail_path(filepath),
                'rating': rating,
                'rating_source': rating_source,
                'tag_count': len(tags),
                'tags': tags,
                'ai_rating': rating if rating_source == 'ai_inference' else None,
                'ai_confidence': 0.7 if rating_source == 'ai_inference' else None  # Placeholder
            })

        return {
            'images': images,
            'count': len(images)
        }


@api_blueprint.route('/rate/next', methods=['GET'])
@api_handler()
async def api_get_next_image_for_rating():
    """Get the next single image for rating review interface."""
    filter_type = request.args.get('filter', 'unrated')
    # Support multiple exclude parameters
    exclude_ids = [int(id) for id in request.args.getlist('exclude') if id.isdigit()]

    with get_db_connection() as conn:
        cur = conn.cursor()

        if filter_type == 'unrated':
            # Get next image without any rating tag
            if exclude_ids:
                placeholders = ','.join('?' * len(exclude_ids))
                cur.execute(f"""
                    SELECT i.id, i.filepath
                    FROM images i
                    WHERE i.id NOT IN ({placeholders})
                    AND NOT EXISTS (
                        SELECT 1 FROM image_tags it
                        JOIN tags t ON it.tag_id = t.id
                        WHERE it.image_id = i.id
                        AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                    )
                    ORDER BY i.id
                    LIMIT 1
                """, tuple(exclude_ids) + tuple(rating_inference.RATINGS))
            else:
                cur.execute(f"""
                    SELECT i.id, i.filepath
                    FROM images i
                    WHERE NOT EXISTS (
                        SELECT 1 FROM image_tags it
                        JOIN tags t ON it.tag_id = t.id
                        WHERE it.image_id = i.id
                        AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                    )
                    ORDER BY i.id
                    LIMIT 1
                """, rating_inference.RATINGS)

        elif filter_type == 'ai_predicted':
            # Get next image with AI-predicted ratings
            if exclude_ids:
                placeholders = ','.join('?' * len(exclude_ids))
                cur.execute(f"""
                    SELECT DISTINCT i.id, i.filepath
                    FROM images i
                    JOIN image_tags it ON i.id = it.image_id
                    JOIN tags t ON it.tag_id = t.id
                    WHERE i.id NOT IN ({placeholders})
                    AND t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                      AND it.source = 'ai_inference'
                    ORDER BY i.id
                    LIMIT 1
                """, tuple(exclude_ids) + tuple(rating_inference.RATINGS))
            else:
                cur.execute(f"""
                    SELECT DISTINCT i.id, i.filepath
                    FROM images i
                    JOIN image_tags it ON i.id = it.image_id
                    JOIN tags t ON it.tag_id = t.id
                    WHERE t.name IN ({','.join('?' * len(rating_inference.RATINGS))})
                      AND it.source = 'ai_inference'
                    ORDER BY i.id
                    LIMIT 1
                """, rating_inference.RATINGS)

        else:  # 'all'
            # Get next image (any)
            if exclude_ids:
                placeholders = ','.join('?' * len(exclude_ids))
                cur.execute(f"SELECT id, filepath FROM images WHERE id NOT IN ({placeholders}) ORDER BY id LIMIT 1", tuple(exclude_ids))
            else:
                cur.execute("SELECT id, filepath FROM images ORDER BY id LIMIT 1")

        # Fetch the image
        row = cur.fetchone()
        
        if not row:
            return {"error": "No more images found matching the current filter."}

        image_id = row['id']
        filepath = row['filepath']

        # Fetch all tags for this image with categories
        cur.execute("""
            SELECT t.name, t.category, it.source
            FROM image_tags it
            JOIN tags t ON it.tag_id = t.id
            WHERE it.image_id = ?
        """, (image_id,))

        all_tags = cur.fetchall()
        
        # Separate rating tags from regular tags
        rating_tags = [t for t in all_tags if t['name'].startswith('rating:')]
        regular_tags = [t for t in all_tags if not t['name'].startswith('rating:')]
        
        # Get rating info
        rating = None
        rating_source = None
        for rt in rating_tags:
            rating = rt['name']
            rating_source = rt['source']
            break

        # Group tags by category
        tags_by_category = {
            'character': [],
            'copyright': [],
            'artist': [],
            'general': [],
            'meta': []
        }
        
        for tag in regular_tags:
            category = tag['category'] or 'general'
            # Map to one of the expected categories
            if category not in tags_by_category:
                category = 'general'
            tags_by_category[category].append(tag['name'])

        from utils.file_utils import get_thumbnail_path
        
        # Calculate total tag count
        total_tag_count = sum(len(tags) for tags in tags_by_category.values())
        
        # Build response similar to /api/rate/images but for single image
        # Remove 'images/' prefix if present (database stores paths relative to static/images/)
        normalized_filepath = filepath.replace('images/', '', 1) if filepath.startswith('images/') else filepath
        
        result = {
            'id': image_id,
            'filepath': normalized_filepath,
            'thumb': get_thumbnail_path(filepath),
            'rating': rating,
            'rating_source': rating_source,
            'tag_count': total_tag_count,
            'tags': tags_by_category,
            'ai_rating': rating if rating_source == 'ai_inference' else None,
            'ai_confidence': 0.7 if rating_source == 'ai_inference' else None  # Placeholder
        }

        return result

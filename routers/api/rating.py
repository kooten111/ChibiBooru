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
        response = client.train_rating_model(timeout=10.0)
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
            response = client.infer_ratings(image_ids=[image_id], timeout=10.0)
        else:
            # Infer all unrated images
            response = client.infer_ratings(image_ids=None, timeout=10.0)
            
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

    return result


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

    with get_db_connection() as conn:
        cur = conn.cursor()

        if filter_type == 'unrated':
            # Get images without any rating tag
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

            images.append({
                'id': image_id,
                'filepath': f"images/{filepath}" if not filepath.startswith('images/') else filepath,
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

    with get_db_connection() as conn:
        cur = conn.cursor()

        if filter_type == 'unrated':
            # Get next image without any rating tag
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
        result = {
            'id': image_id,
            'filepath': f"images/{filepath}" if not filepath.startswith('images/') else filepath,
            'thumb': get_thumbnail_path(filepath),
            'rating': rating,
            'rating_source': rating_source,
            'tag_count': total_tag_count,
            'tags': tags_by_category,
            'ai_rating': rating if rating_source == 'ai_inference' else None,
            'ai_confidence': 0.7 if rating_source == 'ai_inference' else None  # Placeholder
        }

        return result

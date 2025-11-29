from quart import request, jsonify
from . import api_blueprint
from services import rating_service as rating_inference
from database import models
from database import get_db_connection

# ============================================================================
# Rating Inference API Endpoints
# ============================================================================

@api_blueprint.route('/rate/train', methods=['POST'])
async def api_train_model():
    """Train the rating inference model."""
    try:
        stats = rating_inference.train_model()
        return jsonify({
            "success": True,
            "stats": stats
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/infer', methods=['POST'])
async def api_infer_ratings():
    """Run inference on unrated images or a specific image."""
    try:
        data = await request.get_json() or {}
        image_id = data.get('image_id')

        if image_id:
            # Infer single image
            result = rating_inference.infer_rating_for_image(image_id)
            return jsonify({
                "success": True,
                "result": result
            })
        else:
            # Infer all unrated images
            stats = rating_inference.infer_all_unrated_images()
            return jsonify({
                "success": True,
                "stats": stats
            })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/clear_ai', methods=['POST'])
async def api_clear_ai_ratings():
    """Remove all AI-inferred ratings."""
    try:
        deleted_count = rating_inference.clear_ai_inferred_ratings()
        return jsonify({
            "success": True,
            "deleted_count": deleted_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/retrain_all', methods=['POST'])
async def api_retrain_all():
    """Clear AI ratings, retrain, and re-infer everything."""
    try:
        result = rating_inference.retrain_and_reapply_all()
        return jsonify({
            "success": True,
            **result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/stats', methods=['GET'])
async def api_rating_stats():
    """Get model statistics and configuration."""
    try:
        stats = rating_inference.get_model_stats()
        return jsonify(stats)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/set', methods=['POST'])
async def api_set_rating():
    """Set rating for an image (user correction)."""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400

        image_id = data.get('image_id')
        rating = data.get('rating')  # Can be None to remove rating

        if image_id is None:
            return jsonify({
                "success": False,
                "error": "image_id is required"
            }), 400

        # Validate rating if provided
        if rating is not None and rating not in rating_inference.RATINGS:
            return jsonify({
                "success": False,
                "error": f"Invalid rating. Must be one of: {', '.join(rating_inference.RATINGS)}"
            }), 400

        result = rating_inference.set_image_rating(image_id, rating, source='user')

        # Reload data to update in-memory cache
        models.load_data_from_db()

        return jsonify({
            "success": True,
            **result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/top_tags', methods=['GET'])
async def api_top_weighted_tags():
    """Get highest-weighted tags for a rating."""
    try:
        rating = request.args.get('rating')
        limit = request.args.get('limit', 50, type=int)

        if not rating:
            return jsonify({
                "error": "rating parameter is required"
            }), 400

        if rating not in rating_inference.RATINGS:
            return jsonify({
                "error": f"Invalid rating. Must be one of: {', '.join(rating_inference.RATINGS)}"
            }), 400

        result = rating_inference.get_top_weighted_tags(rating, limit)
        return jsonify({
            "rating": rating,
            **result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/config', methods=['POST'])
async def api_update_config():
    """Update inference configuration."""
    try:
        data = await request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided"
            }), 400

        updated = []
        for key, value in data.items():
            try:
                rating_inference.update_config(key, float(value))
                updated.append(key)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Failed to update {key}: {str(e)}"
                }), 400

        return jsonify({
            "success": True,
            "updated": updated
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@api_blueprint.route('/rate/images', methods=['GET'])
async def api_get_images_for_rating():
    """Get images for rating review interface."""
    try:
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

            images = []
            for row in cur.fetchall():
                image_id = row['id']
                filepath = row['filepath']

                # Get tags for this image
                cur.execute("""
                    SELECT t.name, it.source
                    FROM image_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE it.image_id = ?
                """, (image_id,))

                all_tags = cur.fetchall()
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
                    'filepath': filepath,
                    'rating': rating,
                    'rating_source': rating_source,
                    'tag_count': len(tags),
                    'tags': tags,
                    'ai_rating': rating if rating_source == 'ai_inference' else None,
                    'ai_confidence': 0.7 if rating_source == 'ai_inference' else None  # Placeholder
                })

            return jsonify({
                'images': images,
                'count': len(images)
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500

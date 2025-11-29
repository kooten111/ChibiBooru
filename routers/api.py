from quart import Blueprint, request, jsonify
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
import database_models as models
from services import api_service, system_service, monitor_service
import asyncio

api_blueprint = Blueprint('api', __name__)

@api_blueprint.route('/images')
async def get_images():
    return api_service.get_images_for_api()

@api_blueprint.route('/reload', methods=['POST'])
async def reload_data():
    return await asyncio.to_thread(system_service.reload_data)

@api_blueprint.route('/system/status')
async def system_status():
    return system_service.get_system_status()

@api_blueprint.route('/system/logs')
async def system_logs():
    return jsonify(monitor_service.get_status().get('logs', []))

@api_blueprint.route('/system/scan', methods=['POST'])
async def trigger_scan():
    return await asyncio.to_thread(system_service.scan_and_process_service)

@api_blueprint.route('/system/rebuild', methods=['POST'])
async def trigger_rebuild():
    return await asyncio.to_thread(system_service.rebuild_service)

@api_blueprint.route('/system/rebuild_categorized', methods=['POST'])
async def trigger_rebuild_categorized():
    return await asyncio.to_thread(system_service.rebuild_categorized_service)

@api_blueprint.route('/system/recategorize', methods=['POST'])
async def trigger_recategorize():
    return await asyncio.to_thread(system_service.recategorize_service)

@api_blueprint.route('/system/thumbnails', methods=['POST'])
async def trigger_thumbnails():
    return await asyncio.to_thread(system_service.trigger_thumbnails)

@api_blueprint.route('/system/deduplicate', methods=['POST'])
async def deduplicate():
    return await system_service.deduplicate_service()

@api_blueprint.route('/system/clean_orphans', methods=['POST'])
async def clean_orphans():
    return await system_service.clean_orphans_service()

@api_blueprint.route('/system/apply_merged_sources', methods=['POST'])
async def apply_merged_sources():
    return await asyncio.to_thread(system_service.apply_merged_sources_service)

@api_blueprint.route('/system/recount_tags', methods=['POST'])
async def recount_tags():
    return await asyncio.to_thread(system_service.recount_tags_service)

@api_blueprint.route('/system/monitor/start', methods=['POST'])
async def start_monitor():
    if monitor_service.start_monitor():
        return jsonify({"status": "success", "message": "Monitor started."})
    return jsonify({"error": "Monitor was already running."}), 400

@api_blueprint.route('/system/monitor/stop', methods=['POST'])
async def stop_monitor():
    if monitor_service.stop_monitor():
        return jsonify({"status": "success", "message": "Monitor stopped."})
    return jsonify({"error": "Monitor was not running."}), 400

@api_blueprint.route('/edit_tags', methods=['POST'])
async def edit_tags():
    return await api_service.edit_tags_service()

@api_blueprint.route('/delete_image', methods=['POST'])
async def delete_image():
    return await api_service.delete_image_service()

@api_blueprint.route('/delete_images_bulk', methods=['POST'])
async def delete_images_bulk():
    return await api_service.delete_images_bulk_service()

@api_blueprint.route('/retry_tagging', methods=['POST'])
async def retry_tagging():
    return await api_service.retry_tagging_service()

@api_blueprint.route('/bulk_retry_tagging', methods=['POST'])
async def bulk_retry_tagging():
    return await api_service.bulk_retry_tagging_service()

@api_blueprint.route('/task_status', methods=['GET'])
async def task_status():
    return await api_service.get_task_status_service()

@api_blueprint.route('/database_health_check', methods=['POST'])
async def database_health_check():
    return await api_service.database_health_check_service()

@api_blueprint.route('/tags/fetch')
async def fetch_tags():
    """API endpoint for fetching tags with pagination and filtering."""
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 100))
    search = request.args.get('search', '').lower().strip()
    category = request.args.get('category', 'all')

    all_tags = models.get_all_tags_sorted()

    # Filter tags based on search and category
    filtered_tags = []
    for tag in all_tags:
        matches_search = search == '' or search in tag['name'].lower()
        matches_category = category == 'all' or tag['category'].lower() == category.lower()

        if matches_search and matches_category:
            filtered_tags.append(tag)

    # Paginate
    total = len(filtered_tags)
    tags_page = filtered_tags[offset:offset + limit]

    return jsonify({
        'tags': tags_page,
        'total': total,
        'offset': offset,
        'limit': limit,
        'hasMore': offset + limit < total
    })

@api_blueprint.route('/autocomplete')
async def autocomplete():
    return api_service.autocomplete()

@api_blueprint.route('/saucenao/search', methods=['POST'])
async def saucenao_search():
    return await api_service.saucenao_search_service()

@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
async def saucenao_fetch_metadata():
    return await api_service.saucenao_fetch_metadata_service()

@api_blueprint.route('/saucenao/apply', methods=['POST'])
async def saucenao_apply():
    return await api_service.saucenao_apply_service()

@api_blueprint.route('/switch_source', methods=['POST'])
async def switch_source():
    try:
        data = await request.json
        filepath = data.get('filepath')
        source = data.get('source')

        if not filepath or not source:
            return jsonify({"error": "Missing filepath or source"}), 400

        # Handle special "merged" source
        if source == 'merged':
            result = merge_all_sources(filepath)
        else:
            result = switch_metadata_source_db(filepath, source)

        if "error" in result:
            return jsonify(result), 400

        # Selective reload: only update this image
        models.reload_single_image(filepath.replace('images/', '', 1))

        return jsonify(result), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/pools/create', methods=['POST'])
async def create_pool():
    try:
        data = await request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({"error": "Pool name is required"}), 400

        pool_id = models.create_pool(name, description)
        return jsonify({"status": "success", "pool_id": pool_id, "message": f"Pool '{name}' created successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/update', methods=['POST'])
async def update_pool(pool_id):
    try:
        data = await request.json
        name = data.get('name')
        description = data.get('description')

        if not name and not description:
            return jsonify({"error": "At least one field (name or description) is required"}), 400

        models.update_pool(pool_id, name, description)
        return jsonify({"status": "success", "message": "Pool updated successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/delete', methods=['POST'])
async def delete_pool(pool_id):
    try:
        models.delete_pool(pool_id)
        return jsonify({"status": "success", "message": "Pool deleted successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/add_image', methods=['POST'])
async def add_image_to_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.add_image_to_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image added to pool."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/remove_image', methods=['POST'])
async def remove_image_from_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.remove_image_from_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image removed from pool."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/reorder', methods=['POST'])
async def reorder_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)
        new_position = data.get('position')

        if new_position is None:
            return jsonify({"error": "Position is required"}), 400

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.reorder_pool_images(pool_id, image_id, new_position)
        return jsonify({"status": "success", "message": "Pool reordered successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/for_image', methods=['GET'])
async def get_pools_for_image():
    try:
        filepath = request.args.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        pools = models.get_pools_for_image(image_id)
        return jsonify({"pools": pools})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/all', methods=['GET'])
async def get_all_pools():
    try:
        pools = models.get_all_pools()
        # Add image counts
        for pool in pools:
            pool_details = models.get_pool_details(pool['id'])
            pool['image_count'] = len(pool_details['images']) if pool_details else 0
        return jsonify({"pools": pools})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/suggestions', methods=['GET'])
async def get_implication_suggestions():
    """Get all auto-detected implication suggestions."""
    try:
        from services import implication_service
        suggestions = implication_service.get_all_suggestions()
        return jsonify(suggestions)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/approve', methods=['POST'])
async def approve_implication():
    """Approve a suggestion and create the implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')
        inference_type = data.get('inference_type', 'manual')
        confidence = data.get('confidence', 1.0)

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.approve_suggestion(
            source_tag, implied_tag, inference_type, confidence
        )

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication created: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Failed to create implication"}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/create', methods=['POST'])
async def create_implication():
    """Create a manual implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.create_manual_implication(source_tag, implied_tag)

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication created: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Failed to create implication (tags may not exist)"}), 400

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/delete', methods=['POST'])
async def delete_implication():
    """Delete an implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        success = implication_service.delete_implication(source_tag, implied_tag)

        if success:
            return jsonify({
                "status": "success",
                "message": f"Implication deleted: {source_tag} → {implied_tag}"
            })
        else:
            return jsonify({"error": "Implication not found"}), 404

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/all', methods=['GET'])
async def get_all_implications():
    """Get all existing implications."""
    try:
        from services import implication_service
        implications = implication_service.get_all_implications()
        return jsonify({"implications": implications})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/chain/<tag_name>', methods=['GET'])
async def get_implication_chain(tag_name):
    """Get the full implication chain for a tag."""
    try:
        from services import implication_service
        chain = implication_service.get_implication_chain(tag_name)
        return jsonify(chain)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/preview', methods=['POST'])
async def preview_implication():
    """Preview the impact of creating an implication."""
    try:
        from services import implication_service
        data = await request.json
        source_tag = data.get('source_tag')
        implied_tag = data.get('implied_tag')

        if not source_tag or not implied_tag:
            return jsonify({"error": "Missing source_tag or implied_tag"}), 400

        impact = implication_service.preview_implication_impact(source_tag, implied_tag)
        return jsonify(impact)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@api_blueprint.route('/implications/batch_apply', methods=['POST'])
async def batch_apply_implications():
    """Apply all implications to all existing images."""
    try:
        from services import implication_service
        count = implication_service.batch_apply_implications_to_all_images()
        return jsonify({
            "status": "success",
            "message": f"Applied implications to {count} images"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Rating Inference API Endpoints
# ============================================================================

@api_blueprint.route('/rate/train', methods=['POST'])
async def api_train_model():
    """Train the rating inference model."""
    try:
        from services import rating_service as rating_inference
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
        from services import rating_service as rating_inference

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
        from services import rating_service as rating_inference
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
        from services import rating_service as rating_inference
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
        from services import rating_service as rating_inference
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
        from services import rating_service as rating_inference

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
        from services import rating_service as rating_inference

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
        from services import rating_service as rating_inference

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
        from database import get_db_connection
        from services import rating_service as rating_inference

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

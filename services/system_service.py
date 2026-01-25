# services/system_service.py
import os
from quart import request, jsonify
from typing import Dict, Any, List, Optional
import config
from database import models
from services import processing
from utils.deduplication import scan_and_remove_duplicates
from utils.decorators import require_secret_sync, require_secret
from utils.logging_config import get_logger
from . import monitor_service

logger = get_logger('SystemService')

@require_secret_sync
def scan_and_process_service() -> Any:
    """Service to find and process new, untracked images."""

    try:
        # First, process new images
        processed_count = monitor_service.run_scan()

        # Then, clean orphaned image_tags entries (broken foreign keys)
        logger.info("Checking for orphaned image_tags entries...")
        from database import get_db_connection
        orphaned_tags_count = 0
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM image_tags it
                LEFT JOIN images i ON it.image_id = i.id
                WHERE i.id IS NULL
            """)
            orphaned_tags_count = cursor.fetchone()[0]

            if orphaned_tags_count > 0:
                logger.info(f"Found {orphaned_tags_count} orphaned image_tags entries. Cleaning...")
                cursor.execute("""
                    DELETE FROM image_tags
                    WHERE image_id NOT IN (SELECT id FROM images)
                """)
                conn.commit()
                logger.info(f"Deleted {orphaned_tags_count} orphaned image_tags entries")

        # Then, clean orphaned image records for manually deleted files
        logger.info("Checking for orphaned image records...")
        db_filepaths = models.get_all_filepaths()
        logger.debug(f"Database has {len(db_filepaths)} image records")

        disk_filepaths = set()
        for root, _, files in os.walk("static/images"):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, "static/images").replace('\\', '/')
                disk_filepaths.add(rel_path)
        logger.debug(f"Disk has {len(disk_filepaths)} files")

        orphans = db_filepaths - disk_filepaths
        cleaned_count = 0
        logger.info(f"Found {len(orphans)} orphaned image records")

        if orphans:
            logger.info(f"Cleaning {len(orphans)} orphaned image records...")
            for orphan_path in orphans:
                if models.delete_image(orphan_path):
                    cleaned_count += 1
            logger.info(f"Cleaned {cleaned_count} orphaned image records")
        else:
            logger.info("No orphaned image records to clean")

        # Reload data to update tag counts after cleaning
        if cleaned_count > 0 or orphaned_tags_count > 0:
            logger.info("Reloading data to update tag counts...")
            from core.cache_manager import load_data_from_db_async
            load_data_from_db_async()
            logger.info("Data reload complete")

        # Optimize query planner if new images were added
        if processed_count > 0:
            logger.info("New images added. Analyzing database statistics...")
            with get_db_connection() as conn:
                conn.execute("ANALYZE")
            logger.info("Database analysis complete")

        # Build response message
        messages = []
        if processed_count > 0:
            messages.append(f"Processed {processed_count} new images")
        else:
            messages.append("No new images found")

        if cleaned_count > 0:
            messages.append(f"cleaned {cleaned_count} orphaned image records")

        if orphaned_tags_count > 0:
            messages.append(f"cleaned {orphaned_tags_count} orphaned tag entries")

        message = ", ".join(messages) + "."

        return jsonify({
            "status": "success",
            "message": message,
            "processed": processed_count,
            "cleaned": cleaned_count,
            "orphaned_tags_cleaned": orphaned_tags_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@require_secret_sync
def rebuild_service():
    """Service to re-process all tags from the raw_metadata in the database."""
    try:
        monitor_service.stop_monitor()
        
        models.repopulate_from_database()
        
        from core.cache_manager import load_data_from_db_async
        load_data_from_db_async()
        
        return jsonify({"status": "success", "message": "Tag re-processing complete."})
    except Exception as e:
        from core.cache_manager import load_data_from_db_async
        load_data_from_db_async()
        return jsonify({"error": str(e)}), 500

@require_secret_sync
def rebuild_categorized_service():
    """Service to back-fill the categorized tag columns in the images table."""
    try:
        updated_count = models.rebuild_categorized_tags_from_relations()
        from core.cache_manager import load_data_from_db_async
        load_data_from_db_async()  # Refresh cache
        return jsonify({
            "status": "success",
            "message": f"Updated categorized tags for {updated_count} images.",
            "changes": updated_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@require_secret_sync
def apply_merged_sources_service():
    """
    Service to apply the merged sources setting to all images with multiple sources.
    
    When USE_MERGED_SOURCES_BY_DEFAULT is True: merges tags from all sources.
    When USE_MERGED_SOURCES_BY_DEFAULT is False: reverts to primary source tags.
    """
    try:
        import config
        from database import get_db_connection
        from services.switch_source_db import merge_all_sources, switch_metadata_source_db

        use_merged = config.USE_MERGED_SOURCES_BY_DEFAULT
        action = "merge" if use_merged else "un-merge"
        
        # Get all images with multiple sources
        processed_count = 0
        error_count = 0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.filepath, i.active_source, COUNT(DISTINCT s.id) as source_count
                FROM images i
                JOIN image_sources isrc ON i.id = isrc.image_id
                JOIN sources s ON isrc.source_id = s.id
                GROUP BY i.id, i.filepath
                HAVING source_count > 1
            """)

            multi_source_images = cursor.fetchall()
            total = len(multi_source_images)

            if total == 0:
                monitor_service.add_log("No images with multiple sources found", "info")
                return jsonify({
                    "status": "success",
                    "message": "No images with multiple sources found.",
                    "processed": 0,
                    "errors": 0
                })

            monitor_service.add_log(f"Starting {action} for {total} images with multiple sources", "info")

            for idx, row in enumerate(multi_source_images, 1):
                filepath = row['filepath']
                current_source = row['active_source']

                # Log progress every 10% or for small batches, every item
                if total <= 10 or idx % max(1, total // 10) == 0:
                    progress_pct = int((idx / total) * 100)
                    monitor_service.add_log(f"Progress: {idx}/{total} ({progress_pct}%) - {processed_count} processed, {error_count} errors", "info")

                if use_merged:
                    # Merge all sources
                    if current_source != 'merged':
                        result = merge_all_sources(filepath)
                        if result.get("status") == "success":
                            processed_count += 1
                        else:
                            error_count += 1
                            monitor_service.add_log(f"Error merging {filepath}: {result.get('error', 'Unknown')}", "error")
                    # Already merged, skip
                else:
                    # Revert to primary source
                    if current_source == 'merged':
                        # Find the primary source based on priority
                        cursor.execute("""
                            SELECT s.name FROM sources s
                            JOIN image_sources isrc ON s.id = isrc.source_id
                            JOIN images i ON isrc.image_id = i.id
                            WHERE i.filepath = ?
                        """, (filepath,))
                        available_sources = [r['name'] for r in cursor.fetchall()]
                        
                        primary_source = None
                        for src in config.BOORU_PRIORITY:
                            if src in available_sources:
                                primary_source = src
                                break
                        
                        if primary_source:
                            result = switch_metadata_source_db(filepath, primary_source)
                            if result.get("status") == "success":
                                processed_count += 1
                            else:
                                error_count += 1
                                monitor_service.add_log(f"Error reverting {filepath}: {result.get('error', 'Unknown')}", "error")
                        else:
                            error_count += 1
                            monitor_service.add_log(f"No primary source found for {filepath}", "error")
                    # Already using single source, skip

        # Refresh cache and recount tags
        monitor_service.add_log("Refreshing cache...", "info")
        models.load_data_from_db()

        monitor_service.add_log("Recounting tags...", "info")
        models.reload_tag_counts()

        action_past = "merged" if use_merged else "reverted to primary source"
        message = f"✓ Processed {total} images: {processed_count} {action_past}"
        if error_count > 0:
            message += f", {error_count} errors"

        monitor_service.add_log(message, "success")

        return jsonify({
            "status": "success",
            "message": message,
            "action": action,
            "processed": processed_count,
            "errors": error_count,
            "total": total
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        monitor_service.add_log(f"Fatal error during {action}: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500
        
@require_secret_sync
def recount_tags_service():
    """Service to recount all tag usage counts."""
    try:
        monitor_service.add_log("Recounting all tags...", "info")
        models.reload_tag_counts()

        # Get total tag count for confirmation
        tag_count = len(models.get_tag_counts())

        monitor_service.add_log(f"✓ Recounted {tag_count} tags", "success")
        return jsonify({
            "status": "success",
            "message": f"Recounted {tag_count} tags",
            "tag_count": tag_count
        })
    except Exception as e:
        monitor_service.add_log(f"Error recounting tags: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500

@require_secret_sync
def recategorize_service():
    """Service to recategorize misplaced tags without full rebuild."""
    try:
        changes = models.recategorize_misplaced_tags()
        models.load_data_from_db()  # Refresh cache
        return jsonify({
            "status": "success",
            "message": f"Recategorized {changes} tags",
            "changes": changes
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def validate_secret_service() -> Dict[str, Any]:
    """
    Service to validate if the provided secret matches config.SYSTEM_API_SECRET.
    
    This endpoint does not require authentication (it's used to validate secrets).
    
    Returns:
        JSON response with success=True and valid=True/False indicating if the secret is correct
    """
    secret = request.args.get('secret', '') or request.form.get('secret', '')

    if secret and secret == config.SYSTEM_API_SECRET:
        return jsonify({"success": True, "valid": True})
    else:
        return jsonify({"success": True, "valid": False})

def get_system_status() -> Dict[str, Any]:
    """
    Service to get system status, including monitor status.
    
    Returns:
        JSON response containing:
        - monitor: Current monitor service status
        - collection: Total images, unprocessed, tagged, and rated counts
    """
    from database import get_db_connection
    
    monitor_status = monitor_service.get_status()
    unprocessed_count = 0
    tagged_count = 0
    rated_count = 0
    
    try:
        unprocessed_count = len(monitor_service.find_unprocessed_images())
    except Exception:
        pass
    
    # Count images with at least one tag
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Count images that have at least one tag
            cursor.execute("""
                SELECT COUNT(DISTINCT image_id) FROM image_tags
            """)
            tagged_count = cursor.fetchone()[0] or 0
            
            # Count images that have a rating tag (rating:general, rating:questionable, etc.)
            cursor.execute("""
                SELECT COUNT(DISTINCT it.image_id)
                FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE t.name LIKE 'rating:%'
            """)
            rated_count = cursor.fetchone()[0] or 0
    except Exception:
        pass

    return jsonify({
        "monitor": monitor_status,
        "collection": {
            "total_images": models.get_image_count(),
            "unprocessed": unprocessed_count,
            "tagged": tagged_count,
            "rated": rated_count,
        },
    })
    
@require_secret_sync
def reload_data():
    """Service to trigger a data reload from the database."""
    if models.load_data_from_db():
        image_count = models.get_image_count()
        tag_count = len(models.get_tag_counts())
        return jsonify({"status": "success", "images": image_count, "tags": tag_count})
    else:
        return jsonify({"error": "Failed to reload data"}), 500

@require_secret_sync
def trigger_thumbnails():
    """Service to manually trigger thumbnail generation."""
    try:
        from services.health_service import check_missing_thumbnails
        result = check_missing_thumbnails(auto_fix=True)
        return jsonify({
            "status": "success",
            "message": f"Generated {result.issues_fixed} thumbnails (found {result.issues_found} missing)",
            "issues_found": result.issues_found,
            "issues_fixed": result.issues_fixed,
            "messages": result.messages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@require_secret
async def deduplicate_service():
    """Service to run MD5 deduplication scan."""
    data = await request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        results = scan_and_remove_duplicates(dry_run=dry_run)
        if not dry_run and results['removed'] > 0:
            models.load_data_from_db()
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@require_secret
async def clean_orphans_service():
    """Service to find and remove database entries for deleted files."""
    data = await request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        # First, clean orphaned image_tags entries (broken foreign keys)
        logger.info("Checking for orphaned image_tags entries...")
        from database import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Count orphaned image_tags
            cursor.execute("""
                SELECT COUNT(*) FROM image_tags it
                LEFT JOIN images i ON it.image_id = i.id
                WHERE i.id IS NULL
            """)
            orphaned_tags_count = cursor.fetchone()[0]

            if orphaned_tags_count > 0:
                logger.info(f"Found {orphaned_tags_count} orphaned image_tags entries. Cleaning...")
                if not dry_run:
                    cursor.execute("""
                        DELETE FROM image_tags
                        WHERE image_id NOT IN (SELECT id FROM images)
                    """)
                    conn.commit()
                    logger.info(f"Deleted {orphaned_tags_count} orphaned image_tags entries")

        # Then, find and remove image records for deleted files
        logger.info("Checking for orphaned image records...")
        db_filepaths = models.get_all_filepaths()

        disk_filepaths = set()
        for root, _, files in os.walk("static/images"):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, "static/images").replace('\\', '/')
                disk_filepaths.add(rel_path)

        orphans = db_filepaths - disk_filepaths

        if dry_run:
            message = f"Found {len(orphans)} orphaned image records and {orphaned_tags_count} orphaned tag entries (dry run - not removed)."
            return jsonify({
                "status": "success",
                "message": message,
                "orphans_found": len(orphans),
                "orphaned_tags": orphaned_tags_count,
                "orphans": sorted(list(orphans)),
                "cleaned": 0
            })
        else:
            cleaned_count = 0
            for orphan_path in orphans:
                if models.delete_image(orphan_path):
                    cleaned_count += 1

            # Always reload data after cleaning to update tag counts and image cache
            if cleaned_count > 0 or orphaned_tags_count > 0:
                logger.info(f"Cleaned {cleaned_count} orphaned image records and {orphaned_tags_count} orphaned tag entries.")
                logger.info("Reloading data to update tag counts...")
                models.load_data_from_db()
                logger.info("Tag counts updated after orphan cleanup.")
                message = f"Cleaned {cleaned_count} orphaned images and {orphaned_tags_count} orphaned tag entries. Tag counts updated."
            else:
                message = f"No orphaned entries found. Database is clean!"

            return jsonify({
                "status": "success",
                "message": message,
                "orphans_found": len(orphans),
                "orphaned_tags": orphaned_tags_count,
                "orphans": sorted(list(orphans)),
                "cleaned": cleaned_count
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@require_secret_sync
def reindex_database_service() -> Any:
    """Service to optimize the database (VACUUM and REINDEX)."""
    try:
        from database.transaction_helpers import get_db_connection_for_maintenance
        import time
        
        start_time = time.time()
        monitor_service.add_log("Starting database optimization...", "info")
        
        # Use maintenance connection helper for VACUUM/REINDEX operations
        with get_db_connection_for_maintenance() as conn:
            # Rebuild FTS index
            monitor_service.add_log("Rebuilding FTS index...", "info")
            conn.execute("INSERT INTO images_fts(images_fts) VALUES('rebuild')")
            
            # Rebuild standard indexes
            monitor_service.add_log("Reindexing standard indexes...", "info")
            conn.execute("REINDEX")
            
            # Optimize database file
            monitor_service.add_log("Vacuuming database...", "info")
            conn.execute("VACUUM")
            
            # Analyze for query planner optimization
            monitor_service.add_log("Analyzing database statistics...", "info")
            conn.execute("ANALYZE")
            
        duration = time.time() - start_time
        message = f"Optimization complete: Rebuilt FTS & standard indexes, vacuumed database, and updated statistics ({duration:.2f}s)."
        monitor_service.add_log(message, "success")
        
        return jsonify({
            "status": "success",
            "message": message,
            "duration": duration
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        monitor_service.add_log(f"Database optimization failed: {str(e)}", "error")

async def get_task_status_service():
    """
    Service to get the status of a background task.
    
    Query Parameters:
        task_id: ID of the task to check
        
    Returns:
        JSON response with task status, or 404 if task not found
    """
    from services.background_tasks import task_manager

    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    status = await task_manager.get_task_status(task_id)
    if not status:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(status)


async def database_health_check_service():
    """
    Service to run database health checks and optionally fix issues.
    
    Request Body (JSON):
        auto_fix: If True, automatically fix issues found (default: True)
        include_thumbnails: If True, check for missing thumbnails (default: False)
        include_tag_deltas: If True, check tag delta consistency (default: True)
        
    Returns:
        JSON response with health check results including issues found and fixed
    """
    data = await request.json or {}
    auto_fix = data.get('auto_fix', True)
    include_thumbnails = data.get('include_thumbnails', False)
    include_tag_deltas = data.get('include_tag_deltas', True)

    try:
        from services import health_service as database_health

        results = database_health.run_all_health_checks(
            auto_fix=auto_fix,
            include_thumbnails=include_thumbnails,
            include_tag_deltas=include_tag_deltas
        )

        return jsonify({
            "status": "success",
            "message": f"Health check complete: {results['total_issues_found']} issues found, {results['total_issues_fixed']} fixed",
            "results": results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@require_secret_sync
def bulk_retag_local_service():
    """
    Service to re-run local tagger for images.
    
    Request Body (JSON):
        local_only: If True, only process images with active_source='local_tagger' or 'camie_tagger'
                   If False/not provided, process ALL images
    """
    try:
        from database import get_db_connection
        from repositories import tagger_predictions_repository
        import config
        from quart import request as quart_request
        import json
        
        # Get request body if available
        local_only = False
        try:
            # For sync context, we need to get the raw data differently
            import flask
            if hasattr(flask, 'request'):
                data = flask.request.get_json(silent=True) or {}
                local_only = data.get('local_only', False)
        except:
            pass

        mode_desc = "locally-tagged images only" if local_only else "ALL images"
        monitor_service.add_log(f"Starting bulk local tagger re-run ({mode_desc})...", "info")

        # Step 1: Clear existing local tagger predictions (only for targeted images if local_only)
        if not local_only:
            deleted = tagger_predictions_repository.clear_all_predictions()
            monitor_service.add_log(f"Cleared {deleted} existing predictions", "info")

        # Step 2: Get images to process based on mode
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if local_only:
                cursor.execute("""
                    SELECT id, filepath FROM images 
                    WHERE active_source IN ('local_tagger', 'camie_tagger')
                """)
            else:
                cursor.execute("SELECT id, filepath FROM images")
            all_images = cursor.fetchall()

        total = len(all_images)
        if total == 0:
            return jsonify({
                "status": "success",
                "message": "No images to process.",
                "processed": 0,
                "predictions_stored": 0
            })

        monitor_service.add_log(f"Processing {total} images...", "info")

        # Step 3: Re-run local tagger for each image
        processed = 0
        total_predictions = 0
        errors = 0

        for idx, row in enumerate(all_images, 1):
            image_id = row['id']
            filepath = row['filepath']

            # Log progress every 10%
            if idx % max(1, total // 10) == 0:
                progress_pct = int((idx / total) * 100)
                monitor_service.add_log(f"Progress: {idx}/{total} ({progress_pct}%)", "info")

            try:
                # Construct full path
                full_path = f"static/images/{filepath}"
                
                # Skip if file doesn't exist
                if not os.path.exists(full_path):
                    continue

                # Skip videos for now (handled differently)
                if full_path.endswith(('.mp4', '.webm')):
                    continue

                # Run local tagger
                result = processing.tag_with_local_tagger(full_path)
                if result and result.get('data', {}).get('all_predictions'):
                    predictions = result['data']['all_predictions']
                    tagger_name = result['data'].get('tagger_name')
                    
                    stored = tagger_predictions_repository.store_predictions(
                        image_id, predictions, tagger_name
                    )
                    total_predictions += stored
                    processed += 1
            except Exception as e:
                errors += 1
                if errors <= 5:  # Only log first 5 errors
                    monitor_service.add_log(f"Error processing {filepath}: {str(e)}", "error")

        message = f"✓ Processed {processed}/{total} images, stored {total_predictions} predictions"
        if errors > 0:
            message += f", {errors} errors"
        monitor_service.add_log(message, "success")

        return jsonify({
            "status": "success",
            "message": message,
            "processed": processed,
            "predictions_stored": total_predictions,
            "errors": errors
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        monitor_service.add_log(f"Bulk retag failed: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500


async def find_broken_images_service() -> Dict[str, Any]:
    """
    Service to find images with missing tags, hashes, or embeddings.
    
    Scans the database for images with:
    - Missing perceptual hash (phash)
    - No tags associated
    - Missing embeddings (if semantic similarity enabled)
    - Invalid embedding dimensions
    
    Returns:
        JSON response containing:
        - total_broken: Total number of broken images found
        - images: List of broken images (limited to first 100) with their issues
        - has_more: Whether there are more than 100 broken images
    """
    try:
        from database import get_db_connection
        from services import similarity_service
        
        broken_images = []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Find images with missing phash
            cursor.execute("""
                SELECT id, filepath, phash, colorhash, md5
                FROM images 
                WHERE phash IS NULL OR phash = ''
            """)
            missing_phash = cursor.fetchall()
            
            for row in missing_phash:
                broken_images.append({
                    'id': row['id'],
                    'filepath': row['filepath'],
                    'md5': row['md5'],
                    'issues': ['missing_phash']
                })
            
            # Find images with no tags at all
            cursor.execute("""
                SELECT i.id, i.filepath, i.md5, COUNT(it.tag_id) as tag_count
                FROM images i
                LEFT JOIN image_tags it ON i.id = it.image_id
                GROUP BY i.id
                HAVING tag_count = 0
            """)
            no_tags = cursor.fetchall()
            
            for row in no_tags:
                # Check if already in list
                existing = next((b for b in broken_images if b['id'] == row['id']), None)
                if existing:
                    existing['issues'].append('no_tags')
                else:
                    broken_images.append({
                        'id': row['id'],
                        'filepath': row['filepath'],
                        'md5': row['md5'],
                        'issues': ['no_tags']
                    })
            
            # Find images with missing embeddings (if semantic similarity is enabled)
            if similarity_service.SEMANTIC_AVAILABLE:
                from services import similarity_db
                
                # Get all image IDs that have embeddings from the separate similarity DB
                embedding_ids = set(similarity_db.get_all_embedding_ids())
                
                # Find images without embeddings
                cursor.execute("SELECT id, filepath, md5 FROM images")
                all_images = cursor.fetchall()
                
                for row in all_images:
                    if row['id'] not in embedding_ids:
                        existing = next((b for b in broken_images if b['id'] == row['id']), None)
                        if existing:
                            existing['issues'].append('missing_embedding')
                        else:
                            broken_images.append({
                                'id': row['id'],
                                'filepath': row['filepath'],
                                'md5': row['md5'],
                                'issues': ['missing_embedding']
                            })
            
            # Find images with invalid embedding dimensions (corrupted data)
            if similarity_service.SEMANTIC_AVAILABLE:
                from services import similarity_db
                import numpy as np
                
                with similarity_db.get_db_connection() as emb_conn:
                    emb_cursor = emb_conn.execute("SELECT image_id, embedding FROM embeddings")
                    for emb_row in emb_cursor:
                        vec = np.frombuffer(emb_row['embedding'], dtype=np.float32)
                        if len(vec) != 1024:  # Expected dimension
                            # Look up the image filepath 
                            cursor.execute("SELECT id, filepath, md5 FROM images WHERE id = ?", (emb_row['image_id'],))
                            img_row = cursor.fetchone()
                            if img_row:
                                existing = next((b for b in broken_images if b['id'] == img_row['id']), None)
                                if existing:
                                    existing['issues'].append('invalid_embedding_dim')
                                else:
                                    broken_images.append({
                                        'id': img_row['id'],
                                        'filepath': img_row['filepath'],
                                        'md5': img_row['md5'],
                                        'issues': ['invalid_embedding_dim']
                                    })
        
        # Sort by number of issues (most broken first)
        broken_images.sort(key=lambda x: len(x['issues']), reverse=True)
        
        return jsonify({
            "status": "success",
            "total_broken": len(broken_images),
            "images": broken_images[:100],  # Limit to first 100
            "has_more": len(broken_images) > 100
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@require_secret
async def cleanup_broken_images_service() -> Dict[str, Any]:
    """
    Service to cleanup or retry broken images.
    Actions:
    - 'scan': Just find and return count of broken images
    - 'delete': Remove broken images from database and move files back to ingest
    - 'retry': Re-process broken images (regenerate hashes/embeddings)
    - 'delete_permanent': Remove from database and delete files permanently
    """
    from utils.validation import validate_enum, validate_list_of_integers
    
    data = await request.json or {}
    action = validate_enum(
        data.get('action', 'scan'),
        param_name='action',
        allowed_values=['scan', 'delete', 'retry', 'delete_permanent']
    )
    image_ids = validate_list_of_integers(
        data.get('image_ids', []),
        param_name='image_ids',
        allow_empty=True
    )
    
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != config.SYSTEM_API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from database import get_db_connection
        from services import similarity_service
        import shutil
        
        # If no specific IDs provided, find all broken images
        if not image_ids:
            from services import similarity_db
            
            # Get embedding IDs from the separate similarity DB
            embedding_ids = set(similarity_db.get_all_embedding_ids()) if similarity_service.SEMANTIC_AVAILABLE else set()
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get all images with phash or tag issues
                cursor.execute("""
                    SELECT DISTINCT i.id
                    FROM images i
                    LEFT JOIN image_tags it ON i.id = it.image_id
                    WHERE i.phash IS NULL 
                       OR i.phash = ''
                       OR it.tag_id IS NULL
                    GROUP BY i.id
                """)
                
                broken_ids = set(row['id'] for row in cursor.fetchall())
                
                # Also add images missing embeddings
                if similarity_service.SEMANTIC_AVAILABLE:
                    cursor.execute("SELECT id FROM images")
                    all_ids = set(row['id'] for row in cursor.fetchall())
                    missing_embeddings = all_ids - embedding_ids
                    broken_ids.update(missing_embeddings)
                
                image_ids = list(broken_ids)
        
        if action == 'scan':
            return jsonify({
                "status": "success",
                "message": f"Found {len(image_ids)} broken images",
                "count": len(image_ids)
            })
        
        if not image_ids:
            return jsonify({
                "status": "success",
                "message": "No broken images found",
                "processed": 0
            })
        
        processed = 0
        errors = 0
        
        if action == 'delete':
            # Move files back to ingest folder and remove from database
            monitor_service.add_log(f"Moving {len(image_ids)} broken images back to ingest...", "info")
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for image_id in image_ids:
                    cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
                    row = cursor.fetchone()
                    if row:
                        filepath = row['filepath']
                        full_path = f"static/images/{filepath}"
                        
                        if os.path.exists(full_path):
                            # Move back to ingest
                            filename = os.path.basename(filepath)
                            ingest_path = os.path.join(config.INGEST_DIRECTORY, filename)
                            
                            try:
                                shutil.move(full_path, ingest_path)
                                models.delete_image(filepath)
                                processed += 1
                            except Exception as e:
                                errors += 1
                                monitor_service.add_log(f"Error moving {filename}: {e}", "error")
                        else:
                            # File doesn't exist, just remove from DB
                            models.delete_image(filepath)
                            processed += 1
            
            models.load_data_from_db()
            message = f"Moved {processed} broken images back to ingest folder"
            
        elif action == 'delete_permanent':
            # Delete files and remove from database permanently
            monitor_service.add_log(f"Permanently deleting {len(image_ids)} broken images...", "info")
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for image_id in image_ids:
                    cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
                    row = cursor.fetchone()
                    if row:
                        filepath = row['filepath']
                        full_path = f"static/images/{filepath}"
                        
                        # Delete file if exists
                        if os.path.exists(full_path):
                            try:
                                os.remove(full_path)
                            except Exception as e:
                                monitor_service.add_log(f"Error deleting {filepath}: {e}", "error")
                        
                        # Remove thumbnail if exists
                        thumb_path = f"static/thumbnails/{filepath.rsplit('.', 1)[0]}.webp"
                        if os.path.exists(thumb_path):
                            try:
                                os.remove(thumb_path)
                            except:
                                pass
                        
                        models.delete_image(filepath)
                        processed += 1
            
            models.load_data_from_db()
            message = f"Permanently deleted {processed} broken images"
            
        elif action == 'retry':
            # Re-process broken images (regenerate hashes/tags/embeddings)
            monitor_service.add_log(f"Retrying {len(image_ids)} broken images...", "info")
            
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                for idx, image_id in enumerate(image_ids, 1):
                    if idx % 10 == 0:
                        monitor_service.add_log(f"Progress: {idx}/{len(image_ids)}", "info")
                    
                    cursor.execute("SELECT filepath, md5 FROM images WHERE id = ?", (image_id,))
                    row = cursor.fetchone()
                    if row:
                        filepath = row['filepath']
                        md5 = row['md5']
                        full_path = f"static/images/{filepath}"
                        
                        if not os.path.exists(full_path):
                            continue
                        
                        try:
                            # Regenerate phash if missing
                            cursor.execute("SELECT phash FROM images WHERE id = ?", (image_id,))
                            if not cursor.fetchone()['phash']:
                                phash = similarity_service.compute_phash_for_file(full_path, md5)
                                if phash:
                                    cursor.execute("UPDATE images SET phash = ? WHERE id = ?", (phash, image_id))
                            
                            # Regenerate colorhash if missing
                            cursor.execute("SELECT colorhash FROM images WHERE id = ?", (image_id,))
                            if not cursor.fetchone()['colorhash']:
                                colorhash = similarity_service.compute_colorhash_for_file(full_path)
                                if colorhash:
                                    cursor.execute("UPDATE images SET colorhash = ? WHERE id = ?", (colorhash, image_id))
                            
                            # Regenerate embedding if missing and available
                            if similarity_service.SEMANTIC_AVAILABLE:
                                from services import similarity_db
                                existing_embedding = similarity_db.get_embedding(image_id)
                                if existing_embedding is None:
                                    engine = similarity_service.get_semantic_engine()
                                    if engine.load_model():
                                        embedding = engine.get_embedding(full_path)
                                        if embedding is not None:
                                            similarity_service.store_embedding(image_id, embedding)
                            
                            conn.commit()
                            processed += 1
                        except Exception as e:
                            errors += 1
                            if errors <= 5:
                                monitor_service.add_log(f"Error retrying {filepath}: {e}", "error")
            
            message = f"Retried {processed} images"
            if errors > 0:
                message += f", {errors} errors"
        else:
            return jsonify({"error": f"Unknown action: {action}"}), 400
        
        monitor_service.add_log(f"✓ {message}", "success")
        
        return jsonify({
            "status": "success",
            "message": message,
            "processed": processed,
            "errors": errors
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
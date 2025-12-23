# services/system_service.py
import os
from quart import request, jsonify
from database import models
from services import processing_service as processing
from utils.deduplication import scan_and_remove_duplicates
from . import monitor_service
import subprocess
import sys

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

async def scan_and_process_service():
    """Service to find and process new, untracked images."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    # Check if we should run as background task
    import uuid
    from services.background_tasks import task_manager
    import asyncio
    
    task_id = f"scan_{uuid.uuid4().hex[:8]}"
    
    async def scan_task(task_id, manager):
        """Background task for scanning and processing."""
        from database import get_db_connection
        import time
        
        monitor_service.add_log("Starting scan and process...", "info")
        
        # Find unprocessed images first to get total count
        unprocessed = await asyncio.to_thread(monitor_service.find_unprocessed_images)
        total_to_process = len(unprocessed)
        
        await manager.update_progress(task_id, 0, total_to_process, "Scanning for new images...")
        
        # Process new images
        processed_count = await asyncio.to_thread(monitor_service.run_scan)
        
        await manager.update_progress(task_id, processed_count, max(total_to_process, processed_count), 
                                      "Cleaning orphaned entries...")
        
        # Clean orphaned image_tags entries
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
                cursor.execute("""
                    DELETE FROM image_tags
                    WHERE image_id NOT IN (SELECT id FROM images)
                """)
                conn.commit()

        # Clean orphaned image records
        db_filepaths = await asyncio.to_thread(models.get_all_filepaths)
        
        disk_filepaths = set()
        for root, _, files in os.walk("static/images"):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, "static/images").replace('\\', '/')
                disk_filepaths.add(rel_path)

        orphans = db_filepaths - disk_filepaths
        cleaned_count = 0

        if orphans:
            for orphan_path in orphans:
                if models.delete_image(orphan_path):
                    cleaned_count += 1

        # Reload data if needed
        if cleaned_count > 0 or orphaned_tags_count > 0:
            from core.cache_manager import load_data_from_db_async
            load_data_from_db_async()

        # Optimize query planner if new images were added
        if processed_count > 0:
            with get_db_connection() as conn:
                conn.execute("ANALYZE")

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
        monitor_service.add_log(message, "success")

        return {
            "processed": processed_count,
            "cleaned": cleaned_count,
            "orphaned_tags_cleaned": orphaned_tags_count,
            "message": message
        }
    
    # Start background task
    monitor_service.add_log("Scan task started...", "info")
    await task_manager.start_task(task_id, scan_task)
    
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'message': 'Scan started in background'
    })

def rebuild_service():
    """Service to re-process all tags from the raw_metadata in the database."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
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

async def rebuild_categorized_service():
    """Service to back-fill the categorized tag columns in the images table."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    import uuid
    from services.background_tasks import task_manager
    import asyncio
    
    task_id = f"rebuild_cat_{uuid.uuid4().hex[:8]}"
    
    async def rebuild_categorized_task(task_id, manager):
        """Background task for rebuilding categorized tags."""
        monitor_service.add_log("Starting categorized tag rebuild...", "info")
        
        # Get total count of images
        from database import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM images")
            total = cursor.fetchone()[0]
        
        await manager.update_progress(task_id, 0, total, "Rebuilding categorized tags...")
        
        # Run the rebuild with progress updates
        # We'll need to modify models.rebuild_categorized_tags_from_relations to support callbacks
        # For now, just run it
        updated_count = await asyncio.to_thread(models.rebuild_categorized_tags_from_relations)
        
        await manager.update_progress(task_id, total, total, "Refreshing cache...")
        
        from core.cache_manager import load_data_from_db_async
        load_data_from_db_async()
        
        message = f"Updated categorized tags for {updated_count} images"
        monitor_service.add_log(message, "success")
        
        return {
            "changes": updated_count,
            "message": message
        }
    
    monitor_service.add_log("Rebuild categorized task started...", "info")
    await task_manager.start_task(task_id, rebuild_categorized_task)
    
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'message': 'Rebuild categorized started in background'
    })

async def apply_merged_sources_service():
    """Service to apply merged sources to all images with multiple sources."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    import uuid
    from services.background_tasks import task_manager
    import asyncio
    import config
    from database import get_db_connection
    from services.switch_source_db import merge_all_sources
    
    task_id = f"merge_{uuid.uuid4().hex[:8]}"
    
    async def merge_sources_task(task_id, manager):
        """Background task for merging sources."""
        monitor_service.add_log("Starting merged sources...", "info")
        
        # Get all images with multiple sources
        merged_count = 0
        skipped_count = 0
        error_count = 0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.filepath, COUNT(DISTINCT s.id) as source_count
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
                return {
                    "merged": 0,
                    "skipped": 0,
                    "errors": 0,
                    "total": 0,
                    "message": "No images with multiple sources found."
                }

            monitor_service.add_log(f"Starting merge for {total} images with multiple sources", "info")

            for idx, row in enumerate(multi_source_images, 1):
                filepath = row['filepath']

                # Update progress
                await manager.update_progress(task_id, idx, total, f"Merging {filepath}...")

                # Log progress every 10%
                if total <= 10 or idx % max(1, total // 10) == 0:
                    progress_pct = int((idx / total) * 100)
                    monitor_service.add_log(f"Progress: {idx}/{total} ({progress_pct}%) - {merged_count} merged, {error_count} errors", "info")

                # Check if we should use merged based on config
                if config.USE_MERGED_SOURCES_BY_DEFAULT:
                    result = await asyncio.to_thread(merge_all_sources, filepath)
                    if result.get("status") == "success":
                        merged_count += 1
                    else:
                        error_count += 1
                        monitor_service.add_log(f"Error merging {filepath}: {result.get('error', 'Unknown')}", "error")
                else:
                    skipped_count += 1

        # Refresh cache and recount tags
        await manager.update_progress(task_id, total, total, "Refreshing cache...")
        monitor_service.add_log("Refreshing cache...", "info")
        await asyncio.to_thread(models.load_data_from_db)

        monitor_service.add_log("Recounting tags...", "info")
        await asyncio.to_thread(models.reload_tag_counts)

        message = f"✓ Processed {total} images: {merged_count} merged"
        if skipped_count > 0:
            message += f", {skipped_count} skipped (config disabled)"
        if error_count > 0:
            message += f", {error_count} errors"

        monitor_service.add_log(message, "success")

        return {
            "merged": merged_count,
            "skipped": skipped_count,
            "errors": error_count,
            "total": total,
            "message": message
        }
    
    monitor_service.add_log("Merge sources task started...", "info")
    await task_manager.start_task(task_id, merge_sources_task)
    
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'message': 'Merge sources started in background'
    })

def recount_tags_service():
    """Service to recount all tag usage counts."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

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

def recategorize_service():
    """Service to recategorize misplaced tags without full rebuild."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

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

def validate_secret_service():
    """Service to validate if the provided secret matches RELOAD_SECRET."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')

    if secret and secret == RELOAD_SECRET:
        return jsonify({"success": True, "valid": True})
    else:
        return jsonify({"success": True, "valid": False})

def get_system_status():
    """Service to get system status, including monitor status."""
    monitor_status = monitor_service.get_status()
    unprocessed_count = 0
    try:
        unprocessed_count = len(monitor_service.find_unprocessed_images())
    except Exception:
        pass

    return jsonify({
        "monitor": monitor_status,
        "collection": {
            "total_images": models.get_image_count(),
            "unprocessed": unprocessed_count,
        },
    })
    
def reload_data():
    """Service to trigger a data reload from the database."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    if models.load_data_from_db():
        image_count = models.get_image_count()
        tag_count = len(models.get_tag_counts())
        return jsonify({"status": "success", "images": image_count, "tags": tag_count})
    else:
        return jsonify({"error": "Failed to reload data"}), 500

async def trigger_thumbnails():
    """Service to manually trigger thumbnail generation."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    import uuid
    from services.background_tasks import task_manager
    import asyncio
    from services.health_service import check_missing_thumbnails
    
    task_id = f"thumbs_{uuid.uuid4().hex[:8]}"
    
    async def thumbnails_task(task_id, manager):
        """Background task for thumbnail generation."""
        monitor_service.add_log("Starting thumbnail generation...", "info")
        
        # Check_missing_thumbnails doesn't support progress callbacks yet
        # So we just run it and report completion
        await manager.update_progress(task_id, 0, 1, "Generating thumbnails...")
        
        result = await asyncio.to_thread(check_missing_thumbnails, auto_fix=True)
        
        await manager.update_progress(task_id, 1, 1, "Complete")
        
        message = f"Generated {result.issues_fixed} thumbnails (found {result.issues_found} missing)"
        monitor_service.add_log(message, "success")
        
        return {
            "issues_found": result.issues_found,
            "issues_fixed": result.issues_fixed,
            "messages": result.messages,
            "message": message
        }
    
    monitor_service.add_log("Thumbnail generation task started...", "info")
    await task_manager.start_task(task_id, thumbnails_task)
    
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'message': 'Thumbnail generation started in background'
    })

async def deduplicate_service():
    """Service to run MD5 deduplication scan."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = await request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        results = scan_and_remove_duplicates(dry_run=dry_run)
        if not dry_run and results['removed'] > 0:
            models.load_data_from_db()
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def clean_orphans_service():
    """Service to find and remove database entries for deleted files."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = await request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        # First, clean orphaned image_tags entries (broken foreign keys)
        print("Checking for orphaned image_tags entries...")
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
                print(f"Found {orphaned_tags_count} orphaned image_tags entries. Cleaning...")
                if not dry_run:
                    cursor.execute("""
                        DELETE FROM image_tags
                        WHERE image_id NOT IN (SELECT id FROM images)
                    """)
                    conn.commit()
                    print(f"Deleted {orphaned_tags_count} orphaned image_tags entries")

        # Then, find and remove image records for deleted files
        print("Checking for orphaned image records...")
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
                print(f"Cleaned {cleaned_count} orphaned image records and {orphaned_tags_count} orphaned tag entries.")
                print("Reloading data to update tag counts...")
                models.load_data_from_db()
                print("Tag counts updated after orphan cleanup.")
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

def reindex_database_service():
    """Service to optimize the database (VACUUM and REINDEX)."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        from database import get_db_connection
        import time
        
        start_time = time.time()
        monitor_service.add_log("Starting database optimization...", "info")
        
        # VACUUM cannot be run inside a transaction
        # We need to use a connection with isolation_level=None (autocommit)
        conn = get_db_connection()
        conn.isolation_level = None
        
        try:
            # Enable auto-vacuum to keep DB size in check
            conn.execute("PRAGMA auto_vacuum = FULL")
            
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
        finally:
            conn.close()
            
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
        return jsonify({"error": str(e)}), 500

async def get_task_status_service():
    """Service to get the status of a background task."""
    from services.background_tasks import task_manager

    task_id = request.args.get('task_id')
    if not task_id:
        return jsonify({"error": "task_id is required"}), 400

    status = await task_manager.get_task_status(task_id)
    if not status:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(status)


async def database_health_check_service():
    """Service to run database health checks and optionally fix issues."""
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



async def bulk_retag_local_service():
    """
    Service to wipe all local tagger predictions and re-run local tagger for all images.
    This populates the local_tagger_predictions table with fresh data.
    """
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    import uuid
    from services.background_tasks import task_manager
    import asyncio
    from database import get_db_connection
    from repositories import tagger_predictions_repository
    import config
    
    task_id = f"retag_{uuid.uuid4().hex[:8]}"
    
    async def retag_task(task_id, manager):
        """Background task for retagging with local AI."""
        monitor_service.add_log("Starting bulk local tagger re-run...", "info")

        # Step 1: Clear all existing local tagger predictions
        deleted = await asyncio.to_thread(tagger_predictions_repository.clear_all_predictions)
        monitor_service.add_log(f"Cleared {deleted} existing predictions", "info")

        # Step 2: Get all images that need tagging
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, filepath FROM images")
            all_images = cursor.fetchall()

        total = len(all_images)
        if total == 0:
            monitor_service.add_log("No images to process", "info")
            return {
                "processed": 0,
                "predictions_stored": 0,
                "errors": 0,
                "message": "No images to process."
            }

        monitor_service.add_log(f"Processing {total} images...", "info")

        # Step 3: Re-run local tagger for each image
        processed = 0
        total_predictions = 0
        errors = 0

        for idx, row in enumerate(all_images, 1):
            image_id = row['id']
            filepath = row['filepath']

            # Update progress
            await manager.update_progress(task_id, idx, total, f"Tagging {filepath}...")

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
                result = await asyncio.to_thread(processing.tag_with_local_tagger, full_path)
                if result and result.get('data', {}).get('all_predictions'):
                    predictions = result['data']['all_predictions']
                    tagger_name = result['data'].get('tagger_name')
                    
                    stored = await asyncio.to_thread(
                        tagger_predictions_repository.store_predictions,
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

        return {
            "processed": processed,
            "predictions_stored": total_predictions,
            "errors": errors,
            "message": message
        }
    
    monitor_service.add_log("Bulk retag task started...", "info")
    await task_manager.start_task(task_id, retag_task)
    
    return jsonify({
        'status': 'started',
        'task_id': task_id,
        'message': 'Bulk retag started in background'
    })
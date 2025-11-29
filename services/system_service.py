# services/system_service.py
import os
from quart import request, jsonify
import database_models as models
from services import processing_service as processing
from utils.deduplication import scan_and_remove_duplicates
from . import monitor_service
import subprocess
import sys

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

def scan_and_process_service():
    """Service to find and process new, untracked images."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        # First, process new images
        processed_count = monitor_service.run_scan()

        # Then, clean orphaned image_tags entries (broken foreign keys)
        print("Checking for orphaned image_tags entries...")
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
                print(f"Found {orphaned_tags_count} orphaned image_tags entries. Cleaning...")
                cursor.execute("""
                    DELETE FROM image_tags
                    WHERE image_id NOT IN (SELECT id FROM images)
                """)
                conn.commit()
                print(f"Deleted {orphaned_tags_count} orphaned image_tags entries")

        # Then, clean orphaned image records for manually deleted files
        print("Checking for orphaned image records...")
        db_filepaths = models.get_all_filepaths()
        print(f"Database has {len(db_filepaths)} image records")

        disk_filepaths = set()
        for root, _, files in os.walk("static/images"):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, "static/images").replace('\\', '/')
                disk_filepaths.add(rel_path)
        print(f"Disk has {len(disk_filepaths)} files")

        orphans = db_filepaths - disk_filepaths
        cleaned_count = 0
        print(f"Found {len(orphans)} orphaned image records")

        if orphans:
            print(f"Cleaning {len(orphans)} orphaned image records...")
            for orphan_path in orphans:
                if models.delete_image(orphan_path):
                    cleaned_count += 1
            print(f"Cleaned {cleaned_count} orphaned image records")
        else:
            print("No orphaned image records to clean")

        # Reload data to update tag counts after cleaning
        if cleaned_count > 0 or orphaned_tags_count > 0:
            print(f"Reloading data to update tag counts...")
            models.load_data_from_db()
            print("Data reload complete")

        # Optimize query planner if new images were added
        if processed_count > 0:
            print("New images added. Analyzing database statistics...")
            with get_db_connection() as conn:
                conn.execute("ANALYZE")
            print("Database analysis complete")

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
            "cleaned": cleaned_count,
            "orphaned_tags_cleaned": orphaned_tags_count
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def rebuild_service():
    """Service to re-process all tags from the raw_metadata in the database."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        monitor_service.stop_monitor()
        
        models.repopulate_from_database()
        
        models.load_data_from_db()
        
        return jsonify({"status": "success", "message": "Tag re-processing complete."})
    except Exception as e:
        models.load_data_from_db()
        return jsonify({"error": str(e)}), 500

def rebuild_categorized_service():
    """Service to back-fill the categorized tag columns in the images table."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        updated_count = models.rebuild_categorized_tags_from_relations()
        models.load_data_from_db()  # Refresh cache
        return jsonify({
            "status": "success",
            "message": f"Updated categorized tags for {updated_count} images.",
            "changes": updated_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def apply_merged_sources_service():
    """Service to apply merged sources to all images with multiple sources."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import config
        from database import get_db_connection
        from services.switch_source_db import merge_all_sources

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
                return jsonify({
                    "status": "success",
                    "message": "No images with multiple sources found.",
                    "merged": 0,
                    "skipped": 0,
                    "errors": 0
                })

            monitor_service.add_log(f"Starting merge for {total} images with multiple sources", "info")

            for idx, row in enumerate(multi_source_images, 1):
                filepath = row['filepath']

                # Log progress every 10% or for small batches, every item
                if total <= 10 or idx % max(1, total // 10) == 0:
                    progress_pct = int((idx / total) * 100)
                    monitor_service.add_log(f"Progress: {idx}/{total} ({progress_pct}%) - {merged_count} merged, {error_count} errors", "info")

                # Check if we should use merged based on config
                if config.USE_MERGED_SOURCES_BY_DEFAULT:
                    result = merge_all_sources(filepath)
                    if result.get("status") == "success":
                        merged_count += 1
                    else:
                        error_count += 1
                        monitor_service.add_log(f"Error merging {filepath}: {result.get('error', 'Unknown')}", "error")
                else:
                    skipped_count += 1

        # Refresh cache and recount tags
        monitor_service.add_log("Refreshing cache...", "info")
        models.load_data_from_db()

        monitor_service.add_log("Recounting tags...", "info")
        models.reload_tag_counts()

        message = f"✓ Processed {total} images: {merged_count} merged"
        if skipped_count > 0:
            message += f", {skipped_count} skipped (config disabled)"
        if error_count > 0:
            message += f", {error_count} errors"

        monitor_service.add_log(message, "success")

        return jsonify({
            "status": "success",
            "message": message,
            "merged": merged_count,
            "skipped": skipped_count,
            "errors": error_count,
            "total": total
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        monitor_service.add_log(f"Fatal error during merge: {str(e)}", "error")
        return jsonify({"error": str(e)}), 500
        
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

def trigger_thumbnails():
    """Service to manually trigger thumbnail generation."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import scripts.generate_thumbnails as generate_thumbnails
        generate_thumbnails.main()
        return jsonify({"status": "success", "message": "Thumbnails generated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        
        with get_db_connection() as conn:
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
            
        duration = time.time() - start_time
        message = f"Database optimization complete in {duration:.2f} seconds."
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
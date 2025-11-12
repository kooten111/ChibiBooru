# services/system_service.py
import os
from quart import request, jsonify
import models
import scripts.generate_thumbnails as generate_thumbnails
import processing
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
        generate_thumbnails.main()
        return jsonify({"status": "success", "message": "Thumbnails generated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def deduplicate_service():
    """Service to run MD5 deduplication scan."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        results = scan_and_remove_duplicates(dry_run=dry_run)
        if not dry_run and results['removed'] > 0:
            models.load_data_from_db()
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def clean_orphans_service():
    """Service to find and remove database entries for deleted files."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
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
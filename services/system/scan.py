import os
from typing import Any, Dict

from database import models
from services import monitor_service
from utils.logging_config import get_logger

from .task_helpers import run_sync_task

logger = get_logger("SystemScan")


def run_scan_and_process() -> Dict[str, Any]:
    """Service to find and process new, untracked images."""
    processed_count, attempted_count = monitor_service.run_scan()

    logger.info("Checking for orphaned image_tags entries...")
    from database import get_db_connection

    orphaned_tags_count = 0
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM image_tags it
            LEFT JOIN images i ON it.image_id = i.id
            WHERE i.id IS NULL
        """
        )
        orphaned_tags_count = cursor.fetchone()[0]

        if orphaned_tags_count > 0:
            logger.info(
                f"Found {orphaned_tags_count} orphaned image_tags entries. Cleaning..."
            )
            cursor.execute(
                """
                DELETE FROM image_tags
                WHERE image_id NOT IN (SELECT id FROM images)
            """
            )
            conn.commit()
            logger.info(f"Deleted {orphaned_tags_count} orphaned image_tags entries")

    logger.info("Checking for orphaned image records...")
    db_filepaths = models.get_all_filepaths()
    logger.debug(f"Database has {len(db_filepaths)} image records")

    disk_filepaths = set()
    for root, _, files in os.walk("static/images"):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, "static/images").replace("\\", "/")
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

    if cleaned_count > 0 or orphaned_tags_count > 0:
        logger.info("Reloading data to update tag counts...")
        from core.cache_manager import load_data_from_db_async

        load_data_from_db_async()
        logger.info("Data reload complete")

    if processed_count > 0:
        logger.info("New images added. Analyzing database statistics...")
        with get_db_connection() as conn:
            conn.execute("ANALYZE")
        logger.info("Database analysis complete")

    messages = []
    if processed_count > 0:
        messages.append(f"Processed {processed_count} new images")
    elif attempted_count > 0:
        messages.append(
            "Found {count} image(s) but none could be processed (see activity log)".format(
                count=attempted_count
            )
        )
    else:
        messages.append("No new images found")

    if cleaned_count > 0:
        messages.append(f"cleaned {cleaned_count} orphaned image records")

    if orphaned_tags_count > 0:
        messages.append(f"cleaned {orphaned_tags_count} orphaned tag entries")

    message = ", ".join(messages) + "."

    return {
        "status": "success",
        "message": message,
        "processed": processed_count,
        "cleaned": cleaned_count,
        "orphaned_tags_cleaned": orphaned_tags_count,
    }


async def scan_and_process_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_scan_and_process."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Scanning and processing...",
        run_scan_and_process,
    )

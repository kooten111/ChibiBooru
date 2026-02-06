import asyncio
import os
from typing import Any, Dict

from database import models
from utils.logging_config import get_logger

logger = get_logger("SystemOrphans")


async def run_clean_orphans(dry_run: bool = True) -> Dict[str, Any]:
    """Service to find and remove database entries for deleted files."""
    from database import get_db_connection

    loop = asyncio.get_running_loop()

    def _clean_orphans_sync():
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
                if not dry_run:
                    cursor.execute(
                        """
                        DELETE FROM image_tags
                        WHERE image_id NOT IN (SELECT id FROM images)
                    """
                    )
                    conn.commit()
                    logger.info(
                        f"Deleted {orphaned_tags_count} orphaned image_tags entries"
                    )

        logger.info("Checking for orphaned image records...")
        db_filepaths = models.get_all_filepaths()

        disk_filepaths = set()
        for root, _, files in os.walk("static/images"):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, "static/images").replace(
                    "\\", "/"
                )
                disk_filepaths.add(rel_path)

        orphans = db_filepaths - disk_filepaths

        if dry_run:
            message = (
                "Found {orphans} orphaned image records and {tags} orphaned tag entries "
                "(dry run - not removed)."
            ).format(orphans=len(orphans), tags=orphaned_tags_count)
            return {
                "status": "success",
                "message": message,
                "orphans_found": len(orphans),
                "orphaned_tags": orphaned_tags_count,
                "orphans": sorted(list(orphans)),
                "cleaned": 0,
            }

        cleaned_count = 0
        for orphan_path in orphans:
            if models.delete_image(orphan_path):
                cleaned_count += 1

        if cleaned_count > 0 or orphaned_tags_count > 0:
            logger.info(
                "Cleaned {images} orphaned image records and {tags} orphaned tag entries.".format(
                    images=cleaned_count, tags=orphaned_tags_count
                )
            )
            logger.info("Reloading data to update tag counts...")
            models.load_data_from_db()
            logger.info("Tag counts updated after orphan cleanup.")
            message = (
                "Cleaned {images} orphaned images and {tags} orphaned tag entries. "
                "Tag counts updated."
            ).format(images=cleaned_count, tags=orphaned_tags_count)
        else:
            message = "No orphaned entries found. Database is clean!"

        return {
            "status": "success",
            "message": message,
            "orphans_found": len(orphans),
            "orphaned_tags": orphaned_tags_count,
            "orphans": sorted(list(orphans)),
            "cleaned": cleaned_count,
        }

    return await loop.run_in_executor(None, _clean_orphans_sync)


async def clean_orphans_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_clean_orphans."""
    await task_manager_instance.update_progress(task_id, 0, 100, "Cleaning orphans...")
    dry_run = kwargs.get("dry_run", True)
    return await run_clean_orphans(dry_run=dry_run)

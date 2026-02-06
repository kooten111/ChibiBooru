import config
from typing import Any, Dict

from database import models
from services import monitor_service

from .task_helpers import run_sync_task


def run_rebuild() -> Dict[str, Any]:
    """Service to re-process all tags from the raw_metadata in the database."""
    try:
        monitor_service.stop_monitor()
        models.repopulate_from_database()
        from core.cache_manager import load_data_from_db_async

        load_data_from_db_async()
        return {"status": "success", "message": "Tag re-processing complete."}
    except Exception as e:
        from core.cache_manager import load_data_from_db_async

        load_data_from_db_async()
        raise e


async def rebuild_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_rebuild."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Rebuilding tags from metadata...",
        run_rebuild,
    )


def run_rebuild_categorized() -> Dict[str, Any]:
    """Service to back-fill the categorized tag columns in the images table."""
    updated_count = models.rebuild_categorized_tags_from_relations()
    from core.cache_manager import load_data_from_db_async

    load_data_from_db_async()
    return {
        "status": "success",
        "message": f"Updated categorized tags for {updated_count} images.",
        "changes": updated_count,
    }


async def rebuild_categorized_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_rebuild_categorized."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Rebuilding categorized tags...",
        run_rebuild_categorized,
    )


def run_apply_merged_sources() -> Dict[str, Any]:
    """
    Service to apply the merged sources setting to all images with multiple sources.

    When USE_MERGED_SOURCES_BY_DEFAULT is True: merges tags from all sources.
    When USE_MERGED_SOURCES_BY_DEFAULT is False: reverts to primary source tags.
    """
    try:
        from database import get_db_connection
        from services.switch_source_db import merge_all_sources, switch_metadata_source_db

        use_merged = config.USE_MERGED_SOURCES_BY_DEFAULT
        action = "merge" if use_merged else "un-merge"

        processed_count = 0
        error_count = 0

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT i.filepath, i.active_source, COUNT(DISTINCT s.id) as source_count
                FROM images i
                JOIN image_sources isrc ON i.id = isrc.image_id
                JOIN sources s ON isrc.source_id = s.id
                GROUP BY i.id, i.filepath
                HAVING source_count > 1
            """
            )

            multi_source_images = cursor.fetchall()
            total = len(multi_source_images)

            if total == 0:
                monitor_service.add_log("No images with multiple sources found", "info")
                return {
                    "status": "success",
                    "message": "No images with multiple sources found.",
                    "processed": 0,
                    "errors": 0,
                }

            monitor_service.add_log(
                f"Starting {action} for {total} images with multiple sources", "info"
            )

            for idx, row in enumerate(multi_source_images, 1):
                filepath = row["filepath"]
                current_source = row["active_source"]

                if total <= 10 or idx % max(1, total // 10) == 0:
                    progress_pct = int((idx / total) * 100)
                    monitor_service.add_log(
                        "Progress: {idx}/{total} ({pct}%) - {processed} processed, {errors} errors".format(
                            idx=idx,
                            total=total,
                            pct=progress_pct,
                            processed=processed_count,
                            errors=error_count,
                        ),
                        "info",
                    )

                if use_merged:
                    if current_source != "merged":
                        result = merge_all_sources(filepath)
                        if result.get("status") == "success":
                            processed_count += 1
                        else:
                            error_count += 1
                            monitor_service.add_log(
                                f"Error merging {filepath}: {result.get('error', 'Unknown')}",
                                "error",
                            )
                else:
                    if current_source == "merged":
                        cursor.execute(
                            """
                            SELECT s.name FROM sources s
                            JOIN image_sources isrc ON s.id = isrc.source_id
                            JOIN images i ON isrc.image_id = i.id
                            WHERE i.filepath = ?
                        """,
                            (filepath,),
                        )
                        available_sources = [r["name"] for r in cursor.fetchall()]

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
                                monitor_service.add_log(
                                    f"Error reverting {filepath}: {result.get('error', 'Unknown')}",
                                    "error",
                                )
                        else:
                            error_count += 1
                            monitor_service.add_log(
                                f"No primary source found for {filepath}", "error"
                            )

        monitor_service.add_log("Refreshing cache...", "info")
        models.load_data_from_db()

        monitor_service.add_log("Recounting tags...", "info")
        models.reload_tag_counts()

        action_past = "merged" if use_merged else "reverted to primary source"
        message = f"✓ Processed {total} images: {processed_count} {action_past}"
        if error_count > 0:
            message += f", {error_count} errors"

        monitor_service.add_log(message, "success")

        return {
            "status": "success",
            "message": message,
            "action": action,
            "processed": processed_count,
            "errors": error_count,
            "total": total,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        monitor_service.add_log(f"Fatal error during {action}: {str(e)}", "error")
        raise e


async def apply_merged_sources_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_apply_merged_sources."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Applying merged sources setting...",
        run_apply_merged_sources,
    )


def run_recount_tags() -> Dict[str, Any]:
    """Service to recount all tag usage counts."""
    monitor_service.add_log("Recounting all tags...", "info")
    models.reload_tag_counts()

    tag_count = len(models.get_tag_counts())

    monitor_service.add_log(f"✓ Recounted {tag_count} tags", "success")
    return {
        "status": "success",
        "message": f"Recounted {tag_count} tags",
        "tag_count": tag_count,
    }


async def recount_tags_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_recount_tags."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Recounting tags...",
        run_recount_tags,
    )


def run_recategorize() -> Dict[str, Any]:
    """Service to recategorize misplaced tags without full rebuild."""
    changes = models.recategorize_misplaced_tags()
    models.load_data_from_db()
    return {
        "status": "success",
        "message": f"Recategorized {changes} tags",
        "changes": changes,
    }


async def recategorize_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_recategorize."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Recategorizing tags...",
        run_recategorize,
    )

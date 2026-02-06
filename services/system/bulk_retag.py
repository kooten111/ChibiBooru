import os
from typing import Any, Dict

from services import monitor_service, processing

from .task_helpers import run_sync_task


def run_bulk_retag_local(local_only: bool = False) -> Dict[str, Any]:
    """Re-run local tagger for images. Returns dict with status, message, processed, etc."""
    from database import get_db_connection
    from repositories import tagger_predictions_repository

    mode_desc = "locally-tagged images only" if local_only else "ALL images"
    monitor_service.add_log(f"Starting bulk local tagger re-run ({mode_desc})...", "info")

    if not local_only:
        deleted = tagger_predictions_repository.clear_all_predictions()
        monitor_service.add_log(f"Cleared {deleted} existing predictions", "info")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if local_only:
            cursor.execute(
                """
                SELECT id, filepath FROM images 
                WHERE active_source IN ('local_tagger', 'camie_tagger')
            """
            )
        else:
            cursor.execute("SELECT id, filepath FROM images")
        all_images = cursor.fetchall()

    total = len(all_images)
    if total == 0:
        return {
            "status": "success",
            "message": "No images to process.",
            "processed": 0,
            "predictions_stored": 0,
        }

    monitor_service.add_log(f"Processing {total} images...", "info")

    processed = 0
    total_predictions = 0
    errors = 0

    for idx, row in enumerate(all_images, 1):
        image_id = row["id"]
        filepath = row["filepath"]

        if idx % max(1, total // 10) == 0:
            progress_pct = int((idx / total) * 100)
            monitor_service.add_log(
                f"Progress: {idx}/{total} ({progress_pct}%)", "info"
            )

        try:
            full_path = f"static/images/{filepath}"
            if not os.path.exists(full_path):
                continue
            if full_path.endswith((".mp4", ".webm")):
                continue

            result = processing.tag_with_local_tagger(full_path)
            if result and result.get("data", {}).get("all_predictions"):
                predictions = result["data"]["all_predictions"]
                tagger_name = result["data"].get("tagger_name")
                stored = tagger_predictions_repository.store_predictions(
                    image_id, predictions, tagger_name
                )
                total_predictions += stored
                processed += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                monitor_service.add_log(f"Error processing {filepath}: {str(e)}", "error")

    message = f"✓ Processed {processed}/{total} images, stored {total_predictions} predictions"
    if errors > 0:
        message += f", {errors} errors"
    monitor_service.add_log(message, "success")

    return {
        "status": "success",
        "message": message,
        "processed": processed,
        "predictions_stored": total_predictions,
        "errors": errors,
    }


async def bulk_retag_local_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_bulk_retag_local."""
    local_only = kwargs.get("local_only", False)
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Retagging local images...",
        run_bulk_retag_local,
        local_only,
    )

import asyncio
import uuid

from services.background_tasks import task_manager


def _create_progress_callback(loop, task_manager_instance, task_id):
    def sync_progress_callback(current, total):
        asyncio.run_coroutine_threadsafe(
            task_manager_instance.update_progress(
                task_id,
                progress=current,
                total=total,
                message=f"Generating thumbnails: {current}/{total}",
            ),
            loop,
        )

    return sync_progress_callback


async def run_thumbnail_generation_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task for thumbnail generation."""
    from services.health_service import check_missing_thumbnails

    loop = asyncio.get_running_loop()
    progress_callback = _create_progress_callback(loop, task_manager_instance, task_id)

    result = await loop.run_in_executor(
        None,
        lambda: check_missing_thumbnails(
            auto_fix=True, progress_callback=progress_callback
        ),
    )

    return {
        "status": "success",
        "message": "Generated {fixed} thumbnails (found {found} missing)".format(
            fixed=result.issues_fixed, found=result.issues_found
        ),
        "issues_found": result.issues_found,
        "issues_fixed": result.issues_fixed,
    }


async def start_thumbnail_generation() -> dict:
    """Start thumbnail generation task."""
    task_id = str(uuid.uuid4())
    await task_manager.start_task(task_id, run_thumbnail_generation_task)

    return {
        "status": "started",
        "task_id": task_id,
        "message": "Thumbnail generation started in background",
    }

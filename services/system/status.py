import config
from typing import Any, Dict

from database import models
from services import monitor_service


def validate_secret_string(secret: str) -> Dict[str, Any]:
    """Service to validate if the provided secret matches config.SYSTEM_API_SECRET."""
    if secret and secret == config.SYSTEM_API_SECRET:
        return {"success": True, "valid": True}
    return {"success": True, "valid": False}


def get_system_status() -> Dict[str, Any]:
    """
    Service to get system status, including monitor status.

    Returns:
        Dict containing:
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

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(DISTINCT image_id) FROM image_tags
            """
            )
            tagged_count = cursor.fetchone()[0] or 0

            cursor.execute(
                """
                SELECT COUNT(DISTINCT it.image_id)
                FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE t.name LIKE 'rating:%'
            """
            )
            rated_count = cursor.fetchone()[0] or 0
    except Exception:
        pass

    return {
        "monitor": monitor_status,
        "collection": {
            "total_images": models.get_image_count(),
            "unprocessed": unprocessed_count,
            "tagged": tagged_count,
            "rated": rated_count,
        },
    }


def run_reload_data() -> Dict[str, Any]:
    """Service to trigger a data reload from the database."""
    if models.load_data_from_db():
        image_count = models.get_image_count()
        tag_count = len(models.get_tag_counts())
        return {"status": "success", "images": image_count, "tags": tag_count}
    raise Exception("Failed to reload data")


async def get_task_status_by_id(task_id: str) -> Dict[str, Any]:
    """Service to get the status of a background task."""
    from services.background_tasks import task_manager

    return await task_manager.get_task_status(task_id)

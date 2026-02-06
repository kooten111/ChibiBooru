"""
Helpers for starting background tasks from API routes.

Provides a consistent pattern: generate task_id, start task, return status dict.
"""

import uuid
from typing import Any, Callable, Optional


async def start_background_task(
    task_func: Callable,
    message: str,
    task_id_prefix: Optional[str] = None,
    task_id_key: str = "task_id",
    **kwargs: Any,
) -> dict:
    """
    Start a background task and return the standard status dict.

    Args:
        task_func: Async callable with signature (task_id, task_manager, *args, **kwargs).
        message: Human-readable message for the response.
        task_id_prefix: If set, task_id is f"{prefix}_{uuid_hex[:8]}"; else str(uuid4()).
        task_id_key: Key for the task id in the response ("task_id" or "job_id").
        **kwargs: Passed to task_manager.start_task(..., **kwargs) and thus to task_func.

    Returns:
        Dict with "status": "started", message, and task_id_key: task_id.
    """
    from services.background_tasks import task_manager

    if task_id_prefix:
        task_id = f"{task_id_prefix}_{uuid.uuid4().hex[:8]}"
    else:
        task_id = str(uuid.uuid4())

    await task_manager.start_task(task_id, task_func, **kwargs)

    return {
        "status": "started",
        "message": message,
        task_id_key: task_id,
    }

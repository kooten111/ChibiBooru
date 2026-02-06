import asyncio
from typing import Any, Callable


async def run_sync_task(
    task_id: str,
    task_manager_instance,
    message: str,
    func: Callable[..., Any],
    *args,
    **kwargs,
) -> Any:
    loop = asyncio.get_running_loop()
    await task_manager_instance.update_progress(task_id, 0, 100, message)
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

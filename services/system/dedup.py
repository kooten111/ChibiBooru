from typing import Any, Dict

from database import models
from utils.deduplication import scan_and_remove_duplicates

from .task_helpers import run_sync_task


def run_deduplicate(dry_run: bool = True) -> Dict[str, Any]:
    """Run MD5 deduplication scan. Returns dict with status and results."""
    results = scan_and_remove_duplicates(dry_run=dry_run)
    if not dry_run and results.get("removed", 0) > 0:
        models.load_data_from_db()
    return {"status": "success", "results": results}


async def deduplicate_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_deduplicate."""
    dry_run = kwargs.get("dry_run", True)
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Deduplicating...",
        run_deduplicate,
        dry_run,
    )

from typing import Any, Dict

from services import monitor_service

from .task_helpers import run_sync_task


def run_reindex_database() -> Dict[str, Any]:
    """Service to optimize the database (VACUUM and REINDEX)."""
    try:
        from database.transaction_helpers import get_db_connection_for_maintenance
        import time

        start_time = time.time()
        monitor_service.add_log("Starting database optimization...", "info")

        with get_db_connection_for_maintenance() as conn:
            monitor_service.add_log("Rebuilding FTS index...", "info")
            conn.execute("INSERT INTO images_fts(images_fts) VALUES('rebuild')")

            monitor_service.add_log("Reindexing standard indexes...", "info")
            conn.execute("REINDEX")

            monitor_service.add_log("Vacuuming database...", "info")
            conn.execute("VACUUM")

            monitor_service.add_log("Analyzing database statistics...", "info")
            conn.execute("ANALYZE")

        duration = time.time() - start_time
        message = (
            "Optimization complete: Rebuilt FTS & standard indexes, vacuumed database, "
            f"and updated statistics ({duration:.2f}s)."
        )
        monitor_service.add_log(message, "success")

        return {
            "status": "success",
            "message": message,
            "duration": duration,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        monitor_service.add_log(f"Database optimization failed: {str(e)}", "error")
        raise e


async def reindex_database_task(task_id, task_manager_instance, *args, **kwargs):
    """Background task wrapper for run_reindex_database."""
    return await run_sync_task(
        task_id,
        task_manager_instance,
        "Optimizing database (VACUUM & REINDEX)...",
        run_reindex_database,
    )

"""
API endpoints for the duplicate review workflow.

Endpoints:
    GET  /api/duplicate-review/cache-stats   — cache info
    POST /api/duplicate-review/scan          — trigger background O(n²) scan
    GET  /api/duplicate-review/queue         — paginated queue from cache
    POST /api/duplicate-review/commit        — batch commit staged actions
"""

import asyncio
from quart import request
from routers.api import api_blueprint
from utils.decorators import api_handler
from services import duplicate_review_service
from utils.background_task_helpers import start_background_task


@api_blueprint.route('/duplicate-review/cache-stats')
@api_handler()
async def duplicate_review_cache_stats():
    """Return stats about the pre-computed duplicate_pairs cache."""
    stats = await asyncio.to_thread(duplicate_review_service.get_cache_stats)
    return stats


@api_blueprint.route('/duplicate-review/scan', methods=['POST'])
@api_handler()
async def duplicate_review_scan():
    """
    Trigger a background pHash scan.

    POST /api/duplicate-review/scan?threshold=15
    """
    threshold = request.args.get('threshold', 15, type=int)
    return await start_background_task(
        duplicate_review_service.run_duplicate_scan_task,
        message=f"Duplicate scan started (threshold {threshold})",
        task_id_prefix="dup_scan",
        threshold=threshold,
    )


@api_blueprint.route('/duplicate-review/queue')
@api_handler()
async def get_duplicate_review_queue():
    """
    Paginated queue from the pre-computed cache.

    GET /api/duplicate-review/queue?threshold=5&offset=0&limit=50
    """
    threshold = request.args.get('threshold', 5, type=int)
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 50, type=int)

    result = await asyncio.to_thread(
        duplicate_review_service.get_duplicate_queue,
        threshold=threshold,
        offset=offset,
        limit=limit,
    )
    return result


@api_blueprint.route('/duplicate-review/commit', methods=['POST'])
@api_handler()
async def commit_duplicate_review_actions():
    """
    Commit a batch of staged actions as a background task with progress.

    POST /api/duplicate-review/commit
    Body: { "actions": [ { "image_id_a": int, "image_id_b": int, "action": str, "detail": str? }, ... ] }
    Returns: { "status": "started", "task_id": "..." }
    """
    data = await request.get_json()
    if not data or 'actions' not in data:
        raise ValueError("Request body must contain 'actions' array")

    actions = data['actions']
    if not isinstance(actions, list) or len(actions) == 0:
        raise ValueError("'actions' must be a non-empty array")

    return await start_background_task(
        duplicate_review_service.run_commit_task,
        message=f"Committing {len(actions)} action(s)",
        task_id_prefix="dup_commit",
        actions=actions,
    )

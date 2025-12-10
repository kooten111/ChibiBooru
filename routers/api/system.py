from quart import request, jsonify
from . import api_blueprint
from services import system_service, monitor_service
from utils import api_handler
import asyncio

@api_blueprint.route('/reload', methods=['POST'])
@api_handler()
async def reload_data():
    """Reload data from the database."""
    return await asyncio.to_thread(system_service.reload_data)

@api_blueprint.route('/system/status')
@api_handler()
async def system_status():
    """Get system status information."""
    return system_service.get_system_status()

@api_blueprint.route('/system/logs')
@api_handler()
async def system_logs():
    """Get system logs."""
    return jsonify(monitor_service.get_status().get('logs', []))

@api_blueprint.route('/system/scan', methods=['POST'])
@api_handler()
async def trigger_scan():
    """Scan for new images and process them."""
    return await asyncio.to_thread(system_service.scan_and_process_service)

@api_blueprint.route('/system/rebuild', methods=['POST'])
@api_handler()
async def trigger_rebuild():
    """Rebuild the database from image metadata."""
    return await asyncio.to_thread(system_service.rebuild_service)

@api_blueprint.route('/system/rebuild_categorized', methods=['POST'])
@api_handler()
async def trigger_rebuild_categorized():
    """Rebuild the database with categorized tags."""
    return await asyncio.to_thread(system_service.rebuild_categorized_service)

@api_blueprint.route('/system/recategorize', methods=['POST'])
@api_handler()
async def trigger_recategorize():
    """Recategorize all tags based on current rules."""
    return await asyncio.to_thread(system_service.recategorize_service)

@api_blueprint.route('/system/thumbnails', methods=['POST'])
@api_handler()
async def trigger_thumbnails():
    """Generate thumbnails for all images."""
    return await asyncio.to_thread(system_service.trigger_thumbnails)

@api_blueprint.route('/system/reindex', methods=['POST'])
@api_handler()
async def system_reindex():
    """Reindex the database for faster searches."""
    return await asyncio.to_thread(system_service.reindex_database_service)

@api_blueprint.route('/system/deduplicate', methods=['POST'])
@api_handler()
async def deduplicate():
    """Find and remove duplicate images."""
    return await system_service.deduplicate_service()

@api_blueprint.route('/system/clean_orphans', methods=['POST'])
@api_handler()
async def clean_orphans():
    """Clean orphaned database entries."""
    return await system_service.clean_orphans_service()

@api_blueprint.route('/system/apply_merged_sources', methods=['POST'])
@api_handler()
async def apply_merged_sources():
    """Apply merged metadata sources to all images."""
    return await asyncio.to_thread(system_service.apply_merged_sources_service)

@api_blueprint.route('/system/recount_tags', methods=['POST'])
@api_handler()
async def recount_tags():
    """Recalculate tag counts for all tags."""
    return await asyncio.to_thread(system_service.recount_tags_service)

@api_blueprint.route('/system/monitor/start', methods=['POST'])
@api_handler()
async def start_monitor():
    if not monitor_service.start_monitor():
        raise ValueError("Monitor was already running")
    return {"message": "Monitor started"}

@api_blueprint.route('/system/monitor/stop', methods=['POST'])
@api_handler()
async def stop_monitor():
    if not monitor_service.stop_monitor():
        raise ValueError("Monitor was not running")
    return {"message": "Monitor stopped"}

@api_blueprint.route('/task_status', methods=['GET'])
@api_handler()
async def task_status():
    """Get status of background tasks."""
    return await system_service.get_task_status_service()

@api_blueprint.route('/database_health_check', methods=['POST'])
@api_handler()
async def database_health_check():
    """Run database health check and repair."""
    return await system_service.database_health_check_service()

@api_blueprint.route('/system/bulk_retag_local', methods=['POST'])
@api_handler()
async def bulk_retag_local():
    """Wipe all local tagger predictions and re-run local tagger for all images."""
    return await asyncio.to_thread(system_service.bulk_retag_local_service)

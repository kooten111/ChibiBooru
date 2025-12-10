from quart import request, jsonify
from . import api_blueprint
from services import system_service, monitor_service
from utils import api_handler
import asyncio

@api_blueprint.route('/reload', methods=['POST'])
async def reload_data():
    return await asyncio.to_thread(system_service.reload_data)

@api_blueprint.route('/system/status')
async def system_status():
    return system_service.get_system_status()

@api_blueprint.route('/system/logs')
async def system_logs():
    return jsonify(monitor_service.get_status().get('logs', []))

@api_blueprint.route('/system/scan', methods=['POST'])
async def trigger_scan():
    return await asyncio.to_thread(system_service.scan_and_process_service)

@api_blueprint.route('/system/rebuild', methods=['POST'])
async def trigger_rebuild():
    return await asyncio.to_thread(system_service.rebuild_service)

@api_blueprint.route('/system/rebuild_categorized', methods=['POST'])
async def trigger_rebuild_categorized():
    return await asyncio.to_thread(system_service.rebuild_categorized_service)

@api_blueprint.route('/system/recategorize', methods=['POST'])
async def trigger_recategorize():
    return await asyncio.to_thread(system_service.recategorize_service)

@api_blueprint.route('/system/thumbnails', methods=['POST'])
async def trigger_thumbnails():
    return await asyncio.to_thread(system_service.trigger_thumbnails)

@api_blueprint.route('/system/reindex', methods=['POST'])
async def system_reindex():
    return await asyncio.to_thread(system_service.reindex_database_service)

@api_blueprint.route('/system/deduplicate', methods=['POST'])
async def deduplicate():
    return await system_service.deduplicate_service()

@api_blueprint.route('/system/clean_orphans', methods=['POST'])
async def clean_orphans():
    return await system_service.clean_orphans_service()

@api_blueprint.route('/system/apply_merged_sources', methods=['POST'])
async def apply_merged_sources():
    return await asyncio.to_thread(system_service.apply_merged_sources_service)

@api_blueprint.route('/system/recount_tags', methods=['POST'])
async def recount_tags():
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
async def task_status():
    return await system_service.get_task_status_service()

@api_blueprint.route('/database_health_check', methods=['POST'])
async def database_health_check():
    return await system_service.database_health_check_service()

@api_blueprint.route('/system/bulk_retag_local', methods=['POST'])
async def bulk_retag_local():
    """Wipe all local tagger predictions and re-run local tagger for all images."""
    return await asyncio.to_thread(system_service.bulk_retag_local_service)

from quart import request, jsonify
from . import api_blueprint
from services import system_service, monitor_service
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
async def start_monitor():
    if monitor_service.start_monitor():
        return jsonify({"status": "success", "message": "Monitor started."})
    return jsonify({"error": "Monitor was already running."}), 400

@api_blueprint.route('/system/monitor/stop', methods=['POST'])
async def stop_monitor():
    if monitor_service.stop_monitor():
        return jsonify({"status": "success", "message": "Monitor stopped."})
    return jsonify({"error": "Monitor was not running."}), 400

@api_blueprint.route('/task_status', methods=['GET'])
async def task_status():
    return await system_service.get_task_status_service()

@api_blueprint.route('/database_health_check', methods=['POST'])
async def database_health_check():
    return await system_service.database_health_check_service()

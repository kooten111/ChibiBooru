from quart import request, jsonify
from . import api_blueprint
from services import system_service, monitor_service
from services.background_tasks import task_manager
from utils import api_handler
from utils.background_task_helpers import start_background_task
import asyncio

@api_blueprint.route('/reload', methods=['POST'])
@api_handler()
async def reload_data():
    """Reload data from the database."""
    return await asyncio.to_thread(system_service.run_reload_data)

@api_blueprint.route('/system/validate_secret', methods=['POST'])
@api_handler()
async def validate_secret():
    """Validate if the provided secret is correct."""
    secret = request.args.get('secret', '') or (await request.form).get('secret', '')
    return await asyncio.to_thread(system_service.validate_secret_string, secret)

@api_blueprint.route('/system/status')
@api_handler()
async def system_status():
    """Get system status information."""
    return await asyncio.to_thread(system_service.get_system_status)


@api_blueprint.route('/ready')
async def check_ready():
    """Check if the application is ready to serve requests.
    
    This endpoint is used by the startup page to determine when
    the application has fully initialized.
    """
    from quart import session
    from app import is_app_ready, get_init_status, get_init_progress
    
    try:
        status = get_init_status()
        progress = get_init_progress()
        
        # Check if app has completed initialization
        if not is_app_ready():
            return jsonify({
                'ready': False,
                'status': status,
                'progress': progress
            })
        
        # Determine redirect based on session
        if 'logged_in' in session:
            redirect_url = '/'
        else:
            redirect_url = '/login'
        
        return jsonify({
            'ready': True,
            'status': status,
            'progress': 100,
            'redirect': redirect_url
        })
    except Exception as e:
        return jsonify({
            'ready': False,
            'status': f'Error: {e}',
            'progress': 0
        }), 503

@api_blueprint.route('/system/logs')
@api_handler()
async def system_logs():
    """Get system logs."""
    return jsonify(monitor_service.get_status().get('logs', []))

@api_blueprint.route('/system/scan', methods=['POST'])
@api_handler()
async def trigger_scan():
    """Scan for new images and process them."""
    return await start_background_task(system_service.scan_and_process_task, "Scan started in background")

@api_blueprint.route('/system/rebuild', methods=['POST'])
@api_handler()
async def trigger_rebuild():
    """Rebuild the database from image metadata."""
    return await start_background_task(system_service.rebuild_task, "Rebuild started in background")

@api_blueprint.route('/system/rebuild_categorized', methods=['POST'])
@api_handler()
async def trigger_rebuild_categorized():
    """Rebuild the database with categorized tags."""
    return await start_background_task(system_service.rebuild_categorized_task, "Categorized tags rebuild started in background")

@api_blueprint.route('/system/recategorize', methods=['POST'])
@api_handler()
async def trigger_recategorize():
    """Recategorize all tags based on current rules."""
    return await start_background_task(system_service.recategorize_task, "Recategorization started in background")

@api_blueprint.route('/system/thumbnails', methods=['POST'])
@api_handler()
async def trigger_thumbnails():
    """Generate thumbnails for all images."""
    return await system_service.start_thumbnail_generation()

@api_blueprint.route('/system/reindex', methods=['POST'])
@api_handler()
async def system_reindex():
    """Reindex the database for faster searches."""
    return await start_background_task(system_service.reindex_database_task, "Database optimization started in background")

@api_blueprint.route('/system/deduplicate', methods=['POST'])
@api_handler()
async def deduplicate():
    """Find and remove duplicate images."""
    data = (await request.get_json(silent=True)) or {}
    dry_run = data.get("dry_run", True)
    return await start_background_task(system_service.deduplicate_task, "Deduplication started in background", dry_run=dry_run)

@api_blueprint.route('/system/clean_orphans', methods=['POST'])
@api_handler()
async def clean_orphans():
    """Clean orphaned database entries."""
    data = (await request.get_json(silent=True)) or {}
    dry_run = data.get('dry_run', True)
    return await start_background_task(system_service.clean_orphans_task, "Orphan cleanup started in background", dry_run=dry_run)

@api_blueprint.route('/system/apply_merged_sources', methods=['POST'])
@api_handler()
async def apply_merged_sources():
    """Apply merged metadata sources to all images."""
    return await start_background_task(system_service.apply_merged_sources_task, "Source merge application started in background")

@api_blueprint.route('/system/recount_tags', methods=['POST'])
@api_handler()
async def recount_tags():
    """Recalculate tag counts for all tags."""
    return await start_background_task(system_service.recount_tags_task, "Tag recount started in background")

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
    task_id = request.args.get('task_id')
    if not task_id:
        return {"error": "task_id is required"}, 400
    
    status = await system_service.get_task_status_by_id(task_id)
    if not status:
        return {"error": "Task not found"}, 404
        
    return status

@api_blueprint.route('/database_health_check', methods=['POST'])
@api_handler()
async def database_health_check():
    """Run database health check and repair."""
    data = (await request.get_json(silent=True)) or {}
    auto_fix = data.get("auto_fix", True)
    include_thumbnails = data.get("include_thumbnails", False)
    include_tag_deltas = data.get("include_tag_deltas", True)
    return await asyncio.to_thread(
        system_service.run_database_health_check,
        auto_fix,
        include_thumbnails,
        include_tag_deltas,
    )

@api_blueprint.route('/system/bulk_retag_local', methods=['POST'])
@api_handler()
async def bulk_retag_local():
    """Wipe all local tagger predictions and re-run local tagger for all images."""
    data = (await request.get_json(silent=True)) or {}
    local_only = data.get("local_only", False)
    return await start_background_task(system_service.bulk_retag_local_task, "Bulk local retagging started in background", local_only=local_only)

@api_blueprint.route('/system/broken_images', methods=['GET'])
@api_handler()
async def find_broken_images():
    """Find images with missing tags, hashes, or embeddings."""
    return await system_service.run_find_broken_images()

@api_blueprint.route('/system/broken_images/cleanup', methods=['POST'])
@api_handler()
async def cleanup_broken_images():
    """Cleanup or retry broken images."""
    import config
    from utils.validation import validate_enum, validate_list_of_integers
    
    data = (await request.get_json(silent=True)) or {}
    action = validate_enum(
        data.get('action', 'scan'),
        param_name='action',
        allowed_values=['scan', 'delete', 'retry', 'delete_permanent']
    )
    image_ids = validate_list_of_integers(
        data.get('image_ids', []),
        param_name='image_ids',
        allow_empty=True
    )
    
    secret = request.args.get('secret', '') or (await request.form).get('secret', '')
    if secret != config.SYSTEM_API_SECRET:
        return {"error": "Unauthorized"}, 401
        
    return await system_service.run_cleanup_broken_images(action, image_ids)

@api_blueprint.route('/system/config', methods=['GET'])
@api_handler()
async def get_config():
    """Get all editable settings grouped by category."""
    from services import config_service
    return await asyncio.to_thread(config_service.get_editable_settings)

@api_blueprint.route('/system/config/schema', methods=['GET'])
@api_handler()
async def get_config_schema():
    """Get setting metadata/schema."""
    from services import config_service
    return await asyncio.to_thread(config_service.get_setting_schema)

@api_blueprint.route('/system/config/update', methods=['POST'])
@api_handler()
async def update_config():
    """Update one or more settings."""
    from services import config_service
    import config as config_module  # Import at the top to avoid UnboundLocalError
    
    data = await request.get_json()
    if not data:
        raise ValueError("No data provided")
    
    # Validate secret (required for security)
    secret = request.args.get('secret')
    if not secret:
        raise ValueError("System secret required")
    
    # Check secret
    if secret != config_module.SYSTEM_API_SECRET:
        raise ValueError("Invalid system secret")
    
    # Update settings
    success, errors = await asyncio.to_thread(config_service.update_settings_batch, data)
    
    if success:
        # Reload config
        config_module.reload_config()
        return {"status": "success", "message": "Settings updated successfully"}
    else:
        return {"status": "error", "errors": errors}, 400

@api_blueprint.route('/system/config/reload', methods=['POST'])
@api_handler()
async def reload_config():
    """Reload config from files."""
    import config
    config.reload_config()
    return {"status": "success", "message": "Config reloaded"}

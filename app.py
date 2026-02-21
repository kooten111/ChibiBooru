import config
from quart import Quart, redirect, request
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv(override=True)

from routers import main_blueprint, api_blueprint
from database import models
from database import initialize_database, repair_orphaned_image_tags
from services.priority_service import check_and_apply_priority_changes
from services.health_service import startup_health_check
from utils.logging_config import setup_logging, get_logger

# Global app readiness state
_app_ready = False
_init_status = "Starting..."
_init_progress = 0  # 0-100


def is_app_ready():
    """Check if the application is fully initialized."""
    return _app_ready


def get_init_status():
    """Get current initialization status message."""
    return _init_status


def get_init_progress():
    """Get current initialization progress (0-100)."""
    return _init_progress


def create_app():
    """Create and configure the Quart application."""
    global _app_ready, _init_status
    _app_ready = False
    _init_status = "Starting server..."
    
    # Initialize logging first
    log_level = getattr(config, 'LOG_LEVEL', 'INFO')
    setup_logging(level=log_level)
    logger = get_logger('App')
    logger.info("Creating ChibiBooru application...")

    app = Quart(__name__)

    # Quart config
    app.config['SYSTEM_API_SECRET'] = config.SYSTEM_API_SECRET
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max request size

    # Add before_request handler to redirect to startup if not ready
    @app.before_request
    async def check_app_ready():
        """Redirect to startup page if app is not fully initialized."""
        if not _app_ready:
            # Allow these paths during startup
            allowed_paths = ['/startup', '/api/ready', '/static/', '/favicon', '/api/system/']
            path = request.path
            
            if not any(path.startswith(p) for p in allowed_paths):
                return redirect('/startup')

    # Helper function for importing default categorizations
    async def _import_default_categorizations():
        """Import default tag categorizations if file exists and this is a first run."""
        from pathlib import Path
        import json
        
        default_cat_file = Path(__file__).parent / "data" / "default_tag_categorizations.json"
        
        # Check if file exists
        if not default_cat_file.exists():
            logger.debug("No default tag categorizations file found")
            return
        
        try:
            # Check if database already has categorizations (not first run)
            from database import get_db_connection
            with get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as count FROM tags WHERE extended_category IS NOT NULL")
                result = cur.fetchone()
                categorized_count = result['count'] if result else 0
            
            # Only import if no categorizations exist yet
            if categorized_count > 0:
                logger.debug(f"Database already has {categorized_count} categorized tags, skipping default import")
                return
            
            # Load and import the default categorizations
            with open(default_cat_file, 'r') as f:
                data = json.load(f)
            
            from services import tag_categorization_service
            stats = tag_categorization_service.import_tag_categorizations(data, mode='merge', create_missing=True)
            
            logger.info(f"Imported default tag categorizations: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped")
            if stats.get('errors'):
                logger.warning(f"Import errors: {stats['errors']}")
                
        except Exception as e:
            logger.warning(f"Failed to import default tag categorizations: {e}")

    # Heavy initialization runs as a BACKGROUND TASK (non-blocking)
    @app.before_serving
    async def start_background_init():
        """Start initialization as a background task so server accepts connections immediately."""
        import asyncio
        asyncio.create_task(initialize_app())
    
    async def initialize_app():
        """Initialize the application in the background."""
        global _app_ready, _init_status, _init_progress
        import asyncio
        
        logger.info("Initializing ChibiBooru in background...")
        
        try:
            _init_status = "Initializing database..."
            _init_progress = 5
            await asyncio.sleep(0)  # Yield to allow other tasks
            initialize_database()
            
            _init_status = "Repairing orphaned tags..."
            _init_progress = 15
            await asyncio.sleep(0)
            repair_orphaned_image_tags()
            
            _init_status = "Running health checks..."
            _init_progress = 30
            await asyncio.sleep(0)
            startup_health_check()
            
            _init_status = "Importing default tag categorizations..."
            _init_progress = 37
            await asyncio.sleep(0)
            await _import_default_categorizations()
            
            _init_status = "Checking priority changes..."
            _init_progress = 45
            await asyncio.sleep(0)
            check_and_apply_priority_changes()
            
            _init_status = "Loading data from database..."
            _init_progress = 60
            await asyncio.sleep(0)
            # This is the heavy step - run in thread
            await asyncio.to_thread(models.load_data_from_db, verbose=False)
            
            # Mark app as ready
            _init_progress = 100
            _app_ready = True
            _init_status = "Ready"
            logger.info("ChibiBooru initialization complete - app is ready")
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            _init_status = f"Error: {e}"
            raise


    # Note: Monitor service is now run as a standalone process (monitor_runner.py)
    # and is started by start_booru.sh. This prevents duplicate monitors when
    # using multiple uvicorn workers.

    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')
    
    # Register static file blueprint for proper handling of special characters
    from routers import static_blueprint
    app.register_blueprint(static_blueprint)

    # Register custom Jinja2 filters
    from utils import url_encode_path
    import os
    app.jinja_env.filters['urlencode_path'] = url_encode_path
    app.jinja_env.filters['basename'] = os.path.basename

    # Add after_request handler to manage response headers
    @app.after_request
    async def set_response_headers(response):
        """Set response headers for all responses."""
        # Remove Permissions-Policy to avoid browser console warnings from
        # unsupported directives (e.g., browsing-topics) across user agents.
        response.headers.pop('Permissions-Policy', None)
        return response

    return app

if __name__ == '__main__':
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT, log_level="info")
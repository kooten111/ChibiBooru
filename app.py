import config
from quart import Quart
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv(override=True)

from routers import main_blueprint, api_blueprint
from database import models
from database import initialize_database, repair_orphaned_image_tags
from services.priority_service import check_and_apply_priority_changes
from services.health_service import startup_health_check
from utils.logging_config import setup_logging, get_logger

def create_app():
    """Create and configure the Quart application."""
    # Initialize logging first
    log_level = getattr(config, 'LOG_LEVEL', 'INFO')
    setup_logging(level=log_level)
    logger = get_logger('App')
    logger.info("Initializing ChibiBooru application...")

    app = Quart(__name__)

    # Quart config
    app.config['RELOAD_SECRET'] = config.RELOAD_SECRET
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max request size

    # Ensure the database file and tables exist.
    initialize_database()

    # Auto-repair any orphaned image tags (data integrity check)
    repair_orphaned_image_tags()

    # Run database health checks and auto-fix critical issues
    startup_health_check()

    # Check if BOORU_PRIORITY changed and auto-apply if needed
    # This must happen before loading data from DB
    check_and_apply_priority_changes()

    # Load data from DB on startup (no app context needed in Quart)
    models.load_data_from_db()

    # Start monitor service if enabled
    if config.MONITOR_ENABLED:
        from services import monitor_service
        if monitor_service.start_monitor():
            logger.info("✓ Monitor service started automatically")
        else:
            logger.warning("⚠ Monitor service was already running")

    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # Register custom Jinja2 filters
    from utils import url_encode_path
    import os
    app.jinja_env.filters['urlencode_path'] = url_encode_path
    app.jinja_env.filters['basename'] = os.path.basename

    return app

if __name__ == '__main__':
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT, log_level="info")
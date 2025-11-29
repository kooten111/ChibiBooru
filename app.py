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

def create_app():
    """Create and configure the Quart application."""
    app = Quart(__name__)

    # Quart config
    app.config['RELOAD_SECRET'] = config.RELOAD_SECRET
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=4)

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

    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app

if __name__ == '__main__':
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT, log_level="info")
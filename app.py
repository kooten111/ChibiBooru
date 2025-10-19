import config
from flask import Flask
from dotenv import load_dotenv

load_dotenv(override=True)

from routes import main_blueprint, api_blueprint
import models
from database import initialize_database

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Flask config
    app.config['RELOAD_SECRET'] = config.RELOAD_SECRET
    app.config['SECRET_KEY'] = config.SECRET_KEY
    
    # Ensure the database file and tables exist.
    initialize_database()

    with app.app_context():
        models.load_data_from_db()

    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
# app.py
from flask import Flask
from dotenv import load_dotenv

load_dotenv(override=True)

from routes import main_blueprint, api_blueprint
import models
from database import initialize_database

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Ensure the database file and tables exist.
    initialize_database()

    with app.app_context():
        models.load_data_from_db()

    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
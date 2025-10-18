from flask import Flask
from dotenv import load_dotenv
import onnxruntime

# Load environment variables
load_dotenv(override=True)
onnxruntime.preload_dlls()

# Import blueprints and services
from routes import main_blueprint, api_blueprint
from services import start_monitor

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # Start the background monitor
    start_monitor()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=5000, debug=True)
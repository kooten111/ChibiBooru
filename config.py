"""
HomeBooru Configuration
Centralized configuration for all modules
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==================== PATHS ====================

# Image storage
IMAGE_DIRECTORY = "./static/images"
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000  # Max dimension for thumbnails

# Data storage
TAGS_FILE = "./tags.json"
METADATA_DIR = "./metadata"
DATABASE_PATH = "./booru.db"

# ==================== API KEYS ====================

# SauceNao reverse image search
SAUCENAO_API_KEY = os.environ.get('SAUCENAO_API_KEY', '')

# Gelbooru API (optional, for authenticated requests)
GELBOORU_API_KEY = os.environ.get('GELBOORU_API_KEY', '')
GELBOORU_USER_ID = os.environ.get('GELBOORU_USER_ID', '')

# System control secret
RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

# ==================== LOCAL TAGGER (AI TAGGING) ====================

# Model paths - supports any ONNX tagger with similar metadata format
LOCAL_TAGGER_MODEL_PATH = "./models/Tagger/model.onnx"
LOCAL_TAGGER_METADATA_PATH = "./models/Tagger/metadata.json"

# Model behavior
LOCAL_TAGGER_THRESHOLD = 0.5  # Confidence threshold for tag predictions
LOCAL_TAGGER_TARGET_SIZE = 512  # Input image size for model

# Display name - this is what shows in metadata and UI
# Change this when you swap models (e.g., "CamieTagger", "WD14", "Z3D-E621")
LOCAL_TAGGER_NAME = os.environ.get('LOCAL_TAGGER_NAME', 'CamieTagger')

# ==================== MONITORING ====================

# Automatic background scanning for new images
MONITOR_ENABLED = True
MONITOR_INTERVAL = 300  # seconds between checks (5 minutes)

# ==================== PROCESSING ====================

# Parallel processing
MAX_WORKERS = 4  # Number of parallel threads for tag fetching

# Request timeouts
REQUEST_TIMEOUT = 10  # seconds

# Rate limiting
RATE_LIMIT_DELAY = 0.5  # seconds between requests

# ==================== SOURCE PRIORITY ====================

# Order matters - first match wins for primary source
# Used for determining which source provides categorized tags
BOORU_PRIORITY = [
    "e621",         # Good categorization
    "danbooru",     # Best categorization
    "gelbooru",     # Tags only
    "yandere",      # Tags only
    "local_tagger"  # AI fallback
]

# ==================== FLASK APP ====================

# Web server
FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Pagination
IMAGES_PER_PAGE = 50

# ==================== FEATURE FLAGS ====================

# Enable/disable features
ENABLE_SAUCENAO = bool(SAUCENAO_API_KEY)  # Auto-enable if key present
ENABLE_LOCAL_TAGGER = True  # Set to False to disable AI tagging entirely
ENABLE_DEDUPLICATION = True  # MD5-based duplicate detection

# ==================== VALIDATION ====================

def validate_config():
    """Validate configuration and warn about issues"""
    warnings = []
    
    if not os.path.exists(IMAGE_DIRECTORY):
        warnings.append(f"Image directory not found: {IMAGE_DIRECTORY}")
    
    if ENABLE_LOCAL_TAGGER:
        if not os.path.exists(LOCAL_TAGGER_MODEL_PATH):
            warnings.append(f"Local tagger model not found: {LOCAL_TAGGER_MODEL_PATH}")
        if not os.path.exists(LOCAL_TAGGER_METADATA_PATH):
            warnings.append(f"Local tagger metadata not found: {LOCAL_TAGGER_METADATA_PATH}")
    
    if RELOAD_SECRET == 'change-this-secret':
        warnings.append("RELOAD_SECRET is set to default value - change this for production!")
    
    if warnings:
        print("\n⚠️  Configuration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
    
    return len(warnings) == 0

# ==================== HELPER FUNCTIONS ====================

def get_local_tagger_config():
    """Get local tagger configuration as a dict"""
    return {
        "model_path": LOCAL_TAGGER_MODEL_PATH,
        "metadata_path": LOCAL_TAGGER_METADATA_PATH,
        "threshold": LOCAL_TAGGER_THRESHOLD,
        "target_size": LOCAL_TAGGER_TARGET_SIZE,
        "name": LOCAL_TAGGER_NAME,
        "enabled": ENABLE_LOCAL_TAGGER
    }

def get_booru_apis():
    """Get configured booru API settings"""
    return {
        "gelbooru": {
            "api_key": GELBOORU_API_KEY,
            "user_id": GELBOORU_USER_ID
        }
    }

# Run validation on import
if __name__ != "__main__":
    validate_config()
"""
Centralized configuration for all modules
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Application name (shown in header and page titles)
APP_NAME = os.environ.get('APP_NAME', 'ChibiBooru')

# ==================== PATHS ====================

# Image storage
IMAGE_DIRECTORY = "./static/images"
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000  # Max dimension for thumbnails

# Ingest folder - drop images here and they'll be processed automatically
INGEST_DIRECTORY = "./ingest"

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

# ==================== NEW: APP SECURITY ====================

# Password for simple web UI login
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'default-password')

# Secret key for Flask sessions (required for login)
# Set this in your .env file to a long, random string
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-for-production')


# ==================== LOCAL TAGGER (AI TAGGING) ====================

# Model paths - supports any ONNX tagger with similar metadata format
LOCAL_TAGGER_MODEL_PATH = "./models/Tagger/model.onnx"
LOCAL_TAGGER_METADATA_PATH = "./models/Tagger/metadata.json"

# Model behavior
LOCAL_TAGGER_THRESHOLD = 0.6  # Confidence threshold for tag predictions
LOCAL_TAGGER_TARGET_SIZE = 512  # Input image size for model

# Display name - this is what shows in metadata and UI
# Change this when you swap models (e.g., "CamieTagger", "WD14", "Z3D-E621")
LOCAL_TAGGER_NAME = os.environ.get('LOCAL_TAGGER_NAME', 'CamieTagger')

# Confidence thresholds for immutable data architecture
# STORAGE_THRESHOLD: Store all predictions >= this value (for cross-referencing later)
# DISPLAY_THRESHOLD: When merging into other sources, only show predictions >= this value
LOCAL_TAGGER_STORAGE_THRESHOLD = float(os.environ.get('LOCAL_TAGGER_STORAGE_THRESHOLD', 0.50))
LOCAL_TAGGER_DISPLAY_THRESHOLD = float(os.environ.get('LOCAL_TAGGER_DISPLAY_THRESHOLD', 0.70))

# Categories to merge into other sources (character/copyright/artist usually correct from boorus)
LOCAL_TAGGER_MERGE_CATEGORIES = ['general']

# ==================== MONITORING ====================

# Automatic background scanning for new images
MONITOR_ENABLED = True
MONITOR_INTERVAL = 300  # seconds between checks (5 minutes)

# ==================== DATABASE PERFORMANCE ====================

# SQLite cache size in MB (default 64MB, increase for better performance with large databases)
# Higher values use more RAM but improve query performance
DB_CACHE_SIZE_MB = int(os.environ.get('DB_CACHE_SIZE_MB', 64))

# Memory-mapped I/O size in MB (default 256MB)
# Allows SQLite to map database file to memory for faster reads
DB_MMAP_SIZE_MB = int(os.environ.get('DB_MMAP_SIZE_MB', 256))

# Batch size for database operations (default 100)
# Higher values = fewer commits = faster but longer locks
DB_BATCH_SIZE = int(os.environ.get('DB_BATCH_SIZE', 100))

# WAL checkpoint interval (number of frames, default 1000)
# Controls when WAL file is checkpointed back to main database
DB_WAL_AUTOCHECKPOINT = int(os.environ.get('DB_WAL_AUTOCHECKPOINT', 1000))

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
#
# IMPORTANT: When you change BOORU_PRIORITY, increment BOORU_PRIORITY_VERSION
# This ensures remote systems detect the change and re-tag automatically
BOORU_PRIORITY_VERSION = 4  # Increment this when changing priority order

BOORU_PRIORITY = [
    "danbooru",     # Best general categorization
    "e621",         # Good specific categorization
    "gelbooru",     # Tags only
    "yandere",      # Tags only
    "pixiv",        # Pixiv tags and artist info
    "local_tagger"  # AI fallback
]

# Use merged sources as default for new images
# When True: Images with multiple sources will default to merged view
# When False: Images will use first available source from BOORU_PRIORITY
USE_MERGED_SOURCES_BY_DEFAULT = True

# ==================== FLASK APP ====================

# Web server
FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Pagination
IMAGES_PER_PAGE = 100

# ==================== FEATURE FLAGS ====================

# Enable/disable features
ENABLE_SAUCENAO = bool(SAUCENAO_API_KEY)  # Auto-enable if key present
ENABLE_LOCAL_TAGGER = True  # Set to False to disable AI tagging entirely
ENABLE_DEDUPLICATION = True  # MD5-based duplicate detection

# Local tagger behavior
# If True, runs local tagger on ALL images (even when online sources are found)
# If False, only runs local tagger as fallback when no online sources are found
LOCAL_TAGGER_ALWAYS_RUN = os.environ.get('LOCAL_TAGGER_ALWAYS_RUN', 'false').lower() in ('true', '1', 'yes')

# ==================== SIMILARITY CALCULATION ====================

# Similarity calculation method
# Options: 'jaccard' (basic set intersection/union), 'weighted' (IDF + category weights)
SIMILARITY_METHOD = os.environ.get('SIMILARITY_METHOD', 'weighted')

# Category weights for weighted similarity
# Higher values mean matching tags in that category contributes more to similarity
SIMILARITY_CATEGORY_WEIGHTS = {
    'character': 6.0,   # Character matches are very significant
    'copyright': 3.0,   # Same series/franchise is important
    'artist': 2.0,      # Same artist style matters
    'species': 2.5,     # Species tags
    'general': 3.0,     # Standard descriptive tags
    'meta': 0.5         # Resolution, format, year - less relevant for similarity
}

# ==================== VALIDATION ====================

def validate_config():
    """Validate configuration and warn about issues"""
    warnings = []

    if not os.path.exists(IMAGE_DIRECTORY):
        warnings.append(f"Image directory not found: {IMAGE_DIRECTORY}")

    # Create ingest directory if it doesn't exist
    if not os.path.exists(INGEST_DIRECTORY):
        try:
            os.makedirs(INGEST_DIRECTORY, exist_ok=True)
            print(f"✓ Created ingest directory: {INGEST_DIRECTORY}")
        except Exception as e:
            warnings.append(f"Failed to create ingest directory: {e}")

    if ENABLE_LOCAL_TAGGER:
        if not os.path.exists(LOCAL_TAGGER_MODEL_PATH):
            warnings.append(f"Local tagger model not found: {LOCAL_TAGGER_MODEL_PATH}")
        if not os.path.exists(LOCAL_TAGGER_METADATA_PATH):
            warnings.append(f"Local tagger metadata not found: {LOCAL_TAGGER_METADATA_PATH}")

    if RELOAD_SECRET == 'change-this-secret':
        warnings.append("RELOAD_SECRET is set to default value - change this for production!")

    if APP_PASSWORD == 'default-password':
        warnings.append("APP_PASSWORD is set to default value - change this for security!")

    if SECRET_KEY == 'dev-secret-key-change-for-production':
        warnings.append("SECRET_KEY is set to default value - change this for production!")

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
        "enabled": ENABLE_LOCAL_TAGGER,
        "storage_threshold": LOCAL_TAGGER_STORAGE_THRESHOLD,
        "display_threshold": LOCAL_TAGGER_DISPLAY_THRESHOLD,
        "merge_categories": LOCAL_TAGGER_MERGE_CATEGORIES,
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
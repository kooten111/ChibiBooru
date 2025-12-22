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

# ==================== LOGGING ====================

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

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

# Pixiv complement behavior
# If True, always runs local tagger to complement Pixiv tags (even when LOCAL_TAGGER_ALWAYS_RUN is False)
# Pixiv tags are often incomplete, so this helps add missing tags
LOCAL_TAGGER_COMPLEMENT_PIXIV = os.environ.get('LOCAL_TAGGER_COMPLEMENT_PIXIV', 'true').lower() in ('true', '1', 'yes')

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

# ==================== VISUAL SIMILARITY (PERCEPTUAL HASH) ====================

# Enable visual similarity in the related images sidebar
# When enabled, uses a blend of tag-based and visual perceptual hash similarity
VISUAL_SIMILARITY_ENABLED = os.environ.get('VISUAL_SIMILARITY_ENABLED', 'true').lower() in ('true', '1', 'yes')

# Weight for visual similarity vs tag-based similarity in blended results
# Values from 0.0 to 1.0, visual_weight + tag_weight should equal 1.0
VISUAL_SIMILARITY_WEIGHT = float(os.environ.get('VISUAL_SIMILARITY_WEIGHT', 0.3))
TAG_SIMILARITY_WEIGHT = float(os.environ.get('TAG_SIMILARITY_WEIGHT', 0.7))

# Hamming distance threshold for considering images similar
# Lower = stricter matching (0-64 scale, 64-bit hash)
# 0-5: Near identical, 6-10: Very similar, 11-15: Somewhat similar
VISUAL_SIMILARITY_THRESHOLD = int(os.environ.get('VISUAL_SIMILARITY_THRESHOLD', 15))

# Enable semantic (vector-based) similarity
# This requires significant RAM and CPU. Disable for weaker machines.
# If False, visual similarity will rely only on fast pHash/ColorHash.
ENABLE_SEMANTIC_SIMILARITY = os.environ.get('ENABLE_SEMANTIC_SIMILARITY', 'true').lower() in ('true', '1', 'yes')

# ==================== FILE TYPES ====================

SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif')
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.webm')
SUPPORTED_ZIP_EXTENSIONS = ('.zip',)
SUPPORTED_ANIMATION_EXTENSIONS = ('.gif', '.webp', '.apng')
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_VIDEO_EXTENSIONS + SUPPORTED_ZIP_EXTENSIONS


def is_supported_media(filepath: str) -> bool:
    """Check if a file is a supported media type."""
    return filepath.lower().endswith(SUPPORTED_MEDIA_EXTENSIONS)


def is_supported_image(filepath: str) -> bool:
    """Check if a file is a supported image type."""
    return filepath.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)


def is_video(filepath: str) -> bool:
    """Check if a file is a video."""
    return filepath.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)


def is_animated(filepath: str) -> bool:
    """Check if a file might be animated (gif, webp, apng)."""
    return filepath.lower().endswith(SUPPORTED_ANIMATION_EXTENSIONS)


def is_zip_animation(filepath: str) -> bool:
    """Check if a file is a zip-based animation."""
    return filepath.lower().endswith(SUPPORTED_ZIP_EXTENSIONS)


# ==================== DEFAULTS ====================

class Defaults:
    """Default values for various operations."""
    PAGINATION_LIMIT = 100
    IMAGE_BROWSER_LIMIT = 50
    BATCH_SIZE = 100
    SIMILARITY_CANDIDATES = 500
    AUTOCOMPLETE_MIN_CHARS = 2
    AUTOCOMPLETE_MAX_RESULTS = 20


class Timeouts:
    """Timeout values in seconds."""
    API_REQUEST = 10
    SAUCENAO_SEARCH = 30
    LONG_OPERATION = 300
    FILE_DOWNLOAD = 60

    # JavaScript timeouts (in milliseconds)
    JS_API_TIMEOUT = 5000
    JS_LONG_TIMEOUT = 90000


class Intervals:
    """Interval values in seconds."""
    MONITOR_CHECK = 300
    RATE_LIMIT_WINDOW = 30
    CACHE_REFRESH = 600


class Thresholds:
    """Threshold values."""
    LOCAL_TAGGER_CONFIDENCE = 0.6
    LOCAL_TAGGER_DISPLAY = 0.7
    SIMILARITY_MINIMUM = 0.1
    HIGH_CONFIDENCE = 0.9


class Limits:
    """Size and count limits."""
    MAX_UPLOAD_SIZE_MB = 100
    CHUNK_SIZE = 4096
    MAX_FILENAME_LENGTH = 255
    MAX_TAGS_PER_IMAGE = 500

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
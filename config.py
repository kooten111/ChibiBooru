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
DATABASE_PATH = "./data/booru.db"

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

# Semantic similarity model path
SEMANTIC_MODEL_PATH = os.environ.get('SEMANTIC_MODEL_PATH', './models/Similarity/model.onnx')

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
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 2))  # Reduced for memory efficiency - each worker adds ~200-400MB due to SQLite memory mapping

# Weight loading mode for multiprocessing
# Options: 'shared' (use shared memory), 'lazy' (query database on-demand), 'full' (load all into each worker)
WEIGHT_LOADING_MODE = os.environ.get('WEIGHT_LOADING_MODE', 'shared').lower()

# Batch size for multiprocessing operations
MULTIPROCESSING_BATCH_SIZE = int(os.environ.get('MULTIPROCESSING_BATCH_SIZE', 200))

# Enable SQLite WAL mode for better concurrent access
ENABLE_WAL_MODE = os.environ.get('ENABLE_WAL_MODE', 'true').lower() in ('true', '1', 'yes')

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

# Tag Implications behavior
# If True, automatically applies tag implications when images are ingested
# (e.g., if 'hatsune_miku' implies 'vocaloid', adds 'vocaloid' automatically)
APPLY_IMPLICATIONS_ON_INGEST = os.environ.get('APPLY_IMPLICATIONS_ON_INGEST', 'true').lower() in ('true', '1', 'yes')

# Extended categories allowed for implication detection
# Only tags in these categories will be considered as implied tags
# This prevents contextual tags (pose, action, expression) from being suggested as implications
# Categories are from the Platinum Schema - Group 1 (Identity) contains permanent traits
IMPLICATION_ALLOWED_EXTENDED_CATEGORIES = [
    #'00_Subject_Count',    # 1girl, solo, 1boy
    '01_Body_Physique',    # breasts, tail, animal_ears
    '02_Body_Hair',        # long_hair, twintails, blonde_hair
    '03_Body_Face',        # blue_eyes, sharp_teeth
    #'04_Body_Genitalia',   # nipples, penis, pussy
    #'21_Status',           # nude, wet (often consistent for characters)
]

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

# ==================== SIMILARITY CACHE SETTINGS ====================

# Use pre-computed cache for sidebar similarity lookups
# When enabled, similarities are pre-computed and stored in SQLite
# This saves ~300-400 MB RAM by not keeping FAISS index loaded
SIMILARITY_CACHE_ENABLED = os.environ.get('SIMILARITY_CACHE_ENABLED', 'true').lower() in ('true', '1', 'yes')

# Number of similar images to pre-compute and cache per image
SIMILARITY_CACHE_SIZE = int(os.environ.get('SIMILARITY_CACHE_SIZE', 50))

# Seconds before unloading idle FAISS index (5 minutes default)
# Only used when cache is enabled - FAISS loaded on-demand for computation
FAISS_IDLE_TIMEOUT = int(os.environ.get('FAISS_IDLE_TIMEOUT', 300))

# ==================== FILE TYPES ====================

SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif')
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.webm')
SUPPORTED_ZIP_EXTENSIONS = ('.zip',)
SUPPORTED_ANIMATION_EXTENSIONS = ('.gif', '.webp', '.apng')
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_VIDEO_EXTENSIONS + SUPPORTED_ZIP_EXTENSIONS

# ==================== UPSCALER (AI IMAGE UPSCALING) ====================

# Enable upscaling feature (disabled by default - set UPSCALER_ENABLED=true in .env)
UPSCALER_ENABLED = os.environ.get('UPSCALER_ENABLED', 'false').lower() in ('true', '1', 'yes')

# Model to use for upscaling
UPSCALER_MODEL = os.environ.get('UPSCALER_MODEL', 'RealESRGAN_x4plus')

# Upscale factor (the x4plus model is designed for 4x)
UPSCALER_SCALE = int(os.environ.get('UPSCALER_SCALE', 4))

# Tile size for processing large images without running out of VRAM
UPSCALER_TILE_SIZE = int(os.environ.get('UPSCALER_TILE_SIZE', 512))

# Directory to store upscaled images (separate from originals)
UPSCALED_IMAGES_DIR = os.environ.get('UPSCALED_IMAGES_DIR', './static/upscaled')


# ==================== ML WORKER (MEMORY OPTIMIZATION) ====================

# ML Worker is REQUIRED for all ML operations (tagging, similarity, upscaling)
# ML frameworks (PyTorch, ONNXRuntime) run in a separate process that auto-terminates
# when idle, saving ~2-3 GB of RAM in the main process.
# The main process NEVER loads ML frameworks directly - all inference via ML Worker.

# Idle timeout for ML worker (auto-terminate after N seconds of inactivity)
# Default: 300 seconds (5 minutes)
ML_WORKER_IDLE_TIMEOUT = int(os.environ.get('ML_WORKER_IDLE_TIMEOUT', 300))

# ML worker backend (cuda/xpu/mps/cpu/auto)
# 'auto' will prompt for selection on first run
# Set by migration script or manually in .env file
ML_WORKER_BACKEND = os.environ.get('ML_WORKER_BACKEND', 'auto')

# ML worker socket path (Unix domain socket for IPC)
ML_WORKER_SOCKET = os.environ.get('ML_WORKER_SOCKET', '/tmp/chibibooru_ml_worker.sock')

# Note: Tag ID optimization is now always enabled
# All tag storage uses int32 IDs for memory efficiency (~200-500 MB savings)


# ==================== ML MODEL TRAINING CONFIGURATION ====================

# Character prediction model configuration
CHARACTER_MODEL_CONFIG = {
    'min_confidence': float(os.environ.get('CHAR_MIN_CONFIDENCE', 0.3)),
    'max_predictions': int(os.environ.get('CHAR_MAX_PREDICTIONS', 3)),
    'pair_weight_multiplier': float(os.environ.get('CHAR_PAIR_WEIGHT_MULTIPLIER', 1.5)),
    'min_pair_cooccurrence': int(os.environ.get('CHAR_MIN_PAIR_COOCCURRENCE', 10)),
    'min_tag_frequency': int(os.environ.get('CHAR_MIN_TAG_FREQUENCY', 10)),
    'max_pair_count': int(os.environ.get('CHAR_MAX_PAIR_COUNT', 10000)),
    'pruning_threshold': float(os.environ.get('CHAR_PRUNING_THRESHOLD', 0.0)),
}

# Rating prediction model configuration
RATING_MODEL_CONFIG = {
    'min_confidence': float(os.environ.get('RATING_MIN_CONFIDENCE', 0.4)),
    'pair_weight_multiplier': float(os.environ.get('RATING_PAIR_WEIGHT_MULTIPLIER', 1.5)),
    'min_tag_frequency': int(os.environ.get('RATING_MIN_TAG_FREQUENCY', 10)),
    'min_pair_cooccurrence': int(os.environ.get('RATING_MIN_PAIR_COOCCURRENCE', 10)),
    'max_pair_count': int(os.environ.get('RATING_MAX_PAIR_COUNT', 5000)),
}


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
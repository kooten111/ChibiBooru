"""
Centralized configuration for all modules
Loads from .env (secrets) and config.yml (settings)
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file (secrets and server settings)
load_dotenv()

# Load settings from config.yml
_config_yml = None
def _load_config_yml():
    """Lazy load config.yml to avoid circular imports"""
    global _config_yml
    if _config_yml is not None:
        return _config_yml
    
    try:
        import yaml
        from pathlib import Path
        config_path = Path('./config.yml')
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                _config_yml = yaml.safe_load(f) or {}
        else:
            _config_yml = {}
    except Exception as e:
        print(f"Warning: Could not load config.yml: {e}")
        _config_yml = {}
    
    return _config_yml

def _get_setting(key: str, default=None, env_key=None, env_default=None):
    """Get setting from config.yml, then .env, then default
    env_key: if different from key for .env lookup
    env_default: default for .env lookup (falls back to default)
    """
    config_yml = _load_config_yml()
    
    # Check config.yml first
    if key in config_yml:
        return config_yml[key]
    
    # Then check .env
    env_key = env_key or key
    env_value = os.environ.get(env_key, env_default if env_default is not None else default)
    
    return env_value

def reload_config():
    """Reload config from files (useful after updates)"""
    global _config_yml
    _config_yml = None
    _load_config_yml()

# Application name (shown in header and page titles)
APP_NAME = _get_setting('APP_NAME', 'ChibiBooru')

# ==================== PATHS ====================

# Image storage
IMAGE_DIRECTORY = _get_setting('IMAGE_DIRECTORY', "./static/images")
THUMB_DIR = _get_setting('THUMB_DIR', "./static/thumbnails")
THUMB_SIZE = _get_setting('THUMB_SIZE', 1000)  # Max dimension for thumbnails

# Ingest folder - drop images here and they'll be processed automatically
INGEST_DIRECTORY = _get_setting('INGEST_DIRECTORY', "./ingest")

# Data storage
TAGS_FILE = _get_setting('TAGS_FILE', "./tags.json")
METADATA_DIR = _get_setting('METADATA_DIR', "./metadata")
DATABASE_PATH = _get_setting('DATABASE_PATH', "./data/booru.db")

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
SEMANTIC_MODEL_PATH = _get_setting('SEMANTIC_MODEL_PATH', './models/Similarity/model.onnx')

# Model behavior
LOCAL_TAGGER_THRESHOLD = float(_get_setting('LOCAL_TAGGER_THRESHOLD', 0.6))  # Confidence threshold for tag predictions
LOCAL_TAGGER_TARGET_SIZE = int(_get_setting('LOCAL_TAGGER_TARGET_SIZE', 512))  # Input image size for model

# Display name - this is what shows in metadata and UI
# Change this when you swap models (e.g., "CamieTagger", "WD14", "Z3D-E621")
LOCAL_TAGGER_NAME = _get_setting('LOCAL_TAGGER_NAME', 'CamieTagger')

# Confidence thresholds for immutable data architecture
# STORAGE_THRESHOLD: Store all predictions >= this value (for cross-referencing later)
# DISPLAY_THRESHOLD: When merging into other sources, only show predictions >= this value
LOCAL_TAGGER_STORAGE_THRESHOLD = float(_get_setting('LOCAL_TAGGER_STORAGE_THRESHOLD', 0.50))
LOCAL_TAGGER_DISPLAY_THRESHOLD = float(_get_setting('LOCAL_TAGGER_DISPLAY_THRESHOLD', 0.70))

# Categories to merge into other sources (character/copyright/artist usually correct from boorus)
LOCAL_TAGGER_MERGE_CATEGORIES = _get_setting('LOCAL_TAGGER_MERGE_CATEGORIES', ['general'])

# ==================== MONITORING ====================

# Automatic background scanning for new images
MONITOR_ENABLED = _get_setting('MONITOR_ENABLED', True)
MONITOR_INTERVAL = int(_get_setting('MONITOR_INTERVAL', 300))  # seconds between checks (5 minutes)

# ==================== DATABASE PERFORMANCE ====================

# SQLite cache size in MB (default 64MB, increase for better performance with large databases)
# Higher values use more RAM but improve query performance
DB_CACHE_SIZE_MB = int(_get_setting('DB_CACHE_SIZE_MB', 64))

# Memory-mapped I/O size in MB (default 256MB)
# Allows SQLite to map database file to memory for faster reads
DB_MMAP_SIZE_MB = int(_get_setting('DB_MMAP_SIZE_MB', 256))

# Batch size for database operations (default 100)
# Higher values = fewer commits = faster but longer locks
DB_BATCH_SIZE = int(_get_setting('DB_BATCH_SIZE', 100))

# WAL checkpoint interval (number of frames, default 1000)
# Controls when WAL file is checkpointed back to main database
DB_WAL_AUTOCHECKPOINT = int(_get_setting('DB_WAL_AUTOCHECKPOINT', 1000))

# ==================== PROCESSING ====================

# Parallel processing
MAX_WORKERS = int(_get_setting('MAX_WORKERS', 2))  # Reduced for memory efficiency - each worker adds ~200-400MB due to SQLite memory mapping

# Weight loading mode for multiprocessing
# Options: 'shared' (use shared memory), 'lazy' (query database on-demand), 'full' (load all into each worker)
WEIGHT_LOADING_MODE = str(_get_setting('WEIGHT_LOADING_MODE', 'shared')).lower()

# Batch size for multiprocessing operations
MULTIPROCESSING_BATCH_SIZE = int(_get_setting('MULTIPROCESSING_BATCH_SIZE', 200))

# Enable SQLite WAL mode for better concurrent access
wal_mode = _get_setting('ENABLE_WAL_MODE', 'true')
if isinstance(wal_mode, bool):
    ENABLE_WAL_MODE = wal_mode
else:
    ENABLE_WAL_MODE = str(wal_mode).lower() in ('true', '1', 'yes')

# Request timeouts
REQUEST_TIMEOUT = int(_get_setting('REQUEST_TIMEOUT', 10))  # seconds

# Rate limiting
RATE_LIMIT_DELAY = float(_get_setting('RATE_LIMIT_DELAY', 0.5))  # seconds between requests

# ==================== SOURCE PRIORITY ====================

# Order matters - first match wins for primary source
# Used for determining which source provides categorized tags
#
# IMPORTANT: When you change BOORU_PRIORITY, increment BOORU_PRIORITY_VERSION
# This ensures remote systems detect the change and re-tag automatically
BOORU_PRIORITY_VERSION = int(_get_setting('BOORU_PRIORITY_VERSION', 4))  # Increment this when changing priority order

BOORU_PRIORITY = _get_setting('BOORU_PRIORITY', [
    "danbooru",     # Best general categorization
    "e621",         # Good specific categorization
    "gelbooru",     # Tags only
    "yandere",      # Tags only
    "pixiv",        # Pixiv tags and artist info
    "local_tagger"  # AI fallback
])

# Use merged sources as default for new images
# When True: Images with multiple sources will default to merged view
# When False: Images will use first available source from BOORU_PRIORITY
USE_MERGED_SOURCES_BY_DEFAULT = _get_setting('USE_MERGED_SOURCES_BY_DEFAULT', True)

# ==================== LOGGING ====================

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = str(_get_setting('LOG_LEVEL', 'INFO')).upper()

# ==================== FLASK APP ====================

# Web server
FLASK_HOST = os.environ.get('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.environ.get('FLASK_PORT', 5000))
FLASK_DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

# Pagination
IMAGES_PER_PAGE = int(_get_setting('IMAGES_PER_PAGE', 100))

# ==================== FEATURE FLAGS ====================

# Enable/disable features
ENABLE_SAUCENAO = bool(SAUCENAO_API_KEY)  # Auto-enable if key present
enable_local = _get_setting('ENABLE_LOCAL_TAGGER', True)
ENABLE_LOCAL_TAGGER = enable_local if isinstance(enable_local, bool) else str(enable_local).lower() in ('true', '1', 'yes')
enable_dedup = _get_setting('ENABLE_DEDUPLICATION', True)
ENABLE_DEDUPLICATION = enable_dedup if isinstance(enable_dedup, bool) else str(enable_dedup).lower() in ('true', '1', 'yes')

# Local tagger behavior
# If True, runs local tagger on ALL images (even when online sources are found)
# If False, only runs local tagger as fallback when no online sources are found
always_run = _get_setting('LOCAL_TAGGER_ALWAYS_RUN', False)
LOCAL_TAGGER_ALWAYS_RUN = always_run if isinstance(always_run, bool) else str(always_run).lower() in ('true', '1', 'yes')

# Pixiv complement behavior
# If True, always runs local tagger to complement Pixiv tags (even when LOCAL_TAGGER_ALWAYS_RUN is False)
# Pixiv tags are often incomplete, so this helps add missing tags
complement_pixiv = _get_setting('LOCAL_TAGGER_COMPLEMENT_PIXIV', True)
LOCAL_TAGGER_COMPLEMENT_PIXIV = complement_pixiv if isinstance(complement_pixiv, bool) else str(complement_pixiv).lower() in ('true', '1', 'yes')

# Tag Implications behavior
# If True, automatically applies tag implications when images are ingested
# (e.g., if 'hatsune_miku' implies 'vocaloid', adds 'vocaloid' automatically)
apply_impl = _get_setting('APPLY_IMPLICATIONS_ON_INGEST', True)
APPLY_IMPLICATIONS_ON_INGEST = apply_impl if isinstance(apply_impl, bool) else str(apply_impl).lower() in ('true', '1', 'yes')

# Extended categories allowed for implication detection
# Only tags in these categories will be considered as implied tags
# This prevents contextual tags (pose, action, expression) from being suggested as implications
# Categories are from the Platinum Schema - Group 1 (Identity) contains permanent traits
IMPLICATION_ALLOWED_EXTENDED_CATEGORIES = _get_setting('IMPLICATION_ALLOWED_EXTENDED_CATEGORIES', [
    #'00_Subject_Count',    # 1girl, solo, 1boy
    '01_Body_Physique',    # breasts, tail, animal_ears
    '02_Body_Hair',        # long_hair, twintails, blonde_hair
    '03_Body_Face',        # blue_eyes, sharp_teeth
    #'04_Body_Genitalia',   # nipples, penis, pussy
    #'21_Status',           # nude, wet (often consistent for characters)
])

# ==================== SIMILARITY CALCULATION ====================

# Similarity calculation method
# Options: 'jaccard' (basic set intersection/union), 'weighted' (IDF + category weights)
SIMILARITY_METHOD = str(_get_setting('SIMILARITY_METHOD', 'weighted'))

# Category weights for weighted similarity
# Higher values mean matching tags in that category contributes more to similarity
SIMILARITY_CATEGORY_WEIGHTS = _get_setting('SIMILARITY_CATEGORY_WEIGHTS', {
    'character': 6.0,   # Character matches are very significant
    'copyright': 3.0,   # Same series/franchise is important
    'artist': 2.0,      # Same artist style matters
    'species': 2.5,     # Species tags
    'general': 3.0,     # Standard descriptive tags
    'meta': 0.5         # Resolution, format, year - less relevant for similarity
})

# ==================== VISUAL SIMILARITY (PERCEPTUAL HASH) ====================

# Enable visual similarity in the related images sidebar
# When enabled, uses a blend of tag-based and visual perceptual hash similarity
visual_sim = _get_setting('VISUAL_SIMILARITY_ENABLED', True)
VISUAL_SIMILARITY_ENABLED = visual_sim if isinstance(visual_sim, bool) else str(visual_sim).lower() in ('true', '1', 'yes')

# Weight for visual similarity vs tag-based similarity in blended results
# Values from 0.0 to 1.0, visual_weight + tag_weight should equal 1.0
VISUAL_SIMILARITY_WEIGHT = float(_get_setting('VISUAL_SIMILARITY_WEIGHT', 0.3))
TAG_SIMILARITY_WEIGHT = float(_get_setting('TAG_SIMILARITY_WEIGHT', 0.7))

# Hamming distance threshold for considering images similar
# Lower = stricter matching (0-64 scale, 64-bit hash)
# 0-5: Near identical, 6-10: Very similar, 11-15: Somewhat similar
VISUAL_SIMILARITY_THRESHOLD = int(_get_setting('VISUAL_SIMILARITY_THRESHOLD', 15))

# Enable semantic (vector-based) similarity
# This requires significant RAM and CPU. Disable for weaker machines.
# If False, visual similarity will rely only on fast pHash/ColorHash.
semantic_sim = _get_setting('ENABLE_SEMANTIC_SIMILARITY', True)
ENABLE_SEMANTIC_SIMILARITY = semantic_sim if isinstance(semantic_sim, bool) else str(semantic_sim).lower() in ('true', '1', 'yes')

# ==================== SIMILARITY CACHE SETTINGS ====================

# Use pre-computed cache for sidebar similarity lookups
# When enabled, similarities are pre-computed and stored in SQLite
# This saves ~300-400 MB RAM by not keeping FAISS index loaded
sim_cache = _get_setting('SIMILARITY_CACHE_ENABLED', True)
SIMILARITY_CACHE_ENABLED = sim_cache if isinstance(sim_cache, bool) else str(sim_cache).lower() in ('true', '1', 'yes')

# Number of similar images to pre-compute and cache per image
SIMILARITY_CACHE_SIZE = int(_get_setting('SIMILARITY_CACHE_SIZE', 50))

# Seconds before unloading idle FAISS index (5 minutes default)
# Only used when cache is enabled - FAISS loaded on-demand for computation
FAISS_IDLE_TIMEOUT = int(_get_setting('FAISS_IDLE_TIMEOUT', 300))

# ==================== FILE TYPES ====================

SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif')
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.webm')
SUPPORTED_ZIP_EXTENSIONS = ('.zip',)
SUPPORTED_ANIMATION_EXTENSIONS = ('.gif', '.webp', '.apng')
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_VIDEO_EXTENSIONS + SUPPORTED_ZIP_EXTENSIONS

# ==================== UPSCALER (AI IMAGE UPSCALING) ====================

# Enable upscaling feature (disabled by default - set UPSCALER_ENABLED=true in .env)
upscaler_enabled = _get_setting('UPSCALER_ENABLED', False)
UPSCALER_ENABLED = upscaler_enabled if isinstance(upscaler_enabled, bool) else str(upscaler_enabled).lower() in ('true', '1', 'yes')

# Model to use for upscaling
UPSCALER_MODEL = str(_get_setting('UPSCALER_MODEL', 'RealESRGAN_x4plus'))

# Upscale factor (the x4plus model is designed for 4x)
UPSCALER_SCALE = int(_get_setting('UPSCALER_SCALE', 4))

# Tile size for processing large images without running out of VRAM
UPSCALER_TILE_SIZE = int(_get_setting('UPSCALER_TILE_SIZE', 512))

# Directory to store upscaled images (separate from originals)
UPSCALED_IMAGES_DIR = str(_get_setting('UPSCALED_IMAGES_DIR', './static/upscaled'))


# ==================== ML WORKER (MEMORY OPTIMIZATION) ====================

# ML Worker is REQUIRED for all ML operations (tagging, similarity, upscaling)
# ML frameworks (PyTorch, ONNXRuntime) run in a separate process that auto-terminates
# when idle, saving ~2-3 GB of RAM in the main process.
# The main process NEVER loads ML frameworks directly - all inference via ML Worker.

# Idle timeout for ML worker (auto-terminate after N seconds of inactivity)
# Default: 300 seconds (5 minutes)
ML_WORKER_IDLE_TIMEOUT = int(_get_setting('ML_WORKER_IDLE_TIMEOUT', 300))

# ML worker backend (cuda/xpu/mps/cpu/auto)
# 'auto' will prompt for selection on first run
# Set by migration script or manually in .env file
ML_WORKER_BACKEND = str(_get_setting('ML_WORKER_BACKEND', 'auto'))

# ML worker socket path (Unix domain socket for IPC)
ML_WORKER_SOCKET = str(_get_setting('ML_WORKER_SOCKET', '/tmp/chibibooru_ml_worker.sock'))

# Note: Tag ID optimization is now always enabled
# All tag storage uses int32 IDs for memory efficiency (~200-500 MB savings)


# ==================== ML MODEL TRAINING CONFIGURATION ====================

# Character prediction model configuration
CHARACTER_MODEL_CONFIG = {
    'min_confidence': float(_get_setting('CHAR_MIN_CONFIDENCE', 0.3)),
    'max_predictions': int(_get_setting('CHAR_MAX_PREDICTIONS', 3)),
    'pair_weight_multiplier': float(_get_setting('CHAR_PAIR_WEIGHT_MULTIPLIER', 1.5)),
    'min_pair_cooccurrence': int(_get_setting('CHAR_MIN_PAIR_COOCCURRENCE', 10)),
    'min_tag_frequency': int(_get_setting('CHAR_MIN_TAG_FREQUENCY', 10)),
    'max_pair_count': int(_get_setting('CHAR_MAX_PAIR_COUNT', 10000)),
    'pruning_threshold': float(_get_setting('CHAR_PRUNING_THRESHOLD', 0.0)),
}

# Rating prediction model configuration
RATING_MODEL_CONFIG = {
    'min_confidence': float(_get_setting('RATING_MIN_CONFIDENCE', 0.4)),
    'pair_weight_multiplier': float(_get_setting('RATING_PAIR_WEIGHT_MULTIPLIER', 1.5)),
    'min_tag_frequency': int(_get_setting('RATING_MIN_TAG_FREQUENCY', 10)),
    'min_pair_cooccurrence': int(_get_setting('RATING_MIN_PAIR_COOCCURRENCE', 10)),
    'max_pair_count': int(_get_setting('RATING_MAX_PAIR_COUNT', 5000)),
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

# Run validation on import
if __name__ != "__main__":
    validate_config()
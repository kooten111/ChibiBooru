"""
Configuration service for managing settings in config.yml
Separates secrets (in .env) from editable settings (in config.yml)
"""
import os
import yaml
import shutil
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from functools import lru_cache
from utils.logging_config import get_logger

logger = get_logger('ConfigService')

CONFIG_YML_PATH = Path('./config.yml')
CONFIG_YML_BACKUP_PATH = Path('./config.yml.backup')

# Settings that should remain in .env (secrets and server settings)
ENV_ONLY_SETTINGS = {
    'APP_PASSWORD',
    'SECRET_KEY',
    'SYSTEM_API_SECRET',
    'SAUCENAO_API_KEY',
    'GELBOORU_API_KEY',
    'GELBOORU_USER_ID',
    'FLASK_HOST',
    'FLASK_PORT',
    'FLASK_DEBUG',
}

# Setting metadata: category, type, description, editable
SETTING_METADATA: Dict[str, Dict[str, Any]] = {
    # Application
    'APP_NAME': {
        'category': 'Application',
        'type': 'string',
        'description': 'Application name shown in header and page titles',
        'editable': True,
    },
    'IMAGE_DIRECTORY': {
        'category': 'Application',
        'type': 'string',
        'description': 'Directory for storing images',
        'editable': True,
    },
    'THUMB_DIR': {
        'category': 'Application',
        'type': 'string',
        'description': 'Directory for storing thumbnails',
        'editable': True,
    },
    'THUMB_SIZE': {
        'category': 'Application',
        'type': 'int',
        'description': 'Max dimension for thumbnails in pixels',
        'editable': True,
    },
    'THUMB_QUALITY': {
        'category': 'Application',
        'type': 'int',
        'description': 'WebP quality for thumbnails (1-100)',
        'editable': True,
        'min': 1,
        'max': 100,
    },
    'INGEST_DIRECTORY': {
        'category': 'Application',
        'type': 'string',
        'description': 'Drop images here for automatic processing',
        'editable': True,
    },
    'TAGS_FILE': {
        'category': 'Application',
        'type': 'string',
        'description': 'Path to tags JSON file',
        'editable': True,
    },
    'METADATA_DIR': {
        'category': 'Application',
        'type': 'string',
        'description': 'Directory for metadata files',
        'editable': True,
    },
    'DATABASE_PATH': {
        'category': 'Application',
        'type': 'string',
        'description': 'Path to SQLite database',
        'editable': True,
    },
    'IMAGES_PER_PAGE': {
        'category': 'Application',
        'type': 'int',
        'description': 'Number of images per page',
        'editable': True,
    },
    
    # AI Tagging
    'LOCAL_TAGGER_MODEL_PATH': {
        'category': 'AI Tagging',
        'type': 'string',
        'description': 'Path to ONNX tagger model',
        'editable': True,
    },
    'LOCAL_TAGGER_METADATA_PATH': {
        'category': 'AI Tagging',
        'type': 'string',
        'description': 'Path to tagger metadata JSON',
        'editable': True,
    },
    'SEMANTIC_MODEL_PATH': {
        'category': 'AI Tagging',
        'type': 'string',
        'description': 'Path to semantic similarity model',
        'editable': True,
    },
    'LOCAL_TAGGER_THRESHOLD': {
        'category': 'AI Tagging',
        'type': 'float',
        'description': 'Confidence threshold for tag predictions (0.0-1.0)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'LOCAL_TAGGER_TARGET_SIZE': {
        'category': 'AI Tagging',
        'type': 'int',
        'description': 'Input image size for model',
        'editable': True,
    },
    'LOCAL_TAGGER_NAME': {
        'category': 'AI Tagging',
        'type': 'string',
        'description': 'Display name for AI tagger',
        'editable': True,
    },
    'LOCAL_TAGGER_STORAGE_THRESHOLD': {
        'category': 'AI Tagging',
        'type': 'float',
        'description': 'Store predictions >= this value (0.0-1.0)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'LOCAL_TAGGER_DISPLAY_THRESHOLD': {
        'category': 'AI Tagging',
        'type': 'float',
        'description': 'Show predictions >= this value when merging (0.0-1.0)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'LOCAL_TAGGER_MERGE_CATEGORIES': {
        'category': 'AI Tagging',
        'type': 'list',
        'description': 'Categories to merge into other sources',
        'editable': True,
    },
    'ENABLE_LOCAL_TAGGER': {
        'category': 'AI Tagging',
        'type': 'bool',
        'description': 'Enable AI tagging feature',
        'editable': True,
    },
    'LOCAL_TAGGER_ALWAYS_RUN': {
        'category': 'AI Tagging',
        'type': 'bool',
        'description': 'Run tagger on all images, not just fallback',
        'editable': True,
    },
    
    # Database
    'DB_CACHE_SIZE_MB': {
        'category': 'Database',
        'type': 'int',
        'description': 'SQLite cache size in MB',
        'editable': True,
    },
    'DB_MMAP_SIZE_MB': {
        'category': 'Database',
        'type': 'int',
        'description': 'Memory-mapped I/O size in MB',
        'editable': True,
    },
    'DB_BATCH_SIZE': {
        'category': 'Database',
        'type': 'int',
        'description': 'Batch size for database operations',
        'editable': True,
    },
    'DB_WAL_AUTOCHECKPOINT': {
        'category': 'Database',
        'type': 'int',
        'description': 'WAL checkpoint interval (frames)',
        'editable': True,
    },
    'ENABLE_WAL_MODE': {
        'category': 'Database',
        'type': 'bool',
        'description': 'Enable SQLite WAL mode for concurrent access',
        'editable': True,
    },
    
    # Processing
    'MAX_WORKERS': {
        'category': 'Processing',
        'type': 'int',
        'description': 'Number of parallel workers',
        'editable': True,
    },
    'WEIGHT_LOADING_MODE': {
        'category': 'Processing',
        'type': 'string',
        'description': 'Weight loading mode: shared, lazy, or full',
        'editable': True,
    },
    'MULTIPROCESSING_BATCH_SIZE': {
        'category': 'Processing',
        'type': 'int',
        'description': 'Batch size for multiprocessing operations',
        'editable': True,
    },
    'REQUEST_TIMEOUT': {
        'category': 'Processing',
        'type': 'int',
        'description': 'Request timeout in seconds',
        'editable': True,
    },
    'RATE_LIMIT_DELAY': {
        'category': 'Processing',
        'type': 'float',
        'description': 'Delay between requests in seconds',
        'editable': True,
    },
    
    # Monitor
    'MONITOR_ENABLED': {
        'category': 'Monitor',
        'type': 'bool',
        'description': 'Enable automatic background scanning',
        'editable': True,
    },
    'MONITOR_INTERVAL': {
        'category': 'Monitor',
        'type': 'int',
        'description': 'Seconds between monitor checks',
        'editable': True,
    },
    
    # Similarity
    'SIMILARITY_METHOD': {
        'category': 'Similarity',
        'type': 'string',
        'description': 'Similarity method: jaccard, weighted, weighted_tfidf, asymmetric, asymmetric_tfidf',
        'editable': True,
    },
    'ASYMMETRIC_ALPHA': {
        'category': 'Similarity',
        'type': 'float',
        'description': 'Higher = more tolerant of extra tags in detailed images (0.6 default)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'SIMILARITY_CATEGORY_WEIGHTS': {
        'category': 'Similarity',
        'type': 'dict',
        'description': 'Category weights for weighted similarity',
        'editable': True,
    },
    'SIMILARITY_EXTENDED_CATEGORY_WEIGHTS': {
        'category': 'Similarity',
        'type': 'dict',
        'description': 'Extended category weights (22 categories) for fine-grained similarity',
        'editable': True,
    },
    'USE_EXTENDED_SIMILARITY': {
        'category': 'Similarity',
        'type': 'bool',
        'description': 'Use extended categories for tag similarity (requires categorized tags)',
        'editable': True,
    },
    'VISUAL_SIMILARITY_ENABLED': {
        'category': 'Similarity',
        'type': 'bool',
        'description': 'Enable visual similarity in sidebar',
        'editable': True,
    },
    'VISUAL_SIMILARITY_WEIGHT': {
        'category': 'Similarity',
        'type': 'float',
        'description': 'Weight for visual similarity (0.0-1.0)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'TAG_SIMILARITY_WEIGHT': {
        'category': 'Similarity',
        'type': 'float',
        'description': 'Weight for tag-based similarity (0.0-1.0)',
        'editable': True,
        'min': 0.0,
        'max': 1.0,
    },
    'VISUAL_SIMILARITY_THRESHOLD': {
        'category': 'Similarity',
        'type': 'int',
        'description': 'Hamming distance threshold (0-64)',
        'editable': True,
        'min': 0,
        'max': 64,
    },
    'ENABLE_SEMANTIC_SIMILARITY': {
        'category': 'Similarity',
        'type': 'bool',
        'description': 'Enable semantic (vector-based) similarity',
        'editable': True,
    },
    'SIMILARITY_CACHE_ENABLED': {
        'category': 'Similarity',
        'type': 'bool',
        'description': 'Use pre-computed similarity cache',
        'editable': True,
    },
    'SIMILARITY_CACHE_SIZE': {
        'category': 'Similarity',
        'type': 'int',
        'description': 'Number of similar images to cache per image',
        'editable': True,
    },
    'FAISS_IDLE_TIMEOUT': {
        'category': 'Similarity',
        'type': 'int',
        'description': 'Seconds before unloading idle FAISS index',
        'editable': True,
    },
    'SIMILAR_SIDEBAR_SOURCES': {
        'category': 'Similarity',
        'type': 'string',
        'description': 'Which similar sources to show: both, tag, or faiss',
        'editable': True,
    },
    'SIMILAR_SIDEBAR_SHOW_CHIPS': {
        'category': 'Similarity',
        'type': 'bool',
        'description': 'Show Tag/FAISS source chips on similar images',
        'editable': True,
    },

    # UI
    'INFORMATION_PANEL_DEFAULT_VISIBLE': {
        'category': 'UI',
        'type': 'bool',
        'description': 'On image page: Information panel expanded by default (uncheck = collapsed by default)',
        'editable': True,
    },

    # Feature Flags
    'ENABLE_SAUCENAO': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Enable SauceNao reverse image search',
        'editable': True,
    },
    'ENABLE_DEDUPLICATION': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Enable MD5-based duplicate detection',
        'editable': True,
    },
    'APPLY_IMPLICATIONS_ON_INGEST': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Automatically apply tag implications on ingest',
        'editable': True,
    },
    'IMPLICATION_ALLOWED_EXTENDED_CATEGORIES': {
        'category': 'Feature Flags',
        'type': 'list',
        'description': 'Extended categories allowed for implication detection',
        'editable': True,
    },
    'USE_MERGED_SOURCES_BY_DEFAULT': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Use merged sources as default for new images',
        'editable': True,
    },
    'UPSCALER_ENABLED': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Enable AI image upscaling feature',
        'editable': True,
    },
    'UPSCALER_MODEL': {
        'category': 'Feature Flags',
        'type': 'string',
        'description': 'Model to use for upscaling',
        'editable': True,
    },
    'UPSCALER_SCALE': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'Upscale factor',
        'editable': True,
    },
    'UPSCALER_TILE_SIZE': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'Tile size for processing large images',
        'editable': True,
    },
    'UPSCALER_OUTPUT_FORMAT': {
        'category': 'Feature Flags',
        'type': 'string',
        'description': 'Output format for upscaled images (png or webp)',
        'editable': True,
    },
    'UPSCALER_OUTPUT_QUALITY': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'WebP quality level (1-100, only used when format is webp)',
        'editable': True,
        'min': 1,
        'max': 100,
    },
    'UPSCALED_IMAGES_DIR': {
        'category': 'Feature Flags',
        'type': 'string',
        'description': 'Directory to store upscaled images',
        'editable': True,
    },
    'UPSCALE_MAINTENANCE_USE_FILESIZE_KB': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Bulk upscale maintenance: include file size threshold',
        'editable': True,
    },
    'UPSCALE_MAINTENANCE_MAX_FILESIZE_KB': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'Bulk upscale maintenance: max file size in KB',
        'editable': True,
        'min': 1,
    },
    'UPSCALE_MAINTENANCE_USE_MEGAPIXELS': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Bulk upscale maintenance: include megapixel threshold',
        'editable': True,
    },
    'UPSCALE_MAINTENANCE_MAX_MEGAPIXELS': {
        'category': 'Feature Flags',
        'type': 'float',
        'description': 'Bulk upscale maintenance: max megapixels',
        'editable': True,
        'min': 0.01,
    },
    'UPSCALE_MAINTENANCE_USE_DIMENSIONS': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Bulk upscale maintenance: include width/height threshold',
        'editable': True,
    },
    'UPSCALE_MAINTENANCE_MAX_WIDTH': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'Bulk upscale maintenance: max width in pixels',
        'editable': True,
        'min': 1,
    },
    'UPSCALE_MAINTENANCE_MAX_HEIGHT': {
        'category': 'Feature Flags',
        'type': 'int',
        'description': 'Bulk upscale maintenance: max height in pixels',
        'editable': True,
        'min': 1,
    },
    'UPSCALE_MAINTENANCE_EXCLUDE_UPSCALED': {
        'category': 'Feature Flags',
        'type': 'bool',
        'description': 'Bulk upscale maintenance: skip images already upscaled',
        'editable': True,
    },
    
    # ML Worker
    'ML_WORKER_IDLE_TIMEOUT': {
        'category': 'ML Worker',
        'type': 'int',
        'description': 'Idle timeout for ML worker in seconds',
        'editable': True,
    },
    'ML_WORKER_BACKEND': {
        'category': 'ML Worker',
        'type': 'string',
        'description': 'ML worker backend: cuda/xpu/mps/cpu/auto',
        'editable': True,
    },
    'ML_WORKER_SOCKET': {
        'category': 'ML Worker',
        'type': 'string',
        'description': 'ML worker socket path',
        'editable': True,
    },
    
    # Logging
    'LOG_LEVEL': {
        'category': 'Logging',
        'type': 'string',
        'description': 'Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL',
        'editable': True,
    },
    
    # Source Priority
    'BOORU_PRIORITY_VERSION': {
        'category': 'Source Priority',
        'type': 'int',
        'description': 'Version number for booru priority (increment when changing)',
        'editable': True,
    },
    'BOORU_PRIORITY': {
        'category': 'Source Priority',
        'type': 'list',
        'description': 'Order of booru sources (first match wins)',
        'editable': True,
    },
    
    # Character/Rating Model Config
    'CHAR_MIN_CONFIDENCE': {
        'category': 'ML Models',
        'type': 'float',
        'description': 'Character model minimum confidence',
        'editable': True,
    },
    'CHAR_MAX_PREDICTIONS': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Character model max predictions',
        'editable': True,
    },
    'CHAR_PAIR_WEIGHT_MULTIPLIER': {
        'category': 'ML Models',
        'type': 'float',
        'description': 'Character model pair weight multiplier',
        'editable': True,
    },
    'CHAR_MIN_PAIR_COOCCURRENCE': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Character model min pair cooccurrence',
        'editable': True,
    },
    'CHAR_MIN_TAG_FREQUENCY': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Character model min tag frequency',
        'editable': True,
    },
    'CHAR_MAX_PAIR_COUNT': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Character model max pair count',
        'editable': True,
    },
    'CHAR_PRUNING_THRESHOLD': {
        'category': 'ML Models',
        'type': 'float',
        'description': 'Character model pruning threshold',
        'editable': True,
    },
    'RATING_MIN_CONFIDENCE': {
        'category': 'ML Models',
        'type': 'float',
        'description': 'Rating model minimum confidence',
        'editable': True,
    },
    'RATING_PAIR_WEIGHT_MULTIPLIER': {
        'category': 'ML Models',
        'type': 'float',
        'description': 'Rating model pair weight multiplier',
        'editable': True,
    },
    'RATING_MIN_TAG_FREQUENCY': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Rating model min tag frequency',
        'editable': True,
    },
    'RATING_MIN_PAIR_COOCCURRENCE': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Rating model min pair cooccurrence',
        'editable': True,
    },
    'RATING_MAX_PAIR_COUNT': {
        'category': 'ML Models',
        'type': 'int',
        'description': 'Rating model max pair count',
        'editable': True,
    },
}


@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """Load settings from config.yml.
    
    Results are cached since config changes infrequently.
    Cache is invalidated when save_config() is called or via invalidate_config_cache().
    """
    if not CONFIG_YML_PATH.exists():
        logger.warning(f"config.yml not found at {CONFIG_YML_PATH}, using defaults")
        return {}
    
    try:
        with open(CONFIG_YML_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        logger.debug(f"Loaded config from {CONFIG_YML_PATH}")
        return config
    except Exception as e:
        logger.error(f"Error loading config.yml: {e}")
        return {}


def invalidate_config_cache():
    """Invalidate config cache after changes."""
    load_config.cache_clear()
    logger.debug("Config cache invalidated")


def save_config(config: Dict[str, Any]) -> bool:
    """Save settings to config.yml with backup"""
    try:
        # Create backup if config exists
        if CONFIG_YML_PATH.exists():
            shutil.copy2(CONFIG_YML_PATH, CONFIG_YML_BACKUP_PATH)
            logger.debug(f"Created backup: {CONFIG_YML_BACKUP_PATH}")
        
        # Write new config
        with open(CONFIG_YML_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        # Invalidate cache so next load reads the new values
        invalidate_config_cache()
        
        logger.info(f"Saved config to {CONFIG_YML_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error saving config.yml: {e}")
        # Restore backup on failure
        if CONFIG_YML_BACKUP_PATH.exists():
            shutil.copy2(CONFIG_YML_BACKUP_PATH, CONFIG_YML_PATH)
            logger.warning("Restored config from backup due to save failure")
        return False


def get_editable_settings() -> Dict[str, Any]:
    """Get all editable settings grouped by category"""
    config_yml = load_config()
    categorized = {}
    
    # Import config to get current values (which include defaults)
    import config as config_module
    
    for key, metadata in SETTING_METADATA.items():
        if not metadata.get('editable', True):
            continue
        
        category = metadata['category']
        if category not in categorized:
            categorized[category] = []
        
        # Get current value: first from config.yml, then from config.py (which has defaults)
        # Use 'in' check to distinguish between missing key (use default) and key with None value (use default)
        if key not in config_yml:
            # Key doesn't exist in config.yml, use default from config.py
            value = getattr(config_module, key, None)
            if value is None:
                # For ML Model settings, extract from CHARACTER_MODEL_CONFIG or RATING_MODEL_CONFIG
                if key.startswith('CHAR_'):
                    config_dict = getattr(config_module, 'CHARACTER_MODEL_CONFIG', {})
                    key_map = {
                        'CHAR_MIN_CONFIDENCE': 'min_confidence',
                        'CHAR_MAX_PREDICTIONS': 'max_predictions',
                        'CHAR_PAIR_WEIGHT_MULTIPLIER': 'pair_weight_multiplier',
                        'CHAR_MIN_PAIR_COOCCURRENCE': 'min_pair_cooccurrence',
                        'CHAR_MIN_TAG_FREQUENCY': 'min_tag_frequency',
                        'CHAR_MAX_PAIR_COUNT': 'max_pair_count',
                        'CHAR_PRUNING_THRESHOLD': 'pruning_threshold',
                    }
                    if key in key_map:
                        value = config_dict.get(key_map[key])
                elif key.startswith('RATING_'):
                    config_dict = getattr(config_module, 'RATING_MODEL_CONFIG', {})
                    key_map = {
                        'RATING_MIN_CONFIDENCE': 'min_confidence',
                        'RATING_PAIR_WEIGHT_MULTIPLIER': 'pair_weight_multiplier',
                        'RATING_MIN_TAG_FREQUENCY': 'min_tag_frequency',
                        'RATING_MIN_PAIR_COOCCURRENCE': 'min_pair_cooccurrence',
                        'RATING_MAX_PAIR_COUNT': 'max_pair_count',
                    }
                    if key in key_map:
                        value = config_dict.get(key_map[key])
        else:
            # Key exists in config.yml
            value = config_yml.get(key)
            # If value is explicitly None, also use default from config.py
            if value is None:
                value = getattr(config_module, key, None)
                if value is None:
                    # For ML Model settings, extract from dictionaries
                    if key.startswith('CHAR_'):
                        config_dict = getattr(config_module, 'CHARACTER_MODEL_CONFIG', {})
                        key_map = {
                            'CHAR_MIN_CONFIDENCE': 'min_confidence',
                            'CHAR_MAX_PREDICTIONS': 'max_predictions',
                            'CHAR_PAIR_WEIGHT_MULTIPLIER': 'pair_weight_multiplier',
                            'CHAR_MIN_PAIR_COOCCURRENCE': 'min_pair_cooccurrence',
                            'CHAR_MIN_TAG_FREQUENCY': 'min_tag_frequency',
                            'CHAR_MAX_PAIR_COUNT': 'max_pair_count',
                            'CHAR_PRUNING_THRESHOLD': 'pruning_threshold',
                        }
                        if key in key_map:
                            value = config_dict.get(key_map[key])
                    elif key.startswith('RATING_'):
                        config_dict = getattr(config_module, 'RATING_MODEL_CONFIG', {})
                        key_map = {
                            'RATING_MIN_CONFIDENCE': 'min_confidence',
                            'RATING_PAIR_WEIGHT_MULTIPLIER': 'pair_weight_multiplier',
                            'RATING_MIN_TAG_FREQUENCY': 'min_tag_frequency',
                            'RATING_MIN_PAIR_COOCCURRENCE': 'min_pair_cooccurrence',
                            'RATING_MAX_PAIR_COUNT': 'max_pair_count',
                        }
                        if key in key_map:
                            value = config_dict.get(key_map[key])
        
        categorized[category].append({
            'key': key,
            'value': value,
            'type': metadata['type'],
            'description': metadata.get('description', ''),
            'min': metadata.get('min'),
            'max': metadata.get('max'),
        })
    
    return categorized


def validate_setting(key: str, value: Any) -> Tuple[bool, Optional[str]]:
    """Validate a setting value"""
    if key not in SETTING_METADATA:
        return False, f"Unknown setting: {key}"
    
    metadata = SETTING_METADATA[key]
    setting_type = metadata['type']
    
    # Type validation
    if setting_type == 'int':
        try:
            value = int(value)
            if 'min' in metadata and value < metadata['min']:
                return False, f"Value must be >= {metadata['min']}"
            if 'max' in metadata and value > metadata['max']:
                return False, f"Value must be <= {metadata['max']}"
        except (ValueError, TypeError):
            return False, f"Value must be an integer"
    
    elif setting_type == 'float':
        try:
            value = float(value)
            if 'min' in metadata and value < metadata['min']:
                return False, f"Value must be >= {metadata['min']}"
            if 'max' in metadata and value > metadata['max']:
                return False, f"Value must be <= {metadata['max']}"
        except (ValueError, TypeError):
            return False, f"Value must be a number"
    
    elif setting_type == 'bool':
        if isinstance(value, str):
            value = value.lower() in ('true', '1', 'yes', 'on')
        if not isinstance(value, bool):
            return False, f"Value must be a boolean"
    
    elif setting_type == 'string':
        if not isinstance(value, str):
            return False, f"Value must be a string"
        # Basic path validation for file paths
        if 'path' in key.lower() or 'dir' in key.lower():
            # Prevent directory traversal
            if '..' in value or value.startswith('/'):
                return False, f"Invalid path: must be relative and not contain '..'"
    
    elif setting_type == 'list':
        if not isinstance(value, list):
            return False, f"Value must be a list"
    
    elif setting_type == 'dict':
        if not isinstance(value, dict):
            return False, f"Value must be a dictionary"
    
    return True, None


def update_setting(key: str, value: Any) -> Tuple[bool, Optional[str]]:
    """Update a single setting"""
    # Validate
    valid, error = validate_setting(key, value)
    if not valid:
        return False, error
    
    # Load current config
    config = load_config()
    
    # Update value
    config[key] = value
    
    # Save
    if save_config(config):
        return True, None
    else:
        return False, "Failed to save config"


def update_settings_batch(settings: Dict[str, Any]) -> Tuple[bool, Dict[str, str]]:
    """Update multiple settings at once"""
    config = load_config()
    errors = {}
    
    # Validate all first
    for key, value in settings.items():
        valid, error = validate_setting(key, value)
        if not valid:
            errors[key] = error
    
    if errors:
        return False, errors
    
    # Update all
    for key, value in settings.items():
        config[key] = value
    
    # Save
    if save_config(config):
        return True, {}
    else:
        return False, {'_general': 'Failed to save config'}


def get_setting_schema() -> Dict[str, Any]:
    """Get setting metadata/schema for API"""
    return SETTING_METADATA

# Configuration Documentation

## Table of Contents
- [Overview](#overview)
- [Environment Variables](#environment-variables)
- [Configuration File](#configuration-file)
- [Configuration Validation](#configuration-validation)
- [Helper Functions](#helper-functions)

---

## Overview

ChibiBooru uses a centralized configuration system that separates secrets from editable settings.

**Configuration Sources**:
1. `.env` file (secrets and server settings only)
2. `config.yml` file (all editable settings)
3. `config.py` (Python constants with defaults)

**Key Changes**:
- Secrets (passwords, API keys) remain in `.env`
- All other settings are in `config.yml` and can be edited via the web UI at `/system`
- Settings can be changed without editing files directly

---

## Configuration Files

### .env File (Secrets Only)

**File**: `.env` (create manually in project root)

**Note**: The `.env` file now contains **only secrets and server settings**. All other settings have been moved to `config.yml` and can be edited via the web UI.

---

### Security Settings

#### `APP_PASSWORD` ⚠️ REQUIRED
**Type**: String  
**Default**: `"default-password"`  
**Description**: Password for web UI login  
**Security**: Change this before deployment!

---

#### `SECRET_KEY` ⚠️ REQUIRED
**Type**: String  
**Default**: `"dev-secret-key-change-for-production"`  
**Description**: Flask session encryption key  
**Security**: Use long random string in production  
**Generate**: `python -c "import secrets; print(secrets.token_hex(32))"`

---

#### `SYSTEM_API_SECRET` ⚠️ REQUIRED
**Type**: String  
**Default**: `"change-this-secret"`  
**Description**: Secret for system control API operations (administrative endpoints)  
**Security**: Change this before deployment!

---

### API Keys (Optional)

#### `SAUCENAO_API_KEY`
**Type**: String  
**Default**: `""`  
**Description**: SauceNao API key for reverse image search  
**Get Key**: https://saucenao.com/user.php  
**Feature**: Enables SauceNao integration when set

---

#### `GELBOORU_API_KEY`
**Type**: String  
**Default**: `""`  
**Description**: Gelbooru API key (optional)  
**Get Key**: https://gelbooru.com/index.php?page=account&s=options

---

#### `GELBOORU_USER_ID`
**Type**: String  
**Default**: `""`  
**Description**: Gelbooru user ID (optional)

---

### AI Tagging

#### `LOCAL_TAGGER_NAME`
**Type**: String  
**Default**: `"CamieTagger"`  
**Description**: Display name for local AI tagger  
**Examples**: `"CamieTagger"`, `"WD14"`, `"Z3D-E621"`

---

### Web Server

---

## config.yml File (Editable Settings)

**File**: `config.yml` (created automatically or via migration script)

**Note**: All non-secret settings are stored in `config.yml` and can be edited via the web UI at `/system`. The file uses YAML format for readability.

### Editing Settings

**Via Web UI** (Recommended):
1. Navigate to `/system` in your browser
2. Click the "Settings" tab
3. Edit settings by category
4. Click "Save All Changes"

**Via File**:
- Edit `config.yml` directly (YAML format)
- Restart the application or click "Reload Config" in the web UI

### Setting Categories

Settings in `config.yml` are organized into categories:

- **Application**: APP_NAME, paths, pagination
- **AI Tagging**: Model paths, thresholds, behavior flags
- **Database**: Cache size, batch size, WAL settings
- **Processing**: Workers, batch sizes, timeouts
- **Similarity**: Methods, weights, thresholds
- **Monitor**: Enabled, interval
- **Feature Flags**: ENABLE_* settings
- **ML Worker**: Backend, timeout, socket path
- **ML Models**: Character and rating model configuration
- **Source Priority**: Booru priority order

---

## Legacy: Environment Variables (Deprecated)

The following settings can still be set in `.env` for backward compatibility, but are recommended to be in `config.yml`:

### AI Tagging

#### `LOCAL_TAGGER_NAME`
**Type**: String  
**Default**: `"CamieTagger"`  
**Description**: Display name for local AI tagger  
**Examples**: `"CamieTagger"`, `"WD14"`, `"Z3D-E621"`  
**Note**: Now in `config.yml` - edit via web UI

---

### Web Server

**Note**: These settings must remain in `.env` and cannot be changed via the web UI.

#### `FLASK_HOST`
**Type**: String  
**Default**: `"0.0.0.0"`  
**Description**: Web server host  
**Options**:
- `"0.0.0.0"`: Allow external connections
- `"127.0.0.1"`: Localhost only

---

#### `FLASK_PORT`
**Type**: Integer  
**Default**: `5000`  
**Description**: Web server port number

---

#### `FLASK_DEBUG`
**Type**: Boolean  
**Default**: `false`  
**Description**: Enable Flask debug mode  
**Values**: `"true"` or `"false"`  
**Warning**: Never enable in production!

---

### Similarity Calculation

#### `SIMILARITY_METHOD`
**Type**: String  
**Default**: `"weighted"`  
**Description**: Similarity calculation method  
**Options**:
- `"jaccard"`: Basic set intersection/union
- `"weighted"`: IDF + category weights (recommended)

---

## Configuration File

**File**: `config.py`

### Path Configuration

#### Image Storage
```python
IMAGE_DIRECTORY = "./static/images"      # Main image storage
THUMB_DIR = "./static/thumbnails"        # Thumbnail storage
THUMB_SIZE = 1000                        # Max thumbnail dimension (px)
```

---

#### Ingest Folder
```python
INGEST_DIRECTORY = "./ingest"            # Auto-processing folder
```

**Purpose**: Drop images here for automatic processing

---

#### Data Storage
```python
TAGS_FILE = "./tags.json"                # Legacy tags file
METADATA_DIR = "./metadata"              # Metadata storage
DATABASE_PATH = "./data/booru.db"             # Main database
```

---

### Local AI Tagger Configuration

```python
LOCAL_TAGGER_MODEL_PATH = "./models/Tagger/model.onnx"
LOCAL_TAGGER_METADATA_PATH = "./models/Tagger/metadata.json"
LOCAL_TAGGER_THRESHOLD = 0.6             # Confidence threshold (0.0-1.0)
LOCAL_TAGGER_TARGET_SIZE = 512           # Input image size
LOCAL_TAGGER_NAME = os.environ.get('LOCAL_TAGGER_NAME', 'CamieTagger')
```

**Threshold**: Higher = fewer but more confident tags  
**Target Size**: Model input dimension (don't change unless using different model)

---

### Database Performance Configuration

```python
# SQLite cache size in MB (default 64MB)
DB_CACHE_SIZE_MB = 64                    # Higher values use more RAM but improve query performance

# Memory-mapped I/O size in MB (default 256MB)
DB_MMAP_SIZE_MB = 256                    # Allows SQLite to map database file to memory for faster reads

# Batch size for database operations (default 100)
DB_BATCH_SIZE = 100                      # Higher values = fewer commits = faster but longer locks

# WAL checkpoint interval (default 1000 frames)
DB_WAL_AUTOCHECKPOINT = 1000             # Controls when WAL file is checkpointed back to main database
```

**Environment Variables**: All database settings support environment variable overrides:
```env
DB_CACHE_SIZE_MB=128
DB_MMAP_SIZE_MB=512
DB_BATCH_SIZE=200
DB_WAL_AUTOCHECKPOINT=2000
```

**Performance Impact**:
- **DB_CACHE_SIZE_MB**: Higher = faster queries but more RAM usage (64-256MB recommended)
- **DB_MMAP_SIZE_MB**: Higher = faster reads for large databases (256-512MB recommended)
- **DB_BATCH_SIZE**: Higher = faster bulk operations but longer database locks (100-500 recommended)
- **DB_WAL_AUTOCHECKPOINT**: Higher = less frequent checkpoints but larger WAL file (1000-5000 recommended)

**Tuning Guidelines**:
- Small collections (<5k images): Use defaults
- Medium collections (5k-50k images): Increase cache to 128MB, MMAP to 512MB
- Large collections (>50k images): Increase cache to 256MB, MMAP to 1GB, batch size to 200

---

### Monitoring Configuration

```python
MONITOR_ENABLED = True                   # Auto-start monitor service on app startup
MONITOR_INTERVAL = 300                   # Check interval (seconds) - only used in polling mode
```

**Monitor**: Automatically watches for new files in `IMAGE_DIRECTORY` and `INGEST_DIRECTORY` when `MONITOR_ENABLED = True`. Uses **watchdog mode** for real-time filesystem monitoring by default. `MONITOR_INTERVAL` is only used in legacy polling mode.

**Manual Control**: You can also start/stop the monitor via API:
- `POST /api/system/monitor/start` - Start monitoring
- `POST /api/system/monitor/stop` - Stop monitoring

---

### Processing Configuration

```python
MAX_WORKERS = 4                          # Parallel threads for metadata fetching
REQUEST_TIMEOUT = 10                     # API request timeout (seconds)
RATE_LIMIT_DELAY = 0.5                   # Delay between requests (seconds)
```

**MAX_WORKERS**: Higher = faster processing but more API load
**Recommendation**: 4-8 workers for good balance

---

### Source Priority Configuration

```python
BOORU_PRIORITY_VERSION = 4               # Increment when changing priority
BOORU_PRIORITY = [
    "danbooru",     # Best general categorization
    "e621",         # Good specific categorization  
    "gelbooru",     # Tags only
    "yandere",      # Tags only
    "pixiv",        # Pixiv tags and artist info
    "local_tagger"  # AI fallback
]
```

**Priority Order**: First match wins for primary source  
**Version**: Increment `BOORU_PRIORITY_VERSION` when changing order to trigger re-tagging

---

#### Merged Sources
```python
USE_MERGED_SOURCES_BY_DEFAULT = True     # Default to merged view for multi-source images
```

**True**: Images with multiple sources default to merged view  
**False**: Use first source from `BOORU_PRIORITY`

---

### Pagination

```python
IMAGES_PER_PAGE = 100                    # Images per page in gallery
```

---

### Feature Flags

```python
ENABLE_SAUCENAO = bool(SAUCENAO_API_KEY)       # Auto-enable if key present
ENABLE_LOCAL_TAGGER = True                     # Enable/disable AI tagging
ENABLE_DEDUPLICATION = True                    # MD5-based duplicate detection
```

---

### Similarity Category Weights

```python
SIMILARITY_CATEGORY_WEIGHTS = {
    'character': 6.0,    # Character matches very significant
    'copyright': 3.0,    # Same series/franchise important
    'artist': 2.0,       # Same artist style matters
    'species': 2.5,      # Species tags
    'general': 1.0,      # Standard descriptive tags
    'meta': 0.5          # Less relevant for similarity
}
```

**Higher Weight**: Category contributes more to similarity score  
**Use Case**: Fine-tune similarity matching behavior

---

## Configuration Validation

### `validate_config() -> bool`

Validates configuration and warns about issues.

**Checks**:
1. Image directory exists
2. Ingest directory exists (creates if missing)
3. Local tagger model files exist (if enabled)
4. Security settings changed from defaults

**Output**:
```
⚠️  Configuration Warnings:
  - SYSTEM_API_SECRET is set to default value - change this for production!
  - APP_PASSWORD is set to default value - change this for security!
  - SECRET_KEY is set to default value - change this for production!
```

**Called**: Automatically on module import (except when `__main__`)

**Returns**: `True` if no warnings, `False` if warnings present

---

## Helper Functions

### `get_local_tagger_config() -> Dict`

Get local tagger configuration as a dictionary.

**Returns**:
```python
{
    "model_path": "./models/Tagger/model.onnx",
    "metadata_path": "./models/Tagger/metadata.json",
    "threshold": 0.6,
    "target_size": 512,
    "name": "CamieTagger",
    "enabled": True
}
```

**Use Case**: Pass to tagger initialization functions

---

### `get_booru_apis() -> Dict`

Get configured booru API settings.

**Returns**:
```python
{
    "gelbooru": {
        "api_key": "...",
        "user_id": "..."
    }
}
```

**Use Case**: Authentication for API requests

---

## Configuration Best Practices

### Security

1. **Change All Secrets**:
   ```env
   APP_PASSWORD=your-strong-password-here
   SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
   SYSTEM_API_SECRET=another-strong-secret
   ```

2. **Never Commit `.env`**:
   - Already in `.gitignore`
   - Contains sensitive credentials

3. **Use Different Secrets**:
   - Don't reuse passwords
   - Each secret should be unique

---

### Performance Tuning

#### For Fast Metadata Fetching
```python
MAX_WORKERS = 8              # More parallel requests
REQUEST_TIMEOUT = 15         # Longer timeout for slow APIs
RATE_LIMIT_DELAY = 0.2       # Faster requests (may hit rate limits)
```

#### For Large Collections
```python
IMAGES_PER_PAGE = 50         # Fewer images per page (faster loading)
THUMB_SIZE = 800             # Smaller thumbnails (faster generation)

# Database performance (via environment variables)
DB_CACHE_SIZE_MB = 256       # More cache for large collections
DB_MMAP_SIZE_MB = 1024       # 1GB MMAP for faster reads
DB_BATCH_SIZE = 200          # Larger batches for bulk operations
```

#### For Better Similarity
```python
SIMILARITY_METHOD = "weighted"   # More accurate than jaccard
SIMILARITY_CATEGORY_WEIGHTS = {
    'character': 8.0,            # Increase character importance
    'copyright': 4.0,
    'general': 0.8               # Decrease general tag importance
}
```

#### Database Optimization for Large Collections (50k+ images)
```env
# In .env file
DB_CACHE_SIZE_MB=256
DB_MMAP_SIZE_MB=1024
DB_BATCH_SIZE=200
DB_WAL_AUTOCHECKPOINT=5000
```

**Expected Results**:
- 2-3x faster tag searches
- 5-10x faster bulk operations (repopulation, rebuilds)
- Reduced UI blocking during cache reloads
- Better concurrent access performance

---

### Model Configuration

#### Switching AI Models
1. Download new ONNX model
2. Place in `models/Tagger/`
3. Rename to `model.onnx` and `metadata.json`
4. Update `.env`:
   ```env
   LOCAL_TAGGER_NAME=WD14
   ```
5. Adjust threshold if needed in `config.py`:
   ```python
   LOCAL_TAGGER_THRESHOLD = 0.7  # Different models need different thresholds
   ```

---

### Source Priority Tuning

#### Change Priority Order
```python
# In config.py
BOORU_PRIORITY_VERSION = 5  # INCREMENT THIS!
BOORU_PRIORITY = [
    "e621",         # Now prefer e621 first
    "danbooru",
    # ...
]
```

**Important**: Always increment `BOORU_PRIORITY_VERSION` to trigger automatic re-tagging

---

## Environment-Specific Configurations

### Development
```env
FLASK_DEBUG=true
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
```

### Production
```env
FLASK_DEBUG=false
FLASK_HOST=0.0.0.0
FLASK_PORT=80
# Strong secrets required!
```

### High-Volume Processing
```python
MAX_WORKERS = 16
MONITOR_INTERVAL = 60  # Check more frequently
```

---

## Troubleshooting

### "Local tagger model not found"
**Solution**: Download model or disable local tagging:
```python
ENABLE_LOCAL_TAGGER = False
```

### "SYSTEM_API_SECRET is set to default value"
**Solution**: Change in `.env`:
```env
SYSTEM_API_SECRET=your-unique-secret-here
```

### Slow image loading
**Solution**: Reduce images per page:
```python
IMAGES_PER_PAGE = 50
```

### API rate limiting
**Solution**: Increase delay:
```python
RATE_LIMIT_DELAY = 1.0  # 1 second between requests
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [DATABASE.md](DATABASE.md) - Database configuration
- [SERVICES.md](SERVICES.md) - Services using configuration

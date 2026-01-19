# Services Layer Documentation

## Table of Contents
- [Overview](#overview)
- [Service Index](#service-index)
- [Background Tasks Service](#background-tasks-service)
- [Health Service](#health-service)
- [Image Service](#image-service)
- [Implication Service](#implication-service)
- [Monitor Service](#monitor-service)
- [Priority Service](#priority-service)
- [Processing Service](#processing-service)
- [Query Service](#query-service)
- [Rating Service](#rating-service)
- [SauceNao Service](#saucenao-service)
- [Switch Source Service](#switch-source-service)
- [System Service](#system-service)
- [Tag Service](#tag-service)
- [Tag Categorization Service](#tag-categorization-service)

---

## Overview

The Services layer contains the business logic for ChibiBooru. Services orchestrate operations between routers, repositories, and external APIs. They handle complex workflows, coordinate multiple data sources, and implement core application features.

### Design Principles
- **Single Responsibility**: Each service handles a specific domain
- **Async-First**: Services support async operations where needed
- **Error Handling**: Comprehensive error handling and logging
- **Separation of Concerns**: Services don't directly handle HTTP routing
- **Event-Driven**: Services trigger cache invalidation events

---

## Service Index

| Service | File | Purpose |
|---------|------|---------|
| Background Tasks | `background_tasks.py` | Async task management with progress tracking |
| Health | `health_service.py` | Database health checks and auto-repair |
| Image | `image_service.py` | Image CRUD and bulk operations |
| Implication | `implication_service.py` | Tag implication detection and management |
| Monitor | `monitor_service.py` | Background file monitoring and processing |
| Priority | `priority_service.py` | Source priority change detection |
| Processing | `processing_service.py` | Metadata fetching and image processing |
| Query | `query_service.py` | Search, filtering, and similarity calculations |
| Rating | `rating_service.py` | AI-based rating inference |
| SauceNao | `saucenao_service.py` | Reverse image search integration |
| Switch Source | `switch_source_db.py` | Metadata source switching |
| System | `system_service.py` | System operations (scan, rebuild, etc.) |
| Tag | `tag_service.py` | Tag operations and autocomplete |
| Tag Categorization | `tag_categorization_service.py` | Extended categories tag categorization |

---

## Background Tasks Service

**File**: `services/background_tasks.py`

### Purpose
Manages long-running background tasks with progress tracking and status monitoring.

### Classes

#### `BackgroundTaskManager`

Manages async background tasks with progress tracking.

**Attributes**:
- `tasks: Dict[str, Dict[str, Any]]` - Active and completed tasks
- `_lock: asyncio.Lock` - Thread-safe task access

**Methods**:

##### `async start_task(task_id: str, task_func: Callable, *args, **kwargs)`

Start a new background task.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `task_id` | `str` | Unique task identifier |
| `task_func` | `Callable` | Async function to execute |
| `*args` | | Positional arguments for task_func |
| `**kwargs` | | Keyword arguments for task_func |

**Raises**:
- `ValueError` - If task_id already running

**Example**:
```python
async def my_task(task_id, manager, data):
    await manager.update_progress(task_id, 0, 100, "Starting...")
    # Do work
    await manager.update_progress(task_id, 100, 100, "Complete!")
    return {"result": "success"}

await task_manager.start_task("my-task", my_task, data={"test": 123})
```

##### `async update_progress(task_id: str, progress: int, total: int, message: Optional[str] = None, current_item: Optional[str] = None)`

Update task progress.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `task_id` | `str` | Task identifier |
| `progress` | `int` | Current progress (e.g., 50) |
| `total` | `int` | Total items (e.g., 100) |
| `message` | `Optional[str]` | Status message |
| `current_item` | `Optional[str]` | Current item being processed |

##### `async get_task_status(task_id: str) -> Optional[Dict[str, Any]]`

Get current task status.

**Returns**:
```python
{
    "status": "running",  # pending, running, completed, failed, cancelled
    "progress": 50,
    "total": 100,
    "current_item": "image.jpg",
    "message": "Processing images...",
    "started_at": "2024-01-01T12:00:00",
    "completed_at": None,
    "error": None,
    "result": None
}
```

##### `async cancel_task(task_id: str)`

Mark task as cancelled. Note: Actual cancellation requires cooperation from the task function.

### Global Instance

```python
# services/background_tasks.py
task_manager = BackgroundTaskManager()
```

Use this global instance throughout the application.

---

## Health Service

**File**: `services/health_service.py`

### Purpose
Performs database health checks and automatic repairs to maintain data integrity.

### Classes

#### `HealthCheckResult`

Result of a health check operation.

**Attributes**:
- `check_name: str` - Name of the check
- `passed: bool` - Whether check passed
- `issues_found: int` - Number of issues detected
- `issues_fixed: int` - Number of issues repaired
- `errors: List[str]` - Error messages
- `messages: List[str]` - Informational messages

**Methods**:
- `add_message(msg: str)` - Add info message
- `add_error(error: str)` - Add error and mark as failed
- `to_dict() -> dict` - Convert to dictionary

### Functions

#### `check_and_fix_null_active_source(auto_fix: bool = True) -> HealthCheckResult`

Check for images with NULL active_source that have sources available.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `auto_fix` | `bool` | Whether to automatically fix issues |

**What it does**:
1. Finds images with NULL `active_source` but with available sources
2. Sets `active_source` based on `config.BOORU_PRIORITY`
3. Falls back to first available source if no priority match

**Returns**: `HealthCheckResult` with fix details

**Side Effects**:
- Updates `images.active_source` column
- Commits database changes

---

#### `check_orphaned_image_sources(auto_fix: bool = True) -> HealthCheckResult`

Check for orphaned records in image_sources table.

**What it does**:
1. Finds `image_sources` entries referencing deleted images
2. Removes orphaned entries

**Side Effects**:
- Deletes orphaned `image_sources` records

---

#### `check_missing_thumbnails(auto_fix: bool = False) -> HealthCheckResult`

Check for images without thumbnails.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `auto_fix` | `bool` | Whether to generate missing thumbnails (can be slow) |

**What it does**:
1. Finds images in database without corresponding thumbnails
2. Optionally generates missing thumbnails

---

#### `check_corrupted_metadata(auto_fix: bool = True) -> HealthCheckResult`

Check for corrupted JSON metadata in raw_metadata table.

**What it does**:
1. Validates JSON in `raw_metadata.data` column
2. Removes corrupted entries

**Side Effects**:
- Deletes invalid JSON metadata

---

#### `check_fts_index_consistency(auto_fix: bool = True) -> HealthCheckResult`

Check FTS5 index consistency.

**What it does**:
1. Compares `images` count vs `images_fts` count
2. Rebuilds FTS index if inconsistent

**Side Effects**:
- Repopulates `images_fts` table

---

#### `startup_health_check() -> List[HealthCheckResult]`

Run all critical health checks on application startup.

**Checks Performed**:
1. NULL active_source
2. Orphaned image_sources
3. Corrupted metadata
4. FTS index consistency

**Returns**: List of `HealthCheckResult` for each check

**Called from**: `app.py` during initialization

---

## Image Service

**File**: `services/image_service.py`

### Purpose
Handle image CRUD operations, bulk operations, and API endpoints.

### Functions

#### `get_images_for_api() -> Response`

Provide paginated images for infinite scroll API.

**Request Parameters**:
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `query` | `str` | `""` | Search query |
| `page` | `int` | `1` | Page number |
| `seed` | `int` | None | Random seed for shuffling |

**Returns**:
```json
{
    "images": [
        {
            "path": "images/folder/image.jpg",
            "thumb": "thumbnails/folder/image.webp",
            "tags": "tag1 tag2 tag3"
        }
    ],
    "page": 1,
    "total_pages": 10,
    "total_results": 500,
    "has_more": true
}
```

**Performance**: 50 images per page for optimal loading

---

#### `async delete_image_service() -> Response`

Delete an image and its metadata.

**Request Body**:
```json
{
    "filepath": "images/folder/image.jpg"
}
```

**Process**:
1. Remove database entry
2. Delete image file from disk
3. Delete thumbnail file
4. Update in-memory cache
5. Reload tag counts

**Returns**:
```json
{
    "status": "success",
    "message": "Deletion process completed."
}
```

**Side Effects**:
- Deletes file from `static/images/`
- Deletes thumbnail from `static/thumbnails/`
- Removes from database
- Invalidates cache

**Error Handling**:
- Returns 400 if filepath missing
- Returns 500 on unexpected errors
- Logs full traceback for debugging

---

#### `async delete_images_bulk_service() -> Response`

Delete multiple images at once.

**Request Body**:
```json
{
    "filepaths": [
        "images/folder/image1.jpg",
        "images/folder/image2.jpg"
    ]
}
```

**Returns**:
```json
{
    "total": 2,
    "deleted": 2,
    "failed": 0,
    "errors": []
}
```

**Performance**: Processes images sequentially, updates cache once at end

---

#### `async update_relationship_service() -> Response`

Update parent/child relationships between images.

**Request Body**:
```json
{
    "filepath": "images/child.jpg",
    "parent_id": 123,
    "has_children": false
}
```

**Side Effects**:
- Updates `images.parent_id`
- Updates `images.has_children`
- Clears related image cache

---

## Implication Service

**File**: `services/implication_service.py`

### Purpose
Detect and manage tag implications (A → B relationships).

### Implication Types

1. **Pattern-based**: Detected from tag naming patterns
   - Example: `hatsune_miku_(vocaloid)` → `vocaloid`
   - Example: `hatsune_miku_(append)` → `hatsune_miku`

2. **Statistical**: Detected from co-occurrence statistics
   - Example: `hatsune_miku` → `twintails` (95% co-occurrence)

3. **Manual**: Created by users

### Functions

#### `detect_pattern_based_implications() -> List[Dict]`

Detect implications from tag naming patterns.

**Pattern Rules**:
- `character_(outfit)_(series)` → `character_(series)`
- `character_(outfit)` → `character`
- `character_(series)` → `series`

**Returns**:
```python
[
    {
        "source_tag": "hatsune_miku_(append)",
        "implied_tag": "hatsune_miku",
        "inference_type": "pattern",
        "confidence": 1.0,
        "pattern": "character_(variant) implies character"
    }
]
```

---

#### `detect_statistical_implications(min_support: int = 10, min_confidence: float = 0.85) -> List[Dict]`

Detect implications from tag co-occurrence statistics.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `min_support` | `int` | Minimum times tags must appear together |
| `min_confidence` | `float` | Minimum percentage (e.g., 0.85 = 85%) |

**Algorithm**:
1. Count tag co-occurrences
2. Calculate confidence: `P(B|A) = count(A,B) / count(A)`
3. Filter by thresholds
4. Exclude obvious implications (character → series already exists)

**Returns**: List of detected implications

---

#### `get_pending_implications() -> List[Dict]`

Get all implications awaiting approval.

**Returns**:
```python
[
    {
        "id": (1, 2),
        "source_tag": "hatsune_miku",
        "implied_tag": "vocaloid",
        "inference_type": "statistical",
        "confidence": 0.95,
        "status": "pending",
        "impact": 150  # Images that would be affected
    }
]
```

---

#### `approve_implication(source_tag_id: int, implied_tag_id: int) -> bool`

Approve and activate an implication.

**Process**:
1. Update status to 'active'
2. Apply to all existing images with source tag
3. Invalidate caches

**Side Effects**:
- Updates `tag_implications.status`
- Adds implied tags to images
- Invalidates cache

---

#### `apply_implications_for_image(image_id: int)`

Apply all active implications for an image.

**Called when**: New image added or tags modified

**Process**:
1. Get all tags for image
2. Find active implications for those tags
3. Add implied tags if not already present
4. Handle implication chains (A→B→C)

---

## Monitor Service

**File**: `services/monitor_service.py`

### Purpose
Background service that monitors filesystem for new images and processes them automatically.

### Monitoring Modes

1. **Watchdog Mode** (default): Real-time filesystem monitoring
2. **Polling Mode** (legacy): Periodic directory scanning

### Global State

```python
monitor_status = {
    "running": bool,           # Is monitor active
    "last_check": str,         # ISO timestamp
    "last_scan_found": int,    # Images found in last scan
    "total_processed": int,    # Total images processed
    "interval_seconds": int,   # Polling interval (legacy)
    "logs": List[Dict],        # Recent log entries
    "mode": str,               # "watchdog" or "polling"
    "pending_reload": bool,    # Cache reload needed
    "last_activity": float     # Timestamp of last activity
}
```

### Classes

#### `ImageFileHandler(FileSystemEventHandler)`

Watchdog event handler for filesystem events.

**Attributes**:
- `processing_lock: threading.Lock` - Prevents concurrent processing
- `recently_processed: Dict[str, float]` - Debounce tracker
- `debounce_seconds: int` - Debounce delay (default 2s)
- `watch_ingest: bool` - Whether monitoring ingest folder

**Methods**:

##### `is_image_file(filepath: str) -> bool`

Check if file is an image or video.

**Supported formats**: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.mp4`, `.webm`

##### `should_process(filepath: str) -> bool`

Check if file should be processed (debouncing).

Prevents duplicate processing when a file triggers multiple events.

##### `on_created(event)`

Handle file creation events.

**Process**:
1. Verify file is an image
2. Check debounce
3. Wait 0.5s for file to be fully written
4. Determine if from ingest folder
5. Process image (move from ingest if needed)
6. Update monitor status
7. Mark cache for reload

---

### Functions

#### `find_ingest_files() -> List[str]`

Find all image files in ingest directory.

**Returns**: List of absolute file paths

---

#### `run_scan() -> int`

Scan for new images and process them.

**Process**:
1. Scan `static/images/` for new files
2. Scan `ingest/` for files to process
3. Process all found files
4. Generate thumbnails
5. Update database
6. Reload cache

**Returns**: Number of images processed

---

#### `start_monitor()`

Start the background monitor service.

**Process**:
1. Stop existing monitor if running
2. Create watchdog observer
3. Set up event handlers for both directories
4. Start observer thread
5. Update status

**Side Effects**:
- Starts background thread
- Creates global observer instance

---

#### `stop_monitor()`

Stop the background monitor service.

**Side Effects**:
- Stops observer
- Joins threads
- Updates status

---

#### `get_status() -> Dict`

Get current monitor status.

**Returns**: `monitor_status` dictionary

---

## Priority Service

**File**: `services/priority_service.py`

### Purpose
Detect changes to `BOORU_PRIORITY` configuration and trigger automatic re-tagging.

### Functions

#### `check_and_apply_priority_changes()`

Check if BOORU_PRIORITY changed and auto-apply if needed.

**Process**:
1. Read stored priority version from database
2. Compare with `config.BOORU_PRIORITY_VERSION`
3. If changed:
   - Trigger database rebuild
   - Update stored version
   - Log change

**Called from**: `app.py` during startup (before loading data)

**Configuration**:
```python
# config.py
BOORU_PRIORITY_VERSION = 4  # Increment when changing priority
BOORU_PRIORITY = [
    "danbooru",
    "e621",
    "gelbooru",
    # ...
]
```

**Database Storage**: Stored in `rating_model_metadata` table

---

## Processing Service

**File**: `services/processing_service.py`

### Purpose
Core metadata fetching and image processing engine. Handles:
- MD5 hash calculation
- Metadata fetching from multiple boorus
- SauceNao reverse image search
- Local AI tagging (ONNX)
- Thumbnail generation

### Dependencies

```python
import onnxruntime as ort  # Optional, for AI tagging
import torchvision.transforms  # Optional, for AI tagging
```

### Rate Limiting

#### `AdaptiveSauceNAORateLimiter`

Adaptive rate limiter for SauceNAO API requests.

**Features**:
- Starts with no limits (unlimited requests)
- Learns rate limits by detecting 429 errors
- Backs off conservatively on rate limit hit
- Gradually increases limit when successful
- Automatic backoff period

**Attributes**:
- `current_limit: Optional[int]` - Requests per window (None = unlimited)
- `window_duration: int` - Window duration in seconds (30s)
- `requests: deque` - Recent request timestamps
- `consecutive_successes: int` - Successful requests since last 429
- `test_threshold: int` - Test limit increase every N requests (50)

**Methods**:

##### `wait_if_needed()`

Block until a request can be made.

**Behavior**:
- If at limit, waits until window expires
- If in backoff, waits until backoff expires
- Prints wait time to console

##### `record_success()`

Record a successful request.

**Side Effects**:
- Adds timestamp to request queue
- Increments success counter
- May increase limit if testing

##### `record_rate_limit_hit()`

Record a 429 rate limit error.

**Side Effects**:
- Sets conservative limit (6 requests/30s)
- Enters backoff period (60s)
- Resets success counter

**Example Usage**:
```python
saucenao_rate_limiter = AdaptiveSauceNAORateLimiter()

saucenao_rate_limiter.wait_if_needed()
response = requests.get(saucenao_url, ...)
if response.status_code == 429:
    saucenao_rate_limiter.record_rate_limit_hit()
else:
    saucenao_rate_limiter.record_success()
```

---

### Local AI Tagger

#### `initialize_local_tagger()`

Initialize the local ONNX tagger model.

**Process**:
1. Check if ONNX Runtime available
2. Load model from `config.LOCAL_TAGGER_MODEL_PATH`
3. Load metadata from `config.LOCAL_TAGGER_METADATA_PATH`
4. Build tag index and category mappings

**Side Effects**:
- Sets global `local_tagger_session`
- Sets global `local_tagger_metadata`
- Sets global `idx_to_tag_map` and `tag_to_category_map`

---

#### `tag_image_locally(image_path: str) -> Dict`

Tag an image using local ONNX model.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `image_path` | `str` | Path to image file |

**Returns**:
```python
{
    "tags": {
        "character": ["hatsune_miku"],
        "copyright": ["vocaloid"],
        "general": ["1girl", "blue_hair", "twintails"],
        "meta": ["highres"]
    },
    "confidence": 0.85,
    "model": "CamieTagger"
}
```

**Process**:
1. Load and preprocess image
2. Run model inference
3. Apply threshold filtering
4. Categorize tags
5. Return structured results

**Error Handling**:
- Returns empty dict on error
- Logs errors to console

---

### Metadata Fetching

#### `calculate_md5(filepath: str) -> str`

Calculate MD5 hash of a file.

**Returns**: Hexadecimal MD5 string

---

#### `fetch_by_md5(md5_hash: str) -> Optional[Dict]`

Fetch metadata using MD5 hash lookup.

**Sources Checked** (in order):
1. Danbooru
2. e621
3. Gelbooru
4. Yandere

**Returns**:
```python
{
    "source": "danbooru",
    "data": {...}  # Full API response
}
```

**Performance**: Parallel requests with ThreadPoolExecutor

---

#### `fetch_by_post_id(source: str, post_id: str) -> Optional[Dict]`

Fetch metadata by post ID from a specific booru.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `source` | `str` | Source name ('danbooru', 'e621', etc.) |
| `post_id` | `str` | Post ID |

**Returns**: `{"source": str, "data": dict}`

---

#### `search_saucenao(image_path: str) -> Optional[Dict]`

Reverse image search using SauceNao API.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `image_path` | `str` | Path to image file |

**Returns**:
```python
{
    "results": [
        {
            "header": {
                "similarity": "95.5",
                "thumbnail": "https://..."
            },
            "data": {
                "ext_urls": ["https://danbooru.donmai.us/posts/123"]
            }
        }
    ]
}
```

**Rate Limiting**: Uses `AdaptiveSauceNAORateLimiter`

**API Key**: From `config.SAUCENAO_API_KEY`

---

### Image Processing

#### `process_image_file(filepath: str, move_from_ingest: bool = False) -> bool`

Process a single image file.

**Process**:
1. Calculate MD5 hash
2. Check for duplicates
3. Move from ingest if needed
4. Fetch metadata:
   - Try MD5 lookup
   - Try SauceNao if no match
   - Fall back to local tagger
5. Extract tags and categorize
6. Store in database
7. Generate thumbnail
8. Apply tag implications
9. Infer rating (if enabled)

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Path to image file |
| `move_from_ingest` | `bool` | Whether to move from ingest folder |

**Returns**: `True` if processed, `False` if duplicate/error

**Side Effects**:
- Moves file to bucketed structure if from ingest
- Creates database entry
- Generates thumbnail
- Adds tags
- Records metadata source

---

#### `extract_tag_data(data: Dict, source: str) -> Dict`

Extract normalized tag data from raw API response.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `data` | `Dict` | Raw API response |
| `source` | `str` | Source name |

**Returns**:
```python
{
    "tags": {
        "character": ["..."],
        "copyright": ["..."],
        "artist": ["..."],
        "general": ["..."],
        "meta": ["..."]
    },
    "image_url": "https://...",
    "preview_url": "https://...",
    "width": 1920,
    "height": 1080,
    "file_size": 1024000
}
```

**Handles source-specific formats**:
- Danbooru: `tag_string_character`, `tag_string_copyright`, etc.
- e621: `tags` object with nested arrays
- Gelbooru: Space-separated tag string
- Pixiv: Special handling with local tagger supplement

---

#### `generate_thumbnail(image_path: str) -> Optional[str]`

Generate thumbnail for an image.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `image_path` | `str` | Path to source image |

**Returns**: Path to generated thumbnail or None on error

**Thumbnail Settings**:
- Format: WebP
- Max dimension: `config.THUMB_SIZE` (default 1000px)
- Preserves aspect ratio
- Quality: 85

**Output Path**: `static/thumbnails/{path}.webp`

---

## Query Service

**File**: `services/query_service.py`

### Purpose
Advanced search, filtering, and similarity calculations.

### Similarity Calculation

#### `calculate_similarity(tags1: str, tags2: str) -> float`

Calculate similarity between two tag sets using configured method.

**Methods**:
- `jaccard`: Simple set intersection/union
- `weighted`: IDF + category weighting (default)

**Configuration**: `config.SIMILARITY_METHOD`

---

#### `calculate_jaccard_similarity(tags1: str, tags2: str) -> float`

Basic Jaccard similarity.

**Formula**: `|A ∩ B| / |A ∪ B|`

**Returns**: Float between 0.0 and 1.0

---

#### `calculate_weighted_similarity(tags1: str, tags2: str) -> float`

Weighted similarity using IDF and category multipliers.

**Features**:
- Rare tags contribute more (IDF weighting)
- Category weights (character > copyright > general)
- Cached tag weights for performance

**Formula**:
```
weight(tag) = (1 / log(frequency + 1)) * category_weight
similarity = Σ(weights of common tags) / Σ(weights of all tags)
```

**Category Weights** (`config.SIMILARITY_CATEGORY_WEIGHTS`):
```python
{
    'character': 6.0,   # Very significant
    'copyright': 3.0,   # Important
    'artist': 2.0,      # Matters
    'species': 2.5,     # Species tags
    'general': 1.0,     # Standard
    'meta': 0.5         # Less relevant
}
```

---

### Search Functions

#### `perform_search(query: str) -> Tuple[List[Dict], bool]`

Execute a search query and return results.

**Query Syntax**:
- `tag1 tag2`: AND search
- `-tag`: Exclude tag
- `source:danbooru`: Filter by source
- `filename:text`: Search filenames
- `.png`: Filter by extension
- `has:parent`: Has parent relationship
- `has:child`: Has children
- `pool:name`: In specific pool
- `order:new` or `order:newest`: Newest first
- `order:old` or `order:oldest`: Oldest first
- `character:name`: Category-specific search

**Returns**:
```python
(
    [
        {"filepath": "...", "tags": "..."},
        ...
    ],
    True  # should_shuffle (True if no specific ordering)
)
```

**Search Strategy**:
1. Parse query into components
2. Decide between FTS5 or tag-based search
3. Execute optimized SQL query
4. Apply filters and sorting
5. Return results

---

#### `get_enhanced_stats() -> Dict`

Get detailed statistics about the collection.

**Returns**:
```python
{
    "total": 1000,
    "with_metadata": 1000,
    "without_metadata": 0,
    "total_tags": 5000,
    "avg_tags_per_image": 25.5,
    "source_breakdown": {
        "danbooru": 500,
        "e621": 300,
        "local_tagger": 200
    },
    "top_tags": [
        ("1girl", 800),
        ("solo", 750),
        ...
    ],
    "category_counts": {
        "character": 1000,
        "copyright": 500,
        ...
    },
    "saucenao_used": 50,
    "local_tagger_used": 200
}
```

---

## Rating Service

**File**: `services/rating_service.py`

### Purpose
AI-based content rating inference using tag-based machine learning.

### Rating Categories
- `rating:general` - Safe for work
- `rating:sensitive` - Slightly suggestive
- `rating:questionable` - Suggestive/ecchi
- `rating:explicit` - NSFW/adult content

### Functions

#### `train_rating_model() -> Dict`

Train the rating inference model from existing rated images.

**Process**:
1. Extract all images with rating tags
2. Calculate tag weights for each rating
3. Calculate tag pair weights for context
4. Store weights in database
5. Update model metadata

**Returns**:
```python
{
    "status": "success",
    "samples": {
        "general": 500,
        "sensitive": 200,
        "questionable": 150,
        "explicit": 100
    },
    "tag_weights": 5000,
    "pair_weights": 10000
}
```

**Side Effects**:
- Populates `rating_tag_weights` table
- Populates `rating_tag_pair_weights` table
- Updates `rating_model_metadata`

---

#### `infer_rating(tags: List[str]) -> Dict`

Infer rating for an image based on its tags.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `tags` | `List[str]` | List of tag names |

**Returns**:
```python
{
    "rating": "rating:questionable",
    "confidence": 0.85,
    "scores": {
        "general": 0.1,
        "sensitive": 0.15,
        "questionable": 0.65,
        "explicit": 0.1
    }
}
```

**Algorithm**:
1. Load tag weights from database
2. Calculate individual tag scores
3. Calculate tag pair scores (context)
4. Combine scores with pair weight multiplier
5. Apply thresholds to determine rating
6. Return rating with confidence

**Thresholds** (`rating_inference_config`):
- `threshold_general`: 0.5
- `threshold_sensitive`: 0.6
- `threshold_questionable`: 0.7
- `threshold_explicit`: 0.8

---

## SauceNao Service

**File**: `services/saucenao_service.py`

### Purpose
Reverse image search integration with SauceNao API.

### Functions

#### `async saucenao_search_service() -> Response`

Search SauceNao for an image.

**Request Body**:
```json
{
    "secret": "...",
    "filepath": "images/folder/image.jpg"
}
```

**Returns**:
```json
{
    "status": "success",
    "found": true,
    "results": [
        {
            "similarity": 95.5,
            "thumbnail": "https://...",
            "sources": [
                {
                    "type": "danbooru",
                    "url": "https://danbooru.donmai.us/posts/123",
                    "post_id": "123"
                }
            ]
        }
    ]
}
```

**Similarity Threshold**: 60% minimum

---

#### `async saucenao_fetch_metadata_service() -> Response`

Fetch full metadata from a booru source.

**Request Body**:
```json
{
    "secret": "...",
    "source": "danbooru",
    "post_id": "123"
}
```

**Returns**:
```json
{
    "status": "success",
    "source": "danbooru",
    "tags": {
        "character": ["..."],
        "general": ["..."]
    },
    "image_url": "https://...",
    "preview_url": "https://...",
    "width": 1920,
    "height": 1080,
    "file_size": 1024000
}
```

---

#### `async saucenao_apply_service() -> Response`

Apply selected metadata and optionally download new image.

**Request Body**:
```json
{
    "secret": "...",
    "filepath": "images/old.jpg",
    "source": "danbooru",
    "post_id": "123",
    "download_image": true,
    "image_url": "https://..."
}
```

**Process**:
1. Delete old database entry
2. Download new image if requested
3. Delete old file if download successful
4. Process new/existing image
5. Redirect to image detail page

**Returns**:
```json
{
    "status": "success",
    "redirect_url": "/image/images/new.jpg"
}
```

---

## Switch Source Service

**File**: `services/switch_source_db.py`

### Purpose
Switch metadata sources for images and merge tags from multiple sources.

### Functions

#### `switch_source(filepath: str, new_source: str) -> bool`

Switch active metadata source for an image.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative image path |
| `new_source` | `str` | Source name |

**Process**:
1. Verify source exists in raw_metadata
2. Update `active_source` column
3. Rebuild tags from new source
4. Update denormalized tag columns
5. Update FTS index

**Returns**: `True` on success

---

#### `merge_all_sources(filepath: str) -> bool`

Merge tags from all available sources.

**Process**:
1. Load all source metadata
2. Combine tags from all sources
3. Remove duplicates
4. Apply tag implications
5. Update database

**Source Priority** (for conflicts):
Uses `config.BOORU_PRIORITY` to determine which source wins

---

## System Service

**File**: `services/system_service.py`

### Purpose
System-wide operations: scanning, rebuilding, thumbnails, deduplication.

### Functions

#### `scan_and_process_service() -> Response`

Find and process new, untracked images.

**Authorization**: Requires `RELOAD_SECRET`

**Process**:
1. Run scan for new images
2. Clean orphaned image_tags entries
3. Clean orphaned image records (deleted files)
4. Reload data if changes made
5. Run ANALYZE if new images added

**Returns**:
```json
{
    "status": "success",
    "message": "Processed 5 new images, cleaned 2 orphaned image records.",
    "processed": 5,
    "cleaned": 2,
    "orphaned_tags_cleaned": 0
}
```

---

#### `rebuild_service() -> Response`

Re-process all tags from raw_metadata.

**Authorization**: Requires `RELOAD_SECRET`

**Process**:
1. Stop monitor service
2. Run `models.repopulate_from_database()`
3. Reload data from DB
4. Apply tag deltas (restore manual edits)

**Use Cases**:
- After changing `BOORU_PRIORITY`
- After fixing corrupted metadata
- After database schema changes

---

#### `rebuild_categorized_service() -> Response`

Back-fill categorized tag columns.

**Process**:
1. Rebuild denormalized tag columns from image_tags
2. Update FTS index
3. Reload cache

---

#### `generate_thumbnails_service() -> Response`

Generate missing thumbnails for all images.

**Process**:
1. Find images without thumbnails
2. Generate thumbnails in parallel
3. Report progress

---

#### `deduplicate_service() -> Response`

Find and remove duplicate images based on MD5 hash.

**Process**:
1. Scan for duplicate MD5 hashes
2. Keep one copy (usually first alphabetically)
3. Delete duplicates
4. Update database

---

## Tag Service

**File**: `services/tag_service.py`

### Purpose
Tag editing and autocomplete functionality.

### Functions

#### `async edit_tags_service() -> Response`

Update tags for an image with category support.

**Request Body**:
```json
{
    "filepath": "images/folder/image.jpg",
    "categorized_tags": {
        "character": ["hatsune_miku"],
        "copyright": ["vocaloid"],
        "general": ["1girl", "blue_hair"]
    }
}
```

**Important**: This records tag deltas for preservation across rebuilds.

**Process**:
1. Update image_tags relationships
2. Record tag deltas
3. Update denormalized columns
4. Reload single image cache
5. Reload tag counts
6. Clear image details cache

**Returns**:
```json
{
    "status": "success"
}
```

---

#### `autocomplete() -> Response`

Enhanced autocomplete with grouped suggestions.

**Query Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `q` | `str` | Search query |

**Returns**:
```json
{
    "groups": [
        {
            "name": "Filters",
            "items": [
                {
                    "tag": "source:danbooru",
                    "display": "Danbooru images",
                    "count": null,
                    "type": "filter"
                }
            ]
        },
        {
            "name": "Tags",
            "items": [
                {
                    "tag": "hatsune_miku",
                    "display": "hatsune_miku",
                    "count": 500,
                    "category": "character",
                    "type": "tag",
                    "is_prefix": true
                }
            ]
        }
    ]
}
```

**Features**:
- Negative tag search (prefix with `-`)
- Category-specific search
- File extension suggestions
- Special filter suggestions
- Grouped by type (Filters, Tags, Files)
- Prioritizes prefix matches
- Shows usage counts

---

## Tag Categorization Service

**File**: `services/tag_categorization_service.py`

### Purpose
Advanced tag categorization using the Extended Categories system (22-category extended system) for granular tag organization.

> **📘 For complete documentation**, see [**Extended Categories Documentation**](EXTENDED_CATEGORIES.md)

### Extended Categories Overview

The service provides a **22-category system** organized into three main groups:

1. **Identity (Permanent Traits)**: Subject count, body features, hair, face, genitalia
2. **Context (Temporary/Situational)**: Attire, actions, poses, expressions, objects, settings
3. **Technical/Meta**: Framing, focus, art style, visual effects, metadata

### Key Constants

#### `EXTENDED_CATEGORIES`

List of all 22 extended categories with metadata:

```python
EXTENDED_CATEGORIES = [
    ('00_Subject_Count', 'Subject Count', '0', 'Count & Gender (1girl, solo, 1boy)'),
    ('01_Body_Physique', 'Body Physique', '1', 'Permanent body traits (breasts, tail, animal_ears)'),
    # [... 20 more categories - see EXTENDED_CATEGORIES.md for complete list]
]
```

Each tuple contains: `(category_key, display_name, keyboard_shortcut, description)`

#### `TAG_CATEGORIES`

Simplified list of category keys for validation:
```python
TAG_CATEGORIES = ['00_Subject_Count', '01_Body_Physique', ..., '21_Status']
```

### Functions

#### `get_uncategorized_tags_by_frequency(limit: int = 100, include_simple_categories: bool = True) -> List[Dict]`

Get uncategorized tags sorted by usage frequency.

**Returns**:
```python
[
    {
        'name': 'sitting',
        'usage_count': 1250,
        'sample_images': ['images/1.jpg', 'images/2.jpg', 'images/3.jpg'],
        'current_category': 'general'
    }
]
```

---

#### `get_categorization_stats() -> Dict`

Get comprehensive statistics about tag categorization status.

**Returns**:
```python
{
    'total_tags': 5000,
    'categorized': 3200,
    'uncategorized': 1800,
    'meaningful_uncategorized': 450,
    'meaningful_categorized': 2850,
    'by_category': {
        '02_Body_Hair': 320,
        '03_Body_Face': 180,
        '09_Action': 420
    },
    'categories': TAG_CATEGORIES,
    'extended_categories': EXTENDED_CATEGORIES
}
```

---

#### `set_tag_category(tag_name: str, category: Optional[str]) -> Dict`

Set or update the extended category for a tag.

**Returns**:
```python
{
    'old_category': None,
    'new_category': '10_Pose'
}
```

**Raises**: `ValueError` if category is invalid or tag not found

---

#### `bulk_categorize_tags(categorizations: List[Tuple[str, str]]) -> Dict`

Categorize multiple tags at once.

**Parameters**:
- `categorizations`: List of `(tag_name, category)` tuples

**Returns**:
```python
{
    'success_count': 150,
    'error_count': 5,
    'errors': ['tag1: Invalid category', ...]
}
```

---

#### `suggest_category_for_tag(tag_name: str) -> Optional[str]`

Suggest a category based on naming patterns and co-occurrence statistics.

**Algorithm**:
1. Check pattern-based rules (e.g., `artist:`, `by_`, parentheses)
2. Analyze co-occurrence with already categorized tags
3. Return most likely category or default to 'general'

---

#### `get_tag_details(tag_name: str) -> Dict`

Get detailed information about a tag including suggestions.

**Returns**:
```python
{
    'name': 'sitting',
    'category': 'general',
    'usage_count': 1250,
    'suggested_category': '10_Pose',
    'cooccurring_tags': [
        {'name': 'chair', 'category': 'general', 'cooccurrence': 450}
    ]
}
```

---

#### `export_tag_categorizations(categorized_only: bool = False) -> Dict`

Export tag categorizations to JSON-serializable format.

**Returns**:
```python
{
    'export_version': '1.0',
    'export_date': '2024-01-15T12:00:00.000000',
    'tag_count': 3200,
    'categorized_only': True,
    'categories': TAG_CATEGORIES,
    'tags': {
        'sitting': '10_Pose',
        'running': '09_Action',
        # ...
    }
}
```

---

#### `import_tag_categorizations(data: Dict, mode: str = 'merge') -> Dict`

Import tag categorizations from exported data.

**Modes**:
- `merge`: Keep existing, only add new
- `overwrite`: Replace all categorizations
- `update`: Only update already-categorized tags

**Returns**:
```python
{
    'total': 500,
    'updated': 450,
    'skipped': 50,
    'errors': []
}
```

---

### Related Tools

- **Web UI**: `/tag_categorize` - Interactive categorization interface with keyboard shortcuts
- **LLM Script**: `scripts/llm_auto_categorize_tags.py` - Automated categorization using local LLM
- **API Endpoints**: See [Extended Categories Documentation](EXTENDED_CATEGORIES.md#api-endpoints)

---

### See Also

- **[Extended Categories Documentation](EXTENDED_CATEGORIES.md)** - Complete guide to the 22-category system
- **[Database Schema](DATABASE.md#tags)** - Tags table with `extended_category` column

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [DATABASE.md](DATABASE.md) - Database schema
- [REPOSITORIES.md](REPOSITORIES.md) - Data access layer
- [ROUTERS.md](ROUTERS.md) - Web and API routes
- [DATA_FLOW.md](DATA_FLOW.md) - End-to-end data flows
- [EXTENDED_CATEGORIES.md](EXTENDED_CATEGORIES.md) - Extended tag categorization system

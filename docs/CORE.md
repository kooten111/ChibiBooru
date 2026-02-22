# Core Infrastructure Documentation

## Table of Contents
- [Overview](#overview)
- [Cache Manager](#cache-manager)
- [Cache Manager](#cache-manager)
- [Tag ID Cache](#tag-id-cache)
- [Cache Events](#cache-events)
- [Utilities](#utilities)

---

## Overview

The Core infrastructure provides cross-cutting functionality used throughout the application:
- **Cache Manager**: In-memory caching with thread safety and tag ID optimization
- **Tag ID Cache**: Bidirectional tag name ↔ integer ID mapping for memory efficiency
- **Cache Events**: Event-driven cache invalidation
- **Utilities**: File operations, deduplication, API responses, decorators, and more

---

## Cache Manager

**File**: `core/cache_manager.py`

### Purpose
Manages in-memory caches for frequently accessed data to reduce database queries.

### Global Caches

```python
tag_counts = {}          # Dict[int, int]: tag ID → usage count (integer IDs for memory efficiency)
image_data = []          # List[Dict]: all images with tag_ids as array('i') of integer IDs
post_id_to_md5 = {}     # Dict[int, str]: post ID → MD5 hash
data_lock = threading.RLock()  # Thread-safe access (reentrant)
_loading_in_progress = False   # Flag to prevent concurrent loads
_load_executor = ThreadPoolExecutor(max_workers=1)  # Background loading
```

### Functions

#### `load_data_from_db(verbose=True) -> bool`

Load or reload data from database into in-memory caches (synchronous).

**Process**:
1. Trigger cache invalidation event
2. Load tag counts (optimized query with DISTINCT)
3. Load image data with tags
4. Build cross-source post_id index with batched JSON parsing
5. Use temp storage to minimize lock time
6. Atomically update global caches

**Optimizations** (New):
- Batched JSON parsing (1000 entries at a time) with progress tracking
- Temp storage built outside lock, then atomically swapped in
- Prevents concurrent loads with `_loading_in_progress` flag
- Shows progress for large collections

**Returns**: `True` on success, `False` if tables don't exist

**Side Effects**:
- Updates all global caches
- Triggers cache invalidation callbacks
- Thread-safe with `data_lock` (RLock for reentrant calls)

**Called from**: `app.py` during startup, system operations

**Output**:
```
Loading data from database...
Building cross-source post_id index...
  Processed 1000/5000 metadata entries...
  Processed 2000/5000 metadata entries...
  ...
Loaded 1000 images, 5000 unique tags, 8000 cross-source post_ids.
```

---

#### `load_data_from_db_async() -> Future`

Load data asynchronously in background thread to avoid blocking the main thread.

**Process**:
1. Check if load already in progress (returns None if so)
2. Submit `_load_data_from_db_impl()` to executor
3. Return Future object for optional waiting

**Returns**: `Future` object or `None` if load already in progress

**Use Cases**:
- After tag categorization changes
- After rating updates
- After bulk operations
- Any time UI responsiveness matters

**Example**:
```python
from core.cache_manager import load_data_from_db_async

# Non-blocking cache reload
future = load_data_from_db_async()
if future:
    # Optional: wait for completion if needed
    future.result()  # Blocks until done
```

**Benefits**:
- UI remains responsive during reload
- No blocking of API responses
- Safe concurrent access (prevents multiple simultaneous loads)
- Automatic error handling

---

#### `reload_single_image(filepath: str)`

Reload a single image's data without full reload.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative image path |

**Use Case**: After updating tags for one image

**Side Effects**:
- Updates specific entry in `image_data`
- Thread-safe operation

---

#### `remove_image_from_cache(filepath: str)`

Remove a single image from in-memory cache.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative image path |

**Use Case**: After deleting an image

**Side Effects**:
- Removes from `image_data` list
- Thread-safe operation

---

#### `get_image_data() -> List[Dict]`

Get all image data from in-memory cache.

**Returns**: Copy of `image_data` list

**Thread-safe**: Uses `data_lock`

---

#### `get_tag_counts() -> Dict[str, int]`

Get tag counts from in-memory cache.

**Returns**: Copy of `tag_counts` dict

**Thread-safe**: Uses `data_lock`

---

#### `is_loading() -> bool`

Check if cache is currently being loaded.

**Returns**: `True` if load in progress, `False` otherwise

**Use Case**: UI status indicators, preventing redundant operations

**Example**:
```python
from core.cache_manager import is_loading

if is_loading():
    return {"status": "Cache is reloading, please wait..."}
```

---

#### `reload_tag_counts()`

Reload just tag counts without reloading all image data.

**Query**: `SELECT name, COUNT(DISTINCT image_id) FROM tags JOIN image_tags ...`

**Use Case**: After tag modifications

**Side Effects**:
- Updates `tag_counts` cache
- Thread-safe operation

---

#### `trigger_cache_reload_async()`

Trigger an async cache reload from any context.

**Use Case**: When cache needs refreshing from non-async code paths.

---

#### `get_image_tags_as_string(filepath: str) -> str`

Get space-separated tag string for an image from cache.

---

#### `get_image_tags_as_set(filepath: str) -> set`

Get tag names as a set for an image from cache.

---

#### `get_image_tags_as_ids(filepath: str) -> array`

Get tag IDs as an int32 array for an image from cache.

---

#### `get_image_tag_count(filepath: str) -> int`

Get the number of tags for an image from cache.

---

#### `invalidate_image_cache(filepath: str)`

Invalidate cached data for a specific image.

---

#### `invalidate_tag_cache()`

Invalidate all tag-related caches.

---

#### `invalidate_all_caches()`

Invalidate all caches (images, tags, similarity, etc.).

---

## Tag ID Cache

**File**: `core/tag_id_cache.py`

### Purpose
Provides bidirectional mapping between tag names (strings) and integer IDs for memory efficiency. All tag storage in ChibiBooru uses int32 IDs instead of strings, saving ~200-500 MB of RAM for large collections.

### Class: `TagIDCache`

#### `get_id(tag_name: str) -> int`
Convert a tag name to its integer ID.

#### `get_name(tag_id: int) -> str`
Convert an integer ID to its tag name.

#### `get_ids(tag_names: list) -> array('i')`
Convert a list of tag names to an int32 array of IDs.

#### `get_names(tag_ids: array) -> list`
Convert an array of IDs to a list of tag name strings.

#### `get_ids_from_string(tags_string: str) -> array('i')`
Convert a space-separated tag string to an int32 array of IDs.

#### `get_string_from_ids(tag_ids: array) -> str`
Convert an int32 array of IDs to a space-separated tag string.

#### `reload()`
Refresh the bidirectional mappings from the database.

---

### Thread Safety

All cache operations use `data_lock` (RLock) for thread safety:

```python
with data_lock:
    # Safe to access/modify caches
    tag_counts[tag_name] = count
```

**Why Thread Safety Matters**:
- Multiple request threads access caches simultaneously
- Monitor service runs in background thread
- Cache updates must be atomic

**RLock (Reentrant Lock)**:
- Allows the same thread to acquire the lock multiple times
- Necessary for functions that call other cache functions
- Prevents deadlocks in complex call chains

**Concurrency Protection**:
- `_loading_in_progress` flag prevents concurrent cache loads
- Only one load operation at a time (synchronous or async)
- Background executor ensures serial processing

---

### Cache Invalidation Strategy

**When to Invalidate**:
- After adding/removing images
- After modifying tags
- After database rebuild
- After source priority changes

**How to Invalidate**:
```python
from events.cache_events import trigger_cache_invalidation

trigger_cache_invalidation()  # Notifies all registered callbacks
```

---

## Cache Events

**File**: `events/cache_events.py`

### Purpose
Event-driven system for coordinating cache invalidation across modules.

### Architecture

**Problem**: Direct dependencies cause circular imports
- `models.py` needs to invalidate `query_service.py` caches
- `query_service.py` imports from `models.py`
- Circular dependency!

**Solution**: Event-based decoupling
- `models.py` triggers generic invalidation event
- `query_service.py` registers callback for event
- No direct dependency between modules

### Global State

```python
_cache_invalidation_callbacks = []  # List of registered callbacks
```

### Functions

#### `register_cache_invalidation_callback(callback: Callable)`

Register a function to be called when caches should be invalidated.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `callback` | `Callable` | Function with no parameters |

**Example**:
```python
# In query_service.py
def invalidate_similarity_cache():
    global _tag_category_cache, _similarity_context_cache
    _tag_category_cache = None
    _similarity_context_cache = None

register_cache_invalidation_callback(invalidate_similarity_cache)
```

---

#### `trigger_cache_invalidation()`

Trigger all registered cache invalidation callbacks.

**Process**:
1. Iterate through all registered callbacks
2. Call each callback
3. Log errors but don't stop on failure

**Called from**:
- `cache_manager.load_data_from_db()`
- After database modifications
- After metadata changes

**Example**:
```python
# After modifying data
from events.cache_events import trigger_cache_invalidation

update_database(...)
trigger_cache_invalidation()  # Notify all caches
```

---

### Registered Callbacks

Current callbacks:
- `query_service.invalidate_similarity_cache()` - Clears similarity calculation caches

**To Add Your Own**:
```python
# In your module
from events.cache_events import register_cache_invalidation_callback

_my_cache = {}

def invalidate_my_cache():
    global _my_cache
    _my_cache = {}

# Register during module initialization
register_cache_invalidation_callback(invalidate_my_cache)
```

---

## Utilities

### Deduplication

**File**: `utils/deduplication.py`

#### `scan_and_remove_duplicates() -> Dict`

Find and remove duplicate images based on MD5 hash.

**Process**:
1. Scan all images in database
2. Group by MD5 hash
3. For each duplicate group:
   - Keep first image (alphabetically)
   - Delete others

**Returns**:
```python
{
    "duplicates_found": 10,
    "duplicates_removed": 9,
    "space_saved_mb": 125.5
}
```

**Side Effects**:
- Deletes duplicate files from disk
- Deletes database entries
- Updates cache

---

#### `remove_duplicate(md5: str, keep_filepath: str) -> bool`

Remove duplicate image while keeping one copy.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `md5` | `str` | MD5 hash |
| `keep_filepath` | `str` | Filepath to keep |

**Returns**: `True` on success

---

### File Utilities

**File**: `utils/file_utils.py`

#### `get_thumbnail_path(image_path: str) -> str`

Get thumbnail path for an image.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `image_path` | `str` | Image path (e.g., "images/folder/img.jpg") |

**Returns**: `"thumbnails/folder/img.webp"`

**Format**: Changes extension to `.webp`, changes `images/` to `thumbnails/`

---

#### `get_bucketed_path(filename: str) -> str`

Generate bucketed directory path for file organization.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filename` | `str` | Original filename |

**Returns**: Bucketed path (e.g., `"ab/cd/filename.jpg"`)

**Bucketing Strategy**: Uses first 4 characters of MD5 hash

**Example**:
```python
# MD5: "abcd1234..."
get_bucketed_path("image.jpg")  # Returns "ab/cd/image.jpg"
```

**Purpose**: Distribute files across directories to avoid file system limits

---

#### `get_file_md5(filepath: str) -> str`

Calculate MD5 hash of a file.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Path to file |

**Returns**: Hexadecimal MD5 string

---

#### `sanitize_filename_for_fs(filename: str) -> str`

Sanitize filename for safe storage on the filesystem.

**Process**:
1. Remove/replace unsafe characters
2. Limit length
3. Ensure safe for filesystem use

**Returns**: Safe filename string

---

### Additional Utility Modules

The `utils/` directory contains these additional modules:

| File | Purpose |
|------|---------|
| `api_responses.py` | Standardized JSON response helpers (`success_response`, `error_response`) |
| `background_task_helpers.py` | Helpers for async background task management |
| `decorators.py` | Shared decorators (`@api_handler`, `@require_secret`) |
| `gpu_detection.py` | Hardware detection for ML backends (CUDA, XPU, MPS, CPU) |
| `logging_config.py` | Centralized logging configuration |
| `memory_utils.py` | Memory monitoring and optimization utilities |
| `request_helpers.py` | Request validation helpers (`require_json_body()`) |
| `rrdbnet_arch.py` | Standalone PyTorch RRDBNet architecture for RealESRGAN upscaling |
| `tag_db.py` | Tag database utilities (imports from danbooru/e621 merged CSV) |
| `tag_extraction.py` | Tag extraction and normalization from various source formats |
| `validation.py` | Input validation utilities |
| `video_utils.py` | Video file processing and metadata extraction |

---

## Performance Considerations

### Cache Size

**Tag Counts**:
- ~5,000 unique tags = ~200 KB RAM
- Negligible memory footprint

**Image Data**:
- 10,000 images × 100 bytes = ~1 MB RAM
- Scales linearly with image count
- Optimized for collections up to 100k images

**Post ID Mapping**:
- Cross-source mapping
- ~8,000 entries = ~256 KB RAM

**Total**: ~2 MB for typical collection (10k images)

---

### Lock Contention

**Read Operations**: Fast, minimal lock time
**Write Operations**: Rare, acceptable lock time with new optimizations

**Optimizations** (New):
- Temp storage built outside lock, minimizing critical section
- Batched operations reduce lock acquisition frequency
- RLock allows reentrant calls without deadlocks
- Async loading prevents UI blocking

**Performance Impact**:
- Lock time reduced from ~5-10 seconds to ~0.5-1 second for large collections
- UI remains responsive during reloads
- Background operations don't block user interactions

---

### Cache Hit Rate

**Expected**:
- Tag counts: 100% hit rate (always cached)
- Image details: ~95% hit rate (LRU cache in repositories)
- Similarity weights: ~90% hit rate (LRU cache in query_service)

---

### Async Loading Performance

**Before** (synchronous loading):
- UI freezes during cache reload (5-10 seconds for large collections)
- API requests timeout during reload
- User must wait for completion

**After** (async loading):
- UI remains responsive
- API continues serving requests
- Background loading doesn't block operations
- Progress tracking for large collections

**When to Use Async**:
- Tag categorization updates (many images affected)
- Rating changes (bulk operations)
- System rebuilds (large-scale operations)
- Any user-initiated operation where responsiveness matters

**When to Use Sync**:
- Application startup (acceptable to wait)
- Critical operations requiring immediate consistency
- Small collections (<1000 images)

---

## Best Practices

### When to Reload Cache

**Full Reload** (`load_data_from_db()`):
- Application startup
- Database rebuild
- Major data changes

**Partial Reload**:
- Single image: `reload_single_image(filepath)`
- Tag counts only: `reload_tag_counts()`

**Cache Removal**:
- After deletion: `remove_image_from_cache(filepath)`

### Error Handling

```python
try:
    with data_lock:
        # Cache operation
        pass
except Exception as e:
    print(f"Cache error: {e}")
    # Fallback to database query
```

### Monitoring

Check cache size:
```python
print(f"Images in cache: {len(get_image_data())}")
print(f"Unique tags: {len(get_tag_counts())}")
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SERVICES.md](SERVICES.md) - Services using caches
- [DATABASE.md](DATABASE.md) - Database schema

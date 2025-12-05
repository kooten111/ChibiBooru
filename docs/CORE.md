# Core Infrastructure Documentation

## Table of Contents
- [Overview](#overview)
- [Cache Manager](#cache-manager)
- [Cache Events](#cache-events)
- [Utilities](#utilities)

---

## Overview

The Core infrastructure provides cross-cutting functionality used throughout the application:
- **Cache Manager**: In-memory caching with thread safety
- **Cache Events**: Event-driven cache invalidation
- **Utilities**: File operations, deduplication, helpers

---

## Cache Manager

**File**: `core/cache_manager.py`

### Purpose
Manages in-memory caches for frequently accessed data to reduce database queries.

### Global Caches

```python
tag_counts = {}          # Dict[str, int]: tag name → usage count
image_data = []          # List[Dict]: all images with tags
post_id_to_md5 = {}     # Dict[int, str]: post ID → MD5 hash
data_lock = threading.Lock()  # Thread-safe access
```

### Functions

#### `load_data_from_db() -> bool`

Load or reload data from database into in-memory caches.

**Process**:
1. Trigger cache invalidation event
2. Load tag counts
3. Load image data with tags
4. Build cross-source post_id index

**Returns**: `True` on success, `False` if tables don't exist

**Side Effects**:
- Updates all global caches
- Triggers cache invalidation callbacks
- Thread-safe with `data_lock`

**Called from**: `app.py` during startup

**Output**:
```
Loading data from database...
Building cross-source post_id index...
Loaded 1000 images, 5000 unique tags, 8000 cross-source post_ids.
```

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

#### `reload_tag_counts()`

Reload just tag counts without reloading all image data.

**Query**: `SELECT name, COUNT(DISTINCT image_id) FROM tags JOIN image_tags ...`

**Use Case**: After tag modifications

**Side Effects**:
- Updates `tag_counts` cache
- Thread-safe operation

---

### Thread Safety

All cache operations use `data_lock` for thread safety:

```python
with data_lock:
    # Safe to access/modify caches
    tag_counts[tag_name] = count
```

**Why Thread Safety Matters**:
- Multiple request threads access caches simultaneously
- Monitor service runs in background thread
- Cache updates must be atomic

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
_invalidation_callbacks = []  # List of registered callbacks
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

#### `ensure_directory_exists(filepath: str)`

Create directory structure if it doesn't exist.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Full file path |

**Side Effects**: Creates all parent directories

---

#### `safe_filename(filename: str) -> str`

Sanitize filename for safe storage.

**Process**:
1. Remove/replace unsafe characters
2. Limit length
3. Ensure uniqueness if needed

**Returns**: Safe filename string

---

## Performance Considerations

### Cache Size

**Tag Counts**:
- ~5,000 unique tags = ~200 KB RAM
- Negligible memory footprint

**Image Data**:
- 10,000 images × 100 bytes = ~1 MB RAM
- Scales linearly with image count
- Consider pagination for very large collections (100k+ images)

**Post ID Mapping**:
- Cross-source mapping
- ~8,000 entries = ~256 KB RAM

**Total**: ~2 MB for typical collection (10k images)

---

### Lock Contention

**Read Operations**: Fast, minimal lock time
**Write Operations**: Rare, acceptable lock time

**Optimization**: Read operations don't modify cache, only acquire lock briefly

---

### Cache Hit Rate

**Expected**:
- Tag counts: 100% hit rate (always cached)
- Image details: ~95% hit rate (LRU cache in repositories)
- Similarity weights: ~90% hit rate (LRU cache in query_service)

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

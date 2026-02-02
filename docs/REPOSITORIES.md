# Repositories Layer Documentation

## Table of Contents
- [Overview](#overview)
- [Repository Index](#repository-index)
- [Data Access Repository](#data-access-repository)
- [Tag Repository](#tag-repository)
- [Pool Repository](#pool-repository)
- [Rating Repository](#rating-repository)
- [Delta Tracker Repository](#delta-tracker-repository)

---

## Overview

The Repositories layer provides an abstraction over database operations. It handles:
- Pure database CRUD operations
- SQL query construction
- Data validation and normalization
- Caching strategies
- Transaction management

### Design Principles
- **Separation of Concerns**: Pure data access, no business logic
- **Single Responsibility**: Each repository handles a specific domain
- **Caching**: Uses `@lru_cache` for frequently accessed data
- **Error Handling**: Graceful handling of database errors

---

## Repository Index

| Repository | File | Purpose |
|------------|------|---------|
| Data Access | `data_access.py` | Core CRUD operations and statistics |
| Tag Repository | `tag_repository.py` | Tag operations and categorization |
| Pool Repository | `pool_repository.py` | Pool management |
| Rating Repository | `rating_repository.py` | Rating model data access |
| Favourites Repository | `favourites_repository.py` | User favourite management |
| Tagger Predictions | `tagger_predictions_repository.py` | AI tagger raw data access |
| Delta Tracker | `delta_tracker.py` | Track manual tag modifications |

---

## Data Access Repository

**File**: `repositories/data_access.py`

### Purpose
Core database operations for images, statistics, and basic queries.

### Statistics Functions

#### `get_image_count() -> int`

Get total count of images in the database.

**Returns**: Integer count

**Query**: `SELECT COUNT(id) FROM images`

---

#### `get_avg_tags_per_image() -> float`

Calculate average number of tags per image.

**Returns**: Float (rounded to 1 decimal)

**Query**: Aggregates tag counts per image

---

#### `get_source_breakdown() -> Dict[str, int]`

Get count of images per metadata source.

**Returns**:
```python
{
    "danbooru": 500,
    "e621": 300,
    "local_tagger": 200
}
```

---

#### `get_category_counts() -> Dict[str, int]`

Get count of tags per category.

**Returns**:
```python
{
    "character": 1000,
    "copyright": 500,
    "general": 10000,
    "meta": 200
}
```

---

#### `get_saucenao_lookup_count() -> int`

Get count of images that were looked up on SauceNAO.

**Returns**: Integer count

---

### Image Queries

#### `md5_exists(md5: str) -> bool`

Check if an MD5 hash already exists.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `md5` | `str` | MD5 hash to check |

**Returns**: `True` if exists, `False` otherwise

**Use Case**: Duplicate detection before processing new image

---

#### `get_all_images_with_tags() -> List[Dict]`

Get all images with their concatenated tags.

**Returns**:
```python
[
    {
        "filepath": "folder/image.jpg",
        "tags": "tag1 tag2 tag3"
    },
    ...
]
```

**Note**: Results are in random order

---

#### `get_all_filepaths() -> Set[str]`

Returns a set of all filepaths in the database.

**Returns**: `Set[str]` of relative filepaths

**Use Case**: Finding orphaned database records

---

#### `@lru_cache(maxsize=10000)`<br>`get_image_details(filepath: str) -> Optional[Dict]`

Get detailed information about a specific image.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative filepath |

**Returns**:
```python
{
    "id": 1,
    "filepath": "folder/image.jpg",
    "md5": "abc123...",
    "post_id": 12345,
    "parent_id": None,
    "has_children": False,
    "active_source": "danbooru",
    "tags_character": "hatsune_miku",
    "tags_copyright": "vocaloid",
    "tags_general": "1girl blue_hair",
    "all_tags": "hatsune_miku vocaloid 1girl blue_hair",
    "raw_metadata": {
        "sources": {
            "danbooru": {...}
        }
    }
}
```

**Caching**: Results cached for performance (invalidate with `get_image_details.cache_clear()`)

**Side Effects**: None (read-only)

---

#### `delete_image(filepath: str) -> bool`

Delete an image and all related data.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative filepath |

**Returns**: `True` if deleted, `False` on error

**Deletes**:
- Image record from `images` table
- Related tags from `image_tags` (CASCADE)
- Raw metadata from `raw_metadata` (CASCADE)
- Image sources from `image_sources` (CASCADE)

**Side Effects**:
- Database write
- Foreign key cascades trigger
- Does NOT delete physical file

---

### Relationship Queries

#### `get_related_images(post_id: int, parent_id: int, post_id_to_md5_mapping: Dict) -> List[Dict]`

Find parent and child images using optimized indexed lookups.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `post_id` | `int` | Current image's post ID |
| `parent_id` | `int` | Parent's post ID |
| `post_id_to_md5_mapping` | `Dict` | Cross-source mapping |

**Returns**:
```python
[
    {
        "path": "images/parent.jpg",
        "type": "parent"
    },
    {
        "path": "images/child1.jpg",
        "type": "child"
    },
    {
        "path": "images/child2.jpg",
        "type": "child"
    }
]
```

**Performance**: Uses indexed columns (`parent_id`, `post_id`) for fast lookups

**Fallback**: Uses MD5 mapping for cross-source relationships

---

### Search Functions

#### `search_images_by_tags(tags: List[str], negative_tags: List[str] = []) -> List[str]`

Search images by tag presence.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `tags` | `List[str]` | Tags that must be present (AND) |
| `negative_tags` | `List[str]` | Tags to exclude |

**Returns**: List of filepaths matching criteria

**Query Strategy**: Uses indexed `image_tags` joins for performance

---

#### `search_images_by_source(source_name: str) -> List[str]`

Find images from a specific metadata source.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `source_name` | `str` | Source name (e.g., "danbooru") |

**Returns**: List of filepaths

---

#### `search_images_by_multiple_sources(source_names: List[str]) -> List[str]`

Find images that have metadata from multiple sources.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `source_names` | `List[str]` | List of source names |

**Returns**: List of filepaths with ALL specified sources

---

#### `search_images_by_relationship(relationship_type: str) -> List[str]`

Find images with specific relationships.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `relationship_type` | `str` | "parent", "child", or "relationship" |

**Returns**: List of filepaths

**Relationship Types**:
- `"parent"`: Images with a parent
- `"child"`: Images with children
- `"relationship"`: Images with parent OR children

---

#### `add_image_with_metadata(filepath: str, md5: str, metadata: Dict, tags: Dict) -> bool`

Add a new image with full metadata.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative filepath |
| `md5` | `str` | MD5 hash |
| `metadata` | `Dict` | Raw JSON metadata |
| `tags` | `Dict` | Categorized tags |

**Process**:
1. Insert into `images` table
2. Insert into `raw_metadata` table
3. Create tag entries
4. Link tags to image
5. Update denormalized tag columns
6. Link image to sources

**Returns**: `True` on success, `False` on error

**Side Effects**: Multiple database writes in transaction

---

## Tag Repository

**File**: `repositories/tag_repository.py`

### Purpose
Handles all tag-related operations including counting, categorization, and normalization.

### Tag Counting

#### `get_tag_counts() -> Dict[str, int]`

Get tag counts from in-memory cache.

**Returns**:
```python
{
    "hatsune_miku": 500,
    "1girl": 800,
    "blue_hair": 600
}
```

**Source**: `cache_manager.tag_counts`

---

#### `reload_tag_counts()`

Reload tag counts from database.

**Side Effects**: Updates `cache_manager.tag_counts`

**When to call**: After tag modifications

---

#### `get_all_tags_sorted() -> List[Dict]`

Get all tags with counts, sorted alphabetically.

**Returns**:
```python
[
    {
        "name": "1girl",
        "category": "general",
        "count": 800
    },
    ...
]
```

---

#### `search_tags(query: str = None, category: str = None, limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]`

Search tags with pagination and filtering.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `query` | `str` | Partial match search |
| `category` | `str` | Category filter or "all" |
| `limit` | `int` | Max results (default 100) |
| `offset` | `int` | Pagination offset |

**Returns**: `(tags, total_count)` tuple

**Example**:
```python
tags, total = search_tags(query="miku", category="character", limit=20, offset=0)
```

---

### Tag Normalization

#### `normalize_tag_name(tag_name: str) -> str`

Normalize tag names (rating tag conversion).

**Conversions**:
- `rating_explicit` → `rating:explicit`
- `rating_general` → `rating:general`
- `rating_questionable` → `rating:questionable`
- `rating_sensitive` → `rating:sensitive`

**Returns**: Normalized tag name

---

#### `get_tag_category(tag_name: str) -> Optional[str]`

Determine category for a tag based on name.

**Rules**:
- Tags starting with `rating:` → `"meta"`
- Other tags → `None` (caller decides)

---

### Tag Categorization

#### `recategorize_misplaced_tags()`

Move tags to correct categories based on known categorization.

**Process**:
1. Build lookup of known categorized tags
2. Normalize rating tags
3. Find misplaced tags
4. Move to correct category
5. Update all image_tags relationships

**Side Effects**: Database writes, updates cache

---

#### `rebuild_categorized_tags_from_relations() -> int`

Rebuild denormalized tag columns from image_tags.

**Returns**: Count of images updated

**Process**:
1. For each image, collect tags by category
2. Update `tags_character`, `tags_copyright`, etc.
3. Update FTS index (via triggers)

**When to call**: After tag structure changes

---

### Tag Updates

#### `update_image_tags(filepath: str, new_tags_str: str, record_deltas: bool = False) -> bool`

Update tags for an image (plain format).

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative filepath |
| `new_tags_str` | `str` | Space-separated tags |
| `record_deltas` | `bool` | Record changes for preservation |

**Returns**: `True` on success

**Side Effects**:
- Updates `image_tags` relationships
- Updates denormalized columns
- Optionally records deltas

---

#### `update_image_tags_categorized(filepath: str, categorized_tags: Dict, record_deltas: bool = False) -> bool`

Update tags for an image (categorized format).

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Relative filepath |
| `categorized_tags` | `Dict` | Tags grouped by category |
| `record_deltas` | `bool` | Record changes |

**Example**:
```python
categorized_tags = {
    "character": ["hatsune_miku"],
    "copyright": ["vocaloid"],
    "general": ["1girl", "blue_hair"]
}
update_image_tags_categorized("folder/img.jpg", categorized_tags, record_deltas=True)
```

---

### Tag Implications

#### `add_implication(source_tag: str, implied_tag: str, inference_type: str = "manual", confidence: float = 1.0) -> bool`

Create a tag implication rule.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `source_tag` | `str` | Source tag name |
| `implied_tag` | `str` | Implied tag name |
| `inference_type` | `str` | "manual", "pattern", "statistical" |
| `confidence` | `float` | 0.0 to 1.0 |

**Returns**: `True` on success

---

#### `get_implications_for_tag(tag_name: str) -> List[str]`

Get all tags implied by a given tag.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `tag_name` | `str` | Source tag name |

**Returns**: List of implied tag names

---

#### `apply_implications_for_image(image_id: int)`

Apply all active implications for an image.

**Process**:
1. Get current tags
2. Find active implications
3. Add implied tags (if not present)
4. Handle implication chains

**Side Effects**: May add tags to image

---

## Pool Repository

**File**: `repositories/pool_repository.py`

### Purpose
Manage pools (collections of images with custom ordering).

### Functions

#### `create_pool(name: str, description: str = "") -> int`

Create a new pool.

**Returns**: Pool ID

**Raises**: Error if name already exists

---

#### `get_all_pools() -> List[Dict]`

Get all pools with image counts.

**Returns**:
```python
[
    {
        "id": 1,
        "name": "My Collection",
        "description": "...",
        "image_count": 25
    },
    ...
]
```

---

#### `get_pool_details(pool_id: int) -> Optional[Dict]`

Get pool details with ordered images.

**Returns**:
```python
{
    "id": 1,
    "name": "My Collection",
    "description": "...",
    "images": [
        {"filepath": "...", "sort_order": 1},
        {"filepath": "...", "sort_order": 2}
    ]
}
```

---

#### `add_image_to_pool(pool_id: int, image_filepath: str, sort_order: int = None) -> bool`

Add image to pool.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `pool_id` | `int` | Pool ID |
| `image_filepath` | `str` | Image filepath |
| `sort_order` | `int` | Custom order (auto if None) |

---

#### `remove_image_from_pool(pool_id: int, image_filepath: str) -> bool`

Remove image from pool.

---

#### `delete_pool(pool_id: int) -> bool`

Delete pool and all associations.

**Side Effects**: CASCADE deletes pool_images entries

---

#### `update_pool(pool_id: int, name: str = None, description: str = None) -> bool`

Update pool metadata.

---

#### `reorder_pool_images(pool_id: int, ordered_filepaths: List[str]) -> bool`

Reorder images in pool.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `pool_id` | `int` | Pool ID |
| `ordered_filepaths` | `List[str]` | Filepaths in desired order |

**Process**: Assigns sort_order 1, 2, 3, ...

---

#### `search_pools(query: str) -> List[Dict]`

Search pools by name.

---

#### `get_pools_for_image(filepath: str) -> List[Dict]`

Get all pools containing an image.

---

#### `search_images_by_pool(pool_name: str) -> List[str]`

Get all images in a pool.

---

## Rating Repository

**File**: `repositories/rating_repository.py`

### Purpose
Data access for AI rating inference model.

### Functions

#### `store_tag_weights(weights: Dict)`

Store tag weights for rating inference.

**Parameters**:
```python
weights = {
    ("tag_name", "rating"): {
        "weight": 0.85,
        "sample_count": 100
    }
}
```

---

#### `store_tag_pair_weights(pair_weights: Dict)`

Store tag pair weights.

**Parameters**:
```python
pair_weights = {
    ("tag1", "tag2", "rating"): {
        "weight": 1.2,
        "co_occurrence_count": 50
    }
}
```

---

#### `get_tag_weight(tag_name: str, rating: str) -> Optional[float]`

Get weight for tag+rating combination.

---

#### `get_all_tag_weights() -> Dict`

Get all tag weights for inference.

---

#### `get_inference_config() -> Dict`

Get rating inference configuration.

**Returns**:
```python
{
    "threshold_general": 0.5,
    "threshold_sensitive": 0.6,
    "threshold_questionable": 0.7,
    "threshold_explicit": 0.8,
    "min_confidence": 0.4,
    ...
}
```

---

#### `update_inference_config(key: str, value: float)`

Update configuration parameter.

---

## Delta Tracker Repository

**File**: `repositories/delta_tracker.py`

### Purpose
Track manual tag modifications to preserve across database rebuilds.

### Concepts

**Tag Deltas**: Record of user-made tag changes
- `add`: User added a tag
- `remove`: User removed a tag

**Delta Preservation**: When database is rebuilt:
1. Original tags restored from metadata sources
2. Deltas applied on top
3. User's manual edits preserved

### Functions

#### `record_tag_delta(image_md5: str, tag_name: str, tag_category: str, operation: str)`

Record a tag modification.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `image_md5` | `str` | Image MD5 hash |
| `tag_name` | `str` | Tag name |
| `tag_category` | `str` | Tag category |
| `operation` | `str` | "add" or "remove" |

**Side Effects**: Inserts into `tag_deltas` table

---

## Favourites Repository

**File**: `repositories/favourites_repository.py`

### Purpose
Manage user's favourite images.

### Functions

#### `add_favourite(image_id: int) -> bool`
Add image to favourites.

#### `remove_favourite(image_id: int) -> bool`
Remove image from favourites.

#### `toggle_favourite(image_id: int) -> bool`
Toggle favourite status.

#### `is_favourite(image_id: int) -> bool`
Check if image is favourited.

---

## Tagger Predictions Repository

**File**: `repositories/tagger_predictions_repository.py`

### Purpose
Data access for stored AI tagger predictions.

### Functions

#### `store_predictions(image_id: int, predictions: list, tagger_version: str = None)`
Store batch of predictions for an image.

#### `get_predictions_for_image(image_id: int, min_confidence: float = None)`
Retrieve predictions above threshold.

#### `get_merged_general_tags(image_id: int, existing_general_tags: set, min_confidence: float = None)`
Get tags to be merged into display (excluding already present ones).

#### `compute_tag_deltas(filepath: str, old_tags: Dict, new_tags: Dict) -> List[Dict]`

Compute deltas between old and new tag sets.

**Parameters**:
| Name | Type | Description |
|------|------|-------------|
| `filepath` | `str` | Image filepath |
| `old_tags` | `Dict` | Original categorized tags |
| `new_tags` | `Dict` | New categorized tags |

**Returns**: List of delta operations

**Example**:
```python
[
    {
        "md5": "abc123",
        "tag_name": "new_tag",
        "category": "general",
        "operation": "add"
    },
    {
        "md5": "abc123",
        "tag_name": "old_tag",
        "category": "general",
        "operation": "remove"
    }
]
```

---

#### `apply_tag_deltas()`

Apply all recorded deltas to current images.

**Process**:
1. Load all deltas from database
2. Group by image MD5
3. For each image:
   - Apply "remove" operations
   - Apply "add" operations
4. Update database

**Called**: After `repopulate_from_database()`

**Side Effects**: Modifies `image_tags` relationships

---

#### `clear_deltas_for_image(image_md5: str)`

Clear all deltas for an image.

**Use Case**: When user resets tags to original

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [DATABASE.md](DATABASE.md) - Database schema
- [SERVICES.md](SERVICES.md) - Business logic layer
- [ROUTERS.md](ROUTERS.md) - Web and API routes

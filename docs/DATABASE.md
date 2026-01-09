# Database Documentation

## Table of Contents
- [Overview](#overview)
- [Database Schema](#database-schema)
- [Tables Reference](#tables-reference)
- [Indexes and Performance](#indexes-and-performance)
- [Full-Text Search (FTS5)](#full-text-search-fts5)
- [Triggers](#triggers)
- [Data Relationships](#data-relationships)
- [Database Operations](#database-operations)

## Overview

ChibiBooru uses **SQLite 3** as its embedded database with several performance optimizations:

- **WAL Mode**: Write-Ahead Logging for better concurrency
- **FTS5**: Full-text search on tags and filenames
- **Foreign Keys**: Enforced referential integrity
- **Indexes**: 20+ optimized indexes for common queries
- **Triggers**: Automatic FTS updates on data changes

### Database Files
- **Main Database**: `data/booru.db` - Core application data
- **Rating Model**: `data/rating_model.db` - AI rating inference data (deprecated, moved to main DB)

### Connection Settings
```python
# database/core.py
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")      # Enable referential integrity
conn.execute("PRAGMA journal_mode = WAL")     # Write-Ahead Logging
conn.execute("PRAGMA synchronous = NORMAL")   # Balance safety/performance
conn.execute(f"PRAGMA cache_size = {-DB_CACHE_SIZE_MB * 1024}")  # Configurable cache
conn.execute("PRAGMA page_size = 8192")       # Larger page size for better performance
conn.execute(f"PRAGMA mmap_size = {DB_MMAP_SIZE_MB * 1024 * 1024}")  # Memory-mapped I/O
conn.execute("PRAGMA temp_store = MEMORY")    # Temp tables in memory
conn.execute(f"PRAGMA wal_autocheckpoint = {DB_WAL_AUTOCHECKPOINT}")  # Checkpoint control
conn.row_factory = sqlite3.Row                # Dict-like row access
```

**Performance Optimizations**:
- **check_same_thread=False**: Allow multi-threaded access (safe with proper locking)
- **cache_size**: Configurable page cache (default 64MB, can increase for large databases)
- **page_size**: 8KB pages for better performance with large blobs
- **mmap_size**: Memory-mapped I/O for faster reads (default 256MB)
- **temp_store = MEMORY**: Keep temporary tables in RAM for faster sorts/indexes
- **wal_autocheckpoint**: Control when WAL file is checkpointed (default 1000 frames)

## Database Schema

### Entity-Relationship Diagram (Text)

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   images     │       │  image_tags  │       │     tags     │
│──────────────│       │──────────────│       │──────────────│
│ id (PK)      │◀─────▶│ image_id(FK) │◀─────▶│ id (PK)      │
│ filepath     │       │ tag_id (FK)  │       │ name (UNIQUE)│
│ md5          │       │ source       │       │ category     │
│ post_id      │       └──────────────┘       │ ext_category │
│ parent_id    │                              └──────────────┘
│ has_children │                                      ▲
│ active_source│                                      │
│ ingested_at  │       ┌──────────────┐              │
│ tags_*       │       │tag_implic... │              │
└──────────────┘       │──────────────│              │
       │               │ source_tag_id├──────────────┘
       │               │ implied_tag  │
       │               │ inference_typ│
       │               │ confidence   │
       │               │ status       │
       ▼               │ created_at   │
┌──────────────┐       └──────────────┘
│image_sources │
│──────────────│       ┌──────────────┐
│ image_id(FK) │──────▶│   sources    │
│ source_id(FK)│       │──────────────│
└──────────────┘       │ id (PK)      │
       │               │ name (UNIQUE)│
       │               └──────────────┘
       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│ pool_images  │       │    pools     │       │ raw_metadata │
│──────────────│       │──────────────│       │──────────────│
│ pool_id (FK) │──────▶│ id (PK)      │       │ image_id(FK) │
│ image_id(FK) │       │ name (UNIQUE)│       │ data (JSON)  │
│ sort_order   │       │ description  │       └──────────────┘
└──────────────┘       └──────────────┘
       │
       ▼
┌──────────────┐
│  tag_deltas  │
│──────────────│
│ id (PK)      │
│ image_md5    │
│ tag_name     │
│ tag_category │
│ operation    │
│ timestamp    │
└──────────────┘
```

### Rating Inference Tables

```
┌────────────────────┐       ┌──────────────────────┐
│rating_tag_weights  │       │rating_tag_pair_weights│
│────────────────────│       │──────────────────────│
│ tag_name (PK)      │       │ tag1 (PK)            │
│ rating (PK)        │       │ tag2 (PK)            │
│ weight             │       │ rating (PK)          │
│ sample_count       │       │ weight               │
└────────────────────┘       │ co_occurrence_count  │
                             └──────────────────────┘

┌─────────────────────────┐  ┌───────────────────────┐
│rating_inference_config  │  │rating_model_metadata  │
│─────────────────────────│  │───────────────────────│
│ key (PK)                │  │ key (PK)              │
│ value                   │  │ value                 │
└─────────────────────────┘  │ updated_at            │
                             └───────────────────────┘
```

## Tables Reference

### `images`
**Primary table storing image metadata**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing unique identifier |
| `filepath` | TEXT | NOT NULL, UNIQUE | Path relative to `static/images/` |
| `md5` | TEXT | NOT NULL, UNIQUE | MD5 hash of file contents |
| `post_id` | INTEGER | | Post ID from primary metadata source |
| `parent_id` | INTEGER | | Parent image post ID (for relationships) |
| `has_children` | BOOLEAN | | Whether this image has child variations |
| `saucenao_lookup` | BOOLEAN | | Whether SauceNao was used to find source |
| `active_source` | TEXT | | Currently displayed metadata source |
| `ingested_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When image was added |
| `tags_character` | TEXT | | Space-separated character tags (denormalized) |
| `tags_copyright` | TEXT | | Space-separated copyright tags (denormalized) |
| `tags_artist` | TEXT | | Space-separated artist tags (denormalized) |
| `tags_species` | TEXT | | Space-separated species tags (denormalized) |
| `tags_meta` | TEXT | | Space-separated meta tags (denormalized) |
| `tags_general` | TEXT | | Space-separated general tags (denormalized) |

**Indexes**:
- `idx_images_filepath ON images(filepath)`
- `idx_images_md5 ON images(md5)`
- `idx_images_post_id ON images(post_id)`
- `idx_images_parent_id ON images(parent_id)`
- `idx_images_has_children ON images(has_children)`
- `idx_images_active_source ON images(active_source)`
- `idx_images_relationships ON images(parent_id, has_children)`
- `idx_images_ingested_at ON images(ingested_at DESC)`

**Notes**:
- `filepath` must be unique per image
- `md5` ensures no duplicate images
- Denormalized tag columns (`tags_*`) improve query performance
- `parent_id` and `has_children` enable relationship navigation

---

### `tags`
**Tag definitions with categories**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing unique identifier |
| `name` | TEXT | NOT NULL, UNIQUE | Tag name (normalized, lowercase with underscores) |
| `category` | TEXT | | Primary category (character, copyright, artist, species, general, meta) |
| `extended_category` | TEXT | | Platinum Schema categorization (finer-grained) |

**Indexes**:
- `idx_tags_name ON tags(name)`
- `idx_tags_name_lower ON tags(LOWER(name))`  *(New: case-insensitive search optimization)*
- `idx_tags_category ON tags(category)`
- `idx_tags_extended_category ON tags(extended_category)`

**Categories**:
- `character`: Character names (e.g., `hatsune_miku`)
- `copyright`: Series/franchise (e.g., `vocaloid`)
- `artist`: Artist names (e.g., `wlop`)
- `species`: Animal species (e.g., `cat`, `dragon`)
- `general`: Descriptive tags (e.g., `1girl`, `blue_hair`)
- `meta`: Metadata tags (e.g., `rating:safe`, `highres`)

**Extended Categories** (Platinum Schema):
- More fine-grained categorization for specialized tagging systems
- Optional, used by advanced tagging models

---

### `image_tags`
**Many-to-many relationship between images and tags**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `image_id` | INTEGER | FK → images(id), CASCADE | Reference to image |
| `tag_id` | INTEGER | FK → tags(id), CASCADE | Reference to tag |
| `source` | TEXT | DEFAULT 'original', CHECK | Tag source: 'original', 'user', 'ai_inference' |

**Primary Key**: `(image_id, tag_id)`

**Indexes**:
- `idx_image_tags_image_id ON image_tags(image_id)`
- `idx_image_tags_tag_id ON image_tags(tag_id)`
- `idx_image_tags_source ON image_tags(source)`

**Source Values**:
- `original`: From metadata sources (Danbooru, e621, etc.)
- `user`: Manually added by user
- `ai_inference`: Added by AI (rating inference, local tagger)

---

### `sources`
**Metadata source definitions**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing unique identifier |
| `name` | TEXT | NOT NULL, UNIQUE | Source name |

**Known Sources**:
- `danbooru`: Danbooru imageboard
- `e621`: e621 imageboard
- `gelbooru`: Gelbooru imageboard
- `yandere`: Yandere imageboard
- `pixiv`: Pixiv artwork platform
- `local_tagger`: Local AI tagger (ONNX model)

---

### `image_sources`
**Many-to-many relationship tracking which sources have metadata for each image**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `image_id` | INTEGER | FK → images(id), CASCADE | Reference to image |
| `source_id` | INTEGER | FK → sources(id), CASCADE | Reference to source |

**Primary Key**: `(image_id, source_id)`

**Indexes**:
- `idx_image_sources_image_id ON image_sources(image_id)`
- `idx_image_sources_source_id ON image_sources(source_id)`

---

### `raw_metadata`
**Stores complete JSON metadata from all sources**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `image_id` | INTEGER | PRIMARY KEY, FK → images(id), CASCADE | Reference to image |
| `data` | TEXT | NOT NULL | JSON-encoded metadata from all sources |

**Index**:
- `idx_raw_metadata_image_id ON raw_metadata(image_id)`

**JSON Structure**:
```json
{
  "sources": {
    "danbooru": {
      "id": 12345,
      "tag_string_character": "hatsune_miku",
      "tag_string_copyright": "vocaloid",
      "rating": "s",
      ...
    },
    "e621": {
      "id": 67890,
      "tags": {
        "character": ["hatsune_miku"],
        "species": ["humanoid"]
      },
      ...
    },
    "local_tagger": {
      "tags": {...},
      "confidence": 0.85,
      ...
    }
  }
}
```

---

### `pools`
**Named collections of images**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing unique identifier |
| `name` | TEXT | NOT NULL, UNIQUE | Pool name (must be unique) |
| `description` | TEXT | | Optional description |

**Example pools**: Comic series, image sets, themed collections

---

### `pool_images`
**Images in pools with custom ordering**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `pool_id` | INTEGER | FK → pools(id), CASCADE | Reference to pool |
| `image_id` | INTEGER | FK → images(id), CASCADE | Reference to image |
| `sort_order` | INTEGER | | Custom sort order within pool |

**Primary Key**: `(pool_id, image_id)`

---

### `tag_implications`
**Tag implication rules (A → B)**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `source_tag_id` | INTEGER | FK → tags(id), CASCADE | Source tag (A) |
| `implied_tag_id` | INTEGER | FK → tags(id), CASCADE | Implied tag (B) |
| `inference_type` | TEXT | DEFAULT 'manual' | 'manual', 'pattern', 'statistical' |
| `confidence` | REAL | DEFAULT 1.0 | Confidence score (0.0 - 1.0) |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | When rule was created |
| `status` | TEXT | DEFAULT 'active' | 'active', 'inactive', 'pending' |

**Primary Key**: `(source_tag_id, implied_tag_id)`

**Indexes**:
- `idx_implications_source ON tag_implications(source_tag_id)`
- `idx_implications_status ON tag_implications(status)`

**Inference Types**:
- `manual`: Manually created by user
- `pattern`: Detected from naming patterns (e.g., `character_(costume)_(series)` → `character_(series)`)
- `statistical`: Detected from co-occurrence statistics

**Example**: `hatsune_miku` → `vocaloid`

---

### `tag_deltas`
**Tracks manual tag modifications**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing unique identifier |
| `image_md5` | TEXT | NOT NULL | MD5 hash of image |
| `tag_name` | TEXT | NOT NULL | Tag that was modified |
| `tag_category` | TEXT | | Category of tag |
| `operation` | TEXT | NOT NULL, CHECK | 'add' or 'remove' |
| `timestamp` | DATETIME | DEFAULT CURRENT_TIMESTAMP | When modification occurred |

**Unique Constraint**: `(image_md5, tag_name, operation)`

**Index**:
- `idx_tag_deltas_md5 ON tag_deltas(image_md5)`

**Purpose**: Preserve manual tag edits across database rebuilds

---

### `rating_tag_weights`
**Individual tag weights for rating inference**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `tag_name` | TEXT | PRIMARY KEY | Tag name |
| `rating` | TEXT | PRIMARY KEY | Rating ('general', 'sensitive', 'questionable', 'explicit') |
| `weight` | REAL | NOT NULL | Learned weight for this tag+rating combination |
| `sample_count` | INTEGER | NOT NULL | Number of training samples |

**Primary Key**: `(tag_name, rating)`

**Indexes**:
- `idx_rating_weights_rating ON rating_tag_weights(rating)`
- `idx_rating_weights_weight ON rating_tag_weights(weight DESC)`

---

### `rating_tag_pair_weights`
**Tag pair weights for context-aware rating inference**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `tag1` | TEXT | PRIMARY KEY, CHECK(tag1 < tag2) | First tag (alphabetically) |
| `tag2` | TEXT | PRIMARY KEY | Second tag |
| `rating` | TEXT | PRIMARY KEY | Rating |
| `weight` | REAL | NOT NULL | Learned weight for this pair+rating |
| `co_occurrence_count` | INTEGER | NOT NULL | Times this pair appeared together |

**Primary Key**: `(tag1, tag2, rating)`

**Indexes**:
- `idx_rating_pair_weights_rating ON rating_tag_pair_weights(rating)`
- `idx_rating_pair_weights_weight ON rating_tag_pair_weights(weight DESC)`
- `idx_rating_pair_weights_tags ON rating_tag_pair_weights(tag1, tag2)`

**Note**: `tag1 < tag2` constraint ensures canonical ordering

---

### `rating_inference_config`
**Configuration for rating inference model**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | TEXT | PRIMARY KEY | Configuration key |
| `value` | REAL | NOT NULL | Configuration value |

**Default Config**:
```python
{
    'threshold_general': 0.5,
    'threshold_sensitive': 0.6,
    'threshold_questionable': 0.7,
    'threshold_explicit': 0.8,
    'min_confidence': 0.4,
    'pair_weight_multiplier': 1.5,
    'min_training_samples': 50,
    'min_pair_cooccurrence': 5,
    'min_tag_frequency': 10,
    'max_pair_count': 10000,
}
```

---

### `rating_model_metadata`
**Metadata about rating model training**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | TEXT | PRIMARY KEY | Metadata key |
| `value` | TEXT | NOT NULL | Metadata value |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last update time |

**Example keys**: `last_trained`, `training_samples`, `model_version`

---

## Full-Text Search (FTS5)

### `images_fts`
**Virtual table for full-text search on tags and filenames**

```sql
CREATE VIRTUAL TABLE images_fts USING fts5(
    filepath,
    tags_all,
    tags_character,
    tags_copyright,
    tags_artist,
    tags_species,
    tags_meta,
    tags_general
)
```

**Features**:
- Fast fuzzy search on tags
- Partial tag matching
- Filename search
- Proximity search

**Usage Example**:
```sql
-- Find images with tags containing "blue"
SELECT filepath FROM images_fts WHERE tags_all MATCH 'blue*'

-- Search in specific category
SELECT filepath FROM images_fts WHERE tags_character MATCH 'miku*'

-- Filename search
SELECT filepath FROM images_fts WHERE filepath MATCH 'cat*'
```

---

## Triggers

### FTS Update Triggers
**Automatically maintain FTS index on data changes**

#### `images_fts_insert`
```sql
CREATE TRIGGER images_fts_insert AFTER INSERT ON images
BEGIN
    INSERT INTO images_fts(filepath, tags_all, ...)
    VALUES (new.filepath, COALESCE(new.tags_character, '') || ' ' || ..., ...);
END
```

#### `images_fts_update`
```sql
CREATE TRIGGER images_fts_update AFTER UPDATE ON images
BEGIN
    DELETE FROM images_fts WHERE filepath = old.filepath;
    INSERT INTO images_fts(filepath, tags_all, ...)
    VALUES (new.filepath, COALESCE(new.tags_character, '') || ' ' || ..., ...);
END
```

#### `images_fts_delete`
```sql
CREATE TRIGGER images_fts_delete AFTER DELETE ON images
BEGIN
    DELETE FROM images_fts WHERE filepath = old.filepath;
END
```

---

## Indexes and Performance

### Index Strategy

**Primary Keys**: Automatic indexes on all PKs
**Foreign Keys**: Manual indexes on all FKs for JOIN performance
**Search Columns**: Indexes on frequently queried columns
**Composite Indexes**: For multi-column queries

### Index List

```sql
-- Images table
CREATE INDEX idx_images_filepath ON images(filepath);
CREATE INDEX idx_images_md5 ON images(md5);
CREATE INDEX idx_images_post_id ON images(post_id);
CREATE INDEX idx_images_parent_id ON images(parent_id);
CREATE INDEX idx_images_has_children ON images(has_children);
CREATE INDEX idx_images_active_source ON images(active_source);
CREATE INDEX idx_images_relationships ON images(parent_id, has_children);
CREATE INDEX idx_images_ingested_at ON images(ingested_at DESC);

-- Tags table
CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_tags_category ON tags(category);
CREATE INDEX idx_tags_extended_category ON tags(extended_category);

-- Image_tags table
CREATE INDEX idx_image_tags_image_id ON image_tags(image_id);
CREATE INDEX idx_image_tags_tag_id ON image_tags(tag_id);
CREATE INDEX idx_image_tags_source ON image_tags(source);

-- Image_sources table
CREATE INDEX idx_image_sources_image_id ON image_sources(image_id);
CREATE INDEX idx_image_sources_source_id ON image_sources(source_id);

-- Raw_metadata table
CREATE INDEX idx_raw_metadata_image_id ON raw_metadata(image_id);

-- Tag_implications table
CREATE INDEX idx_implications_source ON tag_implications(source_tag_id);
CREATE INDEX idx_implications_status ON tag_implications(status);

-- Tag_deltas table
CREATE INDEX idx_tag_deltas_md5 ON tag_deltas(image_md5);

-- Rating tables
CREATE INDEX idx_rating_weights_rating ON rating_tag_weights(rating);
CREATE INDEX idx_rating_weights_weight ON rating_tag_weights(weight DESC);
CREATE INDEX idx_rating_pair_weights_rating ON rating_tag_pair_weights(rating);
CREATE INDEX idx_rating_pair_weights_weight ON rating_tag_pair_weights(weight DESC);
CREATE INDEX idx_rating_pair_weights_tags ON rating_tag_pair_weights(tag1, tag2);
```

### Query Performance Tips

1. **Use EXPLAIN QUERY PLAN** to verify index usage
2. **Batch inserts** in transactions for better performance (see `DB_BATCH_SIZE` config)
3. **ANALYZE** database periodically for query optimization
4. **VACUUM** to reclaim space and defragment
5. **WAL mode** for concurrent reads during writes

### Performance Optimizations (New in Latest Version)

**Tag Search Optimization**:
- Two-step query approach: First find matching image IDs, then batch fetch details
- Case-insensitive index on tag names for faster searches
- Batched queries (500 images per batch) to avoid SQL parameter limits
- Eliminates expensive `ORDER BY RANDOM()` in favor of `ORDER BY id`

**Bulk Operations**:
- Configurable batch size (`DB_BATCH_SIZE`, default 100) for commits
- Reduces transaction overhead by 5-10x
- Minimizes database lock time during large updates
- Used in: repopulation, tag rebuilding, tag categorization

**Cache Manager Optimization**:
- Batched JSON parsing with progress tracking
- Temp storage to minimize lock time during reload
- Prevents UI blocking with async loading option

**Query Optimization Examples**:
```sql
-- OLD: Expensive random ordering
SELECT * FROM images ORDER BY RANDOM() LIMIT 100;

-- NEW: Fast sequential ordering
SELECT * FROM images ORDER BY id LIMIT 100;

-- OLD: Slow tag search with GROUP_CONCAT on all images
SELECT filepath, GROUP_CONCAT(name) FROM images JOIN image_tags ...

-- NEW: Fast two-step with index-based filtering
-- Step 1: Find matching IDs (uses indexes)
SELECT image_id FROM image_tags WHERE tag_id IN (...) GROUP BY image_id;
-- Step 2: Batch fetch details for matched IDs only
SELECT filepath, tags FROM images WHERE id IN (...);
```

---

## Data Relationships

### Image → Tags (Many-to-Many)
```
images (1) ←→ (N) image_tags (N) ←→ (1) tags
```

### Image → Sources (Many-to-Many)
```
images (1) ←→ (N) image_sources (N) ←→ (1) sources
```

### Image → Raw Metadata (One-to-One)
```
images (1) ←→ (1) raw_metadata
```

### Image → Pools (Many-to-Many)
```
images (1) ←→ (N) pool_images (N) ←→ (1) pools
```

### Tag → Tag (Self-Referencing via Implications)
```
tags (1) ←→ (N) tag_implications (N) ←→ (1) tags
```

### Parent-Child Relationships (Self-Referencing)
```
images.parent_id → images.id (parent image)
images.has_children → TRUE if this image has children
```

---

## Database Operations

### Connection Management

```python
# database/core.py
from database import get_db_connection

def get_db_connection():
    """Create a database connection with optimized settings."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.row_factory = sqlite3.Row
    return conn
```

### Common Patterns

#### Using Context Manager
```python
with get_db_connection() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM images WHERE id = ?", (image_id,))
    result = cur.fetchone()
    # Connection automatically closed and committed
```

#### Transactions
```python
with get_db_connection() as conn:
    try:
        conn.execute("INSERT INTO images (...) VALUES (...)", (...))
        conn.execute("INSERT INTO image_tags (...) VALUES (...)", (...))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
```

#### Batch Operations
```python
with get_db_connection() as conn:
    data = [(tag1, image1), (tag2, image2), ...]
    conn.executemany(
        "INSERT OR IGNORE INTO image_tags (tag_id, image_id) VALUES (?, ?)",
        data
    )
    conn.commit()
```

---

## Database Initialization

### Schema Creation
```python
# database/core.py - initialize_database()
# Creates all tables, indexes, and triggers
# Handles schema migrations (adds new columns)
# Sets up FTS5 virtual table
# Initializes rating inference config
```

### Data Integrity Checks
```python
# database/core.py - repair_orphaned_image_tags()
# Rebuilds image_tags for images with denormalized tags
# Ensures relational integrity
```

### FTS Population
```python
# database/core.py - populate_fts_table()
# Populates FTS table from existing images
# Only runs if FTS is empty
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Overall system architecture
- [REPOSITORIES.md](REPOSITORIES.md) - Data access layer using these tables
- [SERVICES.md](SERVICES.md) - Business logic that reads/writes to DB
- [DATA_FLOW.md](DATA_FLOW.md) - How data flows through the database

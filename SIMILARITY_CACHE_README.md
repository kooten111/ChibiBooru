# Similarity Cache System

## Overview

The similarity cache system pre-computes and stores top-N similar images for each image in the database. This eliminates the need to keep the FAISS semantic similarity index loaded in memory 24/7, reducing memory usage by approximately 300-400 MB (~25% of total RAM for a 15,000 image collection).

## Key Features

- **Memory Reduction**: Saves ~300-400 MB RAM by avoiding persistent FAISS index in memory
- **Faster Sidebar**: 1-2ms cache lookup vs 10-50ms FAISS search
- **Identical Results**: Pre-computed similarities are identical to live FAISS-based results
- **Automatic Updates**: New images automatically get their similarities cached during ingestion
- **Manual Rebuild**: Admin can trigger full cache rebuild via system panel
- **Idle Timeout**: FAISS index auto-unloads after 5 minutes of inactivity when cache is enabled

## Architecture

### Database Schema

```sql
CREATE TABLE similar_images_cache (
    source_image_id INTEGER NOT NULL,
    similar_image_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    similarity_type TEXT NOT NULL,  -- 'visual', 'semantic', 'tag', 'blended'
    rank INTEGER NOT NULL,          -- 1-50 (position in similarity ranking)
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_image_id, similar_image_id, similarity_type),
    FOREIGN KEY (source_image_id) REFERENCES images(id) ON DELETE CASCADE,
    FOREIGN KEY (similar_image_id) REFERENCES images(id) ON DELETE CASCADE
);
```

### Storage Requirements

For a collection of N images storing top-50 similar for each:

- **Per image**: 50 similar × 12 bytes (2 int IDs + 1 float score) = 600 bytes
- **15k images**: ~9 MB per similarity type
- **Multiple types** (visual, semantic, tag, blended): ~36 MB total

Even for 100k images, total storage is only ~240 MB, much smaller than keeping FAISS in RAM.

## Configuration

Add to `.env` or use defaults in `config.py`:

```bash
# Enable similarity cache (default: true)
SIMILARITY_CACHE_ENABLED=true

# Number of similar images to cache per image (default: 50)
SIMILARITY_CACHE_SIZE=50

# Seconds before unloading idle FAISS index (default: 300 = 5 min)
FAISS_IDLE_TIMEOUT=300
```

## Usage

### Automatic Caching (Ingestion)

When new images are ingested:
1. Image is processed and metadata extracted
2. Semantic embedding is computed via ML Worker
3. **Similarities are automatically computed and cached**
4. FAISS index is unloaded after 5 minutes of inactivity

### Manual Cache Rebuild

Via System Panel UI:
1. Navigate to **System** tab in header
2. Expand **Debug Options**
3. Find **Rebuild Similarity Cache** under "Database Maintenance"
4. Click **Rebuild** button
5. Monitor progress in system logs

Via API:
```bash
curl -X POST "http://localhost:5000/api/similarity/rebuild-cache?secret=YOUR_SECRET"
```

### Cache Statistics

Get cache coverage statistics:
```bash
curl "http://localhost:5000/api/similarity/cache-stats"
```

Returns:
```json
{
  "total_images": 15000,
  "blended_cached": 15000,
  "blended_coverage": 100.0,
  "semantic_cached": 14800,
  "semantic_coverage": 98.7,
  "total_entries": 750000,
  "cache_enabled": true,
  "cache_size": 50
}
```

## How It Works

### Cache Hit (Sidebar Display)

When viewing an image with **default similarity parameters**:
1. `find_blended_similar()` checks if cache is enabled
2. Looks up pre-computed results from SQLite (1-2ms)
3. Applies family filter if requested
4. Returns cached results immediately

### Cache Miss (Custom Parameters)

When using **custom similarity weights/thresholds**:
1. Cache is bypassed (parameters don't match cached defaults)
2. Live computation runs as normal
3. FAISS index is loaded on-demand if needed
4. Results are not cached (custom queries are rare)

### Cache Building

When computing cache for an image:
1. Calls `find_blended_similar()` with `use_cache=False`
2. Gets top-50 results from live computation
3. Stores results with rank in `similar_images_cache` table
4. Deletes any previous cache entries for this image+type

## Performance

### Memory Usage

| Mode | FAISS Index | Total RAM | Savings |
|------|-------------|-----------|---------|
| **Without Cache** (old) | Always loaded | ~1.6 GB | - |
| **With Cache** (new) | Auto-unload after 5min | ~1.2 GB | **~400 MB** |

### Query Performance

| Operation | Without Cache | With Cache | Improvement |
|-----------|---------------|------------|-------------|
| Sidebar lookup | 10-50ms | 1-2ms | **5-25x faster** |
| Custom query | 10-50ms | 10-50ms | Same (bypasses cache) |

## Implementation Details

### Files Modified

1. **`database/core.py`**: Added `similar_images_cache` table schema
2. **`config.py`**: Added cache configuration options
3. **`services/similarity_cache.py`**: New service with cache operations
4. **`services/similarity_service.py`**: 
   - Added cache check to `find_blended_similar()`
   - Added FAISS idle timeout management
5. **`services/processing_service.py`**: Auto-cache during ingestion
6. **`routers/api/similarity.py`**: Added rebuild and stats endpoints
7. **`templates/header.html`**: Added rebuild button to system panel
8. **`static/js/system-panel.js`**: Added rebuild button handler

### Key Functions

- `get_similar_from_cache(image_id, limit, similarity_type)` - Fast SQLite lookup
- `store_in_cache(source_id, results, similarity_type)` - Store computed similarities
- `compute_and_cache_for_image(image_id, similarity_type, force)` - Compute + store single image
- `rebuild_cache_full(similarity_type, progress_callback)` - Full rebuild with progress
- `get_cache_stats()` - Cache coverage statistics

### Cache Invalidation

The cache is automatically invalidated when:
- Images are deleted (CASCADE DELETE on foreign keys)
- Manual rebuild is triggered
- Individual image cache is recomputed (replaces old entries)

### Default Parameters

Cache is only used when similarity queries use these default parameters:
- `visual_weight=0.2`
- `tag_weight=0.2`
- `semantic_weight=0.6`
- `visual_threshold=15`
- `tag_threshold=0.1`
- `semantic_threshold=0.3`

This ensures the common sidebar case is fast, while allowing custom exploration.

## Monitoring

### Check Cache Coverage

```python
from services import similarity_cache
stats = similarity_cache.get_cache_stats()
print(f"Blended cache coverage: {stats['blended_coverage']}%")
```

### Clear Cache

```python
from services import similarity_cache
# Clear all cache
similarity_cache.clear_cache()

# Clear specific type
similarity_cache.clear_cache(similarity_type='blended')
```

## Troubleshooting

### Cache Not Being Used

Check:
1. `SIMILARITY_CACHE_ENABLED=true` in config
2. Using default similarity parameters
3. Cache has been built (run rebuild or ingest images)

### Slow First Query After Idle

This is expected behavior:
- FAISS index unloads after 5 minutes of inactivity
- First query after idle period loads index (~1-2 seconds)
- Subsequent queries are fast until next idle period

### Memory Not Reducing

1. Check if cache is actually being used (enable debug logging)
2. Wait 5+ minutes for FAISS index to unload
3. Monitor memory before/after idle timeout
4. Ensure semantic similarity is enabled (cache only helps when FAISS would be loaded)

## Future Enhancements

Potential improvements:
- Support caching for other similarity types (visual, semantic, tag separately)
- Incremental cache updates (only recompute changed images)
- Background cache warming after database operations
- Cache compression for very large collections
- Multi-level cache (in-memory LRU + SQLite)

## References

- Design document: `SIMILARITY_OPTIMIZATION_PLAN.md`
- FAISS documentation: https://github.com/facebookresearch/faiss
- SQLite performance: https://www.sqlite.org/optoverview.html

# Similarity Search Optimization Plan

**Date**: 2026-01-08
**Status**: Planning Phase
**Goal**: Reduce memory usage from FAISS semantic similarity by 300-400 MB (25% of total RAM)

---

## Current Implementation

### Memory Usage Breakdown
- **Total RAM**: 1.6 GB for ~15,000 images
- **FAISS Semantic Similarity**: ~300-400 MB (25% of total)
  - Raw embeddings in memory: 15k × 1024 × 4 bytes = ~61 MB
  - FAISS IndexFlatIP structures: ~150-200 MB
  - numpy working arrays: ~50-80 MB
  - Query/search buffers: ~40-60 MB

### Current Approach
```python
# services/similarity_service.py:340-358
def build_index(self):
    ids, matrix = similarity_db.get_all_embeddings()  # Loads ALL embeddings into RAM
    faiss.normalize_L2(matrix)
    self.index = faiss.IndexFlatIP(dimension)  # Flat index = all in RAM
    self.index.add(matrix)  # Adds all vectors to memory
```

**Behavior**:
- FAISS index stays loaded in memory at all times
- Every similarity search queries against full in-memory index
- Performance: ~10-50ms per search
- Flexible: Can adjust parameters at query time

---

## Problem Statement

The main use case for semantic similarity is:
- **Display 20 most similar images in sidebar** when viewing an image
- This is a fixed query (same parameters every time)
- Results don't need to be dynamic (can be computed ahead of time)

**Current inefficiency**:
- Keep 300-400 MB FAISS index in RAM 24/7
- To serve the same 20 results repeatedly
- Most images queried multiple times with identical parameters

---

## Proposed Solution: Pre-Computed Similarity Cache

### Core Concept
Pre-compute top-50 similar images for each image and store in SQLite. At runtime, simply look up cached results instead of loading FAISS.

### Schema Design

```sql
CREATE TABLE IF NOT EXISTS similar_images_cache (
    source_image_id INTEGER NOT NULL,
    similar_image_id INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    similarity_type TEXT NOT NULL,  -- 'visual', 'semantic', 'tag', 'blended'
    rank INTEGER NOT NULL,  -- 1-50 (position in similarity ranking)
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_image_id, similar_image_id, similarity_type),
    FOREIGN KEY (source_image_id) REFERENCES images(id) ON DELETE CASCADE,
    FOREIGN KEY (similar_image_id) REFERENCES images(id) ON DELETE CASCADE
);

CREATE INDEX idx_similar_lookup ON similar_images_cache(source_image_id, similarity_type, rank);
CREATE INDEX idx_computed_at ON similar_images_cache(computed_at);
```

### Storage Requirements

For 15,000 images storing top-50 similar for each:
```
15,000 images × 50 similar × 12 bytes (2 int IDs + 1 float score) = 9 MB per type
```

**With multiple similarity types**:
- Semantic: 9 MB
- Visual (pHash): 9 MB
- Tag-based: 9 MB
- Blended: 9 MB
- **Total**: ~36 MB

**Scaling**:
| Collection Size | Storage (4 types × 50 similar) |
|----------------|--------------------------------|
| 15k images | 36 MB |
| 50k images | 120 MB |
| 100k images | 240 MB |
| 200k images | 480 MB |

Still much smaller than 400 MB RAM for FAISS!

---

## Implementation Strategies

### Strategy 1: Lazy Pre-Compute (Incremental)

**Compute and cache on first access**:

```python
def get_similar_images(image_id, limit=20, similarity_type='semantic'):
    """Get similar images - uses cache or computes on-demand"""

    # Check cache first
    with get_db_connection() as conn:
        cached = conn.execute("""
            SELECT similar_image_id, similarity_score
            FROM similar_images_cache
            WHERE source_image_id = ? AND similarity_type = ?
            ORDER BY rank
            LIMIT ?
        """, (image_id, similarity_type, limit)).fetchall()

        if cached:
            return format_results(cached)

    # Cache miss - compute and store
    results = compute_similarities(image_id, similarity_type, limit=50)
    store_in_cache(image_id, results, similarity_type)

    return results[:limit]
```

**Characteristics**:
- Gradual cache building (no upfront cost)
- FAISS loads on-demand, unloads after idle timeout
- First view: slow (10-50ms), subsequent views: fast (1-2ms)
- Memory efficient: FAISS only loaded when needed

**Pros**:
- No migration needed
- Builds cache organically as users browse
- Low initial overhead

**Cons**:
- Unpredictable first-view latency
- Some images may never get cached (if rarely viewed)
- FAISS still loads periodically

### Strategy 2: Full Pre-Compute (Batch)

**Compute all similarities upfront**:

```python
def rebuild_similarity_cache_full():
    """Pre-compute top-50 similar images for all images"""

    print("[Similarity] Starting full cache rebuild...")

    # Load FAISS index once
    engine = get_semantic_engine()
    engine.build_index()

    # Get all images
    with get_db_connection() as conn:
        images = conn.execute("SELECT id, filepath FROM images").fetchall()

    # Compute for all images
    for img in tqdm(images, desc="Computing similarities"):
        # Get embedding
        embedding = get_embedding(img['id'])
        if embedding is None:
            continue

        # Search top-50
        results = engine.search(embedding, k=50)

        # Store in cache
        for rank, (similar_id, score) in enumerate(results, 1):
            save_to_cache(img['id'], similar_id, score, 'semantic', rank)

    # Unload FAISS after batch job
    engine.index = None
    print(f"[Similarity] Cache rebuilt for {len(images)} images")
```

**Performance**:
- 15k images × 10ms = ~2.5 minutes one-time
- Memory during build: 400 MB (FAISS loaded)
- Memory after build: 0 MB (FAISS unloaded)

**Pros**:
- Predictable performance (all cached)
- Complete coverage (every image has results)
- FAISS can be fully unloaded after

**Cons**:
- Upfront time investment (~3 minutes)
- Need to handle rebuilds when data changes

### Strategy 3: Hybrid Approach (Recommended)

**Combine lazy + batch for best of both worlds**:

```python
def get_similar_images(image_id, limit=20, use_cache=True, similarity_type='semantic'):
    """
    Get similar images with flexible caching strategy

    Args:
        use_cache: If True (default), use cached results. If False, compute live.
    """
    if use_cache:
        # Try cache first
        cached = get_from_cache(image_id, similarity_type, limit)
        if cached:
            return cached

        # Cache miss - compute and store
        results = compute_and_cache(image_id, similarity_type, limit=50)
        return results[:limit]
    else:
        # Explicit live search (loads FAISS on-demand)
        return live_faiss_search(image_id, limit)
```

**UI Implementation**:
- **Sidebar**: Always uses cached results (instant, 1-2ms)
- **"Find Similar" page**: Shows cached by default
- **Advanced option**: "Search All Images" button for live FAISS search

**Pros**:
- Fast by default (cached)
- Flexibility when needed (live search option)
- FAISS loads only for advanced features
- Best user experience

---

## Incremental Updates During Ingestion

### The Challenge

When ingesting new images, we need to update the similarity cache. Two directions to consider:

1. **Forward**: New image → Old images (find similar existing images)
2. **Backward**: Old images → New image (should old images show new image as similar?)

### Recommended Approach: Unidirectional + Scheduled Rebuilds

**During Ingestion** (Forward direction only):

```python
async def ingest_images_batch(files):
    """Existing ingestion function with similarity cache update"""

    # 1. Normal ingestion (DB, tags, hashes, etc.)
    new_image_ids = []
    for file in files:
        img_id = ingest_single_image(file)
        new_image_ids.append(img_id)

    # 2. Compute hashes in background (already exists)
    generate_missing_hashes_async()

    # 3. NEW: Compute similarities for new images only
    if config.ENABLE_SEMANTIC_SIMILARITY:
        await compute_similarities_for_new_images(new_image_ids)

    return new_image_ids


def compute_similarities_for_new_images(new_image_ids):
    """Compute similarities for newly ingested images (forward direction only)"""

    # Load FAISS once for the batch
    engine = get_semantic_engine()
    engine.build_index()  # ~500ms to load from disk

    with get_db_connection() as conn:
        for img_id in new_image_ids:
            # Get embedding
            embedding = get_embedding(img_id)
            if embedding is None:
                continue

            # Search against existing collection (~10ms)
            results = engine.search(embedding, k=50)

            # Store in cache
            for rank, (similar_id, score) in enumerate(results, 1):
                conn.execute("""
                    INSERT OR REPLACE INTO similar_images_cache
                    (source_image_id, similar_image_id, similarity_score, similarity_type, rank)
                    VALUES (?, ?, ?, 'semantic', ?)
                """, (img_id, similar_id, score, rank))

        conn.commit()

    # Unload FAISS after ingestion
    engine.index = None

    print(f"[Similarity] Cached similarities for {len(new_image_ids)} new images")
```

**Performance for 10 new images**:
- Load FAISS index: ~500ms (one-time)
- Compute 10 embeddings: ~1-2s (via ML worker)
- Search 10 × 10ms: ~100ms
- Insert to DB: ~50ms
- **Total: ~2-3 seconds overhead**

**Trade-off**:
- ✅ Fast ingestion (minimal overhead)
- ✅ New images get results immediately
- ⚠️ Asymmetric: Old images don't show new image yet
- ✅ Fixed by scheduled rebuild (see below)

### Scheduled Full Rebuild

**Weekly cron job to ensure bidirectional consistency**:

```python
def scheduled_similarity_rebuild():
    """
    Weekly rebuild to update old images with new images as similar matches
    """

    # Check if significant changes since last rebuild
    last_rebuild = get_last_rebuild_time()
    new_images_count = count_images_since(last_rebuild)
    total_images = get_total_image_count()

    # Rebuild if >5% of collection is new
    if new_images_count / total_images > 0.05:
        print(f"[Similarity] Rebuilding cache ({new_images_count} new images)")
        rebuild_similarity_cache_full()
    else:
        print(f"[Similarity] Skipping rebuild ({new_images_count} new images, <5% threshold)")
```

**Cron schedule**:
```bash
# Weekly on Sunday at 3 AM
0 3 * * 0 cd /path/to/chibibooru && python -c "from services.similarity_cache import scheduled_similarity_rebuild; scheduled_similarity_rebuild()"
```

---

## Alternative FAISS Optimization Strategies

If pre-computing is not desired, here are other ways to optimize FAISS:

### Option 1: Lazy Loading with Idle Timeout

```python
class SemanticSearchEngine:
    def __init__(self):
        self.index = None
        self.last_used = 0
        self.ttl = 300  # 5 minutes

    def search(self, embedding, k=20):
        # Build on-demand
        if self.index is None:
            self.build_index()

        # Check idle timeout
        if time.time() - self.last_used > self.ttl:
            print("[Similarity] Unloading idle FAISS index")
            self.index = None
            return self.search(embedding, k)  # Rebuild

        self.last_used = time.time()
        # ... search logic
```

**Savings**: ~300 MB when idle
**Trade-off**: First search after idle has ~0.5-1s delay

### Option 2: Memory-Mapped FAISS Index

```python
def build_index(self):
    if os.path.exists("semantic_index.faiss"):
        # Load as memory-mapped (OS manages paging)
        self.index = faiss.read_index("semantic_index.faiss", faiss.IO_FLAG_MMAP)
    else:
        # Build and save
        ids, matrix = similarity_db.get_all_embeddings()
        faiss.normalize_L2(matrix)
        self.index = faiss.IndexFlatIP(matrix.shape[1])
        self.index.add(matrix)
        faiss.write_index(self.index, "semantic_index.faiss")
```

**Savings**: ~150 MB (OS pages out unused vectors)
**Trade-off**: Slightly slower first access after page-out

### Option 3: Product Quantization

```python
def build_index(self):
    ids, matrix = similarity_db.get_all_embeddings()
    faiss.normalize_L2(matrix)

    dimension = matrix.shape[1]
    nlist = 100  # Clusters
    m = 8  # Subquantizers
    nbits = 8  # Bits per subquantizer

    quantizer = faiss.IndexFlatIP(dimension)
    self.index = faiss.IndexIVFPQ(quantizer, dimension, nlist, m, nbits)
    self.index.train(matrix)
    self.index.add(matrix)
```

**Savings**: 90% compression (61 MB → ~6 MB for embeddings)
**Trade-off**: Slight accuracy loss, requires training phase

---

## Performance Comparison

### Current Implementation
| Metric | Value |
|--------|-------|
| Memory (idle) | 400 MB |
| Memory (active) | 400 MB |
| Query time | 10-50 ms |
| Startup time | 2-5 seconds (build index) |
| Ingestion overhead | 0 ms (no cache) |
| Flexibility | Full (dynamic queries) |

### Pre-Computed Cache (Recommended)
| Metric | Value |
|--------|-------|
| Memory (idle) | 0 MB |
| Memory (active) | 0 MB |
| Query time | 1-2 ms (95% cached) |
| Startup time | <100 ms (SQLite lookup) |
| Ingestion overhead | 2-3s per 10 images |
| Flexibility | High (live search option) |
| Storage | 36 MB SQLite |
| Build time | 3 minutes (weekly) |

### Lazy Loading + Timeout
| Metric | Value |
|--------|-------|
| Memory (idle) | 0 MB (after timeout) |
| Memory (active) | 400 MB |
| Query time | 10-50 ms (+ rebuild penalty) |
| Startup time | 0 ms (lazy) |
| Ingestion overhead | 0 ms |
| Flexibility | Full (dynamic queries) |

### Memory-Mapped Index
| Metric | Value |
|--------|-------|
| Memory (idle) | 150 MB (partial paging) |
| Memory (active) | 300 MB |
| Query time | 15-60 ms (page faults) |
| Startup time | 0.5 seconds (mmap) |
| Ingestion overhead | 0 ms |
| Flexibility | Full (dynamic queries) |

---

## Recommendations

### For Current Collection Size (15k images)

**Phase 1: Implement Lazy Pre-Compute** (Low risk, immediate benefit)
1. Add `similar_images_cache` table to schema
2. Implement cache lookup function
3. Fall back to FAISS on cache miss
4. Store results in cache after computation
5. FAISS loads on-demand, unloads after idle

**Expected results**:
- Memory: 1.6 GB → 1.2-1.3 GB (~25% reduction)
- Query time: 50ms → 2ms (once cached)
- No user-facing changes

**Phase 2: Add Incremental Updates** (Improve ingestion experience)
1. Hook into existing ingestion pipeline
2. Compute similarities for new images only
3. 2-3s overhead per 10 images

**Expected results**:
- New images have instant similarity results
- Ingestion slightly slower but acceptable

**Phase 3: Add Full Rebuild** (Complete the system)
1. Background job for weekly rebuilds
2. Admin UI button for manual rebuilds
3. Ensures bidirectional consistency

**Expected results**:
- All images stay fresh
- Old images show new images as similar

### For Growing Collections (50k+ images)

Everything above, plus:
- Monitor cache storage growth (will reach ~120 MB)
- Consider implementing multiple similarity types (visual, semantic, tag, blended)
- Add cache statistics to admin dashboard

### For Very Large Collections (200k+ images)

Everything above, plus:
- Implement cache sharding (partition by image_id ranges)
- Add incremental FAISS index updates (avoid full rebuilds)
- Consider Redis for hot cache layer

---

## Implementation Checklist

### Database Schema
- [ ] Add `similar_images_cache` table
- [ ] Add indexes for fast lookup
- [ ] Add migration script for existing installations

### Core Functions
- [ ] `get_similar_images(image_id, limit, use_cache)` - Main API
- [ ] `compute_and_cache(image_id, similarity_type)` - Compute + store
- [ ] `rebuild_similarity_cache_full()` - Full rebuild
- [ ] `compute_similarities_for_new_images(ids)` - Incremental

### Integration Points
- [ ] Hook into ingestion pipeline (`ingest_images_batch`)
- [ ] Update sidebar similarity display
- [ ] Add "live search" option to advanced UI
- [ ] Add cache statistics to debug page

### Background Jobs
- [ ] Weekly cron for full rebuild
- [ ] Idle timeout for FAISS unloading
- [ ] Cache cleanup for deleted images (handled by CASCADE)

### Admin UI
- [ ] "Rebuild Similarity Cache" button
- [ ] Cache coverage statistics
- [ ] Last rebuild timestamp
- [ ] Cache hit/miss rates

### Configuration
- [ ] `SIMILARITY_CACHE_ENABLED` (default: true)
- [ ] `SIMILARITY_CACHE_SIZE` (top-N to cache, default: 50)
- [ ] `SIMILARITY_REBUILD_THRESHOLD` (%, default: 5%)
- [ ] `FAISS_IDLE_TIMEOUT` (seconds, default: 300)

---

## Migration Plan

### For Existing Installations

**Step 1: Add Schema**
```sql
-- Run migration script
ALTER TABLE ... -- Add similarity cache table
```

**Step 2: Enable Lazy Caching**
```python
# Update config
SIMILARITY_CACHE_ENABLED = true

# Deploy code
# No action needed - cache builds organically
```

**Step 3: Initial Seed (Optional)**
```bash
# Run one-time full rebuild to seed cache
python scripts/rebuild_similarity_cache.py

# Or let it build organically over time
```

**Step 4: Enable Scheduled Rebuilds**
```bash
# Add cron job
crontab -e
# Add: 0 3 * * 0 /path/to/rebuild_similarity.sh
```

---

## Testing Plan

### Unit Tests
- [ ] Cache lookup performance
- [ ] Cache insertion correctness
- [ ] Incremental update logic
- [ ] Full rebuild completeness

### Integration Tests
- [ ] Ingestion with cache update
- [ ] FAISS lazy loading
- [ ] Idle timeout behavior
- [ ] Cache hit rate monitoring

### Performance Tests
- [ ] Query latency (cached vs uncached)
- [ ] Memory usage over time
- [ ] Ingestion overhead measurement
- [ ] Full rebuild time

### User Acceptance Tests
- [ ] Sidebar loads quickly
- [ ] Similar images are relevant
- [ ] New images appear in results after rebuild
- [ ] No user-facing errors

---

## Rollback Plan

If issues arise:

1. **Disable cache lookup**:
   ```python
   SIMILARITY_CACHE_ENABLED = false
   ```
   Falls back to live FAISS search (original behavior)

2. **Drop cache table**:
   ```sql
   DROP TABLE similar_images_cache;
   ```
   Frees storage, no impact on other features

3. **Revert code changes**:
   ```bash
   git revert <commit-hash>
   ```
   Returns to original implementation

---

## Future Enhancements

### Advanced Similarity Types

Pre-compute multiple types for different use cases:

```sql
-- similarity_type values:
'semantic'        -- Neural embedding similarity (current)
'visual_strict'   -- pHash < 5 (near-duplicates)
'visual_relaxed'  -- pHash < 15 (visually similar)
'tag_based'       -- Jaccard similarity on tags
'blended'         -- Weighted combination (default for sidebar)
'same_character'  -- Character tag matching
'same_artist'     -- Artist tag matching
```

### Smart Rebuild Triggers

```python
def should_rebuild_cache():
    """Intelligent rebuild decision"""

    # Trigger 1: Time-based (weekly)
    if days_since_last_rebuild() > 7:
        return True

    # Trigger 2: New images threshold
    if new_images_percent() > 5:
        return True

    # Trigger 3: Cache miss rate
    if cache_miss_rate() > 10:
        return True

    return False
```

### Distributed Caching

For massive collections (1M+ images):

```python
# Partition cache by image_id ranges
PARTITION_SIZE = 100000

def get_cache_partition(image_id):
    return f"similar_cache_{image_id // PARTITION_SIZE}.db"

# Load only relevant partition
conn = sqlite3.connect(get_cache_partition(image_id))
```

---

## Conclusion

**Recommended path forward**:

1. **Immediate**: Implement lazy pre-compute with cache fallback
2. **Short-term**: Add incremental updates during ingestion
3. **Long-term**: Add scheduled rebuilds for bidirectional consistency

**Expected outcomes**:
- ✅ 300-400 MB memory savings (25% reduction)
- ✅ 10-25x faster similarity queries (1-2ms vs 10-50ms)
- ✅ Minimal ingestion overhead (2-3s per 10 images)
- ✅ Better user experience (instant sidebar loading)
- ✅ Scales to larger collections efficiently

**Next steps**: Review this plan and decide if we should proceed with implementation.

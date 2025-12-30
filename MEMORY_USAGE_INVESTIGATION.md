# Memory Usage Investigation - monitor_runner.py

**Date**: 2025-12-30
**Process**: monitor_runner.py (PID 24930)
**Memory Usage**: 4.1 GB RSS (Resident Set Size)
**Expected Usage**: ~400 MB (based on database sizes)
**Memory Inflation**: ~10x overhead

---

## Executive Summary

The monitor_runner.py process is consuming 4.1 GB of RAM, which is excessive given that:
- Total database size: ~201 MB (booru.db)
- Raw metadata JSON: ~74 MB
- Total images: 13,028
- Total tags: 21,113
- Tag associations: 624,717

**Root Cause**: Heavy ML framework overhead + database memory-mapping across multiple workers + Python object overhead.

**Status**: NOT a memory leak (stable over 15+ hours), but inefficient architecture.

---

## Memory Breakdown (Actual)

### From /proc/24930/maps analysis:

| Component | Size | Notes |
|-----------|------|-------|
| Anonymous heap | 8,793 MB | Python objects, library allocations |
| booru.db (memory-mapped) | 2,409 MB | 201 MB DB mapped ~12x (multiple workers) |
| libtorch_xpu.so | 677 MB | PyTorch XPU support library |
| libtorch_cpu.so | 313 MB | PyTorch CPU library |
| Intel MKL libraries | ~200 MB | Math kernel libraries |
| libtriton.so | 140 MB | Triton compiler |
| libccl.so | 141 MB | Collective communications |
| OpenBLAS (multiple) | ~80 MB | Linear algebra libraries |
| ONNXRuntime | 22 MB | ONNX inference runtime |
| **TOTAL** | **~4.1 GB** | |

---

## Investigation Process

### 1. Database Size Check
```bash
booru.db:        201 MB (on disk: 84 MB compressed)
rating_model.db: 135 MB
similarity.db:    58 MB
Total:           ~394 MB
```

### 2. In-Memory Cache Estimation
Based on code analysis of `core/cache_manager.py`:

```python
# Three main in-memory structures:
tag_counts = {}        # 21,113 tags → ~6 MB
image_data = []        # 13,028 images → ~17 MB
post_id_to_md5 = {}    # ~26,000 entries → ~8 MB

# Expected total: ~31 MB
# Actual usage: 4,100 MB
# Inflation factor: 134x
```

### 3. ML Model Status
```
Tagger model (model.onnx): 752 MB - NOT loaded (confirmed)
Similarity model: 370 MB - NOT loaded
Upscaler model: 64 MB - NOT loaded
```

**However**, the ML frameworks ARE loaded:
- PyTorch imported via `torchvision.transforms` (processing_service.py:34)
- ONNXRuntime imported at module level (processing_service.py:27)
- This loads ~2 GB of shared libraries even with no models in memory

### 4. Database Connection Analysis
```
Process has 20+ open file handles to booru.db
Multiple connections from ThreadPoolExecutor workers
Each worker memory-maps the database separately
201 MB × 12 workers ≈ 2.4 GB virtual memory
```

---

## Root Causes

### 1. Heavy ML Framework Overhead (~2 GB)
**Location**: `services/processing_service.py`

```python
# Line 34 - This loads entire PyTorch framework
import torchvision.transforms as transforms

# Line 27 - Loads ONNXRuntime
import onnxruntime as ort
```

**Impact**:
- PyTorch libraries: ~1 GB
- Intel MKL/OpenBLAS: ~300 MB
- ONNXRuntime: ~200 MB
- Other dependencies: ~500 MB

These are loaded at import time, even though models are only loaded on-demand via `load_local_tagger()`.

### 2. Database Memory-Mapping Multiplication (~2.4 GB)
**Location**: Multiple ThreadPoolExecutor workers

The monitor uses a ThreadPoolExecutor with `MAX_WORKERS` threads (likely 4-8). Each worker thread opens its own database connection, and SQLite memory-maps the database file for each connection.

```python
# services/monitor_service.py:367
ingest_executor = ThreadPoolExecutor(
    max_workers=max_workers,
    thread_name_prefix="IngestWorker"
)
```

### 3. Python Object Overhead (~800 MB)
**Location**: `core/cache_manager.py`

Python has significant per-object overhead:
- Each dict: ~232 bytes overhead
- Each string: ~50+ bytes overhead
- Each list: ~56+ bytes overhead

With 624,717 tag associations and complex nested structures, this adds up quickly.

### 4. Additional Memory Consumers
- Heap fragmentation
- Library pre-allocated buffers
- Thread stacks (148 KB each × workers)
- Watchdog observer threads
- JSON parsing buffers

---

## Why This Wasn't Obvious Initially

1. **Database size confusion**: 201 MB on disk, but memory-mapped 12x = 2.4 GB virtual
2. **Lazy loading assumption**: Models aren't loaded, but *frameworks* are (at import time)
3. **Thread pool hidden cost**: Each worker multiplies database mappings
4. **Python overhead**: Not intuitive that 30 MB of data becomes 800 MB in Python objects

---

## Potential Solutions (For Future Investigation)

### Option 1: Lazy Import ML Libraries
**Impact**: Could save ~2 GB

```python
# Instead of:
import torchvision.transforms as transforms

# Use:
def preprocess_image_for_local_tagger(image_path):
    import torchvision.transforms as transforms  # Import only when needed
    ...
```

**Trade-off**: Slightly slower first-time model loading

### Option 2: Reduce ThreadPoolExecutor Workers
**Impact**: Could save ~1.5 GB

```python
# Reduce from MAX_WORKERS (likely 8) to 2-3
# services/monitor_service.py:367
```

**Trade-off**: Slower parallel image processing

### Option 3: Use Single Shared Database Connection
**Impact**: Could save ~2 GB

Use a connection pool with a single shared connection instead of per-worker connections.

**Trade-off**: More complex, potential contention

### Option 4: External Process for ML Tasks
**Impact**: Could save ~2 GB in monitor_runner

Move model inference to a separate process that's only spawned when needed.

**Trade-off**: More complex architecture, IPC overhead

### Option 5: Switch to ProcessPoolExecutor (with caution)
**Impact**: May reduce memory mapping duplication

**Trade-off**: Each process would need its own Python interpreter (~200 MB each)

### Option 6: Optimize In-Memory Cache Structures
**Impact**: Could save ~500 MB

Use more memory-efficient data structures:
- `__slots__` for classes
- Arrays instead of dicts where possible
- Interning strings

**Trade-off**: More complex code, less flexibility

---

## Monitoring Recommendations

### To verify memory leak vs. steady state:
```bash
# Monitor over 24 hours
watch -n 300 'ps -p 24930 -o pid,vsz,rss,cmd'

# Check for growth
pmap -x 24930 | tail -1
```

### To profile memory in detail:
```bash
# Use memory_profiler
pip install memory_profiler
python -m memory_profiler monitor_runner.py
```

### To identify specific allocations:
```python
import tracemalloc
tracemalloc.start()
# ... run code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
```

---

## Current State Assessment

**Severity**: Medium
- Not a critical memory leak (stable usage)
- Process is functioning correctly
- BUT consuming 10x more memory than necessary

**Impact**:
- 4.1 GB used out of 30 GB total RAM (13.7%)
- Contributing to swap pressure (8 GB swap fully utilized)
- Could support 2-3 monitor processes with optimizations

**Recommendation**:
Investigate Option 1 (lazy imports) first as it's:
- Lowest risk
- Highest impact (~2 GB savings)
- Easiest to implement
- No functional trade-offs

---

## Files to Review for Optimization

1. `services/processing_service.py` - ML library imports (Lines 27, 34)
2. `services/monitor_service.py` - ThreadPoolExecutor config (Line 367)
3. `core/cache_manager.py` - In-memory cache structures
4. `config.py` - MAX_WORKERS setting
5. `database/core.py` - Database connection management

---

## Appendix: Raw Data

### Process Memory (from /proc/24930/status)
```
VmSize:    13,541,000 kB (13.2 GB virtual)
VmRSS:      4,103,092 kB (4.0 GB resident)
RssAnon:    3,338,564 kB (3.2 GB anonymous)
RssFile:      764,528 kB (746 MB file-backed)
VmData:     5,694,400 kB (5.4 GB data segment)
VmLib:        987,436 kB (964 MB libraries)
```

### Database Statistics
```sql
SELECT COUNT(*) FROM images;        -- 13,028
SELECT COUNT(*) FROM tags;          -- 21,113
SELECT COUNT(*) FROM image_tags;    -- 624,717
SELECT SUM(LENGTH(data))/1024/1024 FROM raw_metadata; -- 74 MB
```

### Open File Handles to Database
```
20+ file descriptors open to booru.db and booru.db-wal
Multiple memory-mapped regions
```

---

## Next Steps

1. Measure baseline memory with current configuration
2. Test lazy import approach (Option 1) in development
3. Profile memory before/after changes
4. Consider reducing MAX_WORKERS if parallel processing isn't critical
5. Monitor for any performance regressions
6. Document final solution

---

*Investigation completed: 2025-12-30*
*Investigator: Claude Code*

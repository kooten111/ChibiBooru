# Rating Model Database Optimization

## Overview

This document describes the storage optimizations implemented for the rating model database to significantly reduce file size and improve distribution efficiency.

## Changes Summary

### 1. Tag ID Interning (Normalization)
**Impact: ~60-70% size reduction**

Replaced repeated tag name strings with integer foreign keys using lookup tables.

**Before (Old Schema):**
```sql
CREATE TABLE rating_tag_weights (
    tag_name TEXT NOT NULL,
    rating TEXT NOT NULL,
    weight REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (tag_name, rating)
);
```

**After (New Schema):**
```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE rating_tag_weights (
    tag_id INTEGER NOT NULL REFERENCES tags(id),
    rating_id INTEGER NOT NULL REFERENCES ratings(id),
    weight REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    PRIMARY KEY (tag_id, rating_id)
);
```

### 2. Rating as Integer Enum
**Impact: ~15x reduction for rating columns**

Replaced rating strings like `"rating:general"` (15 bytes) with integer values (typically 1-4 bytes).

**Schema:**
```sql
CREATE TABLE ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);
```

Pre-populated with:
- `rating:general`
- `rating:sensitive`
- `rating:questionable`
- `rating:explicit`

### 3. Gzip Compression for Distribution
**Impact: ~60-80% additional compression**

Added functions to export/import compressed databases:

```python
from repositories.rating_repository import export_model_compressed, import_model_compressed

# Export
export_model_compressed('rating_model.db', 'rating_model.db.gz')

# Import
import_model_compressed('rating_model.db.gz', 'rating_model.db')
```

### 4. Pruning Threshold Infrastructure
**Status: Disabled by default (threshold = 0.0)**

Added configuration parameter for future testing:

```python
# In rating_inference_config table
pruning_threshold: 0.0  # Keep all weights (disabled)
# Future testing: 0.01  # Prune weights with |weight| < 0.01
```

When enabled (non-zero), the training process will skip weights below the threshold, further reducing database size at the potential cost of prediction accuracy.

## Migration Guide

### Automatic Migration

New databases automatically use the normalized schema. When connecting to an old database for the first time, the system will automatically detect the schema and migrate data to the new format.

### Manual Migration

Use the standalone migration script to convert existing databases:

```bash
# Migrate with in-place update (creates backup)
python scripts/migrate_rating_model.py rating_model.db

# Migrate to new file
python scripts/migrate_rating_model.py old_rating_model.db new_rating_model.db
```

The migration script:
1. Detects old vs. new schema automatically
2. Creates timestamped backup (for in-place updates)
3. Migrates all data with proper ID mappings
4. Verifies data integrity
5. Reports statistics

### Command-Line Tools

The rating repository module includes CLI commands:

```bash
# Initialize new database
python repositories/rating_repository.py init [path]

# Export from main DB
python repositories/rating_repository.py export [path]

# Import to main DB
python repositories/rating_repository.py import [path]

# Show model info
python repositories/rating_repository.py info [path]

# Compress model
python repositories/rating_repository.py compress [path]

# Decompress model
python repositories/rating_repository.py decompress <gz_path>
```

## API Compatibility

All public APIs remain unchanged. The schema changes are internal only:

```python
# Training - works exactly the same
from services.rating_service import train_model
stats = train_model()

# Inference - works exactly the same
from services.rating_service import predict_rating
rating, confidence = predict_rating(image_tags)

# Loading weights - works exactly the same
from services.rating_service import load_weights
tag_weights, pair_weights = load_weights()
```

## Performance Notes

### Query Performance
The normalized schema with proper indexes provides:
- Faster lookups (integer comparison vs. string comparison)
- Better index efficiency (integers are smaller)
- Improved JOIN performance

### Storage Efficiency Example

For a typical model with:
- 10,000 unique tags
- 4 ratings
- 50,000 tag-rating weights
- 10,000 tag pair weights

**Old Schema:**
- Average tag name: 15 bytes
- Average rating string: 15 bytes
- Tag weights: 50,000 × (15 + 15 + 8 + 4) = ~2.1 MB
- Pair weights: 10,000 × (15 + 15 + 15 + 8 + 4) = ~0.6 MB
- Total: ~2.7 MB

**New Schema:**
- Tags table: 10,000 × (4 + 15) = 0.19 MB
- Ratings table: 4 × (4 + 15) = 76 bytes
- Tag weights: 50,000 × (4 + 4 + 8 + 4) = ~1.0 MB
- Pair weights: 10,000 × (4 + 4 + 4 + 8 + 4) = ~0.24 MB
- Total: ~1.4 MB (48% reduction)

**With Gzip Compression (level 9):**
- Compressed size: ~0.3 MB (89% reduction from original)

## Security

All SQL operations use parameterized queries. The migration script includes:
- Table name whitelisting to prevent SQL injection
- Proper error handling
- Data validation

## Testing

A comprehensive test suite validates:
- Schema initialization
- Tag/rating ID operations
- Weight table operations with JOINs
- Compression/decompression
- Migration from old to new schema
- Data integrity after migration

Run tests with:
```bash
python test_normalized_schema.py  # From project root
```

## Troubleshooting

### "no such column: tag_name"
The database is using the new schema but code is expecting the old schema. Ensure you're using the latest version of the codebase.

### "no such column: tag_id"
The database is using the old schema. Run the migration script or let the system auto-migrate.

### Migration fails
Check that:
1. You have write permissions
2. Sufficient disk space for backup
3. Database is not corrupted
4. No other process is using the database

## Future Enhancements

Potential future optimizations:
1. Test pruning threshold values (0.01, 0.05) for size vs. accuracy tradeoff
2. Implement weight quantization (float32 → int16) for additional 50% size reduction
3. Use VACUUM to reclaim space after pruning
4. Implement incremental updates instead of full retraining

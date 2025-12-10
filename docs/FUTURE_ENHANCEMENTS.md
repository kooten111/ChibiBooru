# Future Enhancements

This document outlines planned future improvements for ChibiBooru. All major refactoring work (Phases 1-6A) has been completed, eliminating ~2,000+ lines of duplicated code and establishing consistent patterns throughout the codebase.

---

## Table of Contents

- [Phase 6B: Service Decomposition](#phase-6b-service-decomposition)
- [Phase 6C: Testing & Polish](#phase-6c-testing--polish)
- [Other Future Enhancements](#other-future-enhancements)

---

## Phase 6B: Service Decomposition

**Priority:** Medium  
**Estimated Effort:** Large (3-4 weeks)  
**Status:** Deferred

### Overview

Several service files have grown large and could benefit from decomposition into smaller, more focused modules. This would improve maintainability and make the codebase easier to navigate.

### Target Files

#### 1. Split `services/processing_service.py` (~1,300 lines)

**Current State:** Contains all metadata fetching logic for multiple sources

**Proposed Structure:**
```
services/processing/
  __init__.py           # Main ProcessingService class
  base.py               # Base fetcher interface
  danbooru.py          # Danbooru fetcher
  e621.py              # e621 fetcher
  gelbooru.py          # Gelbooru fetcher
  yandere.py           # Yandere fetcher
  pixiv.py             # Pixiv fetcher
  local_tagger.py      # Local AI tagger
  utils.py             # Shared utilities
```

**Benefits:**
- Easier to maintain individual source integrations
- Simpler to add new metadata sources
- Better testability with isolated fetchers
- Reduced cognitive load when working on specific sources

**Estimated Effort:** 1-2 weeks

---

#### 2. Split `services/rating_service.py` (~900 lines)

**Current State:** Contains AI rating inference and related utilities

**Proposed Structure:**
```
services/rating/
  __init__.py           # Main RatingService class
  inference.py          # AI model inference logic
  models.py             # Model loading and management
  validation.py         # Rating validation and normalization
  utils.py              # Shared utilities
```

**Benefits:**
- Clearer separation of concerns
- Easier to swap or add new rating models
- Better organization of model-related code

**Estimated Effort:** 1 week

---

#### 3. Split `services/image_service.py` (~850 lines)

**Current State:** Contains image CRUD operations and bulk utilities

**Proposed Structure:**
```
services/image/
  __init__.py           # Main ImageService class
  crud.py               # Basic CRUD operations
  bulk.py               # Bulk operations
  relationships.py      # Parent/child relationships
  validation.py         # Image validation logic
  utils.py              # Shared utilities
```

**Benefits:**
- Clearer separation between single and bulk operations
- Easier to find specific functionality
- Better organization of relationship handling

**Estimated Effort:** 1 week

---

#### 4. Split `services/query_service.py` (~800 lines)

**Current State:** Contains search, filtering, and similarity logic

**Proposed Structure:**
```
services/query/
  __init__.py           # Main QueryService class
  search.py             # Search implementation
  filters.py            # Filter parsing and application
  similarity.py         # Similarity calculations
  builder.py            # Query builder (new)
  pagination.py         # Pagination utilities
  utils.py              # Shared utilities
```

**Benefits:**
- Modular query building capabilities
- Reusable query builder for other services
- Clearer separation of search vs. similarity
- Easier to extend with new filter types

**Estimated Effort:** 1-2 weeks

---

### Implementation Strategy

1. Start with `query_service.py` as it has the clearest boundaries
2. Extract query builder as a standalone utility first
3. Move to `processing_service.py` as it has the most independent modules
4. Complete with `rating_service.py` and `image_service.py`
5. Maintain backward compatibility during transition
6. Update all imports and tests incrementally
7. Validate no functionality is broken

---

## Phase 6C: Testing & Polish

**Priority:** High (for pre-existing failures), Medium (for others)  
**Estimated Effort:** Medium (1-2 weeks)  
**Status:** Deferred

### 1. Fix Pre-existing Test Failures

**Priority:** High  
**Estimated Effort:** 2-3 days

**Current Status:** 3 pre-existing test failures (unrelated to refactoring)

**Action Items:**
- Investigate and document the root cause of each failure
- Fix or update tests to match current behavior
- Ensure all tests pass before future development
- Add regression tests to prevent similar issues

---

### 2. Automated CSS Cache Versioning

**Priority:** Medium  
**Estimated Effort:** 2-3 days

**Current State:** Manual CSS versioning with `?v=25` query parameters

**Proposed Solution:**
```python
# Generate hash-based version from file content
def get_asset_version(filepath):
    """Generate content-based hash for cache busting"""
    with open(filepath, 'rb') as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()[:8]
    return file_hash

# Template helper
def versioned_url(asset_path):
    """Generate versioned URL for static assets"""
    version = get_asset_version(asset_path)
    return f"{asset_path}?v={version}"
```

**Benefits:**
- No manual version updates needed
- Automatic cache invalidation on file changes
- More reliable cache busting
- Developer convenience

**Implementation Notes:**
- Cache version hashes at startup to avoid repeated file reads
- Update all template references to use helper function
- Consider extending to JavaScript files as well

---

### 3. Add Type Hints to Service Files

**Priority:** Low  
**Estimated Effort:** 1-2 weeks (incremental)

**Current State:** Limited type hints in service layer

**Proposed Approach:**
- Add type hints incrementally, starting with public methods
- Use `typing` module for complex types
- Add return type annotations for all service methods
- Consider using `mypy` for type checking

**Example:**
```python
from typing import List, Dict, Optional, Tuple

async def fetch_metadata(
    self, 
    image_path: str, 
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Fetch metadata for an image from specified sources."""
    pass
```

**Benefits:**
- Better IDE autocomplete and error detection
- Improved code documentation
- Easier refactoring with type safety
- Better developer experience

---

## Other Future Enhancements

### Test Coverage Expansion

**Priority:** Medium  
**Estimated Effort:** Ongoing

**Areas for Improvement:**
- Increase unit test coverage for service layer
- Add integration tests for complex workflows
- Add end-to-end tests for critical user paths
- Test edge cases and error conditions

**Target Coverage:** 80%+ for core services

---

### Query Builder Implementation

**Priority:** Medium  
**Estimated Effort:** 1-2 weeks

**Purpose:** Create a reusable query builder for complex database operations

**Features:**
- Fluent interface for building SQL queries
- Type-safe query construction
- Support for complex joins and filters
- Pagination and sorting helpers
- Extensible for new query types

**Example Usage:**
```python
query = (QueryBuilder('images')
    .join('image_tags', 'images.id = image_tags.image_id')
    .where('rating = ?', 'safe')
    .where_in('source', ['danbooru', 'e621'])
    .order_by('created_at DESC')
    .limit(50)
    .build())
```

**Benefits:**
- Reduces SQL string concatenation
- Prevents SQL injection vulnerabilities
- Easier to test and maintain
- Reusable across multiple services

---

### Async/Sync Pattern Cleanup

**Priority:** Low  
**Estimated Effort:** 1 week

**Current State:** Mix of async and sync patterns in some areas

**Goal:** Standardize on async-first approach throughout the codebase

**Action Items:**
- Audit all service methods for async consistency
- Convert remaining sync methods to async where beneficial
- Document when sync methods are intentionally used
- Update all callers to use async patterns

---

### Distributed Caching with Redis

**Priority:** Low  
**Estimated Effort:** 2-3 weeks

**Use Case:** Multi-instance deployments or very large collections

**Features:**
- Replace in-memory cache with Redis backend
- Support distributed cache invalidation
- Session storage in Redis
- Background job queuing with Redis

**Benefits:**
- Horizontal scaling capability
- Persistent cache across restarts
- Better support for multiple workers
- Centralized session management

**Prerequisites:**
- Add Redis dependency
- Create cache abstraction layer
- Maintain backward compatibility with in-memory cache

---

### PostgreSQL Support

**Priority:** Low  
**Estimated Effort:** 3-4 weeks

**Use Case:** Very large datasets (500k+ images) or advanced query needs

**Benefits:**
- Better performance for extremely large datasets
- More advanced indexing options
- Better concurrency for multiple users
- JSONB support for flexible metadata storage

**Implementation Strategy:**
- Create database abstraction layer
- Support both SQLite and PostgreSQL
- Maintain SQLite as default for simplicity
- Provide migration scripts for existing databases

**Considerations:**
- SQLite performs well for most use cases (100k+ images)
- PostgreSQL adds deployment complexity
- Only implement if there's demonstrated need

---

## Contributing

When working on these enhancements:

1. **Review existing architecture:** Consult [ARCHITECTURE.md](ARCHITECTURE.md) and [SERVICES.md](SERVICES.md)
2. **Maintain consistency:** Follow established patterns from Phases 1-6A
3. **Write tests:** Add comprehensive tests for new functionality
4. **Document changes:** Update relevant documentation files
5. **Consider backward compatibility:** Avoid breaking existing functionality

---

## Related Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and patterns
- [Services Documentation](SERVICES.md) - Business logic layer
- [Database Schema](DATABASE.md) - Data models and relationships
- [Configuration Guide](CONFIGURATION.md) - Environment and settings

# Refactoring Next Steps

This document outlines the remaining and deferred tasks from the API standardization refactoring effort.

## Summary of Completed Work

**Phases 1-4 are complete:**
- ✅ Created decorator and logging infrastructure (`@api_handler`, logging config)
- ✅ Centralized tag extraction (~200 lines of duplicated code eliminated)
- ✅ Refactored 25+ API endpoints (~240 lines of boilerplate removed)
- ✅ All tests passing (96/104 tests, 3 pre-existing failures unrelated to refactoring)
- ✅ **Phase 4: Created utility modules for tag database, file paths, and JavaScript helpers**

**Total Impact:**
- ~550 lines of duplicated/boilerplate code eliminated
- 14 files refactored
- Consistent error handling across all API endpoints
- Centralized utilities for common operations

**What's Next:**
- Phase 5: 2 remaining medium-priority tasks (Notification standardization, Template JS extraction)
- Phase 6+: Future enhancements (Test coverage, Query builder, etc.)

---

## Phase 4 Completed Work

**Python Utilities:**
- ✅ Created `utils/tag_db.py` with centralized tag database operations
  - `insert_tag()` - Insert or update tags with category support
  - `bulk_insert_tags()` - Batch insert tags efficiently
  - `update_tag_category()` - Update tag categories
  - `get_or_create_tag()` - Convenience wrapper for tag creation
  - Proper error handling and logging
  - Full test coverage (16 tests)

- ✅ Enhanced `utils/file_utils.py` with path handling utilities
  - `normalize_image_path()` - Remove 'images/' prefix, handle Unicode
  - `validate_image_path()` - Security checks and file existence validation
  - `get_absolute_image_path()` - Convert relative to absolute paths
  - Full test coverage (20 tests)

**JavaScript Utilities:**
- ✅ Enhanced `static/js/utils/helpers.js` with shared functions
  - `getCategoryIcon()` - Get Unicode icons for tag categories
  - `getCategoryClass()` - Get CSS class names for categories
  - `formatTagCount()` - Format tag counts for display

- ✅ Created `static/js/utils/path-utils.js` for path handling
  - `encodeImagePath()` - URL-encode paths while preserving slashes
  - `normalizeImagePath()` - Remove 'images/' prefix
  - `getImageUrl()` - Generate full image URLs

- ✅ Created `static/js/utils/cache.js` for cache invalidation
  - `invalidateImageCache()` - Clear image-related cache
  - `invalidateTagCache()` - Clear tag-related cache
  - `invalidateAllCaches()` - Clear all caches

**Updated Files:**
- ✅ Updated `utils/__init__.py` to export new utility functions
- ✅ Updated `static/js/autocomplete.js` to use shared `getCategoryIcon()`
- ✅ Updated `static/js/tag-editor.js` to use shared `getCategoryIcon()`

**Testing:**
- ✅ Created `tests/test_tag_db.py` with 16 comprehensive tests
- ✅ Created `tests/test_file_utils.py` with 20 comprehensive tests
- ✅ All 36 new tests passing

---

## Deferred Tasks

These tasks were identified during the refactoring but explicitly deferred to future phases:

### Python Utilities (Low Priority)

#### 1. ~~Tag Database Utilities~~ ✅ COMPLETED IN PHASE 4

#### 2. ~~Path Handling Utilities (Python)~~ ✅ COMPLETED IN PHASE 4

### JavaScript Consolidation (Medium Priority)

#### 3. ~~Shared JavaScript Utilities~~ ✅ COMPLETED IN PHASE 4

#### 4. Notification System Standardization
**Estimated Effort:** Low
**Impact:** Low
**Risk:** Low

Standardize notification imports and usage across all JavaScript files:
```javascript
// Current: Mix of inline notifications and imported functions
// Target: All files import from notifications.js
import { showSuccess, showError, showInfo } from './utils/notifications.js';
```

**Files to Update:**
- All JavaScript files in `static/js/` directory

#### 5. Cache Invalidation Helpers
**Estimated Effort:** Low
**Impact:** Low
**Risk:** Low

Add cache invalidation utilities:
```javascript
// static/js/utils/cache.js
export function invalidateImageCache() {
    // Clear image-related cache
}

export function invalidateTagCache() {
    // Clear tag-related cache
}

export function invalidateAllCaches() {
    // Clear all caches
}
```

#### 6. Path Utilities (JavaScript)
**Estimated Effort:** Low
**Impact:** Medium
**Risk:** Low

Create JavaScript path handling utilities:

**File:** `static/js/utils/path-utils.js`
```javascript
export function encodeImagePath(path) {
    return encodeURIComponent(path).replace(/%2F/g, '/');
}

export function normalizeImagePath(path) {
    return path.replace(/^images\//, '');
}

export function getImageUrl(filepath) {
    return `/images/${encodeImagePath(filepath)}`;
}
```

#### 7. Extract Template JavaScript
**Estimated Effort:** Medium
**Impact:** Medium
**Risk:** Low

Move inline JavaScript from templates to dedicated page modules:

**Templates with inline JS to extract:**
- `templates/rate_manage.html` → `static/js/pages/rate-manage.js`
- `templates/rate_review.html` → `static/js/pages/rate-review.js`
- `templates/tag_categorize.html` → `static/js/pages/tag-categorize.js`

**Benefits:**
- Better code organization
- Easier testing
- Improved caching
- Better IDE support

---

## Remaining Deferred Tasks (Phase 5)

These are the remaining medium-priority tasks from the original deferred list:

### 1. Notification System Standardization
**Estimated Effort:** Low
**Impact:** Low
**Risk:** Low
**Priority:** Medium

**Goal:** Standardize notification imports and usage across all JavaScript files.

**Current State:** Mix of inline notifications and imported functions

**Target State:** All files import from notifications.js consistently
```javascript
import { showSuccess, showError, showInfo } from './utils/notifications.js';
```

**Files to Update:**
- All JavaScript files in `static/js/` directory that use notifications

**Benefits:**
- Consistent notification handling
- Easier to maintain and update
- Better code organization

### 2. Extract Template JavaScript
**Estimated Effort:** Medium
**Impact:** Medium
**Risk:** Low
**Priority:** Medium

**Goal:** Move inline JavaScript from templates to dedicated page modules.

**Templates with inline JS to extract:**
- `templates/rate_manage.html` → `static/js/pages/rate-manage.js`
- `templates/rate_review.html` → `static/js/pages/rate-review.js`
- `templates/tag_categorize.html` → `static/js/pages/tag-categorize.js`

**Benefits:**
- Better code organization
- Easier testing
- Improved caching
- Better IDE support
- Separation of concerns

---

## Future Enhancements (Phase 6+)

These are larger refactoring efforts that could be tackled in future phases:

### 1. Test Coverage Expansion
**Estimated Effort:** Medium
**Impact:** High
**Risk:** Low
**Priority:** High

Add tests for:
- Tag extraction utilities (all booru formats)
- API handler decorator (error cases)
- Integration tests for full workflows
- Edge cases in existing utilities

### 2. Query Builder Implementation
**Estimated Effort:** High
**Impact:** Medium
**Risk:** Medium
**Priority:** Medium

Create a query builder for complex database queries:
```python
# utils/query_builder.py
class QueryBuilder:
    def filter_by_tags(self, tags: list[str]):
        pass

    def filter_by_category(self, category: str):
        pass

    def paginate(self, offset: int, limit: int):
        pass
```

**Benefits:**
- Consistent query building
- Easier to test
- Reduce SQL injection risks
- Better maintainability

### 3. Async/Sync Pattern Cleanup
**Estimated Effort:** Medium
**Impact:** Low
**Risk:** Medium
**Priority:** Low

Standardize async/sync patterns across the codebase to reduce confusion about when to use `await`.

**Note:** Working fine currently, only tackle if causing actual issues.

### 4. Circular Import Resolution
**Estimated Effort:** High
**Impact:** Low
**Risk:** High
**Priority:** Low

Resolve circular dependencies in the import structure (if any exist).

**Note:** High risk change, only necessary if circular imports cause actual problems.

---

## Prioritization Recommendation

**Phase 5 (Do Next):**
1. ⏭️ Notification System Standardization - Low effort, improves consistency
2. ⏭️ Extract Template JavaScript - Medium effort, better organization

**Phase 6 (Future):**
1. Test Coverage Expansion - Protect against regressions
2. Query Builder Implementation - Nice to have, improves maintainability

**Low Priority (Optional):**
1. Async/sync cleanup - Working fine, medium risk
2. Circular import resolution - Working fine, high risk

---

## Maintenance Notes

### Guidelines for Future Development

To prevent code duplication from returning:

1. **Before adding new API endpoints:**
   - Always use `@api_handler()` decorator
   - Raise `ValueError` for validation errors (400 response)
   - Raise `FileNotFoundError` for missing resources (404 response)
   - Raise `PermissionError` for auth failures (403 response)
   - Return dict directly (decorator adds `success: true`)

2. **Before extracting tags from booru sources:**
   - Always use `utils.tag_extraction.extract_tags_from_source()`
   - Use `extract_rating_from_source()` for ratings
   - Use `deduplicate_categorized_tags()` to remove duplicates

3. **Before adding constants:**
   - Check if constant belongs in `config.py` (Defaults, Timeouts, Thresholds, Limits)
   - Use existing constants instead of magic numbers

4. **Before adding logging:**
   - Use `get_logger(__name__)` from `utils.logging_config`
   - Don't create new logger instances directly

### Code Review Checklist

When reviewing new code:
- [ ] Are all API endpoints using `@api_handler()`?
- [ ] Is tag extraction using centralized utilities?
- [ ] Are constants defined in `config.py` instead of hardcoded?
- [ ] Is logging using `get_logger()` from utils?
- [ ] Are file paths normalized consistently?
- [ ] Are errors raised with appropriate exception types?

---

## Questions or Suggestions?

If you have questions about these next steps or want to propose changes to priorities, please open a GitHub issue with the tag `refactoring`.

---

**Document Version:** 2.1
**Last Updated:** 2025-12-10
**Related:** See `REFACTOR.md` for full refactoring analysis and completed work

---

## Document Change Log

- **v2.1 (2025-12-10)**: Reorganized remaining tasks into Phase 5 and Phase 6+ sections for clarity
- **v2.0 (2025-12-10)**: Updated with Phase 4 completion status
- **v1.0 (2025-12-10)**: Initial document with deferred tasks from refactoring effort

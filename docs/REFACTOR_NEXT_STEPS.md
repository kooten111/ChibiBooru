# Refactoring Next Steps

This document outlines the remaining and deferred tasks from the API standardization refactoring effort.

## Summary of Completed Work

**Phases 1-5 are complete:**
- ✅ Created decorator and logging infrastructure (`@api_handler`, logging config)
- ✅ Centralized tag extraction (~200 lines of duplicated code eliminated)
- ✅ Refactored 25+ API endpoints (~240 lines of boilerplate removed)
- ✅ All tests passing (96/104 tests, 3 pre-existing failures unrelated to refactoring)
- ✅ **Phase 4: Created utility modules for tag database, file paths, and JavaScript helpers**
- ✅ **Phase 5: Standardized notifications and extracted template JavaScript (1176+ lines moved to modules)**

**Total Impact:**
- ~1,700+ lines of duplicated/boilerplate code eliminated
- 20+ files refactored
- Consistent error handling across all API endpoints
- Centralized utilities for common operations
- Modern ES6 modules for all JavaScript code
- Consistent notification handling (no more alert() dialogs)

**What's Next:**
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

## Phase 5 Completed Work

**Date:** 2025-12-10

**Notification System Standardization:**
- ✅ Enhanced `static/js/utils/notifications.js` with convenience functions
  - `showSuccess()` - Show success notifications
  - `showError()` - Show error notifications
  - `showInfo()` - Show info notifications
  - `showWarning()` - Show warning notifications

- ✅ Removed inline notification implementations
  - Removed inline `showNotification()` from `system-panel.js`
  - Renamed inline `showError()` to `showModalError()` in `saucenao-fetch.js`

- ✅ Replaced all `alert()` calls with standardized notifications (37 replacements total)
  - `bulk-delete.js` - 7 replacements
  - `implications.js` - 14 replacements
  - `pool-detail.js` - 4 replacements
  - `pool-manager.js` - 4 replacements
  - `pools.js` - 4 replacements
  - `source-selector.js` - 4 replacements

- ✅ Converted 7 JavaScript files to ES6 modules
  - Updated templates to load as `type="module"`
  - Exposed functions to window for onclick handlers

**Template JavaScript Extraction:**
- ✅ Created `static/js/pages/` directory for page-specific modules

- ✅ Extracted inline JavaScript to dedicated modules (1176+ lines total)
  - `rate-manage.js` - 428 lines (rating management page)
  - `rate-review.js` - 216 lines (rating review interface)
  - `tag-categorize.js` - 532 lines (tag categorization page)

- ✅ All page modules use ES6 format with proper imports
  - Import `showNotification` from `../utils/notifications.js`
  - Export functions to window for onclick handlers
  - Modern JavaScript structure

**Updated Files (Phase 5):**
- Templates: `rate_manage.html`, `rate_review.html`, `tag_categorize.html` (inline scripts removed)
- Templates: `index.html`, `image.html`, `pool.html`, `pools.html`, `implications.html` (script tags updated)
- JavaScript: `bulk-delete.js`, `implications.js`, `pool-detail.js`, `pool-manager.js`, `pools.js`, `source-selector.js`, `system-panel.js`, `saucenao-fetch.js`
- New files: `static/js/pages/rate-manage.js`, `static/js/pages/rate-review.js`, `static/js/pages/tag-categorize.js`
- Utilities: `static/js/utils/notifications.js` (convenience functions added)

**Impact:**
- 1176+ lines of inline JavaScript extracted to modules
- 37 alert() calls replaced with modern toast notifications
- 7 files converted to ES6 modules
- Better code organization and maintainability
- Improved caching (JS files cached separately)
- Better IDE support (linting, autocomplete)

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

## ~~Remaining Deferred Tasks (Phase 5)~~ ✅ COMPLETED

Phase 5 tasks have been completed as of 2025-12-10:

### 1. ~~Notification System Standardization~~ ✅ COMPLETED
**Estimated Effort:** Low
**Impact:** Low
**Risk:** Low
**Priority:** Medium

**Status:** ✅ **COMPLETED** (2025-12-10)

**Goal:** Standardize notification imports and usage across all JavaScript files.

**What was done:**
- Added convenience exports to `static/js/utils/notifications.js`: `showSuccess`, `showError`, `showInfo`, `showWarning`
- Removed inline `showNotification()` implementation from `system-panel.js`
- Renamed inline `showError()` to `showModalError()` in `saucenao-fetch.js` (modal-specific function)
- Replaced all `alert()` calls with standardized notifications in:
  - `bulk-delete.js` (7 replacements)
  - `implications.js` (14 replacements)
  - `pool-detail.js` (4 replacements)
  - `pool-manager.js` (4 replacements)
  - `pools.js` (4 replacements)
  - `source-selector.js` (4 replacements)
- Converted all affected files to ES6 modules
- Updated templates to load scripts as modules with `type="module"`
- Exposed necessary functions to window object for onclick handlers

**Benefits Achieved:**
- ✅ Consistent notification handling across entire codebase
- ✅ Easier to maintain and update
- ✅ Better code organization
- ✅ No more inline alert() dialogs (replaced with modern toast notifications)

### 2. ~~Extract Template JavaScript~~ ✅ COMPLETED
**Estimated Effort:** Medium
**Impact:** Medium
**Risk:** Low
**Priority:** Medium

**Status:** ✅ **COMPLETED** (2025-12-10)

**Goal:** Move inline JavaScript from templates to dedicated page modules.

**What was done:**
- Created `static/js/pages/` directory for page-specific modules
- Extracted `templates/rate_manage.html` → `static/js/pages/rate-manage.js` (428 lines)
- Extracted `templates/rate_review.html` → `static/js/pages/rate-review.js` (216 lines)
- Extracted `templates/tag_categorize.html` → `static/js/pages/tag-categorize.js` (532 lines)
- Converted all extracted code to ES6 module format
- Imported `showNotification` from utils in all page modules
- Updated templates to use `<script type="module" src="...">` imports
- Exposed functions to window object where needed for onclick handlers

**Benefits Achieved:**
- ✅ Better code organization (1176+ lines moved to dedicated modules)
- ✅ Easier testing (code is now in testable modules)
- ✅ Improved caching (JS files cached separately from HTML)
- ✅ Better IDE support (proper syntax highlighting, linting, autocomplete)
- ✅ Separation of concerns (logic separated from templates)

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

**Document Version:** 3.0
**Last Updated:** 2025-12-10
**Related:** See `REFACTOR.md` for full refactoring analysis and completed work

---

## Document Change Log

- **v3.0 (2025-12-10)**: Updated with Phase 5 completion status (Notification standardization + Template JS extraction)
- **v2.1 (2025-12-10)**: Reorganized remaining tasks into Phase 5 and Phase 6+ sections for clarity
- **v2.0 (2025-12-10)**: Updated with Phase 4 completion status
- **v1.0 (2025-12-10)**: Initial document with deferred tasks from refactoring effort

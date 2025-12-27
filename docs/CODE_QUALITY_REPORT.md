# ChibiBooru Code Quality Report

**Generated:** 2025-12-27  
**Repository:** kooten111/ChibiBooru

This document summarizes code quality issues identified during a comprehensive code review.  Issues are categorized by priority and type to facilitate systematic cleanup.

---

## Table of Contents

1. [Critical Issues](#critical-issues)
2. [Duplicate Code](#duplicate-code)
3. [TODO/FIXME Items](#todofixme-items)
4. [Dead Code & Unused Elements](#dead-code--unused-elements)
5. [Code Quality Issues](#code-quality-issues)
6. [Security Considerations](#security-considerations)
7. [Recommended New Utilities](#recommended-new-utilities)
8. [Action Plan](#action-plan)

---

## Critical Issues

### 1. Thumbnail Path Construction Ignores Bucketed Structure

**Priority:** 🔴 Critical  
**Impact:** Thumbnails won't be found/deleted when using bucketed directory structure

The codebase has `get_thumbnail_path()` in `utils/file_utils.py` which properly handles bucketed thumbnails, but multiple places manually construct thumbnail paths incorrectly: 

| File | Line | Problematic Code |
|------|------|------------------|
| `services/image_service.py` | ~78 | `thumb_path = os.path.join("static/thumbnails", os.path.splitext(filepath)[0] + '.webp')` |
| `services/image_service.py` | ~142 | Same pattern in `delete_images_bulk_service()` |
| `utils/deduplication. py` | ~78 | `thumb_path = os.path.join("./static/thumbnails", os.path.splitext(rel_path)[0] + '.webp')` |

**Problem:** These paths don't include the bucket directory (e.g., `abc/`) so they will fail to find thumbnails in the bucketed structure.

**Solution:** Use `get_thumbnail_path()` from `utils/file_utils.py` or create a new `get_bucketed_thumbnail_path_on_disk()` utility. 

---

### 2. Hardcoded Absolute Path

**Priority:** 🔴 Critical  
**File:** `services/similarity_service.py` line ~262

```python
self.model_path = "/mnt/Server/ChibiBooru/models/Similarity/model.onnx"
```

**Problem:** This absolute path will break on any other system.

**Solution:** Move to `config.py`:
```python
SEMANTIC_MODEL_PATH = os.environ.get('SEMANTIC_MODEL_PATH', './models/Similarity/model. onnx')
```

---

### 3. Duplicate Dictionary Key

**Priority:** 🔴 Bug  
**File:** `services/system_service.py` line ~105

```python
return jsonify({
    ... 
    "cleaned":  cleaned_count,
    "cleaned":  cleaned_count,  # DUPLICATE KEY! 
    "orphaned_tags_cleaned": orphaned_tags_count
})
```

**Solution:** Remove the duplicate line.

---

## Duplicate Code

### 1. MD5 Hash Calculation (3 implementations)

| File | Function | Notes |
|------|----------|-------|
| `utils/deduplication.py:16` | `get_md5(filepath)` | Takes full path |
| `utils/file_utils.py:98` | `get_file_md5(filepath)` | Prepends `static/` |
| `services/processing_service.py:614` | `get_md5(filepath)` | Takes full path |

**Solution:** Consolidate into single function in `utils/file_utils.py`, deprecate others.

---

### 2. Path Normalization Pattern

The pattern `filepath.replace('images/', '', 1)` appears in 10+ locations:

- `services/image_service.py` (lines 57, 134, 202, 246)
- `routers/web. py` (lines 207, 418, 447)
- `services/saucenao_service.py` (line 103)
- And more...

**Solution:** Use existing `utils/file_utils.py:normalize_image_path()` consistently.

---

### 3. Thumbnail Path Construction (scattered implementations)

Multiple files manually construct bucketed thumbnail paths instead of using a shared utility:

| File | Code Pattern |
|------|--------------|
| `services/health_service.py` | `bucket = get_hash_bucket(filename); thumb_path = os.path.join(config.THUMB_DIR, bucket, ...)` |
| `services/processing_service.py` | Same pattern |
| `services/zip_animation_service.py` | Same pattern |

**Solution:** Create `get_bucketed_thumbnail_path()` utility function. 

---

### 4. Image Deletion Logic

Nearly identical code in `services/image_service.py`:
- `delete_image_service()` (lines 52-114)
- `delete_images_bulk_service()` (lines 116-178)

Both contain: 
- Path normalization
- Thumbnail path construction
- File deletion
- Cache invalidation

**Solution:** Extract to shared helper function `_delete_image_files()`.

---

### 5. SauceNAO URL Parsing

Repeated URL parsing logic in `services/image_service.py`:
- `retry_tagging_service()` (lines 280-309)
- `_process_bulk_retry_tagging_task()` (lines 606-631)

```python
if 'danbooru. donmai.us' in url:
    post_id = url.split('/posts/')[-1]. split('? ')[0]
    source = 'danbooru'
elif 'e621.net' in url:
    post_id = url.split('/posts/')[-1].split('?')[0]
    source = 'e621'
```

**Solution:** Create `parse_booru_url()` utility function.

---

### 6. Tag Database Update Logic

Similar tag insertion/update loops in: 
- `retry_tagging_service()` (lines 432-463)
- `_process_bulk_retry_tagging_task()` (lines 740-756)

**Solution:** Create `update_image_tags()` helper in a repository module.

---

### 7. Order Filter Logic in Query Service

Duplicated in `services/query_service.py`:
- Inside `_fts_search()` (lines 355-405)
- Inside `perform_search()` (lines 694-754)

**Solution:** Extract to `_apply_order_filter()` helper function.

---

### 8. Thumbnail Creation Image Processing

Identical image processing code in:
- `services/processing_service.py:ensure_thumbnail()` (~lines 693-702)
- `services/zip_animation_service.py:create_thumbnail_from_animation()` (~lines 237-250)

```python
if img.mode in ('RGBA', 'LA', 'P'):
    background = Image.new('RGB', img.size, (255, 255, 255))
    if img.mode == 'P':  img = img.convert('RGBA')
    background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
    img = background
img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image. Resampling.LANCZOS)
img.save(thumb_path, 'WEBP', quality=85, method=6)
```

**Solution:** Create `utils/image_processing.py` with `convert_and_resize_for_thumbnail()`.

---

## TODO/FIXME Items

### JavaScript

| File | Line | TODO | Priority |
|------|------|------|----------|
| `static/js/animation-player.js` | ~297 | `// TODO: Implement full GIF frame extraction or use gifuct-js` | Medium |

**Context:** GIF parser only shows first frame.  Suggests using `gifuct-js` library.

---

### Python

| File | Line | TODO | Priority |
|------|------|------|----------|
| `services/similarity_service.py` | ~250 | `return None # TODO: Implement zip colorhash` | Low |
| `services/implication_service.py` | ~420 | `'conflicts': [] # TODO:  Detect conflicts (e.g., circular implications)` | Medium |

---

## Dead Code & Unused Elements

### 1. Unused Imports

| File | Import | Status |
|------|--------|--------|
| `services/image_service.py` | `import requests` | Possibly unused |
| `services/image_service.py` | `import uuid` | Only used once, could be local |

### 2. Unused Variables in GIF Parser

**File:** `static/js/animation-player.js`

```javascript
const hasGlobalColorTable = !!(flags & 0x80);  // Defined but never used
const colorTableSize = 1 << ((flags & 0x07) + 1);  // Defined but never used
```

### 3. Potentially Wrong Import

**File:** `services/implication_service.py` line ~437

```python
from database_models import apply_implications_for_image
```

Should probably be: 
```python
from database.models import apply_implications_for_image
```

---

## Code Quality Issues

### 1. Inconsistent Code Style & Architecture

#### Python Logging vs Print
**Observation:** The codebase has a dedicated logging utility `utils/logging_config.py`, but its usage is sporadic.
- **Modern/Correct:** `app.py` properly initializes and uses `variable = get_logger('App')`.
- **Legacy/Inconsistent:** Most service files (e.g., `services/image_service.py`) heavily rely on `print()` statements for debugging and status updates.
**Impact:** `print()` statements output to stdout/stderr without timestamps, log levels, or proper formatting, making production debugging and log filtering difficult.

#### JavaScript Architectural Inconsistency
**Observation:** The frontend code exhibits a split personality between legacy and modern practices.
- **Legacy Pattern (Script-Tag Style):** Files like `static/js/gallery.js` and `static/js/image-page.js` rely on:
    - IIFE (Immediately Invoked Function Expressions) for encapsulation.
    - Exposing functions to the global `window` object for HTML `onclick` handlers (e.g., `window.confirmRetryTagging`).
    - Manual DOM manipulation without a unified state management strategy.
- **Modern Pattern (ES6 Modules/Classes):** Files like `static/js/tag-editor.js` demonstrate a better direction:
    - Use of ES6 `class` syntax (`class TagEditor`).
    - Use of `import/export` modules.
    - Better encapsulation and state management within the class instance.

#### JavaScript Notification System
**Observation:** Notifications are handled inconsistently.
- `tag-editor.js` uses a modern `showNotification` utility.
- `image-page.js` has a fallback that degrades to `alert()` if dependencies aren't met: `const notifier = window.tagEditor || { showNotification: (msg, type) => alert(...) }`.
**Impact:** Inconsistent user experience; `alert()` blocks the UI thread.

### 2. Missing Testing Infrastructure
**Priority:** 🔴 Critical
**Observation:**
- No active test suite found.
- `requirements.txt` lists `pytest` and `coverage` as commented-out optional properties.
- `grep` for "test" revealed no test files.
**Impact:** High risk of regression bugs when refactoring or adding features. Any change to `image_service.py` or database queries requires manual verification.

### 3. Database "God Functions"
**File:** `repositories/data_access.py`
**Observation:**
- `add_image_with_metadata` (lines ~491-643) is a ~150 line function.
- It handles: Transaction management, Tag parsing, Source linking, Metadata insertion, Rating inference, Score extraction, Image table updates.
**Impact:** Hard to test, hard to debug, and violates Single Responsibility Principle.

### 4. Documentation Gaps
**Observation:**
- **Python:** Generally good docstrings (e.g., `repositories/data_access.py`), but type hints are inconsistent.
- **JavaScript:** `gallery.js` has file-level comments but lacks function-level JSDoc. `tag-editor.js` contains debug `console.log` statements (`console.log('toggleEditMode called...')`).

---

## Technical Debt & Maintenance

### 1. CSS Maintainability
**File:** `static/css/components.css`
**Observation:** This single file is over 5400 lines long.
- **Issue 1: Monolithic Structure:** It contains styles for the Header, Search, System Panel, Gallery, Image View, Tags, Actions, Carousel, and more. This makes finding and editing specific styles cumbersome.
- **Issue 2: Specificity Wars:** There is heavy use of `!important` to override styles (e.g., in `.header`, `.header-content`, `.search-bar`). This indicates a struggle with CSS specificity and makes future custom overrides difficult without also using `!important`.

### 2. Bare `except:` Clauses

| File | Line | Code |
|------|------|------|
| `utils/file_utils.py` | ~106 | `except: return None` |
| `services/processing_service.py` | ~243 | `except: pass` |

**Problem:** Silently catches all exceptions including `KeyboardInterrupt`, `SystemExit`.

**Solution:** Use specific exception types:
```python
except (IOError, OSError) as e:
    logger.warning(f"Failed to read file: {e}")
    return None
```

---

### 2. Print Statements Instead of Logging

The codebase has `utils/logging_config.py` with `get_logger()`, but many files still use `print()`:

```python
# Current (throughout codebase)
print(f"[DELETE] Received filepath from frontend: {data. get('filepath')}")
print(f"[SauceNAO] Converted {os.path.basename(filepath)}...")

# Should be
logger = get_logger('ImageService')
logger.info(f"Received filepath from frontend: {data. get('filepath')}")
```

**Affected files:** Most service files in `services/` directory. 

---

### 3. File Extension Checks Not Centralized

Pattern repeated in multiple files:
```python
filepath. lower().endswith(('.png', '.jpg', '.jpeg', '. gif', '.webp', '.mp4'))
```

**Solution:** Use `config. SUPPORTED_IMAGE_EXTENSIONS` or similar constant.

---

## Security Considerations

### Default Secrets That Must Be Changed

| Setting | Default Value | File |
|---------|---------------|------|
| `RELOAD_SECRET` | `"change-this-secret"` | config.py |
| `SECRET_KEY` | `"your-super-secret-key"` | .env.example |
| `APP_PASSWORD` | `"changeme"` | .env.example |

**Recommendation:** Add startup warning if defaults are detected in production.

---

## Recommended New Utilities

### 1. `utils/file_utils.py` additions

```python
def get_bucketed_thumbnail_path(filename:  str, as_disk_path: bool = False) -> str:
    """
    Get the bucketed thumbnail path for a filename.
    
    Args:
        filename: The image filename (not full path)
        as_disk_path: If True, return full disk path.  If False, return relative URL path.
    
    Returns:
        Thumbnail path like "thumbnails/abc/image.webp" or "./static/thumbnails/abc/image.webp"
    """
    bucket = get_hash_bucket(filename)
    thumb_filename = os.path.splitext(filename)[0] + '.webp'
    
    if as_disk_path:
        return os.path.join(config.THUMB_DIR, bucket, thumb_filename)
    return f"thumbnails/{bucket}/{thumb_filename}"
```

### 2. `utils/url_parsing.py` (new file)

```python
def parse_booru_url(url: str) -> tuple[str, str] | tuple[None, None]:
    """
    Parse a booru URL to extract source and post ID.
    
    Returns:
        (source, post_id) or (None, None) if not recognized
    """
    if 'danbooru.donmai. us' in url:
        post_id = url.split('/posts/')[-1].split('?')[0]
        return 'danbooru', post_id
    elif 'e621.net' in url:
        post_id = url.split('/posts/')[-1].split('?')[0]
        return 'e621', post_id
    # ... other sources
    return None, None
```

### 3. `utils/image_processing.py` (new file)

```python
from PIL import Image

def prepare_image_for_thumbnail(img: Image. Image) -> Image.Image:
    """Convert image to RGB mode suitable for WebP thumbnail."""
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P': 
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
        return background
    return img. convert('RGB') if img.mode != 'RGB' else img


def create_thumbnail(source_path: str, dest_path: str, max_size: int = 1000, quality: int = 85) -> bool:
    """Create a WebP thumbnail from source image."""
    try:
        os.makedirs(os.path. dirname(dest_path), exist_ok=True)
        with Image.open(source_path) as img:
            img = prepare_image_for_thumbnail(img)
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img.save(dest_path, 'WEBP', quality=quality, method=6)
        return True
    except Exception as e:
        logger.error(f"Failed to create thumbnail:  {e}")
        return False
```

---

## Recommended Standards

### 1. Python Logging Standard
All new and refactored Python files should use the centralized logger:
```python
from utils.logging_config import get_logger

logger = get_logger('ServiceName')

def some_process():
    try:
        logger.info("Starting process...")
        # ... logic ...
    except Exception as e:
        logger.error(f"Process failed: {e}", exc_info=True)
```

### 2. JavaScript Modernization Standard
- **No Global Scope:** Avoid `window.functionName = ...` assignment. Use `addEventListener` in JS to bind events to DOM elements.
- **ES6 Modules:** Use `import` / `export` for dependencies.
- **Classes:** Encapsulate related functionality (like a "page" or "component") into Classes.
- **Unified Notifications:** Always import and use `showNotification` from `./utils/notifications.js`.

### 3. Database Access
- **No God Functions:** Break complex transactions like image ingestion into smaller, composable steps:
    - `create_image_record()`
    - `link_image_sources()`
    - `process_image_tags()`
- **Type Hints:** All repository functions must have type hints.

### 4. CSS Organization
- **Split by Component:** Break `components.css` into smaller files: `header.css`, `gallery.css`, `image-viewer.css`, `system-panel.css`.
- **Remove !important:** Refactor selectors to use proper specificity nesting instead of force-overriding.

---

## Action Plan

### Phase 1: Critical Fixes (High Priority)

- [ ] Fix thumbnail path construction in `image_service.py` and `deduplication.py`
- [ ] Move hardcoded model path to config
- [ ] Fix duplicate dictionary key in `system_service.py`
- [ ] Fix import in `implication_service.py`

### Phase 2: Consolidate Utilities (Medium Priority)

- [ ] Consolidate MD5 functions into single implementation
- [ ] Create `get_bucketed_thumbnail_path()` utility
- [ ] Create `parse_booru_url()` utility
- [ ] Create image processing utilities
- [ ] Replace `filepath.replace('images/', '', 1)` with `normalize_image_path()`

### Phase 3: Code Cleanup (Lower Priority)

- [ ] JavaScript Modernization
    - [ ] Refactor `image-page.js` to remove `window` global assignments.
    - [ ] Replace `alert()` fallbacks with proper `showNotification` imports.
- [ ] Python Logging Standardization
    - [ ] Replace `print()` with `get_logger()` calls in `services/`.
- [ ] CSS Refactoring
    - [ ] Split `components.css` into smaller, component-specific files.
    - [ ] Reduce usage of `!important` in header/search styles.
- [ ] Extract shared deletion logic in `image_service.py`
- [ ] Extract order filter logic in `query_service.py`
- [ ] Replace bare `except:` with specific exceptions
- [ ] Centralize file extension constants
- [ ] Remove debug `console.log` from `tag-editor.js`

### Phase 4: Infrastructure (New)
- [ ] Initialize `pytest` environment
- [ ] Create basic smoke tests for API endpoints
- [ ] Refactor `add_image_with_metadata` into smaller services
- [ ] Formalize `requirements-dev.txt` for testing tools

### Phase 5: Feature Completion (When Time Permits)

- [ ] Implement full GIF frame extraction or integrate gifuct-js
- [ ] Implement zip colorhash
- [ ] Implement circular implication detection
- [ ] Add startup warning for default secrets

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Critical Issues | 3 |
| Duplicate Code Patterns | 8 |
| TODO Items | 3 |
| Dead/Unused Code | 4 |
| Code Quality Issues | 3 |
| Security Considerations | 3 |

**Total Issues:** ~24

---

*This report was generated by analyzing the kooten111/ChibiBooru repository. Some results may be incomplete due to search limitations.  For complete results, search the repository directly on GitHub.*
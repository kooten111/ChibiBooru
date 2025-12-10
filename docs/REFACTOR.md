# ChibiBooru Refactoring Opportunities & Technical Debt Analysis

**Date:** December 2025  
**Repository:** kooten111/ChibiBooru  
**Analysis Scope:** Code duplication, inconsistent patterns, consolidation opportunities

---

## Executive Summary

This document identifies significant code duplication and inconsistent patterns across the ChibiBooru codebase.  The main areas of concern are:

1. **Tag Extraction & Writing** - Same logic duplicated in 5+ files with slight variations
2. **API Response Formats** - At least 3 different success/error response patterns
3. **Filepath Handling** - Path encoding/normalization repeated everywhere
4. **Logging** - Using print() statements instead of proper logging framework
5. **Exception Handling** - Identical try/except boilerplate in 30+ endpoints
6. **JavaScript Utilities** - Helper functions duplicated across JS files
7. **Magic Numbers** - Hardcoded values scattered throughout without constants

Consolidating these patterns will:
- Reduce bugs from inconsistent implementations
- Make future changes easier (single source of truth)
- Improve code maintainability
- Reduce overall codebase size by an estimated 500+ lines

---

## Table of Contents

### High Priority
1. [Tag Extraction from Sources](#1-tag-extraction-from-sources)
2. [API Response Format Inconsistency](#2-api-response-format-inconsistency) ✅ **COMPLETED**
3. [Exception Handling Boilerplate](#3-exception-handling-boilerplate)
4. [Logging Framework](#4-logging-framework)
5. [Tag Writing to Database](#5-tag-writing-to-database)

### Medium Priority
6. [Filepath Handling - Python](#6-filepath-handling---python)
7. [Filepath Handling - JavaScript](#7-filepath-handling---javascript)
8. [Magic Numbers](#8-magic-numbers)
9. [Supported File Extensions](#9-supported-file-extensions)
10. [Pagination Response Inconsistency](#10-pagination-response-inconsistency)
11. [Tag Deduplication Logic](#11-tag-deduplication-logic)

### Lower Priority
12. [Notification System](#12-notification-system)
13. [Rating Tag Handling](#13-rating-tag-handling)
14. [Cache Invalidation Patterns](#14-cache-invalidation-patterns)
15. [JavaScript Utility Functions](#15-javascript-utility-functions)
16. [Async/Sync Mixing Pattern](#16-asyncsync-mixing-pattern)
17. [DOM Element Creation](#17-dom-element-creation)
18. [Circular Import Pattern](#18-circular-import-pattern)
19. [Query Service Complexity](#19-query-service-complexity)
20. [Template Inline JavaScript](#20-template-inline-javascript)
21. [Inline CSS in JavaScript](#21-inline-css-in-javascript)

### Already Well-Organized
22. [Database Connection Patterns](#22-database-connection-patterns)

---

## High Priority

---

### 1. Tag Extraction from Sources

#### Problem

The logic for extracting categorized tags from different booru sources (danbooru, e621, pixiv, local_tagger) is **duplicated in at least 5 files** with slight variations that can cause bugs. 

#### Affected Files

| File | Lines | Context |
|------|-------|---------|
| `services/processing_service.py` | 1099-1174 | Initial image processing |
| `services/image_service.py` | 709-792 | Bulk retry tagging |
| `services/image_service.py` | 428-528 | Single image retry tagging |
| `database/models. py` | 165-249 | Database repopulation |
| `services/switch_source_db.py` | 284-379 | Source merging |

#### Current Duplicated Pattern

```python
# This pattern appears in MULTIPLE files with slight variations: 

if source_name == 'danbooru': 
    tags_character = primary_source_data.get("tag_string_character", "")
    tags_copyright = primary_source_data.get("tag_string_copyright", "")
    tags_artist = primary_source_data.get("tag_string_artist", "")
    tags_meta = primary_source_data.get("tag_string_meta", "")
    tags_general = primary_source_data.get("tag_string_general", "")
elif source_name in ['e621', 'local_tagger', 'pixiv']: 
    tags = primary_source_data.get("tags", {})
    t_char = tags.get("character", [])
    t_copy = tags.get("copyright", [])
    t_art = tags.get("artist", [])
    t_spec = tags.get("species", [])
    t_meta = tags.get("meta", [])
    t_gen = tags.get("general", [])
    
    tags_character = " ".join(t_char)
    tags_copyright = " ".join(t_copy)
    # ... etc
```

#### Issues with Current Implementation

1. **Danbooru handling varies** - Some files check for `tag_string_general`, others don't
2. **Species handling inconsistent** - Danbooru doesn't have species, but some implementations set it to empty string, others to None
3. **Pixiv + local_tagger merging** - Only done in some places, not others
4. **Gelbooru/Yandere handling** - Missing in some implementations

#### Proposed Solution

Create `utils/tag_extraction.py`:

```python
"""
Centralized tag extraction utilities. 
All tag extraction from booru sources should use these functions.
"""

from typing import Dict, Tuple, Optional, List

# Standard tag categories used throughout the application
TAG_CATEGORIES = ['character', 'copyright', 'artist', 'species', 'meta', 'general']

# Mapping from category names to database column names
TAG_COLUMN_MAP = {
    'character': 'tags_character',
    'copyright': 'tags_copyright',
    'artist': 'tags_artist',
    'species':  'tags_species',
    'meta': 'tags_meta',
    'general': 'tags_general'
}

# Rating constants
RATING_CATEGORY = 'rating'
RATING_TAGS = ['rating: general', 'rating: sensitive', 'rating: questionable', 'rating:explicit']
RATING_MAP = {
    'g': 'rating:general',
    's': 'rating: sensitive',
    'q': 'rating:questionable',
    'e': 'rating:explicit'
}


def extract_tags_from_source(source_data: dict, source_name: str) -> dict:
    """
    Extract categorized tags from any booru source data.
    
    This is THE SINGLE SOURCE OF TRUTH for tag extraction.
    All services should use this function instead of inline extraction.
    
    Args:
        source_data: Raw metadata dict from the booru source
        source_name: Name of the source ('danbooru', 'e621', 'pixiv', 'local_tagger', etc.)
    
    Returns: 
        dict with keys:  tags_character, tags_copyright, tags_artist,
                       tags_species, tags_meta, tags_general
        All values are space-separated strings. 
    """
    if source_name == 'danbooru': 
        return _extract_danbooru_tags(source_data)
    elif source_name == 'e621': 
        return _extract_e621_tags(source_data)
    elif source_name in ['local_tagger', 'camie_tagger']: 
        return _extract_local_tagger_tags(source_data)
    elif source_name == 'pixiv': 
        return _extract_pixiv_tags(source_data)
    elif source_name in ['gelbooru', 'yandere']: 
        return _extract_gelbooru_tags(source_data)
    else:
        # Unknown source - try generic extraction
        return _extract_generic_tags(source_data)


def _extract_danbooru_tags(source_data:  dict) -> dict:
    """Extract tags from Danbooru format."""
    return {
        'tags_character': source_data.get("tag_string_character", ""),
        'tags_copyright':  source_data.get("tag_string_copyright", ""),
        'tags_artist': source_data. get("tag_string_artist", ""),
        'tags_species': "",  # Danbooru doesn't have species
        'tags_meta': source_data. get("tag_string_meta", ""),
        'tags_general': source_data.get("tag_string_general", ""),
    }


def _extract_e621_tags(source_data: dict) -> dict:
    """Extract tags from e621 format."""
    tags = source_data.get("tags", {})
    return {
        'tags_character': " ". join(tags.get("character", [])),
        'tags_copyright': " ".join(tags.get("copyright", [])),
        'tags_artist': " ".join(tags.get("artist", [])),
        'tags_species':  " ".join(tags. get("species", [])),
        'tags_meta': " ". join(tags.get("meta", [])),
        'tags_general': " ".join(tags.get("general", [])),
    }


def _extract_local_tagger_tags(source_data:  dict) -> dict:
    """Extract tags from local tagger format (same as e621)."""
    return _extract_e621_tags(source_data)


def _extract_pixiv_tags(source_data: dict) -> dict:
    """Extract tags from Pixiv format."""
    return _extract_e621_tags(source_data)


def _extract_gelbooru_tags(source_data: dict) -> dict:
    """Extract tags from Gelbooru/Yandere format (tags only, no categories)."""
    all_tags = source_data.get("tags", "")
    if isinstance(all_tags, list):
        all_tags = " ". join(all_tags)
    
    return {
        'tags_character':  "",
        'tags_copyright': "",
        'tags_artist':  "",
        'tags_species': "",
        'tags_meta': "",
        'tags_general': all_tags,
    }


def _extract_generic_tags(source_data: dict) -> dict:
    """Fallback extraction for unknown sources."""
    # Try e621-style first
    if "tags" in source_data and isinstance(source_data["tags"], dict):
        return _extract_e621_tags(source_data)
    
    # Try danbooru-style
    if "tag_string_general" in source_data:
        return _extract_danbooru_tags(source_data)
    
    # Give up - return empty
    return {f'tags_{cat}': '' for cat in TAG_CATEGORIES}


def extract_rating_from_source(source_data: dict, source_name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract rating information from source data.
    
    Args:
        source_data: Raw metadata dict
        source_name:  Name of the source
    
    Returns: 
        tuple: (rating_tag, rating_source) or (None, None)
        rating_tag is like 'rating:general', 'rating: explicit', etc.
        rating_source is 'original' or 'ai_inference'
    """
    rating_char = source_data.get('rating', '').lower()
    rating_tag = RATING_MAP.get(rating_char)
    
    if not rating_tag: 
        return None, None
    
    # Determine trust level
    if source_name in ['danbooru', 'e621']: 
        rating_source = 'original'
    elif source_name in ['local_tagger', 'camie_tagger']:
        rating_source = 'ai_inference'
    else: 
        rating_source = 'original'
    
    return rating_tag, rating_source


def merge_tag_sources(primary_tags: dict, secondary_tags: dict,
                      merge_categories: List[str] = None) -> dict:
    """
    Merge tags from two sources, with primary taking precedence. 
    
    Args: 
        primary_tags: Tags from primary source (takes precedence)
        secondary_tags: Tags from secondary source (fills gaps)
        merge_categories: List of categories to merge (default: all except artist)
    
    Returns:
        Merged categorized tags dict
    """
    if merge_categories is None:
        merge_categories = ['character', 'copyright', 'species', 'meta', 'general']
    
    merged = dict(primary_tags)
    
    for category in merge_categories:
        key = f'tags_{category}'
        primary_set = set(primary_tags. get(key, '').split())
        secondary_set = set(secondary_tags. get(key, '').split())
        
        # Add secondary tags that aren't in primary
        combined = primary_set | secondary_set
        merged[key] = ' '.join(sorted(combined))
    
    return merged


def deduplicate_categorized_tags(categorized_tags: dict) -> dict:
    """
    Remove duplicate tags across categories.
    
    Tags in specific categories (character, copyright, artist, species, meta)
    are removed from the general category if they appear there.
    
    Args:
        categorized_tags:  Dict with keys like 'tags_general', 'tags_character', etc.
    
    Returns:
        Deduplicated categorized tags dict
    """
    sets = {}
    for cat in TAG_CATEGORIES: 
        key = f'tags_{cat}'
        tags_str = categorized_tags.get(key, '') or ''
        sets[cat] = set(tag.strip() for tag in tags_str. split() if tag.strip())
    
    # Remove from general anything that's in other categories
    non_general = (
        sets['character'] |
        sets['copyright'] |
        sets['artist'] |
        sets['meta'] |
        sets['species']
    )
    sets['general'] -= non_general
    
    # Rebuild the dict
    return {f'tags_{cat}': ' '.join(sorted(s)) for cat, s in sets.items()}


def is_rating_tag(tag_name: str) -> bool:
    """Check if a tag is a rating tag."""
    return tag_name in RATING_TAGS or tag_name.startswith('rating:')


def get_tag_category(tag_name: str, default:  str = 'general') -> str:
    """
    Determine the correct category for a tag. 
    
    Handles special cases like rating tags.
    """
    if is_rating_tag(tag_name):
        return RATING_CATEGORY
    return default
```

#### Migration Steps

1. Create `utils/tag_extraction.py` with the above code
2. Update `utils/__init__.py` to export new functions
3. Refactor each affected file one at a time:
   - `services/processing_service.py`
   - `services/image_service. py`
   - `database/models.py`
   - `services/switch_source_db.py`
4. Add unit tests for the new extraction functions
5. Remove duplicated code from all files

#### Estimated Impact
- **Lines removed:** ~200
- **Files affected:** 5
- **Bug risk reduction:** High

---

### 2. API Response Format Inconsistency ✅ **COMPLETED**

#### Problem

API endpoints use at least 3 different response formats for success and error states, causing frontend code to handle multiple patterns. 

#### Current Variations

| Pattern | Files Using |
|---------|-------------|
| `{"status": "success"}` | pools. py, tag_service.py, image-page.js |
| `{"success": True}` | tag_categorization.py, rating. py |
| `{"error": "message"}` | Most error handlers |
| `{"success": False, "error": "message"}` | tag_categorization.py, rating.py |

#### Current Code Examples

```python
# Pattern A - status field
return jsonify({"status": "success", "message": "Pool created"})

# Pattern B - success boolean
return jsonify({"success": True, **stats})

# Error Pattern A - error only
return jsonify({"error": str(e)}), 500

# Error Pattern B - success + error
return jsonify({"success": False, "error": str(e)}), 500
```

#### Frontend Impact

```javascript
// Frontend has to check multiple ways: 
if (data.success || data.status === 'success') {
    // handle success
}
if (data.error || data.success === false) {
    // handle error
}
```

#### Proposed Solution

Create `utils/api_responses.py`:

```python
"""
Standardized API response utilities.
All API endpoints should use these functions for consistent response format.
"""

from quart import jsonify
from typing import Any, Dict, Optional


def success_response(data: Dict[str, Any] = None, message:  str = None) -> tuple:
    """
    Create a standardized success response. 
    
    Args: 
        data: Additional data to include in response
        message: Optional success message
    
    Returns:
        Quart jsonify response with 200 status
    
    Example:
        return success_response({"count": 10}, "Operation completed")
        # Returns: {"success": True, "message": "Operation completed", "count": 10}
    """
    response = {"success": True}
    if message: 
        response["message"] = message
    if data:
        response. update(data)
    return jsonify(response)


def error_response(error: str, status_code: int = 400, data: Dict[str, Any] = None) -> tuple:
    """
    Create a standardized error response. 
    
    Args:
        error:  Error message
        status_code: HTTP status code (default 400)
        data: Additional data to include
    
    Returns: 
        Quart jsonify response with specified status code
    
    Example:
        return error_response("Invalid input", 400)
        # Returns:  {"success": False, "error": "Invalid input"}, 400
    """
    response = {"success": False, "error": str(error)}
    if data:
        response. update(data)
    return jsonify(response), status_code


def not_found_response(message: str = "Resource not found") -> tuple:
    """Create a 404 response."""
    return error_response(message, 404)


def unauthorized_response(message:  str = "Unauthorized") -> tuple:
    """Create a 401 response."""
    return error_response(message, 401)


def validation_error_response(message: str, field: str = None) -> tuple:
    """Create a validation error response."""
    data = {"field": field} if field else None
    return error_response(message, 400, data)


def server_error_response(error: Exception, include_traceback: bool = False) -> tuple:
    """
    Create a 500 server error response.
    
    Args: 
        error: The exception that occurred
        include_traceback: Whether to include traceback (only in debug mode)
    """
    import traceback
    traceback. print_exc()  # Always log to console
    
    data = None
    if include_traceback:
        data = {"traceback": traceback. format_exc()}
    
    return error_response(str(error), 500, data)
```

#### Usage Examples

```python
# Before: 
return jsonify({"status":  "success", "message": "Pool created"})
return jsonify({"error": "Not found"}), 404

# After:
from utils.api_responses import success_response, not_found_response

return success_response(message="Pool created")
return not_found_response("Image not found")
```

#### Estimated Impact
- **Consistency improvement:** High
- **Frontend simplification:** Can use single check pattern
- **Files to update:** 20+

#### Implementation Status ✅

**Completed:** December 2025

**Files Created:**
- `utils/api_responses.py` - 6 standardized response functions
- `tests/test_api_responses.py` - 15 unit tests
- `tests/test_pools_refactored.py` - 5 integration tests

**Files Modified:**
- `utils/__init__.py` - Exported new response functions
- `routers/api/pools.py` - Refactored 3 endpoints (`create_pool`, `update_pool`, `add_image_to_pool`)

**Testing:**
- ✅ 20/20 tests passing
- ✅ 0 security vulnerabilities (CodeQL)
- ✅ Type-safe with proper annotations

**Next Steps:**
- Remaining 17+ endpoints to be refactored in future PRs

---

### 3. Exception Handling Boilerplate

#### Problem

Nearly every API endpoint has identical try/except boilerplate with `traceback.print_exc()`, repeated 30+ times.

#### Current Pattern

```python
@api_blueprint.route('/some/endpoint', methods=['POST'])
async def some_endpoint():
    try: 
        # ...  actual logic (5-50 lines)
        return jsonify({"success": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
```

#### Affected Files

- `routers/api/pools.py` - 8+ endpoints
- `routers/api/rating.py` - 10+ endpoints
- `routers/api/system.py` - 15+ endpoints
- `routers/api/tags.py` - 5+ endpoints
- `services/*. py` - Various service functions

#### Proposed Solution

Create `utils/decorators.py`:

```python
"""
Decorators for API endpoints and service functions.
"""

from functools import wraps
import traceback
from quart import jsonify, request
from typing import Callable, Any
import asyncio


def api_handler(require_auth: bool = False, log_errors: bool = True):
    """
    Decorator for API endpoints that handles: 
    - Exception catching with proper logging
    - Consistent response format
    - Optional authentication check
    
    Args:
        require_auth: If True, checks for system secret in request
        log_errors:  If True, prints traceback on errors
    
    Usage:
        @api_blueprint.route('/endpoint', methods=['POST'])
        @api_handler(require_auth=True)
        async def my_endpoint():
            # Just the logic, no try/except needed
            return {"data": "value"}  # Auto-wrapped with success=True
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                # Optional auth check
                if require_auth: 
                    from config import RELOAD_SECRET
                    secret = request.args.get('secret', '') or request.form.get('secret', '')
                    if secret != RELOAD_SECRET:
                        return jsonify({"success": False, "error": "Unauthorized"}), 401
                
                # Call the actual function
                result = await func(*args, **kwargs)
                
                # Auto-wrap dict responses
                if isinstance(result, dict):
                    if 'success' not in result:
                        result = {"success": True, **result}
                    return jsonify(result)
                
                return result
                
            except ValueError as e:
                if log_errors: 
                    traceback. print_exc()
                return jsonify({"success": False, "error": str(e)}), 400
            except PermissionError as e: 
                return jsonify({"success": False, "error": str(e)}), 403
            except FileNotFoundError as e:
                return jsonify({"success":  False, "error":  str(e)}), 404
            except Exception as e: 
                if log_errors:
                    traceback.print_exc()
                return jsonify({"success":  False, "error":  str(e)}), 500
        
        return wrapper
    return decorator


def sync_to_async(func:  Callable) -> Callable:
    """
    Decorator to run synchronous functions in a thread pool.
    Useful for wrapping sync service functions for async routes.
    
    Usage:
        @sync_to_async
        def my_sync_function():
            # sync code
            return result
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


def require_secret(func: Callable) -> Callable:
    """
    Decorator that requires system secret for the endpoint.
    Can be used standalone or with api_handler.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from config import RELOAD_SECRET
        secret = request. args.get('secret', '') or request.form.get('secret', '')
        if secret != RELOAD_SECRET:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return await func(*args, **kwargs)
    return wrapper
```

#### Usage Examples

```python
# Before (30+ lines of boilerplate across the codebase):
@api_blueprint.route('/pools/<int:pool_id>/add_image', methods=['POST'])
async def add_image_to_pool(pool_id):
    try:
        data = await request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)
        image_data = models.get_image_details(filepath)
        if not image_data: 
            return jsonify({"error": "Image not found"}), 404
        image_id = image_data['id']
        models.add_image_to_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image added to pool."})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error":  str(e)}), 500

# After (clean, focused on logic):
@api_blueprint.route('/pools/<int: pool_id>/add_image', methods=['POST'])
@api_handler()
async def add_image_to_pool(pool_id):
    data = await request.json
    filepath = normalize_image_path(data. get('filepath', ''))
    
    image_data = models. get_image_details(filepath)
    if not image_data:
        raise FileNotFoundError("Image not found")
    
    models.add_image_to_pool(pool_id, image_data['id'])
    return {"message": "Image added to pool. "}
```

#### Estimated Impact
- **Lines removed:** ~150+
- **Endpoints simplified:** 30+
- **Consistency:** All errors handled uniformly

---

### 4.  Logging Framework

#### Problem

The codebase uses `print()` statements throughout instead of Python's logging module, making it hard to control log levels, filter output, or route logs to files.

#### Current Pattern

```python
# These patterns appear hundreds of times: 
print(f"[SauceNAO] Rate limit detected!")
print(f"Processing:  {filepath}")
print(f"[DELETE] Database deletion result: {db_success}")
print(f"[Pixiv] Network error fetching ID {pixiv_id}:  {e}")
print(f"✓ Monitor service started automatically")
print(f"⚠ Monitor service was already running")
```

#### Custom Prefixes Found

| Prefix | Files |
|--------|-------|
| `[SauceNAO]` | saucenao_service.py |
| `[Pixiv]` | saucenao_service.py |
| `[DELETE]` | Various |
| `[Local Tagger]` | processing_service.py |
| `[Bulk Retry]` | image_service.py |
| `[Monitor]` | monitor_service.py |
| `✓` / `⚠` / `❌` | Various status messages |

#### Proposed Solution

Create `utils/logging_config.py`:

```python
"""
Centralized logging configuration. 
All modules should use get_logger() instead of print().
"""

import logging
import sys
from typing import Optional
import config

# Cache for logger instances
_loggers = {}

# Default format with emoji support
DEFAULT_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
SIMPLE_FORMAT = '[%(name)s] %(levelname)s: %(message)s'


def setup_logging(level: str = None, log_file: str = None):
    """
    Configure the root logger for the application.
    Call this once at application startup.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
    """
    level = level or getattr(config, 'LOG_LEVEL', 'INFO')
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging. getLogger('chibibooru')
    root_logger.setLevel(log_level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    root_logger.addHandler(console_handler)
    
    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler. setFormatter(logging. Formatter(DEFAULT_FORMAT))
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (usually module name like 'SauceNAO', 'Monitor', etc.)
    
    Returns:
        Configured logger instance
    
    Usage:
        logger = get_logger('SauceNAO')
        logger.info("Processing request...")
        logger.error(f"Failed:  {e}")
    """
    if name not in _loggers:
        logger = logging.getLogger(f"chibibooru. {name}")
        _loggers[name] = logger
    
    return _loggers[name]


# Convenience class for status messages with emojis
class StatusLogger:
    """Logger wrapper that adds status emojis."""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
    
    def success(self, message:  str):
        """Log success with ✓ prefix."""
        self. logger.info(f"✓ {message}")
    
    def warning(self, message:  str):
        """Log warning with ⚠ prefix."""
        self.logger.warning(f"⚠ {message}")
    
    def error(self, message: str):
        """Log error with ❌ prefix."""
        self.logger.error(f"❌ {message}")
    
    def progress(self, message:  str):
        """Log progress with → prefix."""
        self.logger.info(f"→ {message}")
    
    def info(self, message:  str):
        """Log info without prefix."""
        self. logger.info(message)
    
    def debug(self, message: str):
        """Log debug message."""
        self. logger.debug(message)
```

Add to `config.py`:

```python
# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
LOG_FILE = os. environ.get('LOG_FILE', None)  # Optional:  path to log file
```

Update `app.py`:

```python
from utils.logging_config import setup_logging

def create_app():
    # Setup logging first
    setup_logging(config.LOG_LEVEL, config.LOG_FILE)
    
    # ...  rest of app creation
```

#### Usage Examples

```python
# Before:
print(f"[SauceNAO] Rate limit detected, waiting...")
print(f"[SauceNAO] Request failed: {e}")

# After:
from utils.logging_config import get_logger

logger = get_logger('SauceNAO')
logger.warning("Rate limit detected, waiting...")
logger.error(f"Request failed: {e}")

# Or with status emojis:
from utils.logging_config import StatusLogger

status = StatusLogger('Monitor')
status.success("Service started")
status.warning("Already running")
status.error(f"Failed to start: {e}")
```

#### Estimated Impact
- **print() statements to replace:** 100+
- **Benefits:** Log levels, filtering, file output, timestamps
- **Production readiness:** Significantly improved

---

### 5. Tag Writing to Database

#### Problem

There are **multiple implementations** for writing tags to the database, each with slightly different SQL patterns and behavior. 

#### Affected Files

| File | Function | SQL Pattern |
|------|----------|-------------|
| `repositories/tag_repository.py` | `update_image_tags()` | `INSERT OR IGNORE` |
| `repositories/tag_repository.py` | `update_image_tags_categorized()` | `INSERT OR IGNORE` |
| `repositories/data_access. py` | `add_image_with_metadata()` | `ON CONFLICT DO UPDATE` |
| `services/switch_source_db.py` | `switch_metadata_source_db()` | `ON CONFLICT DO UPDATE` |
| `services/image_service.py` | Inline in retry functions | Direct `INSERT`/`UPDATE` |
| `services/rating_service.py` | `set_rating()` | `INSERT OR IGNORE` then `INSERT OR REPLACE` |
| `database/core.py` | `repair_orphaned_image_tags()` | `INSERT OR IGNORE` |
| `database/models.py` | `repopulate_from_database()` | `ON CONFLICT DO UPDATE` |

#### Current Inconsistencies

```python
# Pattern A (some files) - Ignores if exists: 
cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", ...)

# Pattern B (other files) - Updates category if exists:
cursor.execute("""
    INSERT INTO tags (name, category) VALUES (?, ?)
    ON CONFLICT(name) DO UPDATE SET category = excluded.category
""", ...)

# Pattern C - Different formatting of same thing:
cursor.execute("INSERT INTO tags (name, category) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET category=excluded.category", ...)
```

#### Issues

1. **Category override inconsistency** - Pattern A keeps old category, Pattern B/C updates it
2. **`image_tags` source field** - Sometimes set, sometimes not
3. **Transaction handling** - Some use explicit commits, some rely on context manager
4. **Delta recording** - Only some functions support the `record_deltas` flag

#### Proposed Solution

Add to `utils/tag_extraction.py` or create `utils/tag_db_utils.py`:

```python
"""
Database operations for tags.
All tag database writes should use these functions.
"""

from typing import Dict, List, Optional


def insert_or_update_tag(cursor, tag_name: str, category:  str) -> int:
    """
    Insert a tag or update its category if it exists.
    
    This is THE SINGLE WAY to add/update tags in the database.
    
    Args: 
        cursor: Database cursor
        tag_name: Name of the tag
        category: Category for the tag
    
    Returns: 
        int: The tag_id
    """
    cursor.execute("""
        INSERT INTO tags (name, category) VALUES (?, ?)
        ON CONFLICT(name) DO UPDATE SET category = excluded.category
    """, (tag_name, category))
    
    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    return cursor.fetchone()['id']


def link_tag_to_image(cursor, image_id: int, tag_id: int, source:  str = 'original'):
    """
    Create a link between an image and a tag. 
    
    Args:
        cursor:  Database cursor
        image_id: ID of the image
        tag_id: ID of the tag
        source: Source of the tag ('original', 'ai_inference', 'user')
    """
    cursor.execute("""
        INSERT OR IGNORE INTO image_tags (image_id, tag_id, source)
        VALUES (?, ?, ?)
    """, (image_id, tag_id, source))


def clear_image_tags(cursor, image_id: int, preserve_sources: List[str] = None):
    """
    Clear tags for an image, optionally preserving certain sources.
    
    Args:
        cursor: Database cursor
        image_id:  ID of the image
        preserve_sources:  List of sources to preserve (e.g., ['user'])
    """
    if preserve_sources: 
        placeholders = ','.join('?' * len(preserve_sources))
        cursor.execute(f"""
            DELETE FROM image_tags 
            WHERE image_id = ? AND source NOT IN ({placeholders})
        """, [image_id] + preserve_sources)
    else:
        cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))


def replace_image_tags(cursor, image_id: int, categorized_tags: dict,
                       source: str = 'original'):
    """
    Replace all tags for an image with new categorized tags.
    
    Args: 
        cursor: Database cursor
        image_id: ID of the image
        categorized_tags: Dict with keys like 'tags_general', 'tags_character', etc.
        source: Source for the new tags
    """
    # Clear existing tags
    clear_image_tags(cursor, image_id)
    
    # Insert new tags
    for category_key, tags_str in categorized_tags.items():
        if not tags_str or not tags_str.strip():
            continue
        
        category_name = category_key.replace('tags_', '')
        tags = [t.strip() for t in tags_str. split() if t.strip()]
        
        for tag_name in tags: 
            tag_id = insert_or_update_tag(cursor, tag_name, category_name)
            link_tag_to_image(cursor, image_id, tag_id, source)


def update_image_tag_columns(cursor, image_id: int, categorized_tags: dict):
    """
    Update the denormalized tag columns in the images table.
    
    Args:
        cursor: Database cursor
        image_id:  ID of the image
        categorized_tags: Dict with keys like 'tags_general', 'tags_character', etc. 
    """
    cursor.execute("""
        UPDATE images
        SET tags_character = ?,
            tags_copyright = ?,
            tags_artist = ?,
            tags_species = ?,
            tags_meta = ?,
            tags_general = ? 
        WHERE id = ?
    """, (
        categorized_tags. get('tags_character', ''),
        categorized_tags. get('tags_copyright', ''),
        categorized_tags. get('tags_artist', ''),
        categorized_tags. get('tags_species', ''),
        categorized_tags. get('tags_meta', ''),
        categorized_tags. get('tags_general', ''),
        image_id
    ))


def full_tag_update(cursor, image_id: int, categorized_tags: dict,
                    source:  str = 'original', record_deltas: bool = False,
                    image_md5: str = None, filepath: str = None):
    """
    Complete tag update:  updates both image_tags table and denormalized columns.
    
    This is the preferred function for any tag update operation.
    
    Args:
        cursor: Database cursor
        image_id: ID of the image
        categorized_tags:  Dict with keys like 'tags_general', 'tags_character', etc.
        source: Source for the tags
        record_deltas: Whether to record changes in tag_deltas table
        image_md5: MD5 hash of image (required if record_deltas is True)
        filepath: Image filepath (required if record_deltas is True)
    """
    if record_deltas and image_md5 and filepath:
        from repositories.delta_tracker import compute_tag_deltas, record_tag_delta
        deltas = compute_tag_deltas(filepath, categorized_tags)
        for tag_name, tag_category, operation in deltas:
            record_tag_delta(image_md5, tag_name, tag_category, operation)
    
    # Update relational table
    replace_image_tags(cursor, image_id, categorized_tags, source)
    
    # Update denormalized columns
    update_image_tag_columns(cursor, image_id, categorized_tags)
```

#### Estimated Impact
- **Consistency:** Single implementation for all tag operations
- **Bug reduction:** No more category override mismatches
- **Maintainability:** Changes in one place affect all operations

---

## Medium Priority

---

### 6. Filepath Handling - Python

#### Problem

The pattern for normalizing filepaths (removing `images/` prefix) is duplicated throughout the codebase. 

#### Affected Files

| File | Occurrences |
|------|-------------|
| `routers/api/pools.py` | 4+ times |
| `services/tag_service.py` | 1 time |
| `services/saucenao_service. py` | 1 time |
| `services/switch_source_db. py` | 2 times |
| `routers/web. py` | 3+ times |
| `repositories/tag_repository.py` | 2 times |

#### Current Duplicated Patterns

```python
# Pattern A - Simple replace (most common, 10+ occurrences)
filepath = data. get('filepath', '').replace('images/', '', 1)

# Pattern B - More thorough (some files)
if filepath.startswith('images/'):
    filepath = filepath[7:]
elif filepath.startswith('static/images/'):
    filepath = filepath[14:]

# Pattern C - Inline in f-strings
f"static/images/{filepath. replace('images/', '', 1)}"
```

#### Proposed Solution

Add to `utils/file_utils.py`:

```python
def normalize_image_path(filepath:  str) -> str:
    """
    Normalize a filepath by removing common prefixes.
    
    Handles: 
    - 'images/abc/file.jpg' -> 'abc/file.jpg'
    - 'static/images/abc/file.jpg' -> 'abc/file.jpg'
    - 'abc/file.jpg' -> 'abc/file.jpg' (unchanged)
    
    Args:
        filepath: The filepath to normalize
    
    Returns: 
        Normalized path without 'images/' or 'static/images/' prefix
    """
    if not filepath:
        return filepath
    
    if filepath.startswith('static/images/'):
        return filepath[14:]
    elif filepath.startswith('images/'):
        return filepath[7:]
    
    return filepath


def ensure_image_prefix(filepath: str, prefix: str = 'images/') -> str:
    """
    Ensure filepath has the specified prefix. 
    
    Args: 
        filepath: The filepath
        prefix:  Prefix to ensure (default: 'images/')
    
    Returns:
        Filepath with prefix
    """
    if not filepath:
        return filepath
    
    normalized = normalize_image_path(filepath)
    return f"{prefix}{normalized}"


def get_static_path(filepath:  str) -> str:
    """
    Convert a relative filepath to a static file path.
    
    Args:
        filepath:  Relative path like 'abc/file.jpg' or 'images/abc/file.jpg'
    
    Returns:
        Static path like 'static/images/abc/file.jpg'
    """
    normalized = normalize_image_path(filepath)
    return f"static/images/{normalized}"


def get_absolute_path(filepath:  str) -> str:
    """
    Get the absolute filesystem path for an image. 
    
    Args:
        filepath:  Relative path
    
    Returns: 
        Absolute path like './static/images/abc/file.jpg'
    """
    import os
    normalized = normalize_image_path(filepath)
    return os.path.join("./static/images", normalized)
```

Update `utils/__init__.py`:

```python
from .file_utils import (
    get_thumbnail_path,
    get_file_md5,
    url_encode_path,
    normalize_image_path,    # NEW
    ensure_image_prefix,     # NEW
    get_static_path,         # NEW
    get_absolute_path,       # NEW
)
```

#### Estimated Impact
- **Occurrences to fix:** 15+
- **Lines saved:** ~30
- **Bug prevention:** Consistent path handling

---

### 7. Filepath Handling - JavaScript

#### Problem

JavaScript files each implement their own path encoding for handling non-ASCII characters (Japanese filenames, etc.).

#### Affected Files

| File | Implementation |
|------|---------------|
| `static/js/infinite-scroll.js` | Inline:  `img.path.split('/').map(part => encodeURIComponent(part)).join('/')` |
| `templates/rate_manage. html` | `urlEncodePath()` function (inline in template) |
| `static/js/pool-manager.js` | `encodeURIComponent(filepath)` (doesn't handle slashes properly) |
| `static/js/tags.js` | `encodeURIComponent(tag. name)` |
| `static/js/autocomplete.js` | `encodeURIComponent(query)` |
| `static/js/tag-editor.js` | `encodeURIComponent(query)` |
| `static/js/implications.js` | `encodeURIComponent(tagName)` |

#### Current Inconsistencies

```javascript
// Correct path encoding (some files):
const encodedPath = img.path.split('/').map(part => encodeURIComponent(part)).join('/');

// Incorrect - breaks on slashes (other files):
const encoded = encodeURIComponent(filepath);

// Inline function in templates:
function urlEncodePath(filepath) {
    if (!filepath) return filepath;
    return filepath.split('/').map(part => encodeURIComponent(part)).join('/');
}
```

#### Proposed Solution

Create `static/js/utils/path-utils.js`:

```javascript
// path-utils.js - Centralized filepath handling utilities

/**
 * URL-encode a filepath, preserving forward slashes. 
 * Handles non-ASCII characters (Japanese, Korean, etc.) properly.
 * 
 * @param {string} filepath - The filepath to encode
 * @returns {string} URL-encoded path with preserved slashes
 * 
 * @example
 * urlEncodePath('images/abc/日本語.jpg')
 * // Returns:  'images/abc/%E6%97%A5%E6%9C%AC%E8%AA%9E.jpg'
 */
export function urlEncodePath(filepath) {
    if (!filepath) return filepath;
    return filepath.split('/').map(part => encodeURIComponent(part)).join('/');
}

/**
 * Normalize a filepath by removing the 'images/' prefix if present.
 * 
 * @param {string} filepath - The filepath to normalize
 * @returns {string} Normalized filepath without 'images/' prefix
 */
export function normalizeImagePath(filepath) {
    if (! filepath) return filepath;
    if (filepath.startsWith('static/images/')) {
        return filepath. substring(14);
    }
    if (filepath.startsWith('images/')) {
        return filepath. substring(7);
    }
    return filepath;
}

/**
 * Ensure filepath has the 'images/' prefix. 
 * 
 * @param {string} filepath - The filepath
 * @returns {string} Filepath with 'images/' prefix
 */
export function ensureImagePrefix(filepath) {
    if (!filepath) return filepath;
    const normalized = normalizeImagePath(filepath);
    return 'images/' + normalized;
}

/**
 * Build a static file URL for an image.
 * 
 * @param {string} filepath - The filepath (with or without 'images/' prefix)
 * @returns {string} Full static URL like '/static/images/abc/file.jpg'
 */
export function getStaticUrl(filepath) {
    const normalized = normalizeImagePath(filepath);
    return `/static/images/${urlEncodePath(normalized)}`;
}

/**
 * Build a view URL for an image. 
 * 
 * @param {string} filepath - The filepath
 * @returns {string} View URL like '/view/images/abc/file. jpg'
 */
export function getViewUrl(filepath) {
    const withPrefix = ensureImagePrefix(filepath);
    return `/view/${urlEncodePath(withPrefix)}`;
}

/**
 * Build a thumbnail URL for an image.
 * 
 * @param {string} thumbPath - The thumbnail path
 * @returns {string} Full thumbnail URL
 */
export function getThumbnailUrl(thumbPath) {
    const prefix = (thumbPath.startsWith('thumbnails/') || thumbPath.startsWith('images/')) 
        ? '' 
        : 'images/';
    return `/static/${prefix}${urlEncodePath(thumbPath)}`;
}
```

#### Estimated Impact
- **Files to update:** 7+
- **Consistency:** All path handling unified
- **Bug fixes:** Proper handling of special characters everywhere

---

### 8. Magic Numbers

#### Problem

Hardcoded values are scattered throughout the code without named constants, making them hard to find, understand, and change consistently.

#### Examples Found

| Value | Location | Meaning |
|-------|----------|---------|
| `100` | tags. py, rate_manage.html | Default pagination limit |
| `50` | rate_manage.html | Default image limit |
| `1000` | config.py, various queries | Batch sizes, thumb size |
| `300` | monitor_service.py | Monitor interval (seconds) |
| `30` | processing_service.py | Rate limiter window |
| `0.6`, `0.7` | config.py | Confidence thresholds |
| `5000` | saucenao-fetch.js | JavaScript timeout (ms) |
| `90000` | saucenao-fetch.js | Client timeout (ms) |
| `4096` | file_utils.py | Read chunk size |
| `500` | query_service.py | Similarity candidate limit |

#### Proposed Solution

Add constants section to `config.py`:

```python
# ==================== DEFAULTS ====================

class Defaults:
    """Default values for various operations."""
    PAGINATION_LIMIT = 100
    IMAGE_BROWSER_LIMIT = 50
    BATCH_SIZE = 100
    SIMILARITY_CANDIDATES = 500
    AUTOCOMPLETE_MIN_CHARS = 2
    AUTOCOMPLETE_MAX_RESULTS = 20


class Timeouts:
    """Timeout values in seconds."""
    API_REQUEST = 10
    SAUCENAO_SEARCH = 30
    LONG_OPERATION = 300
    FILE_DOWNLOAD = 60
    
    # JavaScript timeouts (in milliseconds)
    JS_API_TIMEOUT = 5000
    JS_LONG_TIMEOUT = 90000


class Intervals:
    """Interval values in seconds."""
    MONITOR_CHECK = 300
    RATE_LIMIT_WINDOW = 30
    CACHE_REFRESH = 600


class Thresholds:
    """Threshold values."""
    LOCAL_TAGGER_CONFIDENCE = 0.6
    LOCAL_TAGGER_DISPLAY = 0.7
    SIMILARITY_MINIMUM = 0.1
    HIGH_CONFIDENCE = 0.9


class Limits:
    """Size and count limits."""
    MAX_UPLOAD_SIZE_MB = 100
    CHUNK_SIZE = 4096
    MAX_FILENAME_LENGTH = 255
    MAX_TAGS_PER_IMAGE = 500
```

Create `static/js/config.js`:

```javascript
// config.js - JavaScript configuration constants

export const Timeouts = {
    API_REQUEST: 5000,      // 5 seconds
    LONG_OPERATION: 90000,  // 90 seconds
    DEBOUNCE:  200,          // 200ms for input debounce
    ANIMATION:  300,         // 300ms for animations
};

export const Defaults = {
    PAGINATION_LIMIT:  100,
    AUTOCOMPLETE_MIN_CHARS: 2,
    PREFETCH_PAGES: 2,
};

export const Intervals = {
    POLL_STATUS: 1000,      // 1 second
    REFRESH_DATA: 60000,    // 1 minute
};
```

#### Estimated Impact
- **Discoverability:** All config in one place
- **Consistency:** Change once, applies everywhere
- **Documentation:** Self-documenting code

---

### 9. Supported File Extensions

#### Problem

The tuple `('. png', '.jpg', '. jpeg', '.gif', '.webp', '.mp4', '.webm')` is hardcoded in multiple locations.

#### Affected Files

| File | Usage |
|------|-------|
| `services/monitor_service.py` | `find_ingest_files()`, `find_unprocessed_images()`, `is_image_file()` |
| `services/processing_service.py` | Video detection check |
| `routers/web.py` | Upload validation |
| Various | Extension checks |

#### Current Pattern

```python
# Repeated in multiple files with slight variations: 
if file. lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '. mp4', '.webm')):
    ... 

# Sometimes missing extensions:
if file. lower().endswith(('.png', '.jpg', '.jpeg', '. gif', '.webp')):  # Missing video
    ...
```

#### Proposed Solution

Add to `config.py`:

```python
# ==================== FILE TYPES ====================

SUPPORTED_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '. gif', '.webp', '.bmp', '.avif')
SUPPORTED_VIDEO_EXTENSIONS = ('.mp4', '.webm')
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS + SUPPORTED_VIDEO_EXTENSIONS

# For future use
SUPPORTED_ANIMATION_EXTENSIONS = ('.gif', '.webp', '.apng')


def is_supported_media(filepath: str) -> bool:
    """Check if a file is a supported media type."""
    return filepath.lower().endswith(SUPPORTED_MEDIA_EXTENSIONS)


def is_supported_image(filepath: str) -> bool:
    """Check if a file is a supported image type."""
    return filepath.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)


def is_video(filepath: str) -> bool:
    """Check if a file is a video."""
    return filepath.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)


def is_animated(filepath: str) -> bool:
    """Check if a file might be animated (gif, webp, apng)."""
    return filepath.lower().endswith(SUPPORTED_ANIMATION_EXTENSIONS)
```

#### Usage

```python
# Before:
if file.lower().endswith(('.png', '. jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')):

# After:
from config import is_supported_media
if is_supported_media(file):
```

#### Estimated Impact
- **Occurrences to fix:** 5+
- **Future-proofing:** Easy to add new formats (e.g., `.avif`, `.jxl`)
- **Consistency:** No more missing extensions in some places

---

### 10. Pagination Response Inconsistency

#### Problem

Different endpoints use different pagination response formats, causing frontend confusion.

#### Current Variations

```python
# Pattern A (tags. py) - camelCase hasMore
return jsonify({
    'tags': tags_page,
    'total': total,
    'offset': offset,
    'limit': limit,
    'hasMore': offset + limit < total  # camelCase
})

# Pattern B (infinite-scroll.js expects) - snake_case has_more
{
    'images': [... ],
    'has_more': True,  # snake_case
    'page': 1
}

# Pattern C (some endpoints) - no pagination info
return jsonify({'items': items})
```

#### Proposed Solution

Add to `utils/api_responses.py`:

```python
def paginated_response(items: list, total: int, page: int = None, 
                       per_page: int = None, offset: int = None,
                       item_key: str = 'items') -> dict:
    """
    Create a standardized paginated response. 
    
    Supports both page-based and offset-based pagination.
    
    Args:
        items: List of items for current page
        total:  Total number of items
        page: Current page number (1-indexed, for page-based)
        per_page: Items per page
        offset: Current offset (for offset-based)
        item_key: Key name for items list (default: 'items')
    
    Returns:
        Standardized pagination response dict
    """
    response = {
        item_key: items,
        'total':  total,
    }
    
    if page is not None and per_page is not None:
        # Page-based pagination
        response. update({
            'page': page,
            'per_page': per_page,
            'has_more': (page * per_page) < total,
            'total_pages': (total + per_page - 1) // per_page
        })
    elif offset is not None and per_page is not None:
        # Offset-based pagination
        response.update({
            'offset': offset,
            'limit': per_page,
            'has_more': (offset + per_page) < total
        })
    
    return jsonify(response)
```

#### Usage

```python
# Before:
return jsonify({
    'tags': tags_page,
    'total': total,
    'offset': offset,
    'limit':  limit,
    'hasMore': offset + limit < total
})

# After: 
from utils.api_responses import paginated_response
return paginated_response(tags_page, total, offset=offset, per_page=limit, item_key='tags')
```

#### Estimated Impact
- **Consistency:** All pagination uses same format
- **Frontend simplification:** Single pagination handling pattern

---

### 11. Tag Deduplication Logic

#### Problem

The logic for deduplicating tags across categories is duplicated in multiple files.

#### Affected Files

- `services/processing_service.py` (lines ~1150-1165)
- `services/image_service.py` (lines ~750-765)
- `services/switch_source_db. py` (multiple locations)

#### Current Duplicated Pattern

```python
# This exact pattern appears in 3+ files:
character_set = set(tags_character. split())
copyright_set = set(tags_copyright.split())
artist_set = set(tags_artist. split())
species_set = set(tags_species.split())
meta_set = set(tags_meta.split())
general_set = set(tags_general.split())

# Remove from general anything that's in other categories
general_set -= (character_set | copyright_set | artist_set | meta_set | species_set)
```

#### Proposed Solution

Already included in Section 1 (`utils/tag_extraction.py`):

```python
def deduplicate_categorized_tags(categorized_tags: dict) -> dict:
    """
    Remove duplicate tags across categories.
    
    Tags in specific categories (character, copyright, artist, species, meta)
    are removed from the general category if they appear there.
    """
    # ...  implementation in Section 1
```

#### Estimated Impact
- **Lines removed:** ~30
- **Files affected:** 3+

---

## Lower Priority

---

### 12. Notification System

#### Problem

The `showNotification()` function exists as a proper module but is used inconsistently across files.

#### Current State

**Proper Implementation:** `static/js/utils/notifications.js`

#### Inconsistent Usage

| File | Usage Pattern | Issue |
|------|---------------|-------|
| `static/js/global-uploader.js` | ✅ Imports from utils | Correct |
| `static/js/saucenao-fetch. js` | ✅ Imports from utils | Correct |
| `static/js/tag-editor.js` | ❌ Uses without import | Relies on global |
| `static/js/system-panel.js` | ❌ Uses global | No import |
| `static/js/image-page.js` | ❌ `window.tagEditor. showNotification` | Fragile fallback |
| `templates/rate_review.html` | ⚠️ Imports then assigns to window | Works but inconsistent |
| `templates/rate_manage. html` | ⚠️ Uses global | Assumes window.showNotification exists |
| `templates/tag_categorize.html` | ⚠️ Uses global | Same issue |

#### Proposed Solution

1. **All JS modules should import properly:**

```javascript
import { showNotification } from './utils/notifications. js';
```

2. **Templates that need global access should standardize:**

```html
<script type="module">
    import { showNotification } from "{{ url_for('static', filename='js/utils/notifications.js') }}";
    window.showNotification = showNotification;
</script>
```

3. **Remove local implementations** from any files that have them.

#### Estimated Impact
- **Consistency:** All files use same notification system
- **Maintenance:** Single implementation to update

---

### 13. Rating Tag Handling

#### Problem

Rating tags are handled inconsistently across the codebase with different category assignments.

#### Inconsistencies Found

| Location | Category Used | Format |
|----------|---------------|--------|
| `services/rating_service.py` | `'meta'` | `rating: general` |
| `migrations/backfill_ratings.py` | `'rating'` | `rating:general` |
| `database/models. py` | Both `'meta'` and `'rating'` | `rating:general` |
| `routers/web.py` | Queries for `category = 'rating'` | `rating:general` |

#### Current SQL Patterns

```python
# Pattern A - Uses 'rating' category: 
cursor.execute("INSERT INTO tags (name, category) VALUES (?, 'rating') .. .", (rating,))

# Pattern B - Uses 'meta' category:
cursor.execute("INSERT INTO tags (name, category) VALUES (?, 'meta') ...", (rating_tag,))
```

#### Proposed Solution

Already included in Section 1 - standardize on constants:

```python
# In utils/tag_extraction. py
RATING_CATEGORY = 'rating'
RATING_TAGS = ['rating: general', 'rating:sensitive', 'rating: questionable', 'rating:explicit']
```

#### Estimated Impact
- **Data consistency:** All ratings use same category
- **Query simplification:** Can reliably filter by category

---

### 14. Cache Invalidation Patterns

#### Problem

After modifying data, cache invalidation is done inconsistently with the same pattern repeated in many files.

#### Current Pattern

```python
# This pattern appears after many data modifications:
models.reload_single_image(filepath)
models.reload_tag_counts()
from repositories.data_access import get_image_details
get_image_details. cache_clear()
```

#### Affected Files

- `services/tag_service. py`
- `services/saucenao_service.py`
- `services/image_service.py`
- `routers/api/*. py`

#### Proposed Solution

Add to `core/cache_manager.py`:

```python
def invalidate_image_cache(filepath: str = None):
    """
    Invalidate caches after an image modification.
    
    Args:
        filepath: If provided, only reload this specific image. 
                 If None, reloads all data.
    """
    from database import models
    from repositories.data_access import get_image_details
    
    if filepath:
        models.reload_single_image(filepath)
    else:
        models.load_data_from_db()
    
    models.reload_tag_counts()
    get_image_details. cache_clear()


def invalidate_all_caches():
    """Full cache invalidation - use sparingly."""
    from database import models
    from repositories.data_access import get_image_details
    from services. 
    query_service import find_related_by_tags
        
        models.load_data_from_db()
        get_image_details. cache_clear()
        find_related_by_tags. cache_clear()
    
    
    def invalidate_tag_cache():
        """Invalidate only tag-related caches."""
        from database import models
        from repositories.data_access import get_image_details
        
        models.reload_tag_counts()
        get_image_details.cache_clear()
    ```
    
    #### Usage
    
    ```python
    # Before (repeated in many files):
    models.reload_single_image(filepath)
    models.reload_tag_counts()
    from repositories.data_access import get_image_details
    get_image_details. cache_clear()
    
    # After: 
    from core.cache_manager import invalidate_image_cache
    invalidate_image_cache(filepath)
    ```
    
    #### Estimated Impact
    - **Lines removed:** ~40
    - **Consistency:** Cache invalidation always complete
    
    ---
    
    ### 15. JavaScript Utility Functions
    
    #### Problem
    
    Common utility functions are duplicated or inconsistently used across JavaScript files.
    
    #### 15.1 `formatCount()` Duplication
    
    **Affected Files:**
    - `static/js/utils/helpers.js` - Has the shared version (correct)
    - `static/js/autocomplete. js` - Has a local `this.formatCount()` method (duplicate)
    
    **Issue:** `autocomplete.js` uses both the imported `formatCount` AND a local method `this.formatCount()` in different places.
    
    **Solution:** Remove the local method, use only the imported version.
    
    #### 15.2 `getCategoryIcon()` Duplication
    
    **Affected Files:**
    - `static/js/autocomplete.js` - Has its own implementation
    - `static/js/tag-editor.js` - Has its own implementation
    
    **Current Pattern:**
    
    ```javascript
    // In autocomplete.js:
    getCategoryIcon(category) {
        const icons = {
            'character': '👤',
            'copyright': '©️',
            'artist': '🎨',
            'species': '🐾',
            'meta': '📋',
            'general': '🏷️'
        };
        return icons[category] || '🏷️';
    }
    
    // Similar but potentially different in tag-editor.js
    ```
    
    **Solution:** Add to `static/js/utils/helpers.js`:
    
    ```javascript
    /**
     * Get the emoji icon for a tag category
     * @param {string} category - The category name
     * @returns {string} Emoji icon
     */
    export function getCategoryIcon(category) {
        const icons = {
            'character': '👤',
            'copyright': '©️',
            'artist': '🎨',
            'species': '🐾',
            'meta': '📋',
            'general':  '🏷️',
            'rating':  '🔞'
        };
        return icons[category] || '🏷️';
    }
    
    /**
     * Get CSS class for a tag category
     * @param {string} category - The category name
     * @returns {string} CSS class name
     */
    export function getCategoryClass(category) {
        const validCategories = ['character', 'copyright', 'artist', 'species', 'meta', 'general', 'rating'];
        return validCategories.includes(category) ? category : 'general';
    }
    ```
    
    #### Estimated Impact
    - **Files to update:** 3
    - **Consistency:** Single source for category display
    
    ---
    
    ### 16. Async/Sync Mixing Pattern
    
    #### Problem
    
    The codebase mixes asyncio, threading, and synchronous code inconsistently, with `asyncio.to_thread()` wrappers scattered throughout.
    
    #### Current Pattern
    
    ```python
    # In routers/api/system.py - this pattern repeats 10+ times: 
    @api_blueprint.route('/system/scan', methods=['POST'])
    async def trigger_scan():
        return await asyncio.to_thread(system_service.scan_and_process_service)
    
    @api_blueprint.route('/system/rebuild', methods=['POST'])
    async def trigger_rebuild():
        return await asyncio.to_thread(system_service.rebuild_service)
    ```
    
    #### Issues
    
    - Services are sync but wrapped in async handlers
    - Some services use `threading.Lock`, others use `asyncio.Lock`
    - `BackgroundTaskManager` uses `asyncio.Lock` but services use `threading.Lock`
    
    #### Proposed Solution
    
    Already included in Section 3 - the `sync_to_async` decorator:
    
    ```python
    # In utils/decorators.py
    def sync_to_async(func:  Callable) -> Callable: 
        """Decorator to run sync functions in thread pool."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.to_thread(func, *args, **kwargs)
        return wrapper
    ```
    
    #### Usage
    
    ```python
    # In service file:
    @sync_to_async
    def scan_and_process_service():
        # sync implementation
        pass
    
    # In router:
    @api_blueprint.route('/system/scan', methods=['POST'])
    @api_handler(require_auth=True)
    async def trigger_scan():
        return await system_service.scan_and_process_service()
    ```
    
    #### Estimated Impact
    - **Cleaner separation:** Sync services clearly marked
    - **Consistency:** All async wrapping done the same way
    
    ---
    
    ### 17. DOM Element Creation
    
    #### Problem
    
    JavaScript files create DOM elements in at least 3 different ways. 
    
    #### Current Patterns
    
    ```javascript
    // Pattern A:  innerHTML with template strings (most files)
    container.innerHTML = `<div class="item">${data}</div>`;
    
    // Pattern B: createElement + manual properties (some files)
    const div = document.createElement('div');
    div.className = 'item';
    div.textContent = data;
    
    // Pattern C: Helper function (only in saucenao-fetch.js)
    function createElement(tag, className, text) { ... }
    const div = createElement('div', 'item', data);
    ```
    
    #### Proposed Solution
    
    Create `static/js/utils/dom. js`:
    
    ```javascript
    /**
     * Create a DOM element with optional class and content. 
     * 
     * @param {string} tag - HTML tag name
     * @param {string} className - CSS class(es)
     * @param {string} textContent - Text content (escaped)
     * @param {Object} attributes - Additional attributes
     * @returns {HTMLElement}
     */
    export function createElement(tag, className = '', textContent = '', attributes = {}) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (textContent) el.textContent = textContent;
        Object.entries(attributes).forEach(([key, value]) => {
            el.setAttribute(key, value);
        });
        return el;
    }
    
    /**
     * Create a DOM element with innerHTML (use carefully - XSS risk).
     * 
     * @param {string} tag - HTML tag name
     * @param {string} className - CSS class(es)
     * @param {string} innerHTML - HTML content (NOT escaped)
     * @returns {HTMLElement}
     */
    export function createElementHTML(tag, className = '', innerHTML = '') {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (innerHTML) el.innerHTML = innerHTML;
        return el;
    }
    
    /**
     * Create an element from an HTML string.
     * 
     * @param {string} html - HTML string
     * @returns {HTMLElement}
     */
    export function htmlToElement(html) {
        const template = document.createElement('template');
        template.innerHTML = html. trim();
        return template.content.firstChild;
    }
    
    /**
     * Safely set text content (prevents XSS).
     * 
     * @param {HTMLElement} element - Target element
     * @param {string} text - Text to set
     */
    export function setText(element, text) {
        element.textContent = text;
    }
    
    /**
     * Remove all children from an element.
     * 
     * @param {HTMLElement} element - Target element
     */
    export function clearChildren(element) {
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
    }
    ```
    
    #### Estimated Impact
    - **Consistency:** Single approach to DOM creation
    - **XSS safety:** Clear separation of text vs HTML content
    
    ---
    
    ### 18. Circular Import Pattern
    
    #### Problem
    
    Many files have imports inside functions specifically to avoid circular imports, with inconsistent patterns.
    
    #### Current Patterns
    
    ```python
    # Pattern A: Import at top of function with comment
    def some_function():
        # Import inside function to avoid circular import
        from database import models
        from core.cache_manager import load_data_from_db_async
        ... 
    
    # Pattern B:  Lazy imports scattered throughout
    def invalidate_image_cache(filepath: str = None):
        from database import models  # Import here to avoid circular
        from repositories.data_access import get_image_details
        ... 
    
    # Pattern C: No comment, just inline import
    def process_image():
        from services.processing_service import ensure_thumbnail
        ... 
    ```
    
    #### Proposed Solution
    
    1. **Document the dependency graph** in `docs/ARCHITECTURE.md`
    2. **Standardize lazy import pattern:**
    
    ```python
    def some_function():
        """
        Function description.
        
        Note: Uses lazy imports to avoid circular dependencies with: 
        - database. models
        - core.cache_manager
        """
        # Lazy imports (circular dependency avoidance)
        from database import models
        from core.cache_manager import load_data_from_db_async
        
        # Function logic... 
    ```
    
    3. **Consider a lazy imports module** for commonly lazy-imported items:
    
    ```python
    # utils/lazy_imports. py
    """
    Lazy import helpers for commonly used modules that cause circular imports.
    """
    
    def get_models():
        """Get database models module."""
        from database import models
        return models
    
    def get_cache_manager():
        """Get cache manager module."""
        from core import cache_manager
        return cache_manager
    
    def get_image_details_func():
        """Get the get_image_details function."""
        from repositories.data_access import get_image_details
        return get_image_details
    ```
    
    #### Estimated Impact
    - **Code clarity:** Clear documentation of why lazy imports exist
    - **Maintainability:** Easier to understand dependency structure
    
    ---
    
    ### 19. Query Service Complexity
    
    #### Problem
    
    `services/query_service. py` has grown into a monolithic file with complex SQL building logic that's hard to test and maintain.
    
    #### Issues
    
    - `perform_search()` is ~200+ lines with nested conditionals
    - SQL is built via string concatenation with multiple branches
    - Similar query building patterns repeated in `_fts_search()` and `_tag_based_search()`
    
    #### Current Pattern
    
    ```python
    def perform_search(query):
        # ...  200+ lines of: 
        #   - Query parsing
        #   - Filter extraction
        #   - SQL building with string concatenation
        #   - Multiple conditional branches
        #   - Order/shuffle logic
    ```
    
    #### Proposed Solution
    
    Consider a query builder pattern:
    
    ```python
    # utils/query_builder. py
    """
    Query builder for image searches. 
    Provides a fluent interface for building complex queries. 
    """
    
    from typing import List, Optional, Tuple
    from dataclasses import dataclass, field
    
    
    @dataclass
    class SearchFilters:
        """Parsed search filters."""
        positive_tags: List[str] = field(default_factory=list)
        negative_tags:  List[str] = field(default_factory=list)
        sources: List[str] = field(default_factory=list)
        extensions: List[str] = field(default_factory=list)
        filename_pattern: Optional[str] = None
        relationship:  Optional[str] = None  # 'parent', 'child', 'standalone'
        pool_id: Optional[int] = None
        order:  Optional[str] = None  # 'new', 'old', 'random'
        rating: Optional[str] = None
    
    
    class ImageQueryBuilder:
        """
        Fluent query builder for image searches. 
        
        Usage:
            query = (ImageQueryBuilder()
                .with_tags(['holo', '1girl'])
                .without_tags(['explicit'])
                .from_source('danbooru')
                .order_by('new')
                .limit(100)
                .build())
        """
        
        def __init__(self):
            self.select_parts = ["SELECT DISTINCT i.filepath"]
            self.from_part = "FROM images i"
            self. join_parts = []
            self.where_parts = []
            self. order_part = None
            self.limit_value = None
            self.params = []
        
        def with_tags(self, tags: List[str]) -> 'ImageQueryBuilder':
            """Add required tags filter."""
            if not tags:
                return self
            
            for tag in tags: 
                self.join_parts.append(
                    "INNER JOIN image_tags it_{0} ON i.id = it_{0}.image_id "
                    "INNER JOIN tags t_{0} ON it_{0}.tag_id = t_{0}. id". format(len(self.params))
                )
                self.where_parts.append(f"t_{len(self.params)}.name = ? ")
                self.params.append(tag)
            
            return self
        
        def without_tags(self, tags:  List[str]) -> 'ImageQueryBuilder':
            """Add excluded tags filter."""
            if not tags: 
                return self
            
            placeholders = ','.join('?' * len(tags))
            self.where_parts.append(f"""
                i.id NOT IN (
                    SELECT image_id FROM image_tags it
                    JOIN tags t ON it. tag_id = t.id
                    WHERE t.name IN ({placeholders})
                )
            """)
            self.params.extend(tags)
            
            return self
        
        def from_source(self, source: str) -> 'ImageQueryBuilder': 
            """Filter by metadata source."""
            self.where_parts.append("i.active_source = ?")
            self.params. append(source)
            return self
        
        def with_extension(self, ext:  str) -> 'ImageQueryBuilder': 
            """Filter by file extension."""
            self.where_parts. append("i.filepath LIKE ?")
            self.params. append(f"%{ext}")
            return self
        
        def order_by(self, order: str) -> 'ImageQueryBuilder':
            """Set ordering."""
            if order == 'new':
                self. order_part = "ORDER BY i.ingested_at DESC"
            elif order == 'old':
                self.order_part = "ORDER BY i.ingested_at ASC"
            elif order == 'random':
                self. order_part = "ORDER BY RANDOM()"
            return self
        
        def limit(self, count: int) -> 'ImageQueryBuilder': 
            """Set result limit."""
            self.limit_value = count
            return self
        
        def build(self) -> Tuple[str, List]: 
            """Build the final SQL query and parameters."""
            parts = [' '.join(self. select_parts)]
            parts.append(self. from_part)
            parts.extend(self.join_parts)
            
            if self.where_parts:
                parts.append("WHERE " + " AND ".join(self.where_parts))
            
            if self.order_part:
                parts.append(self.order_part)
            
            if self.limit_value:
                parts. append(f"LIMIT {self.limit_value}")
            
            return '\n'.join(parts), self.params
    
    
    def parse_search_query(query: str) -> SearchFilters: 
        """
        Parse a search query string into structured filters.
        
        Handles:
        - Regular tags:  holo 1girl
        - Negative tags: -explicit
        - Source filters: source:danbooru
        - Extensions: . png
        - etc.
        """
        filters = SearchFilters()
        
        tokens = query.lower().split()
        for token in tokens: 
            if token. startswith('-'):
                filters.negative_tags. append(token[1:])
            elif token.startswith('source:'):
                filters.sources.append(token[7:])
            elif token.startswith('.'):
                filters.extensions.append(token)
            elif token.startswith('order:'):
                filters.order = token[6:]
            elif token.startswith('pool:'):
                try:
                    filters. pool_id = int(token[5:])
                except ValueError:
                    pass
            elif token in ('has: parent', 'has: children', 'is:standalone'):
                filters.relationship = token. split(': ')[1]
            else:
                filters.positive_tags.append(token)
        
        return filters
    ```
    
    #### Estimated Impact
    - **Testability:** Query builder can be unit tested
    - **Maintainability:** Clear separation of parsing and query building
    - **Extensibility:** Easy to add new filter types
    
    ---
    
    ### 20. Template Inline JavaScript
    
    #### Problem
    
    Several HTML templates have significant JavaScript code inline rather than in external files.
    
    #### Affected Templates
    
    | Template | Estimated JS Lines |
    |----------|-------------------|
    | `rate_manage.html` | ~200+ lines |
    | `rate_review.html` | ~100+ lines |
    | `tag_categorize.html` | ~150+ lines |
    
    #### Issues
    
    - Can't be cached by browser (embedded in HTML)
    - Can't be minified separately
    - Harder to test
    - Duplicated patterns across templates
    
    #### Proposed Solution
    
    Extract to external files:
    
    ```
    static/js/pages/
    ├── rate-manage.js
    ├── rate-review.js
    └── tag-categorize.js
    ```
    
    Each file exports an `init()` function:
    
    ```javascript
    // static/js/pages/rate-manage.js
    import { showNotification } from '../utils/notifications. js';
    import { urlEncodePath } from '../utils/path-utils.js';
    
    let currentStats = null;
    let currentImages = [];
    
    export function init() {
        loadStats();
        loadImages();
        setupEventListeners();
    }
    
    async function loadStats() {
        // ... extracted from template
    }
    
    // ... rest of functions
    
    // Auto-init if loaded directly
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    ```
    
    Template becomes:
    
    ```html
    <script type="module">
        import { init } from "{{ url_for('static', filename='js/pages/rate-manage.js') }}";
        init();
    </script>
    ```
    
    #### Estimated Impact
    - **Cacheability:** JS cached separately from HTML
    - **Testability:** Can unit test the JS modules
    - **Maintainability:** Cleaner templates
    
    ---
    
    ### 21. Inline CSS in JavaScript
    
    #### Problem
    
    Multiple JS files set `element.style.cssText` with long inline style strings instead of using CSS classes.
    
    #### Examples
    
    ```javascript
    // infinite-scroll.js
    loader.style.cssText = `
        text-align: center;
        padding: 40px;
        color: #87ceeb;
        font-size: 1.1em;
        font-weight: 600;
    `;
    
    // saucenao-fetch.js  
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background:  rgba(0, 0, 0, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index:  10001;
    `;
    ```
    
    #### Proposed Solution
    
    Move these to CSS classes in `components. css`:
    
    ```css
    /* Loader styles */
    .infinite-loader {
        text-align: center;
        padding: 40px;
        color: var(--primary-blue);
        font-size: 1.1em;
        font-weight: 600;
    }
    
    . infinite-loader-error {
        color: var(--error-red);
    }
    
    /* Modal overlay styles */
    .modal-overlay {
        position: fixed;
        top: 0;
        left:  0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10001;
    }
    
    . modal-overlay-loading {
        /* Additional styles for loading state */
    }
    ```
    
    Then in JavaScript:
    
    ```javascript
    // Before: 
    loader.style.cssText = `text-align: center; padding: 40px; ... `;
    
    // After:
    loader.className = 'infinite-loader';
    ```
    
    #### Estimated Impact
    - **Separation of concerns:** Styles in CSS, behavior in JS
    - **Consistency:** Uses CSS variables for colors
    - **Maintainability:** Easier to update styles
    
    ---
    
    ### 22. Database Connection Patterns
    
    #### Status:  ✅ Well Organized
    
    The database connection is properly centralized in `database/core. py` with `get_db_connection()` and correctly imported throughout the codebase. 
    
    #### Current Implementation
    
    ```python
    # database/core.py
    def get_db_connection():
        """Create a database connection with optimized performance settings."""
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        # ... more PRAGMA settings
        conn.row_factory = sqlite3.Row
        return conn
    ```
    
    #### Usage Throughout Codebase
    
    ```python
    from database import get_db_connection
    
    with get_db_connection() as conn:
        cursor = conn. cursor()
        # ... database operations
    ```
    
    #### No Action Required
    
    This is a good example of proper centralization that should be followed for other patterns.  The connection is: 
    - Configured in one place
    - Imported consistently everywhere
    - Uses context manager for proper cleanup
    
    ---
    
    ## Implementation Roadmap
    
    ### Phase 1: High-Impact Quick Wins (1-2 weeks)
    
    | Task | Effort | Impact | Risk |
    |------|--------|--------|------|
    | Create `utils/api_responses.py` | Low | High | Low |
    | Create `utils/decorators.py` (api_handler) | Medium | High | Low |
    | Add file extension constants to config | Low | Medium | Low |
    | Create `utils/logging_config.py` | Medium | High | Low |
    
    ### Phase 2: Core Consolidation (2-3 weeks)
    
    | Task | Effort | Impact | Risk |
    |------|--------|--------|------|
    | Create `utils/tag_extraction.py` | High | High | Medium |
    | Create tag database utilities | Medium | High | Medium |
    | Consolidate filepath handling (Python) | Medium | Medium | Low |
    | Create `static/js/utils/path-utils.js` | Low | Medium | Low |
    
    ### Phase 3: Cleanup & Polish (1-2 weeks)
    
    | Task | Effort | Impact | Risk |
    |------|--------|--------|------|
    | Consolidate JS utilities | Low | Low | Low |
    | Standardize notification usage | Low | Low | Low |
    | Consolidate cache invalidation | Low | Low | Low |
    | Extract template JS to files | Medium | Medium | Low |
    
    ### Phase 4: Larger Refactors (Optional, 2-4 weeks)
    
    | Task | Effort | Impact | Risk |
    |------|--------|--------|------|
    | Query builder implementation | High | Medium | Medium |
    | Async/sync pattern cleanup | Medium | Low | Medium |
    | Circular import resolution | High | Low | High |
    
    ---
    
    ## Testing Recommendations
    
    ### Before Making Changes
    
    Ensure the following test coverage exists or is created:
    
    1. **Tag extraction tests** - Test all source formats (danbooru, e621, pixiv, local_tagger)
    2. **Filepath normalization tests** - Test various path formats including Unicode
    3. **Tag database operation tests** - Test insert, update, delete flows
    4. **API response format tests** - Verify consistent response structure
    5. **Integration tests** - Test full image processing pipeline
    
    ### Test Files to Create
    
    ```
    tests/
    ├── test_tag_extraction.py      # New - test extract_tags_from_source()
    ├── test_api_responses.py       # New - test response utilities
    ├── test_file_utils.py          # Extend - test normalize_image_path()
    ├── test_decorators.py          # New - test api_handler decorator
    └── test_query_builder.py       # New - test query builder (Phase 4)
    ```
    
    ### Sample Test
    
    ```python
    # tests/test_tag_extraction.py
    import pytest
    from utils.tag_extraction import extract_tags_from_source, deduplicate_categorized_tags
    
    class TestExtractTagsFromSource: 
        def test_danbooru_extraction(self):
            source_data = {
                "tag_string_character": "holo",
                "tag_string_copyright": "spice_and_wolf",
                "tag_string_general": "1girl wolf_ears",
            }
            result = extract_tags_from_source(source_data, 'danbooru')
            
            assert result['tags_character'] == "holo"
            assert result['tags_copyright'] == "spice_and_wolf"
            assert result['tags_general'] == "1girl wolf_ears"
            assert result['tags_species'] == ""  # Danbooru has no species
        
        def test_e621_extraction(self):
            source_data = {
                "tags": {
                    "character":  ["holo"],
                    "copyright":  ["spice_and_wolf"],
                    "species": ["wolf"],
                    "general":  ["1girl", "wolf_ears"],
                }
            }
            result = extract_tags_from_source(source_data, 'e621')
            
            assert result['tags_character'] == "holo"
            assert result['tags_species'] == "wolf"
            assert "1girl" in result['tags_general']
    
        def test_deduplication(self):
            tags = {
                'tags_character': 'holo',
                'tags_general': 'holo 1girl wolf_ears',  # holo is duplicate
            }
            result = deduplicate_categorized_tags(tags)
            
            assert 'holo' not in result['tags_general']
            assert '1girl' in result['tags_general']
    ```
    
    ---
    
    ## Migration Checklist
    
    ### Pre-Migration
    
    - [x] Ensure all tests pass ✅
    - [x] Create a new branch for refactoring ✅ **copilot/add-standardized-api-responses**
    - [ ] Back up production database (if applicable)
    
    ### Phase 1 Checklist ✅ **COMPLETED**

    - [x] Create `utils/api_responses.py` ✅ **COMPLETED**
    - [x] Create `utils/decorators.py` ✅ **COMPLETED**
    - [x] Update `config.py` with constants ✅ **COMPLETED** (file types, Defaults, Timeouts, Intervals, Thresholds, Limits)
    - [x] Create `utils/logging_config.py` ✅ **COMPLETED**
    - [x] Update `app.py` to initialize logging ✅ **COMPLETED**
    - [x] Update 5 endpoints to use new patterns (pilot) ✅ **COMPLETED** (3 in pools.py, 2 in rating.py)
    - [x] Test pilot endpoints manually ✅ **20 tests passing**
    - [x] Run full test suite ✅ **All API response tests passing**
    
    ### Phase 2 Checklist - Tag Extraction ✅ **COMPLETED**

    - [x] Create `utils/tag_extraction.py` ✅ **COMPLETED**
    - [x] Update `utils/__init__.py` exports ✅ **COMPLETED**
    - [x] Refactor `services/processing_service.py` ✅ **COMPLETED** (~54 lines → ~28 lines)
    - [x] Refactor `services/image_service.py` ✅ **COMPLETED** (2 locations refactored)
    - [x] Refactor `database/models.py` ✅ **COMPLETED**
    - [x] Refactor `services/switch_source_db.py` ✅ **COMPLETED** (~111 lines → ~51 lines)
    - [x] Run full test suite ✅ **All 20 tests passing**

    #### Deferred to Future Phase:
    - [ ] Add tag database utilities
    - [ ] Add path utilities to `utils/file_utils.py`
    - [ ] Create `static/js/utils/path-utils.js`
    - [ ] Update JavaScript files to use path-utils
    
    ### Phase 3 Checklist - API Endpoint Refactoring (IN PROGRESS)

    #### Completed:
    - [x] Refactor `routers/api/pools.py` ✅ (3 endpoints - Phase 1)
    - [x] Refactor `routers/api/rating.py` ✅ (2 endpoints - Phase 1)
    - [x] Refactor `routers/api/tag_categorization.py` ✅ **9 endpoints, ~110 lines removed**

    #### In Progress:
    - [ ] Refactor `routers/api/system.py` with decorators
    - [ ] Refactor `routers/api/tags.py` with decorators
    - [ ] Refactor `routers/api/images.py` with decorators
    - [ ] Refactor `routers/api/saucenao.py` with decorators
    - [ ] Refactor `routers/api/implications.py` with decorators

    #### Deferred JavaScript Work:
    - [ ] Update `static/js/utils/helpers.js` with shared functions
    - [ ] Update JS files to import from helpers
    - [ ] Standardize notification imports in all JS files
    - [ ] Add cache invalidation helpers
    - [ ] Extract template JS to page modules
    
    ### Post-Migration
    
    - [ ] Manual testing of key flows: 
      - [ ] Upload new image
      - [ ] Edit tags
      - [ ] Switch source
      - [ ] Retry tagging
      - [ ] View image with Japanese filename
      - [ ] Rate an image
      - [ ] Browse tags
    - [ ] Update documentation
    - [ ] Create PR with detailed description
    - [ ] Code review
    - [ ] Merge and deploy
    
    ---
    
    ## Appendix A: File Creation Summary
    
    ### New Python Files
    
    | File | Purpose |
    |------|---------|
    | `utils/tag_extraction.py` | Tag extraction, deduplication, rating utilities |
    | `utils/api_responses. py` | Standardized API response functions |
    | `utils/decorators.py` | api_handler, sync_to_async decorators |
    | `utils/logging_config.py` | Logging setup and get_logger function |
    | `utils/query_builder.py` | (Phase 4) Query builder for searches |
    
    ### New JavaScript Files
    
    | File | Purpose |
    |------|---------|
    | `static/js/utils/path-utils.js` | URL encoding, path normalization |
    | `static/js/utils/dom. js` | DOM element creation helpers |
    | `static/js/config.js` | JavaScript constants |
    | `static/js/pages/rate-manage.js` | (Phase 3) Extracted from template |
    | `static/js/pages/rate-review.js` | (Phase 3) Extracted from template |
    | `static/js/pages/tag-categorize. js` | (Phase 3) Extracted from template |
    
    ### Files to Modify
    
    | File | Changes |
    |------|---------|
    | `utils/__init__.py` | Add new exports |
    | `utils/file_utils. py` | Add path normalization functions |
    | `config.py` | Add constants classes, file extension helpers |
    | `app.py` | Initialize logging |
    | `static/js/utils/helpers.js` | Add getCategoryIcon, getCategoryClass |
    
    ---
    
    ## Appendix B: Dependency Graph
    
    ```
                         ┌─────────────────┐
                         │     config      │
                         │   (constants)   │
                         └────────┬────────┘
                                  │
                ┌─────────────────┼─────────────────┐
                │                 │                 │
                ▼                 ▼                 ▼
        ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
        │    utils/     │ │   database/   │ │    core/      │
        │tag_extraction │ │     core      │ │cache_manager  │
        │api_responses  │ │               │ │               │
        │ decorators    │ └───────┬───────┘ └───────┬───────┘
        │logging_config │         │                 │
        │ file_utils    │         │                 │
        └───────┬───────┘         │                 │
                │                 │                 │
                └─────────────────┼─────────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  repositories/  │
                         │  data_access    │
                         │  tag_repository │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    services/    │
                         │ processing_svc  │
                         │   image_svc     │
                         │   query_svc     │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │    routers/     │
                         │    web. py       │
                         │    api/*. py     │
                         └─────────────────┘
    ```
    
    ---
    
    ## Appendix C:  Estimated Impact Summary
    
    | Category | Lines Removed | Files Affected | Bug Risk Reduction |
    |----------|---------------|----------------|-------------------|
    | Tag Extraction | ~200 | 5 | High |
    | API Responses | ~100 | 20+ | High |
    | Exception Handling | ~150 | 30+ | Medium |
    | Logging | ~100 | 15+ | Low |
    | Tag Database Ops | ~100 | 8 | High |
    | Filepath Handling (Py) | ~30 | 10+ | Medium |
    | Filepath Handling (JS) | ~50 | 7+ | Medium |
    | Magic Numbers | ~20 | 10+ | Low |
    | File Extensions | ~10 | 5+ | Low |
    | Pagination | ~30 | 5+ | Medium |
    | **Total** | **~790** | **~50+** | **High** |
    
    ---
    
    ## Notes
    
    - Search results may be incomplete.  See [GitHub Code Search](https://github.com/search?q=repo%3Akooten111%2FChibiBooru&type=code) for additional occurrences.
    - Some patterns may exist in files not covered by this analysis.
    - Consider creating a `CONTRIBUTING.md` with coding guidelines to prevent future duplication.
    - This document should be updated as refactoring progresses. 
    
    ---
    
    ## Revision History
    
    | Date | Version | Changes |
    |------|---------|---------|
    | 2025-12-10 | 1.0 | Initial analysis with 21 issues identified |

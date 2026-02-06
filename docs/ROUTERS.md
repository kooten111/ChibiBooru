# Routers Layer Documentation

## Table of Contents
- [Overview](#overview)
- [Web Routes](#web-routes)
- [API Routes](#api-routes)
- [Authentication](#authentication)

---

## Overview

The Routers layer handles HTTP request routing and response formatting. It connects the frontend to services and renders templates or returns JSON.

### Architecture
- **Web Routes** (`routers/web.py`): Server-side rendered HTML pages
- **API Routes** (`routers/api/`): JSON API endpoints for AJAX requests

### Blueprints
- `main_blueprint`: Main web UI routes (registered at `/`)
- `api_blueprint`: API routes (registered at `/api`)

---

## Web Routes

**File**: `routers/web.py`

### Authentication

#### `@login_required` Decorator

Protects routes requiring authentication.

**Redirects to**: `/login` if not authenticated

**Example**:
```python
@main_blueprint.route('/protected')
@login_required
async def protected_route():
    return await render_template('page.html')
```

---

### Routes

#### `GET /login`
Login page.

**Template**: `login.html`

#### `POST /login`
Process login form.

**Form Data**:
- `password`: App password

**Success**: Sets session and redirects to `/`

---

#### `GET /logout`
Logout and clear session.

**Redirect**: `/login`

---

#### `GET /` (home)
Main gallery view with search.

**Query Parameters**:
- `query`: Search query

**Template**: `index.html`

**Data**:
- First 50 images
- Random tags
- Collection stats
- Search results count

---

#### `GET /image/<path:filepath>`
Image detail page.

**Parameters**:
- `filepath`: Relative image path

**Template**: `image.html`

**Data**:
- Image details
- Tags by category
- Related images
- Available sources
- Similar images
- Pools containing image

---

#### `GET /tags`
Tag browser page.

**Template**: `tags.html`

**Data**:
- All tags sorted alphabetically
- Tag counts and categories

---

#### `GET /pools`
Pool list page.

**Query Parameters**:
- `query`: Search pools

**Template**: `pools.html`

---

#### `GET /pool/<int:pool_id>`
Pool detail page.

**Template**: `pool.html`

**Data**:
- Pool info
- Ordered images

---

#### `GET /implications`
Tag implications management.

**Template**: `implications.html`

**Data**:
- Pending implications
- Active implications

---

#### `GET /upload`
File upload interface.

**Template**: `upload.html`

---

#### `POST /upload`
Handle file uploads.

**Form Data**:
- Files (multipart/form-data)

**Process**:
1. Save files to temp location
2. Process each image
3. Generate thumbnails
4. Fetch metadata
5. Return results

**Returns**: JSON with success/failure per file

---

#### `GET /system`
System management panel.

**Template**: `system.html`

**Features**:
- Scan & process
- Database rebuild
- Monitor control
- Deduplication

---

#### `GET /rate/review`
Rating review interface.

**Template**: `rate_review.html`

---

#### `GET /rate/manage`
Rating management dashboard.

**Template**: `rate_manage.html`

---

#### `GET /tag_categorize`
Tag categorization interface.

**Template**: `tag_categorize.html`

---

## API Routes

### API Conventions

- **JSON body (required):** Use `data = await request.get_json()` then validate with `if not data: raise ValueError("Request body is required")` (or use `require_json_body()` from `utils.request_helpers`).
- **JSON body (optional):** Use `data = (await request.get_json(silent=True)) or {}` so missing or invalid JSON is treated as an empty dict.
- **Decorators:** Use `@api_handler()` from `utils` on all API endpoints; use `from utils import api_handler, require_secret` for consistency.
- **Responses:** The standard is to return a plain dict from API handlers; `@api_handler()` then adds `success: True` and wraps the response, and catches exceptions into a consistent `{ "success": false, "error": "..." }` shape. For explicit control over status codes or message shape, use `success_response` / `error_response` from `utils.api_responses` (see [utils/api_responses.py](utils/api_responses.py)); rating routes use these. Either style is fine; prefer dict + `@api_handler()` for simple endpoints.

### Images API (`/api/images`)

**File**: `routers/api/images.py`

#### `POST /api/images/delete`
Delete an image.

**Request**:
```json
{
    "filepath": "images/folder/image.jpg"
}
```

**Response**:
```json
{
    "status": "success",
    "message": "Deletion process completed."
}
```

---

#### `POST /api/images/delete-bulk`
Delete multiple images.

**Request**:
```json
{
    "filepaths": ["images/a.jpg", "images/b.jpg"]
}
```

**Response**:
```json
{
    "total": 2,
    "deleted": 2,
    "failed": 0,
    "errors": []
}
```

---

#### `GET /api/images`
Get paginated images for infinite scroll.

**Query Parameters**:
- `query`: Search query
- `page`: Page number
- `seed`: Random seed

**Response**:
```json
{
    "images": [...],
    "page": 1,
    "total_pages": 10,
    "total_results": 500,
    "has_more": true
}
```

---

### Animation API (`/api/animation`)

**File**: `routers/api/animation.py`

#### `GET /api/animation/metadata/<path:filepath>`
Get metadata for an animation file (Zip, GIF, WebP).
Returns frame count, dimensions, and FPS.

#### `GET /api/animation/frame/<md5>/<int:frame_index>`
Serve a specific frame from a zip animation.

#### `GET /api/animation/frames/<md5>`
Get absolute URLs for all frames of a zip animation.

---

### Favourites API (`/api/favourites`)

**File**: `routers/api/favourites.py`

#### `POST /api/favourites/toggle`
Toggle favourite status for an image.

#### `GET /api/favourites/status`
Check if an image is favourited.

#### `GET /api/favourites/count`
Get total count of user favourites.

---

### Tags API (`/api/tags`)

**File**: `routers/api/tags.py`

#### `POST /api/tags/edit`
Edit image tags.

**Request**:
```json
{
    "filepath": "images/image.jpg",
    "categorized_tags": {
        "character": ["hatsune_miku"],
        "general": ["1girl"]
    }
}
```

---

#### `GET /api/tags/autocomplete`
Tag autocomplete suggestions.

**Query Parameters**:
- `q`: Search query

**Response**:
```json
{
    "groups": [
        {
            "name": "Tags",
            "items": [...]
        }
    ]
}
```

---

### Pools API (`/api/pools`)

**File**: `routers/api/pools.py`

#### `POST /api/pools/create`
Create new pool.

**Request**:
```json
{
    "name": "My Collection",
    "description": "..."
}
```

---

#### `POST /api/pools/add-image`
Add image to pool.

**Request**:
```json
{
    "pool_id": 1,
    "filepath": "images/image.jpg"
}
```

---

#### `POST /api/pools/remove-image`
Remove image from pool.

---

#### `POST /api/pools/reorder`
Reorder pool images.

**Request**:
```json
{
    "pool_id": 1,
    "ordered_filepaths": ["images/a.jpg", "images/b.jpg"]
}
```

---

#### `POST /api/pools/delete`
Delete pool.

---

### System API (`/api/system`)

**File**: `routers/api/system.py`

#### `POST /api/system/scan`
Scan and process new images.

**Requires**: `SYSTEM_API_SECRET`

---

#### `POST /api/system/rebuild`
Rebuild database from metadata.

**Requires**: `SYSTEM_API_SECRET`

---

#### `POST /api/system/monitor/start`
Start background monitor.

**Requires**: `SYSTEM_API_SECRET`

---

#### `POST /api/system/monitor/stop`
Stop background monitor.

**Requires**: `SYSTEM_API_SECRET`

---

#### `GET /api/system/monitor/status`
Get monitor status.

**Response**:
```json
{
    "running": true,
    "last_check": "2024-01-01T12:00:00",
    "total_processed": 100,
    "logs": [...]
}
```

---

### Similarity API (`/api/similarity`)

**File**: `routers/api/similarity.py`

#### `GET /api/similar/<path:filepath>`
Find visually similar images using perceptual hash comparison.

#### `GET /api/similar-semantic/<path:filepath>`
Find semantically similar images using FAISS embeddings.

#### `GET /api/similar-blended/<path:filepath>`
Blended search using visual, tag, and semantic similarity.

#### `POST /api/similarity/generate-hashes`
Trigger background task to generate missing hashes.

---

### Rating API (`/api/rating`)

**File**: `routers/api/rating.py`

#### `POST /api/rating/train`
Train rating inference model.

---

#### `POST /api/rating/infer`
Infer rating for images.

---

#### `GET /api/rating/config`
Get inference configuration.

---

#### `POST /api/rating/config`
Update inference configuration.

---

### Implications API (`/api/implications`)

**File**: `routers/api/implications.py`

#### `GET /api/implications/pending`
Get pending implications.

---

#### `POST /api/implications/approve`
Approve implication.

---

#### `POST /api/implications/create`
Create manual implication.

---

#### `POST /api/implications/delete`
Delete implication.

---

---

### Upscaler API (`/api/upscale`)

**File**: `routers/api/upscaler.py`

#### `POST /api/upscale`
Request an AI upscale for an image.

#### `GET /api/upscale/status`
Check ML worker and model availability.

#### `GET /api/upscale/check`
Check if an upscaled version already exists.

#### `DELETE /api/upscale`
Delete an upscaled version.

---

## Authentication

### Session-Based Auth
- Uses Flask sessions
- Session timeout: 4 hours (`PERMANENT_SESSION_LIFETIME`)
- Session key: `logged_in`

### Password Configuration
- `APP_PASSWORD` environment variable
- Set in `.env` file
- Required for all protected routes

### Protecting Routes
```python
@main_blueprint.route('/protected')
@login_required
async def protected():
    # User is authenticated
    pass
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SERVICES.md](SERVICES.md) - Business logic called by routers
- [DATABASE.md](DATABASE.md) - Database schema

# ChibiBooru Architecture

## Table of Contents
- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Layer Architecture](#layer-architecture)
- [Application Lifecycle](#application-lifecycle)
- [Technology Stack](#technology-stack)
- [Design Patterns](#design-patterns)

## Overview

ChibiBooru is a self-hosted image booru application built with a layered architecture pattern. The system fetches metadata from multiple online sources (Danbooru, e621, Gelbooru, Yandere, Pixiv) and uses AI-based tagging as a fallback, providing a rich, searchable media library.

### Key Characteristics
- **Async-first design**: Built on Quart (async Flask) with Uvicorn ASGI server
- **SQLite database**: Fast, embedded database with WAL mode and FTS5 full-text search
- **In-memory caching**: Thread-safe caches for tags and image data
- **Event-driven cache invalidation**: Automatic cache updates on data changes
- **Multi-source metadata**: Aggregates tags from 6+ different sources
- **AI integration**: Local ONNX-based image tagging and rating inference

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Client (Browser)                        │
│              HTML + JavaScript + CSS                        │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/HTTPS
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                  Web Server Layer                           │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐                     │
│  │  Uvicorn     │───▶│   Quart      │                     │
│  │  ASGI Server │    │   Web App    │                     │
│  └──────────────┘    └──────┬───────┘                     │
└─────────────────────────────┼───────────────────────────────┘
                              │
                ┌─────────────┴────────────┐
                │                          │
                ↓                          ↓
┌─────────────────────────┐   ┌──────────────────────────┐
│   Routers (Blueprints)  │   │   Static File Serving    │
│                         │   │   (Images, Thumbnails)   │
│  • Web Routes           │   └──────────────────────────┘
│  • API Endpoints        │
└────────┬────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────────┐
│                     Services Layer                          │
│  (Business Logic)                                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Image        │  │ Processing   │  │ Query          │  │
│  │ Service      │  │ Service      │  │ Service        │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Tag          │  │ Rating       │  │ SauceNao       │  │
│  │ Service      │  │ Service      │  │ Service        │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ System       │  │ Monitor      │  │ Health         │  │
│  │ Service      │  │ Service      │  │ Service        │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Implication  │  │ Priority     │  │ Background     │  │
│  │ Service      │  │ Service      │  │ Tasks          │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ Switch       │  │ Tag Cat.     │                       │
│  │ Source       │  │ Service      │                       │
│  └──────────────┘  └──────────────┘                       │
└────────┬────────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────────┐
│                  Repositories Layer                         │
│  (Data Access)                                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Data Access  │  │ Tag          │  │ Pool           │  │
│  │ Repository   │  │ Repository   │  │ Repository     │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ Rating       │  │ Delta        │                       │
│  │ Repository   │  │ Tracker      │                       │
│  └──────────────┘  └──────────────┘                       │
└────────┬────────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                       │
│  │ Database     │  │ ORM Models   │                       │
│  │ Core         │  │ & Schema     │                       │
│  └──────────────┘  └──────────────┘                       │
└────────┬────────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────────┐
│             SQLite Database (data/booru.db)                      │
│                                                             │
│  • Images table with FTS5 full-text search                 │
│  • Tags, Sources, Pools                                    │
│  • Relationships and Implications                          │
│  • Raw metadata (JSON storage)                             │
│  • Rating inference model data                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Supporting Components                      │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ Core         │  │ Events       │  │ Utils          │  │
│  │ (Cache Mgr)  │  │ (Cache Evt)  │  │ (File, Dedup)  │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   External Services                         │
│                                                             │
│  • Danbooru API    • e621 API      • Gelbooru API          │
│  • Yandere API     • Pixiv API     • SauceNao API          │
│  • Local ONNX Tagger (models/Tagger/)                      │
└─────────────────────────────────────────────────────────────┘
```

## Layer Architecture

### 1. Routers Layer (`routers/`)
**Responsibility**: Handle HTTP requests and route to appropriate services

- **Web Router** (`web.py`): Main UI routes, authentication, page rendering
- **API Routers** (`api/`): RESTful endpoints for AJAX operations
  - Images, Tags, Pools, Rating, System, SauceNao, Implications

**Key Features**:
- Request validation
- Session management
- Response formatting (JSON/HTML)
- Error handling and status codes

### 2. Services Layer (`services/`)
**Responsibility**: Business logic, orchestration, external integrations

Contains 14 specialized services (see [SERVICES.md](SERVICES.md)):
- Image CRUD and bulk operations
- Metadata fetching from multiple sources
- Search and similarity calculations
- AI rating and tagging
- Background monitoring
- Database health checks

**Key Features**:
- Coordinate between multiple data sources
- Implement business rules
- Handle async operations
- Rate limiting for external APIs
- Event triggering for cache invalidation

### 3. Repositories Layer (`repositories/`)
**Responsibility**: Data access abstraction, database operations

- **data_access.py**: Core CRUD operations, queries
- **tag_repository.py**: Tag-specific operations
- **pool_repository.py**: Pool management
- **rating_repository.py**: Rating model data access
- **delta_tracker.py**: Track manual tag modifications

**Key Features**:
- SQL query construction
- Transaction management
- Data validation
- Relationship mapping

### 4. Database Layer (`database/`)
**Responsibility**: Database schema, connection management, ORM

- **core.py**: Connection factory, initialization, migrations
- **models.py**: SQLAlchemy-style models, schema definitions

**Key Features**:
- SQLite with WAL mode
- FTS5 full-text search
- Foreign key constraints
- Automatic schema migrations
- Index optimization

### 5. Core Infrastructure
**Responsibility**: Cross-cutting concerns

- **Cache Manager** (`core/cache_manager.py`): In-memory caches
- **Events** (`events/cache_events.py`): Cache invalidation events
- **Utils** (`utils/`): File operations, deduplication

## Application Lifecycle

### Startup Sequence

```python
# app.py - Application entry point
1. Load environment variables (.env)
2. Create Quart application
3. Initialize database (create tables, indexes)
4. Repair orphaned image tags (data integrity)
5. Run health checks (startup_health_check)
6. Check priority changes (BOORU_PRIORITY_VERSION)
7. Load data from DB into memory caches
8. Register blueprints (web + API)
9. Start Uvicorn server
```

**Startup Health Checks**:
- Verify database integrity
- Check for corrupted metadata
- Validate FTS5 index
- Auto-repair common issues
- Log warnings for missing configurations

### Request Lifecycle (Web)

```
1. Browser → HTTP Request → Uvicorn
2. Uvicorn → Quart routing → Router (web.py)
3. Router → Authentication check (session)
4. Router → Service layer (business logic)
5. Service → Repository (data access)
6. Repository → Database (SQL queries)
7. Database → Repository (results)
8. Repository → Service (processed data)
9. Service → Router (prepared data)
10. Router → Template rendering (Jinja2)
11. Router → HTTP Response → Uvicorn → Browser
```

### Request Lifecycle (API)

```
1. JavaScript → AJAX Request → Uvicorn
2. Uvicorn → Quart routing → API Router
3. API Router → Service layer
4. Service → Repository → Database
5. Database → Repository → Service
6. Service → API Router
7. API Router → JSON Response → JavaScript
8. JavaScript → Update UI (no page reload)
```

### Background Tasks

```
Monitor Service (Optional)
↓
1. Watch filesystem (watchdog library)
2. Detect new files in static/images/ or ingest/
3. Queue files for processing
4. Process in batches (batch_size=10, delay=3s)
5. Trigger metadata fetching
6. Move files from ingest/ to static/images/
7. Generate thumbnails
8. Update database
9. Invalidate caches
10. Wait for next interval (default 300s)
```

## Technology Stack

### Backend
- **Web Framework**: Quart 0.20.0 (async Flask)
- **ASGI Server**: Uvicorn 0.38.0 with standard extras
- **Database**: SQLite 3 with WAL mode
- **HTTP Client**: Requests 2.32.5
- **Image Processing**: Pillow 12.0.0
- **AI/ML**: ONNX Runtime (optional), PyTorch (optional)
- **Monitoring**: Watchdog 6.0.0
- **Config**: python-dotenv 1.2.0

### Frontend
- **Templates**: Jinja2 3.1.6
- **JavaScript**: Vanilla JS (no framework)
- **CSS**: Custom CSS with responsive design
- **UI**: Infinite scroll, drag-and-drop upload

### Database Schema
- **Tables**: 15+ tables (images, tags, sources, pools, etc.)
- **Indexes**: 20+ optimized indexes
- **FTS5**: Full-text search on tags and filenames
- **Triggers**: Automatic FTS updates on data changes

### External APIs
- Danbooru, e621, Gelbooru, Yandere, Pixiv
- SauceNao (reverse image search)
- Local ONNX models (AI tagging)

## Design Patterns

### 1. Layered Architecture
Clean separation between routers, services, repositories, and database.

### 2. Repository Pattern
Abstract data access behind repository interfaces.

### 3. Service Layer Pattern
Centralize business logic in service classes.

### 4. Event-Driven Cache Invalidation
Services trigger cache invalidation events rather than directly managing caches.

```python
# Events pattern example
from events.cache_events import trigger_cache_invalidation

def update_tags(...):
    # Update database
    db.execute(...)
    
    # Trigger cache invalidation
    trigger_cache_invalidation()
```

### 5. Singleton Pattern
Global cache instances managed by cache_manager.

### 6. Factory Pattern
Database connection factory in `database/core.py`.

### 7. Strategy Pattern
Similarity calculation methods (Jaccard vs. Weighted IDF).

```python
if config.SIMILARITY_METHOD == 'weighted':
    return calculate_weighted_similarity(tags1, tags2)
else:
    return calculate_jaccard_similarity(tags1, tags2)
```

### 8. Adapter Pattern
Rate limiter adapts external API behavior to internal needs.

### 9. Observer Pattern
Cache invalidation callbacks registered from different modules.

```python
# Register cache invalidation callback
register_cache_invalidation_callback(invalidate_similarity_cache)
```

### 10. Template Method Pattern
Base processing logic with customizable steps for different metadata sources.

## Data Flow Patterns

### Write Path (New Image)
```
1. File uploaded/detected
2. Calculate MD5 hash
3. Check for duplicates
4. Fetch metadata from sources (parallel)
5. Apply tag implications
6. Infer rating (AI)
7. Generate thumbnail
8. Insert into database
9. Invalidate caches
10. Update FTS index (automatic)
```

### Read Path (Search)
```
1. Parse search query
2. Check if FTS needed (fuzzy search)
3. Execute optimized SQL query
4. Calculate similarity scores
5. Apply filters (source, relationship, pool)
6. Sort and paginate results
7. Return results to client
```

### Cache Invalidation Flow
```
1. Data modification in service
2. Service triggers cache event
3. Cache manager receives event
4. Invalidate affected caches
5. Next read rebuilds cache from DB
```

## Security Considerations

### Authentication
- Session-based login with `APP_PASSWORD`
- `SECRET_KEY` for session encryption
- `SYSTEM_API_SECRET` for system operations

### Database
- Parameterized queries (SQL injection prevention)
- Foreign key constraints (referential integrity)
- Transaction isolation

### File Operations
- Path validation (prevent directory traversal)
- File type validation (image files only)
- MD5-based deduplication

### API Rate Limiting
- Adaptive rate limiter for SauceNao
- Configurable delays between requests
- Automatic backoff on 429 errors

## Performance Optimizations

### Database
- Indexes on all foreign keys
- Composite indexes for common queries
- FTS5 for fast full-text search
- WAL mode for concurrent reads
- PRAGMA settings for performance

### Caching
- In-memory tag counts
- In-memory image data
- LRU cache for similarity calculations
- Cross-source post_id mapping

### Parallel Processing
- ThreadPoolExecutor for metadata fetching
- Configurable worker pool size
- Batching for monitor service

### Image Processing
- Lazy thumbnail generation
- WebP format for thumbnails
- Configurable thumbnail size

## Scalability Notes

### Current Limitations
- Single SQLite database (not distributed)
- In-memory caches (limited by RAM)
- Single-server deployment

### Scaling Strategies
- Increase `MAX_WORKERS` for parallel processing
- Adjust `IMAGES_PER_PAGE` for pagination
- Use larger `THUMB_SIZE` for better quality
- Enable WAL mode for better concurrency

### Future Improvements
- Redis for distributed caching
- PostgreSQL for larger datasets
- Celery for background task queue
- CDN for static file serving

## Related Documentation

- [DATABASE.md](DATABASE.md) - Database schema and models
- [SERVICES.md](SERVICES.md) - Service layer documentation
- [REPOSITORIES.md](REPOSITORIES.md) - Data access layer
- [ROUTERS.md](ROUTERS.md) - Web and API routes
- [CORE.md](CORE.md) - Core infrastructure
- [DATA_FLOW.md](DATA_FLOW.md) - End-to-end data flows
- [CONFIGURATION.md](CONFIGURATION.md) - Configuration options

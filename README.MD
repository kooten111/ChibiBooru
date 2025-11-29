# ChibiBooru

A self-hosted web application for organizing and browsing your local image collection with automated metadata fetching and intelligent tagging. ChibiBooru combines a user-friendly interface with powerful backend tools to create a rich, searchable media library similar to popular image boorus.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Development](#development)
- [Advanced Topics](#advanced-topics)

---

## Screenshots

![Main gallery interface showing the image grid layout with search and filtering options](file:///home/kooten/.gemini/antigravity/brain/506c5117-283e-4d0c-b7c4-b6bfac03e50d/gallery_rating_general_1764451926828.png)
*Gallery view with rating:general filter showing safe content*

![Image detail page displaying the full image, metadata, tags, and related information](file:///home/kooten/.gemini/antigravity/brain/506c5117-283e-4d0c-b7c4-b6bfac03e50d/image_detail_view_1764451986439.png)
*Image detail page with tag editor and metadata viewer*

---

## Features

### 🎨 Automated Metadata & Tagging

- **Multi-Source Tag Fetching:**
  - **Direct Hash Matching:** Finds metadata from Danbooru, e621, Gelbooru, and Yandere using MD5 hash
  - **Pixiv Integration:** Fetches tags and artist info from Pixiv, automatically complemented with local AI tagging
  - **Reverse Image Search:** Uses SauceNao to discover sources when direct matching fails
  - **AI Tagging:** Local ONNX-based tagger analyzes images with no online matches
  - **Flexible Source Switching:** View tags from different sources or merge them all together

- **AI Rating Inference:** Automatic content rating detection (Safe, Questionable, Explicit) with confidence scores

### 🔍 Advanced Search System

- **Tag Search:** Intelligent autocomplete with category-specific filtering (`character:name`, `artist:name`, `copyright:series`)
- **Full-Text Search:** FTS5-powered fuzzy matching and partial tag search
- **Negative Filters:** Exclude tags with `-` prefix (e.g., `-sketch`)
- **File Filters:** Search by filename (`filename:text`) or extension (`.png`, `.gif`)
- **Relationship Filters:** Find parent/child images (`has:parent`, `has:child`, `has:relationship`)
- **Pool Search:** Find images in collections (`pool:series_name`)
- **Source Filtering:** Filter by metadata source (`source:danbooru`)
- **Smart Similarity:** Weighted similarity matching that prioritizes rare tags and important categories

### 🏷️ Tag Management

- **Full Tag Control:**
  - Inline tag editor with category management
  - Switch between metadata sources on-the-fly
  - Tag delta tracking preserves manual edits across rebuilds
  
- **Tag Implications:**
  - Automatic detection via naming patterns and statistical analysis
  - Manual creation and approval workflow
  - Chain preview to see full impact before applying

### 📚 Organization Tools

- **Pools:** Create named collections with custom image ordering
- **Relationships:** Automatic parent/child relationship detection and display
- **Tag Browser:** Browse all tags by category with usage statistics

### ⚙️ System Management

- **Authentication:** Password-protected web interface with session-based login
- **Image Upload:** Drag-and-drop interface with automatic processing
- **Ingest Folder:** Drop images in the ingest folder for automated processing
- **Background Monitor:** Optional service that watches for new files and processes them automatically
- **Debug Panel:** Comprehensive tools for database maintenance, optimization, and bulk operations
- **Health Checks:** Automatic startup health checks with self-repair capabilities

---

## Quick Start

```bash
# Clone and install
git clone <repository-url>
cd Booru
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your settings (set APP_PASSWORD, SECRET_KEY, RELOAD_SECRET)

# Run
python app.py
# Visit http://127.0.0.1:5000
```

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Git (for cloning the repository)

### Step-by-Step Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Booru
   ```

2. **Create a virtual environment** (highly recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Optional: Install AI tagging dependencies:**
   ```bash
   pip install -r requirements-ai.txt
   ```
   Then place your ONNX model files in `models/Tagger/` (e.g., `model.onnx`, `metadata.json`)

5. **Optional: Install development dependencies:**
   ```bash
   pip install -r requirements-dev.txt
   ```

---

## Configuration

### Environment Setup

Copy the example configuration file:

```bash
cp .env.example .env
```

### Required Settings

Edit `.env` and set these **required** values:

```env
# REQUIRED: Change these before first use!
APP_PASSWORD="your-secure-password"
SECRET_KEY="your-secret-key-for-sessions"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
RELOAD_SECRET="your-reload-secret"
```

### Optional Settings

```env
# Application
APP_NAME="ChibiBooru"

# API Keys (optional, but recommended)
SAUCENAO_API_KEY="your_saucenao_api_key"  # Get from https://saucenao.com/user.php
GELBOORU_API_KEY=""
GELBOORU_USER_ID=""

# AI Tagging
LOCAL_TAGGER_NAME="CamieTagger"  # Display name for your AI tagger

# Web Server
FLASK_HOST="0.0.0.0"  # 0.0.0.0 allows external connections
FLASK_PORT="5000"
FLASK_DEBUG="false"

# Similarity
SIMILARITY_METHOD="weighted"  # Options: 'jaccard' or 'weighted'
```

### Security Best Practices

> [!CAUTION]
> - **Always change** `APP_PASSWORD`, `SECRET_KEY`, and `RELOAD_SECRET` before deployment
> - **Never commit** your `.env` file to version control (already in `.gitignore`)
> - Use strong, random values for all secrets
> - Keep API keys private and secure

### Directory Setup

Place your image collection in:
```
static/images/
```

You can organize images in subdirectories. ChibiBooru will scan recursively.

Optionally, use the ingest folder for automatic processing:
```
ingest/
```

Images dropped here will be automatically detected, processed, and moved to the main collection.

---

## Usage

### Initial Setup

1. **Start the application:**
   ```bash
   python app.py
   # Or use: ./start_uvicorn.sh
   ```

2. **Open the web interface** at `http://127.0.0.1:5000`

3. **Log in** with your `APP_PASSWORD` from `.env`

4. **Open the System panel** (gear icon in header) and enter your `RELOAD_SECRET`

5. **Scan & Process Images:**
   - Click **"Scan & Process New Images"** to begin indexing
   - This fetches metadata for all images (may take time for large collections)
   - Progress is shown in real-time

6. **Optional: Start the Monitor** to automatically process new images added to `static/images/` or `ingest/`

### Searching Images

**Basic tag search:**
```
1girl blue_hair
```

**Category-specific search:**
```
character:holo
copyright:spice_and_wolf
artist:artist_name
species:wolf
```

**Advanced queries:**
```
source:danbooru              # Filter by metadata source
filename:cute_cat            # Search in filename
.png                         # Filter by extension
has:parent                   # Has parent relationship
has:child                    # Has child relationship
pool:series_name             # In specific pool
-sketch -monochrome          # Exclude tags
```

**Combined example:**
```
character:holo source:danbooru .png -sketch
```

### Managing Tags

1. Click on an image to view its detail page
2. Click **"Edit Tags"** to open the inline editor
3. Add/remove tags within their categories
4. Click **"Save Tags"** when done
5. Your changes persist even through database rebuilds (delta tracking)

**Switching metadata sources:**
- Use the source dropdown to view tags from different providers
- Enable "Merged" to see tags from all sources combined

### Tag Implications

1. Navigate to **Implications** from the header menu
2. Review auto-detected suggestions:
   - **Pattern-based:** e.g., `character_(costume)_(series)` → `character_(series)`
   - **Statistical:** Tags that commonly appear together
3. Approve suggestions to apply them automatically
4. Create manual implications for custom relationships
5. View active implications and their impact

### Creating Pools

1. Go to **Pools** from the header menu
2. Click **"Create New Pool"**
3. Name your pool and add a description
4. Add images from detail pages or pool management
5. Search for pools using `pool:<name>`

### Uploading Images

1. Click **Upload** in the header
2. Drag and drop or select files
3. Images are automatically processed and added

### Debug & Maintenance

Access the **Debug** section in the System panel for:

- **Database Maintenance:**
  - Full reindex and optimization
  - FTS rebuild
  - Orphan cleanup
  
- **Tag & Metadata:**
  - Rebuild tags from sources
  - Apply tag implications
  - Retry failed tagging
  
- **Advanced:**
  - Find duplicates
  - Generate missing thumbnails
  - Database health checks

---

## Project Structure

```
Booru/
├── app.py                  # Application entry point with Quart + Uvicorn
├── config.py               # Centralized configuration
├── start_uvicorn.sh        # Server startup script
│
├── services/               # Business logic layer (14 services)
│   ├── background_tasks.py      # Async background task management
│   ├── health_service.py        # Database health checks and auto-repair
│   ├── image_service.py         # Image CRUD and bulk operations
│   ├── implication_service.py   # Tag implication detection and management
│   ├── monitor_service.py       # Background file monitoring
│   ├── priority_service.py      # Source priority change detection
│   ├── processing_service.py    # Metadata fetching and image processing
│   ├── query_service.py         # Search and similarity calculations
│   ├── rating_service.py        # AI rating inference
│   ├── saucenao_service.py      # SauceNao reverse image search
│   ├── switch_source_db.py      # Metadata source switching
│   ├── system_service.py        # System operations (scan, thumbnails, etc)
│   └── tag_service.py           # Tag operations and autocomplete
│
├── routers/                # Web and API routing
│   ├── web.py                   # Main web UI routes
│   └── api/                     # RESTful API endpoints
│       ├── images.py            # Image API
│       ├── implications.py      # Implication management API
│       ├── pools.py             # Pool management API
│       ├── rating.py            # Rating inference API
│       ├── saucenao.py          # SauceNao search API
│       ├── system.py            # System management API
│       └── tags.py              # Tag management API
│
├── repositories/           # Data access layer
│   ├── data_access.py           # Core database operations
│   ├── delta_tracker.py         # Tag modification tracking
│   ├── pool_repository.py       # Pool data operations
│   ├── rating_repository.py     # Rating model database
│   └── tag_repository.py        # Tag data operations
│
├── database/               # Database layer
│   ├── core.py                  # SQLite connection and utilities
│   └── models.py                # ORM models and schema
│
├── core/                   # Core infrastructure
│   └── cache_manager.py         # Intelligent cache management
│
├── events/                 # Event handling
│   └── cache_events.py          # Cache invalidation events
│
├── utils/                  # Utility functions
│   ├── deduplication.py         # Duplicate detection (MD5-based)
│   └── file_utils.py            # File handling utilities
│
├── static/                 # Static web assets
│   ├── css/                     # Stylesheets
│   ├── js/                      # JavaScript files
│   ├── images/                  # YOUR IMAGE COLLECTION GOES HERE
│   ├── thumbnails/              # Auto-generated thumbnails
│   └── favicon.svg
│
├── templates/              # Jinja2 HTML templates
│   ├── index.html               # Main gallery view
│   ├── image.html               # Image detail page
│   ├── implications.html        # Implication management
│   ├── pools.html               # Pool management
│   ├── tags.html                # Tag browser
│   ├── upload.html              # Upload interface
│   └── ...
│
├── models/                 # AI model files
│   └── Tagger/                  # Place ONNX models here
│       ├── model.onnx
│       └── metadata.json
│
├── scripts/                # Utility scripts
│   ├── backfill_rating_sources.py
│   └── enable_wal.py
│
├── tests/                  # Test suite
│   ├── test_async_scan.py
│   ├── test_concurrency.py
│   ├── test_database.py
│   ├── test_models.py
│   ├── test_monitor_batching.py
│   └── test_query_service.py
│
├── ingest/                 # Drop images here for auto-processing
├── booru.db                # Main SQLite database (auto-created)
├── rating_model.db         # Rating model database (auto-created)
│
├── requirements.txt        # Core dependencies
├── requirements-ai.txt     # AI tagging dependencies
├── requirements-dev.txt    # Development dependencies
├── .env.example            # Example configuration
└── .env                    # Your configuration (create from .env.example)
```

---

## Development

### Running Tests

The project includes a comprehensive test suite using pytest:

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run specific test file
pytest tests/test_query_service.py

# Run with coverage
pytest --cov=services --cov=repositories

# Run with verbose output
pytest -v
```

### Architecture Overview

ChibiBooru follows a **layered architecture**:

1. **Presentation Layer** (`routers/`)
   - Web UI routes and API endpoints
   - Request validation and response formatting

2. **Business Logic Layer** (`services/`)
   - Core application logic
   - Orchestrates data operations
   - Implements business rules

3. **Data Access Layer** (`repositories/`)
   - Database operations
   - Query building
   - Data transformation

4. **Infrastructure** (`core/`, `events/`)
   - Cross-cutting concerns (caching, events)
   - Shared utilities

**Key Design Principles:**
- **Separation of Concerns:** Clear boundaries between layers
- **Async-First:** Built on Quart (async Flask) for better concurrency
- **Event-Driven:** Cache invalidation and updates via event system
- **Modular Services:** Each service handles a specific domain
- **Repository Pattern:** Centralized data access

### Technology Stack

- **Web Framework:** Quart (async Flask-compatible)
- **ASGI Server:** Uvicorn
- **Database:** SQLite with FTS5 (full-text search)
- **AI/ML:** ONNX Runtime for local tagging
- **Testing:** pytest with async support
- **Templating:** Jinja2

### Code Organization

**Service Layer Pattern:**
Each service module (`services/*.py`) handles a specific domain:
- Encapsulates business logic
- Uses repositories for data access
- Raises domain exceptions
- Returns domain objects

**Repository Pattern:**
Each repository (`repositories/*.py`) handles data persistence:
- Executes SQL queries
- Maps results to dicts/objects
- No business logic

**Event System:**
Cache invalidation via events (`events/cache_events.py`):
- Services emit events on data changes
- Cache manager subscribes and invalidates

### Contributing Guidelines

1. **Code Style:**
   - Follow PEP 8
   - Use type hints where applicable
   - Write docstrings for public functions

2. **Testing:**
   - Write tests for new features
   - Maintain test coverage
   - Test async operations properly

3. **Commits:**
   - Use clear, descriptive commit messages
   - Reference issues where applicable

4. **Pull Requests:**
   - Ensure tests pass
   - Update documentation as needed
   - Keep PRs focused and scoped

---

## Advanced Topics

### Similarity Calculation Methods

Configure via `SIMILARITY_METHOD` in `.env`:

- **`jaccard`:** Simple set intersection/union. Fast and straightforward.
- **`weighted`** (default): Advanced IDF + category weighting:
  - Prioritizes rare tags over common ones
  - Weights character/copyright tags higher
  - Provides more nuanced similarity matching

**Adjust category weights** in `config.py`:

```python
SIMILARITY_CATEGORY_WEIGHTS = {
    'character': 6.0,   # Very significant
    'copyright': 3.0,   # Important
    'artist': 2.0,      # Matters
    'species': 2.5,     # Species tags
    'general': 1.0,     # Standard tags
    'meta': 0.5         # Less relevant
}
```

### Source Priority Configuration

Control which metadata source is used first in `config.py`:

```python
BOORU_PRIORITY = [
    "danbooru",     # Best categorization
    "e621",         # Good specific tags
    "gelbooru",     # Tags only
    "yandere",      # Tags only
    "pixiv",        # Pixiv metadata
    "local_tagger"  # AI fallback
]
```

**Important:** When changing `BOORU_PRIORITY`, increment `BOORU_PRIORITY_VERSION` to trigger automatic re-tagging.

### Custom AI Tagger Models

Use any ONNX-based tagging model:

1. Place `model.onnx` and `metadata.json` in `models/Tagger/`
2. Update `LOCAL_TAGGER_NAME` in `.env`
3. Adjust `LOCAL_TAGGER_THRESHOLD` in `config.py` if needed

Compatible models include WD14, Z3D-E621, and similar ONNX taggers.

### Database Optimization

**Automatic optimizations:**
- FTS5 index maintained automatically
- WAL mode for better concurrency
- Auto-vacuum enabled
- Startup health checks

**Manual optimization:**
Use the Debug panel to:
- **Full Reindex:** Rebuilds all indexes and optimizes database
- **FTS Rebuild:** Reconstructs full-text search index
- **Clean Orphans:** Removes orphaned database entries

**Performance tips:**
- Enable WAL mode: `python scripts/enable_wal.py`
- Run periodic reindexing for large collections
- Monitor disk space (thumbnails can grow large)
- Use SSD storage for better performance

### Backup and Recovery

**What to backup:**
- `booru.db` - Main database (contains all metadata and tags)
- `rating_model.db` - Rating inference data
- `static/images/` - Your image collection
- `.env` - Your configuration (keep secure!)

**Backup command:**
```bash
# Stop the application first
sqlite3 booru.db ".backup booru_backup.db"
sqlite3 rating_model.db ".backup rating_backup.db"
```

**Recovery:**
Simply restore the database files and restart the application.

### Troubleshooting

**Database locked errors:**
- Stop all instances of the application
- Check for abandoned connections
- Enable WAL mode: `python scripts/enable_wal.py`

**Missing thumbnails:**
- Use Debug panel → "Generate Missing Thumbnails"

**Metadata not loading:**
- Check API key configuration
- Verify internet connectivity
- Check rate limits (SauceNao: 6 searches per 30 seconds)

**Import errors:**
- Ensure virtual environment is activated
- Reinstall dependencies: `pip install -r requirements.txt --upgrade`

---

## License

[Add your license information here]

## Acknowledgments

- Built with [Quart](https://quart.palletsprojects.com/) - async Python web framework
- Metadata from Danbooru, e621, Gelbooru, Yandere, and Pixiv
- Reverse image search powered by [SauceNao](https://saucenao.com/)
- AI tagging powered by ONNX Runtime

---

**Made with ❤️ for organizing your image collections**

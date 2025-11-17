# ChibiBooru

ChibiBooru is a self-hosted web application for organizing and browsing your local image collection, designed to automatically fetch tags and metadata from various online sources, similar to popular image boorus. It combines a user-friendly interface with powerful backend tools to create a rich and searchable media library.

## Features

### Core Functionality
  * **Elegant Image Gallery:** A responsive, masonry-style layout for browsing your images with infinite scroll.
  * **Automated Tagging:** Automatically fetches detailed, categorized tags for your images from multiple sources:
      * **Direct Hash Search:** Finds metadata from **Danbooru** and **e621** using the image's MD5 hash.
      * **Reverse Image Search:** Uses **SauceNao** to find sources and metadata when direct hash matching fails.
      * **AI Tagging:** Includes a local, ONNX-based AI tagger as a fallback to analyze and tag images that have no online matches.
  * **Comprehensive Metadata:** Gathers rich metadata, including artist, character, copyright, species, and general tags, as well as image dimensions, file size, and original sources.

### Search & Discovery
  * **Advanced Search System:**
      * **Tag Search:** Search by tags with intelligent autocomplete suggestions
      * **Category-Specific Search:** Filter by tag category (e.g., `character:holo`, `copyright:spice_and_wolf`, `artist:name`)
      * **Full-Text Search:** Partial matching and fuzzy search for finding images even when you don't know exact tag names
      * **Negative Search:** Exclude tags with the `-` prefix (e.g., `-sketch` to exclude sketches)
      * **File Filters:** Search by filename (`filename:cute_cat`) or extension (`.png`, `.gif`)
      * **Source Filtering:** Find images from specific sources (`source:danbooru`)
      * **Relationship Filters:** Find parent/child images (`has:parent`, `has:child`, `has:relationship`)
      * **Pool Search:** Find images in specific collections (`pool:series_name`)
  * **Smart Similarity:** Weighted similarity matching that prioritizes rare tags and important categories (characters, copyright) over common descriptive tags

### Tag Management
  * **Full Tag Control:**
      * Intuitive in-line tag editor to add, remove, and recategorize tags
      * Ability to switch between different metadata sources (e.g., switch from Danbooru's tags to e621's for the same image)
      * Tag delta tracking preserves manual modifications across database rebuilds
  * **Tag Implications:** Automatic tag relationship detection and management:
      * **Smart Detection:** Automatically suggests implications based on naming patterns (e.g., `character_(series)` → `series`)
      * **Statistical Analysis:** Detects correlations between tags based on co-occurrence patterns
      * **Manual Control:** Create, approve, or delete implications with a dedicated management interface
      * **Chain Preview:** See the full impact of implications before applying them

### Organization
  * **Pools:** Group related images into named collections with custom ordering
  * **Image Relationships:** Automatically detects and displays parent/child relationships between images
  * **Tag Browser:** Browse all tags by category with usage counts and quick search access

### System Management
  * **Authentication:** Password-protected web interface with session-based login
  * **Image Upload:** Drag-and-drop interface for adding new images with automatic processing
  * **System Management Panel:** Web UI with powerful tools to manage your library:
      * Scan for and process new images
      * Generate thumbnails
      * Find and remove duplicate files
      * Clean the database of orphaned entries
      * Rebuild tag data from source metadata
      * Apply tag implications in bulk
  * **Background Monitoring:** Optional service that automatically watches your image directory for new files and processes them in the background

-----

## Getting Started

### Prerequisites

  * Python 3.8+
  * Git

### Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd Booru
    ```

2.  **Install dependencies:**
    It is highly recommended to use a virtual environment.

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Configuration:**
    Copy the example environment file and customize it:

    ```bash
    cp .env.example .env
    ```

    Then edit `.env` with your settings. Key values to configure:

    ```env
    # REQUIRED: Security settings - change these!
    APP_PASSWORD="your-secure-password"
    SECRET_KEY="your-secret-key-for-sessions"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    RELOAD_SECRET="a-very-secret-string"

    # OPTIONAL: API keys for enhanced metadata fetching
    SAUCENAO_API_KEY="your_saucenao_api_key"  # Recommended for reverse image search
    GELBOORU_API_KEY=""
    GELBOORU_USER_ID=""

    # OPTIONAL: Customization
    APP_NAME="ChibiBooru"
    LOCAL_TAGGER_NAME="CamieTagger"
    SIMILARITY_METHOD="weighted"  # Options: 'jaccard' or 'weighted'
    ```

    **Important Security Notes:**
    - **REQUIRED:** Change `APP_PASSWORD`, `SECRET_KEY`, and `RELOAD_SECRET` before first use
    - Generate a secure `SECRET_KEY` using: `python -c "import secrets; print(secrets.token_hex(32))"`
    - Never commit your `.env` file to version control (it's already in `.gitignore`)
    - See `.env.example` for full configuration options and documentation

4.  **Place your images:**
    Move your image collection into the `static/images/` directory. You can create subdirectories to organize them.

5.  **Run the application:**

    The application uses Quart (async Flask) with Uvicorn as the ASGI server:

    ```bash
    python app.py
    ```

    Or use the provided shell script:

    ```bash
    ./start_uvicorn.sh
    ```

    The application will be available at `http://127.0.0.1:5000` by default.

-----

## Usage

### Initial Setup

1.  After running the application for the first time, open the web interface.
2.  Log in with the `APP_PASSWORD` you set in your `.env` file.
3.  Navigate to the **System** panel in the header.
4.  Enter the `RELOAD_SECRET` you set in your `.env` file.
5.  Click **"Scan & Process New Images"** to begin indexing your collection. The application will start fetching metadata for all your images. This may take a while for large collections.
6.  Once the initial scan is complete, you can optionally start the **Monitor** to have ChibiBooru automatically process new images you add to the `static/images` folder.

### Searching

  * **Basic Tag Search:** Just type tags separated by spaces in the search bar (e.g., `1girl blue_hair`).
  * **Category Search:** Search within specific tag categories:
      * `character:holo` - Find images with this character
      * `copyright:spice_and_wolf` - Find images from this series
      * `artist:artist_name` - Find images by this artist
      * `species:wolf` - Find images with this species tag
  * **Advanced Queries:**
      * `source:<name>` - Find images from a specific source (e.g., `source:danbooru`)
      * `filename:<text>` - Search for text within the image's filename
      * `.<ext>` - Filter by file extension (e.g., `.png`, `.gif`)
      * `has:parent` - Find images that have a parent
      * `has:child` - Find images that have children
      * `has:relationship` - Find images with any parent/child relationship
      * `pool:<name>` - Find images in a specific pool
      * `-<tag>` - Exclude a tag (e.g., `-sketch -monochrome`)
  * **Combine Multiple Filters:** Mix and match any of the above for powerful queries like:
      * `character:holo source:danbooru .png -sketch`

### Editing Tags

1.  Navigate to an image's detail page.
2.  Click the **"Edit Tags"** button.
3.  An inline editor will appear, allowing you to add or remove tags within their specific categories.
4.  Click **"Save Tags"** when you are done.
5.  Your manual modifications will be preserved even if you rebuild the database.

### Managing Tag Implications

1.  Navigate to the **Implications** page from the header menu.
2.  Review auto-detected suggestions based on:
     * **Naming Patterns:** e.g., `character_(costume)_(series)` → `character_(series)`
     * **Statistical Correlation:** Tags that commonly appear together
3.  Approve suggestions to automatically apply them to all relevant images.
4.  Create manual implications for custom tag relationships.
5.  View and manage all active implications in a single interface.

### Creating Pools

1.  Navigate to the **Pools** page from the header menu.
2.  Click **"Create New Pool"** to create an image collection.
3.  Give your pool a name and optional description.
4.  Add images to pools from the image detail page or pool management interface.
5.  Search for pools using `pool:<name>` in the main search bar.

### Uploading Images

1.  Click the **Upload** button in the header.
2.  Drag and drop images or click to select files.
3.  Images will be automatically processed and added to your collection.

-----

## Project Structure

```
Booru/
├── static/
│   ├── css/            # Stylesheets
│   ├── js/             # JavaScript files
│   ├── images/         # Your image collection goes here
│   ├── thumbnails/     # Auto-generated thumbnails
│   └── favicon.svg     # Application icon
├── templates/          # Flask HTML templates
├── services/           # Service layer for business logic
│   ├── api_service.py           # API integration services
│   ├── implication_service.py   # Tag implication detection
│   ├── monitor_service.py       # Background file monitoring
│   ├── query_service.py         # Search and similarity calculations
│   ├── switch_source_db.py      # Source switching utilities
│   └── system_service.py        # System management operations
├── repositories/       # Data access layer
│   ├── data_access.py       # Core data access functions
│   ├── delta_tracker.py     # Tag modification tracking
│   ├── pool_repository.py   # Pool data operations
│   └── tag_repository.py    # Tag data operations
├── core/               # Core infrastructure
│   └── cache_manager.py     # Cache management system
├── events/             # Event handling
│   └── cache_events.py      # Cache invalidation events
├── utils/              # Utility functions
│   ├── deduplication.py     # Duplicate detection
│   └── file_utils.py        # File handling utilities
├── models/             # AI tagging models (place ONNX models here)
├── app.py              # Main application entry point
├── config.py           # Centralized configuration
├── database.py         # Database schema and initialization
├── models.py           # Database models and data access layer
├── processing.py       # Core image processing and metadata fetching
├── routes.py           # Quart routes and web endpoints
├── rating_inference.py     # AI rating model inference
├── rating_model_db.py      # Rating model database operations
├── backfill_rating_sources.py  # Utility to backfill rating sources
├── priority_monitor.py     # Monitor and respond to priority changes
├── database_health.py      # Database health check utilities
├── start_uvicorn.sh        # Script to start Uvicorn server
├── requirements.txt        # Python dependencies
├── .env                # Your configuration (create from .env.example)
├── .env.example        # Example configuration file
├── booru.db            # SQLite database (created automatically)
└── rating_model.db     # Rating model database (created automatically)
```

## Advanced Configuration

### Similarity Calculation Methods

ChibiBooru supports two similarity calculation methods, configurable via the `SIMILARITY_METHOD` environment variable:

- **`jaccard`**: Simple set intersection/union calculation. Fast and straightforward.
- **`weighted`** (default): Advanced method using Inverse Document Frequency (IDF) and category weights. This method:
  - Prioritizes rare tags over common ones
  - Weights character and copyright tags higher than general descriptive tags
  - Provides more nuanced similarity matching for better recommendations

### Category Weights

When using weighted similarity, you can adjust category importance in `config.py`:

```python
SIMILARITY_CATEGORY_WEIGHTS = {
    'character': 5.0,   # Character matches are very significant
    'copyright': 3.0,   # Same series/franchise is important
    'artist': 2.0,      # Same artist style matters
    'species': 2.5,     # Species tags
    'general': 1.0,     # Standard descriptive tags
    'meta': 0.5         # Resolution, format, year - less relevant
}
```

### Custom AI Tagger Models

ChibiBooru supports any ONNX-based tagging model with compatible metadata:

1. Place your `model.onnx` and `metadata.json` files in `models/Tagger/`
2. Update `LOCAL_TAGGER_NAME` in `.env` to reflect your model
3. Adjust `LOCAL_TAGGER_THRESHOLD` in `config.py` if needed

## Database Management

The application uses SQLite with several advanced features:

- **FTS5 Full-Text Search:** Fast partial matching and fuzzy search
- **Automatic Indexing:** Optimized queries for large collections
- **Tag Delta Tracking:** Preserves manual tag edits across rebuilds
- **Tag Implications:** Recursive tag relationships with chain support

To rebuild the FTS index if needed:
```bash
python database.py
```


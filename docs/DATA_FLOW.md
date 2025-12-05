# Data Flow Documentation

## Table of Contents
- [Overview](#overview)
- [New Image Processing Flow](#new-image-processing-flow)
- [Search Query Flow](#search-query-flow)
- [Tag Update Flow](#tag-update-flow)
- [Source Switching Flow](#source-switching-flow)
- [Rating Inference Flow](#rating-inference-flow)
- [Tag Implication Flow](#tag-implication-flow)
- [Database Rebuild Flow](#database-rebuild-flow)
- [Monitor Service Flow](#monitor-service-flow)

---

## Overview

This document describes end-to-end data flows through ChibiBooru, showing how data moves between components.

### Flow Diagram Legend
```
User/File → Router → Service → Repository → Database
              ↓         ↓          ↓
           Cache   External API   Filesystem
```

---

## New Image Processing Flow

### Scenario: User uploads a new image

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Upload                                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Web Router (routers/web.py)                             │
│    POST /upload                                             │
│    • Receive multipart/form-data                           │
│    • Save to temp location                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Processing Service (services/processing_service.py)     │
│    process_image_file()                                     │
│    • Calculate MD5 hash                                     │
│    • Check for duplicates                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Deduplication (utils/deduplication.py)                  │
│    • Query database for MD5                                 │
│    • If duplicate: return False                             │
│    • If unique: continue                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. File Operations (utils/file_utils.py)                   │
│    • Generate bucketed path (ab/cd/filename.jpg)            │
│    • Move file to static/images/                            │
│    • Create directory structure                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Metadata Fetching (Parallel)                            │
│    ┌─────────────────┐  ┌─────────────────┐               │
│    │ Try MD5 Lookup  │  │ Try SauceNao    │               │
│    │ • Danbooru      │  │ • API request   │               │
│    │ • e621          │  │ • Parse results │               │
│    │ • Gelbooru      │  │ • Extract ID    │               │
│    │ • Yandere       │  └─────────────────┘               │
│    └─────────────────┘                                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    Found? ─── No ───┐
                      │              │
                     Yes             ↓
                      │      ┌─────────────────────────┐
                      │      │ 7. Local AI Tagger      │
                      │      │ • Load ONNX model       │
                      │      │ • Preprocess image      │
                      │      │ • Run inference         │
                      │      │ • Extract tags          │
                      │      └─────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Tag Extraction & Normalization                          │
│    extract_tag_data()                                       │
│    • Parse source-specific format                           │
│    • Categorize tags                                        │
│    • Normalize tag names                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Database Storage (repositories/data_access.py)          │
│    add_image_with_metadata()                                │
│    • BEGIN TRANSACTION                                      │
│    • INSERT INTO images (filepath, md5, ...)                │
│    • INSERT INTO raw_metadata (JSON)                        │
│    • INSERT INTO tags (create if new)                       │
│    • INSERT INTO image_tags (relationships)                 │
│    • INSERT INTO image_sources                              │
│    • UPDATE denormalized tag columns                        │
│    • COMMIT                                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 10. Tag Implications (services/implication_service.py)     │
│     apply_implications_for_image()                          │
│     • Find active implications for image tags               │
│     • Add implied tags                                      │
│     • Handle implication chains                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 11. Rating Inference (services/rating_service.py)          │
│     infer_rating()                                          │
│     • Load tag weights from database                        │
│     • Calculate scores for each rating                      │
│     • Apply thresholds                                      │
│     • Add rating tag to image (if confident)                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 12. Thumbnail Generation (services/processing_service.py)  │
│     generate_thumbnail()                                    │
│     • Load image with Pillow                                │
│     • Resize to max dimension                               │
│     • Convert to WebP                                       │
│     • Save to static/thumbnails/                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 13. Cache Update (core/cache_manager.py)                   │
│     reload_single_image()                                   │
│     • Update image_data cache                               │
│     • Update tag_counts cache                               │
│     • Trigger cache invalidation event                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 14. Response to User                                        │
│     • Return success JSON                                   │
│     • Include image ID and path                             │
│     • Client updates UI                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Search Query Flow

### Scenario: User searches for "1girl blue_hair source:danbooru"

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Input                                               │
│    Query: "1girl blue_hair source:danbooru"                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Web Router (routers/web.py)                             │
│    GET /?query=1girl+blue_hair+source:danbooru              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Query Service (services/query_service.py)               │
│    perform_search()                                         │
│    • Parse query string                                     │
│    • Extract components:                                    │
│      - General terms: ["1girl", "blue_hair"]                │
│      - Source filter: ["danbooru"]                          │
│      - Negative terms: []                                   │
│      - Other filters: {}                                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Decide Search Strategy                                   │
│    _should_use_fts()                                        │
│    • Check if all terms are exact tags                      │
│    • "1girl" → exact tag (in database)                      │
│    • "blue_hair" → exact tag (in database)                  │
│    • Decision: Use tag-based search (faster)                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Execute Optimized Query                                  │
│    _tag_based_search()                                      │
│    SQL:                                                     │
│    SELECT DISTINCT i.filepath, tags_all                     │
│    FROM images i                                            │
│    JOIN image_tags it1 ON i.id = it1.image_id              │
│    JOIN tags t1 ON it1.tag_id = t1.id AND t1.name='1girl'  │
│    JOIN image_tags it2 ON i.id = it2.image_id              │
│    JOIN tags t2 ON it2.tag_id = t2.id AND t2.name='blue_hair' │
│    JOIN image_sources isr ON i.id = isr.image_id           │
│    JOIN sources s ON isr.source_id = s.id AND s.name='danbooru' │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Return Results                                           │
│    • Results: 150 images                                    │
│    • Order: Random (no specific order requested)            │
│    • Should shuffle: True                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Web Router Response                                      │
│    • Shuffle results with random seed                       │
│    • Take first 50 for initial page                         │
│    • Render template with images                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Client Rendering                                         │
│    • Display 50 images                                      │
│    • Setup infinite scroll                                  │
│    • Load more via AJAX as user scrolls                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Tag Update Flow

### Scenario: User edits tags for an image

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Action                                              │
│    • Click "Edit Tags"                                      │
│    • Modify tags in editor                                  │
│    • Click "Save"                                           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. AJAX Request                                             │
│    POST /api/tags/edit                                      │
│    {                                                        │
│      "filepath": "folder/image.jpg",                        │
│      "categorized_tags": {                                  │
│        "character": ["hatsune_miku"],                       │
│        "general": ["1girl", "blue_hair", "twintails"]       │
│      }                                                      │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Tag Service (services/tag_service.py)                   │
│    edit_tags_service()                                      │
│    • Validate request data                                  │
│    • Call repository with record_deltas=True                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Tag Repository (repositories/tag_repository.py)         │
│    update_image_tags_categorized()                          │
│    • Get current tags from database                         │
│    • Compute differences (deltas)                           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Delta Tracker (repositories/delta_tracker.py)           │
│    compute_tag_deltas()                                     │
│    Old tags: {                                              │
│      "character": ["hatsune_miku"],                         │
│      "general": ["1girl", "blue_hair"]                      │
│    }                                                        │
│    New tags: {                                              │
│      "character": ["hatsune_miku"],                         │
│      "general": ["1girl", "blue_hair", "twintails"]         │
│    }                                                        │
│    Deltas: [                                                │
│      {"tag": "twintails", "operation": "add"}               │
│    ]                                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Record Deltas                                            │
│    record_tag_delta()                                       │
│    INSERT INTO tag_deltas                                   │
│    (image_md5, tag_name, tag_category, operation)           │
│    VALUES                                                   │
│    ('abc123...', 'twintails', 'general', 'add')             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Update Database                                          │
│    • DELETE FROM image_tags WHERE image_id = ?              │
│    • INSERT INTO tags (if new)                              │
│    • INSERT INTO image_tags (new relationships)             │
│    • UPDATE images SET tags_general = '...'                 │
│    • FTS index automatically updated (triggers)             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Cache Update                                             │
│    • reload_single_image(filepath)                          │
│    • reload_tag_counts()                                    │
│    • get_image_details.cache_clear()                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Response to Client                                       │
│    {"status": "success"}                                    │
│    • Client updates UI                                      │
│    • Shows new tags                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Source Switching Flow

### Scenario: User switches from Danbooru to e621 metadata

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User selects "e621" from source dropdown                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. AJAX Request                                             │
│    POST /switch-source                                      │
│    {"filepath": "...", "source": "e621"}                    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Switch Source Service (services/switch_source_db.py)    │
│    switch_metadata_source_db()                              │
│    • Load raw_metadata JSON                                 │
│    • Check if e621 metadata exists                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Extract Tags from Source                                 │
│    • Parse e621-specific format                             │
│    • Categorize tags:                                       │
│      - character, copyright, artist                         │
│      - species (e621 specific)                              │
│      - general, meta                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Update Database                                          │
│    • UPDATE images SET active_source = 'e621'               │
│    • DELETE FROM image_tags WHERE image_id = ?              │
│    • INSERT INTO image_tags (new tags)                      │
│    • UPDATE denormalized columns                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Cache Update & Response                                  │
│    • Reload image cache                                     │
│    • Clear LRU caches                                       │
│    • Return new tag data to client                          │
│    • Client updates tag display                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Rating Inference Flow

### Scenario: System infers rating for an image

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Trigger Event                                            │
│    • New image processed                                    │
│    • User requests rating inference                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Rating Service (services/rating_service.py)             │
│    infer_rating()                                           │
│    Input: ["1girl", "blue_hair", "twintails", "dress"]      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Load Weights (repositories/rating_repository.py)        │
│    • Query tag weights:                                     │
│      "1girl" + "general" = 0.8                              │
│      "blue_hair" + "general" = 0.6                          │
│    • Query pair weights:                                    │
│      ("1girl", "dress") + "general" = 1.2                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Calculate Scores                                         │
│    For each rating (general, sensitive, questionable, explicit): │
│    • Sum individual tag weights                             │
│    • Sum tag pair weights (context)                         │
│    • Multiply pair weights by pair_weight_multiplier (1.5)  │
│    • Normalize scores                                       │
│                                                             │
│    Results:                                                 │
│    {                                                        │
│      "general": 0.92,                                       │
│      "sensitive": 0.05,                                     │
│      "questionable": 0.02,                                  │
│      "explicit": 0.01                                       │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Apply Thresholds                                         │
│    • general: 0.92 > 0.5 ✓                                  │
│    • Decision: rating:general                               │
│    • Confidence: 0.92                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Add Rating Tag                                           │
│    • INSERT INTO tags (name='rating:general', category='meta') │
│    • INSERT INTO image_tags (source='ai_inference')         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Return Result                                            │
│    {                                                        │
│      "rating": "rating:general",                            │
│      "confidence": 0.92,                                    │
│      "scores": {...}                                        │
│    }                                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Tag Implication Flow

### Scenario: User approves "hatsune_miku" → "vocaloid" implication

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User clicks "Approve" on pending implication            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Implication Service                                      │
│    approve_implication(source_tag_id=1, implied_tag_id=2)   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Update Status                                            │
│    UPDATE tag_implications                                  │
│    SET status = 'active'                                    │
│    WHERE source_tag_id = 1 AND implied_tag_id = 2           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Find Affected Images                                     │
│    SELECT image_id FROM image_tags it                       │
│    JOIN tags t ON it.tag_id = t.id                          │
│    WHERE t.name = 'hatsune_miku'                            │
│    • Found: 500 images                                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Apply to Each Image                                      │
│    For each of 500 images:                                  │
│    • Check if "vocaloid" already present                    │
│    • If not:                                                │
│      - INSERT INTO image_tags (tag_id=2, source='original') │
│      - Update denormalized columns                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Cache Invalidation                                       │
│    • trigger_cache_invalidation()                           │
│    • Reload tag counts                                      │
│    • "vocaloid" count: 300 → 800                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Response to User                                         │
│    {                                                        │
│      "status": "success",                                   │
│      "images_affected": 500                                 │
│    }                                                        │
│    • UI updates                                             │
│    • Implication moves to "Active" tab                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Rebuild Flow

### Scenario: User clicks "Rebuild Database" after changing BOORU_PRIORITY

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User Action                                              │
│    • Changed BOORU_PRIORITY_VERSION from 4 to 5             │
│    • Changed priority order                                 │
│    • Clicks "Rebuild Database"                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. System Service                                           │
│    rebuild_service()                                        │
│    • Stop monitor (prevent conflicts)                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Database Models (database/models.py)                     │
│    repopulate_from_database()                               │
│    • Clear existing relationships:                          │
│      - DELETE FROM image_tags                               │
│      - DELETE FROM image_sources                            │
│      - DELETE FROM tags                                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. For Each Image (with progress bar)                       │
│    • Load raw_metadata JSON                                 │
│    • Available sources: {danbooru, e621, local_tagger}      │
│    • Apply new BOORU_PRIORITY:                              │
│      [danbooru, e621, gelbooru, ...]                        │
│    • Select primary source: danbooru                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Extract and Insert Tags                                  │
│    • Parse danbooru format                                  │
│    • Create tag entries                                     │
│    • Create image_tags relationships                        │
│    • Update active_source column                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Recategorize Tags                                        │
│    recategorize_misplaced_tags()                            │
│    • Fix tag categories                                     │
│    • Normalize rating tags                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Rebuild Denormalized Columns                             │
│    rebuild_categorized_tags_from_relations()                │
│    • UPDATE images SET tags_general = ...                   │
│    • FTS index automatically updated                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Apply Tag Deltas                                         │
│    apply_tag_deltas()                                       │
│    • Restore user's manual edits                            │
│    • For each delta:                                        │
│      - If "add": INSERT tag                                 │
│      - If "remove": DELETE tag                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Reload Cache                                             │
│    load_data_from_db()                                      │
│    • Reload tag_counts                                      │
│    • Reload image_data                                      │
│    • Rebuild post_id_to_md5 mapping                         │
│    • Trigger cache invalidation event                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 10. Complete                                                │
│     • Return success response                               │
│     • User sees updated gallery                             │
│     • Tags now follow new priority                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Monitor Service Flow

### Scenario: Background monitor detects new file in ingest folder

```
┌─────────────────────────────────────────────────────────────┐
│ 1. File Event                                               │
│    • User drops image.jpg into ingest/                      │
│    • Filesystem event triggered                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Watchdog Handler (services/monitor_service.py)          │
│    ImageFileHandler.on_created()                            │
│    • Check file extension (.jpg)                            │
│    • Debounce check (prevent duplicates)                    │
│    • Wait 0.5s for file to be fully written                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Acquire Processing Lock                                  │
│    with processing_lock:                                    │
│    • Prevent concurrent processing                          │
│    • Determine if from ingest folder: YES                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Process Image                                            │
│    processing.process_image_file(                           │
│        filepath="ingest/image.jpg",                         │
│        move_from_ingest=True                                │
│    )                                                        │
│    • Same flow as "New Image Processing"                    │
│    • File moved to static/images/ab/cd/image.jpg            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Update Monitor Status                                    │
│    • Increment total_processed counter                      │
│    • Set pending_reload flag                                │
│    • Update last_activity timestamp                         │
│    • Add log entry: "Successfully processed from ingest"    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Batch Reload (Deferred)                                  │
│    • Don't reload immediately (prevents UI hang)            │
│    • Wait for batch threshold or timeout                    │
│    • Eventually triggers cache reload                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Client Polling                                           │
│    • UI polls /api/system/monitor/status                    │
│    • Sees new images processed                              │
│    • Reloads gallery to show new images                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [SERVICES.md](SERVICES.md) - Service implementations
- [REPOSITORIES.md](REPOSITORIES.md) - Data access patterns
- [DATABASE.md](DATABASE.md) - Database schema

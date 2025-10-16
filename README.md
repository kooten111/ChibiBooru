# HomeBooru

Self-hosted image gallery with automatic tag fetching from multiple booru sources (Danbooru, e621, Gelbooru, Yandere) and AI tagging fallback. Features infinite scroll, tag editing, similarity search, and real-time statistics.

## Features

- **Automatic Tag Fetching**: MD5-based search across 4 booru APIs in parallel
- **AI Tagging Fallback**: CamieTagger ONNX model for images not found on boorus
- **Reverse Image Search**: SauceNao integration for finding booru sources
- **Categorized Tags**: Character, Copyright, Artist, Meta, General
- **Smart Search**: Multi-tag search with autocomplete
- **Infinite Scroll**: Smooth pagination with prefetching
- **Related Images**: Weighted similarity by character/copyright/artist/general tags
- **Tag Editing**: In-browser tag editor with autocomplete
- **Statistics Dashboard**: Expandable tabs showing collection stats, top tags, sources, categories
- **Image Relationships**: Parent/child linking
- **Live Monitoring**: Background daemon processes new images automatically
- **Hot Reload**: Update without restarting Flask

## Directory Structure

```
.
├── app.py                          # Flask application
├── fetch_metadata.py               # Fetch tags from boorus + AI tagging
├── rebuild_tags_from_metadata.py   # Regenerate tags.json from metadata
├── generate_thumbnails.py          # Batch thumbnail generation
├── tag_watcher_daemon.py           # Background monitoring daemon
├── README.md
├── tags.json                       # Generated: Tag index
├── static/
│   ├── css/
│   │   ├── main.css
│   │   ├── image.css
│   │   ├── actions.css
│   │   ├── stats-tabs.css
│   │   └── carousel.css
│   ├── js/
│   │   ├── autocomplete.js
│   │   ├── tag-editor.js
│   │   ├── infinite-scroll.js
│   │   ├── stats-tabs.js
│   │   ├── carousel.js
│   │   └── image-preloader.js
│   ├── images/                     # Your images
│   └── thumbnails/                 # Generated WebP thumbnails
├── metadata/                       # Generated: Full booru metadata by MD5
├── models/
│   └── CamieTagger/                # Optional: AI tagging model
│       ├── camie-tagger-v2.onnx
│       └── metadata.json
├── templates/
│   ├── index.html
│   └── image.html
└── utils/
    ├── __init__.py
    ├── file_utils.py
    └── metadata_utils.py
```

## Installation

### Requirements

- Python 3.7+
- 4GB+ RAM (8GB recommended with CamieTagger)

### Setup

1. **Install dependencies**

```bash
# Basic requirements
pip install flask pillow requests tqdm

# Optional: AI tagging (GPU recommended)
pip install onnxruntime-gpu numpy  # or onnxruntime for CPU

# Optional: Advanced file processing
pip install openpyxl pandas
```

2. **Create directories**

```bash
mkdir -p static/images static/thumbnails metadata models/CamieTagger
```

3. **Add your images**

```bash
cp -r ~/my-images/* static/images/
```

4. **Configure environment variables**

```bash
# Optional: SauceNao reverse image search
export SAUCENAO_API_KEY="your-api-key-here"

# API reload secret (generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
export RELOAD_SECRET="your-secure-random-string"

# Flask app URL for daemon
export FLASK_URL="http://localhost:5000"
```

5. **Optional: Download CamieTagger model**

Download from [CamieTagger releases](https://huggingface.co/KBlueLeaf/CamieTagger/tree/main) and place in `models/CamieTagger/`:
- `camie-tagger-v2.onnx`
- `metadata.json`

6. **Process images**

```bash
# Generate thumbnails first (optional, fetch_metadata.py does this too)
python3 generate_thumbnails.py

# Fetch tags from boorus and AI tag
python3 fetch_metadata.py
```

7. **Run the web interface**

```bash
python3 app.py
```

Visit http://localhost:5000

## Configuration

### fetch_metadata.py

```python
IMAGE_DIRECTORY = "./static/images"
METADATA_DIR = "./metadata"
TAGS_FILE = "./tags.json"
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000

# CamieTagger
CAMIE_MODEL_PATH = "./models/CamieTagger/camie-tagger-v2.onnx"
CAMIE_METADATA_PATH = "./models/CamieTagger/metadata.json"
CAMIE_THRESHOLD = 0.5
CAMIE_TARGET_SIZE = 512
```

### tag_watcher_daemon.py

```python
CHECK_INTERVAL = 300  # Check for new images every 5 minutes
```

### app.py

```python
RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')
```

## Tag Fetching Process

1. **MD5 Search**: Calculates MD5 hash and searches all boorus in parallel
2. **SauceNao Fallback**: If no MD5 match, uses reverse image search (requires API key)
3. **CamieTagger Fallback**: If still no match, uses AI tagging (requires model)
4. **Metadata Storage**: Saves complete metadata from all sources to `metadata/{md5}.json`
5. **Tag Merging**: Combines tags from all sources, prefers Danbooru/e621 for categories

### Source Priority

1. **Danbooru** - Full categorization, best quality
2. **e621** - Full categorization, good for furry content
3. **Gelbooru** - Tags only, no categories
4. **Yandere** - Tags only, no categories
5. **CamieTagger** - AI predictions with confidence scoring

## Running the Daemon

### Manual (Foreground)

```bash
python3 tag_watcher_daemon.py
# Ctrl+C to stop
```

### Background

```bash
nohup python3 tag_watcher_daemon.py > /dev/null 2>&1 &

# Check status
ps aux | grep tag_watcher

# Stop
pkill -f tag_watcher_daemon.py
```

### Systemd Service

1. **Edit service file**

```bash
nano tag-watcher.service
# Update paths and username
```

2. **Install**

```bash
sudo cp tag-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tag-watcher
sudo systemctl start tag-watcher
```

3. **Manage**

```bash
sudo systemctl status tag-watcher
sudo systemctl restart tag-watcher
sudo journalctl -u tag-watcher -f
```

## Manual Operations

### Process New Images

```bash
python3 fetch_metadata.py
```

Processes images that don't have metadata yet or were marked "not_found".

### Regenerate tags.json

```bash
python3 rebuild_tags_from_metadata.py
```

Rebuilds the search index from existing metadata files.

### Generate Thumbnails

```bash
python3 generate_thumbnails.py
```

### Reload Flask

```bash
curl -X POST http://localhost:5000/api/reload -d "secret=YOUR_SECRET"
```

## API Endpoints

### GET `/`
Gallery with search, infinite scroll, stats dashboard

**Parameters:**
- `query`: Space-separated tags or special queries
- `page`: Page number (default: 1)
- `per_page`: Results per page (25, 50, 100, 200)

**Special Queries:**
- `metadata:missing` - Images without metadata
- `metadata:found` - Images with metadata
- `filename:term` - Search by filename
- `source:danbooru` - Filter by source

### GET `/image/<path:filepath>`
Image detail view with tags, metadata, related images carousel

### GET `/similar/<path:filepath>`
Find images similar to the given one (Jaccard similarity)

### GET `/api/images`
JSON endpoint for infinite scroll

**Parameters:**
- `query`: Search query
- `page`: Page number
- `per_page`: Results per page
- `seed`: Random seed for consistent shuffling

**Returns:**
```json
{
  "images": [...],
  "page": 1,
  "total_pages": 10,
  "total_results": 500,
  "has_more": true
}
```

### POST `/api/reload`
Reload tags.json without restarting Flask

**Parameters:**
- `secret`: Reload secret

### POST `/api/edit_tags`
Update tags for an image

**Body:**
```json
{
  "filepath": "images/path/to/image.jpg",
  "tags": "tag1 tag2 tag3"
}
```

### POST `/api/delete_image`
Delete image, thumbnail, and metadata

**Body:**
```json
{
  "filepath": "images/path/to/image.jpg"
}
```

### GET `/api/autocomplete?q=<query>`
Tag suggestions for autocomplete

**Returns:**
```json
[
  {"tag": "tag_name", "count": 123},
  ...
]
```

## Search Syntax

- **Single tag**: `solo`
- **Multiple tags (AND)**: `1girl blue_eyes long_hair`
- **Filename search**: `filename:abc123` or just type the filename
- **Source filter**: `source:danbooru`
- **Missing metadata**: `metadata:missing`
- **Found metadata**: `metadata:found`

## Features Detail

### Statistics Dashboard

Click tabs to view:
- **Overview**: Total images, metadata coverage, unique tags, AI usage
- **Sources**: Breakdown by Danbooru/e621/Gelbooru/Yandere
- **Top Tags**: 20 most used tags with counts
- **Categories**: Character/Copyright/Artist/Meta/General tag counts
- **Explore**: 30 random tags to browse

### Infinite Scroll

- Automatically loads more images as you scroll
- Prefetches next 2 pages for instant display
- Seeded random shuffle for consistent order
- Works with all search queries

### Related Images

Image detail page shows:
- **Carousel**: Similar images weighted by character > copyright > artist > general tags
- **Parent/Child**: Booru-defined relationships
- **Match Types**: Color-coded badges (Character/Copyright/Artist/Similar)

### Tag Editing

- Click "Edit Tags" on image page
- Chip-based interface
- Autocomplete with counts
- Add: Type and press Enter/Space
- Remove: Click X or Backspace on empty input
- Saves to tags.json and triggers reload

## Metadata Structure

### tags.json

```json
{
  "path/to/image.jpg": {
    "tags": "tag1 tag2 tag3",
    "tags_character": "character_name",
    "tags_copyright": "series_name",
    "tags_artist": "artist_name",
    "tags_meta": "meta_tag",
    "tags_general": "general_tags",
    "id": 12345,
    "parent_id": null,
    "has_children": false,
    "md5": "abc123...",
    "sources": ["danbooru", "e621"],
    "saucenao_lookup": false,
    "camie_tagger_lookup": false
  }
}
```

### metadata/{md5}.json

```json
{
  "md5": "abc123...",
  "relative_path": "path/to/image.jpg",
  "saucenao_lookup": false,
  "saucenao_response": null,
  "camie_tagger_lookup": false,
  "sources": {
    "danbooru": {
      "id": 12345,
      "tag_string": "...",
      "tag_string_character": "...",
      "rating": "s",
      "score": 100,
      ...
    }
  }
}
```

## Known Issues

### tag_watcher_daemon.py Import Bug

The daemon currently imports `tag_finder_simple` which is empty. Fix:

```python
# Change line 93 from:
import tag_finder_simple
tag_finder_simple.main()

# To:
import fetch_metadata
fetch_metadata.main()
```

## Troubleshooting

### No tags found

- Verify images are from booru sources (original uploads won't match)
- Check MD5 hasn't changed (re-encoding changes hash)
- Try SauceNao with API key
- Use CamieTagger as fallback

### CamieTagger not working

```bash
pip install onnxruntime-gpu numpy  # or onnxruntime for CPU
```

Download model files to `models/CamieTagger/`

### Flask not showing new images

```bash
# Trigger reload
curl -X POST http://localhost:5000/api/reload -d "secret=YOUR_SECRET"

# Or restart Flask
```

### Daemon lock file error

```bash
rm tag_watcher.lock
python3 tag_watcher_daemon.py
```

### Memory issues

- Reduce `THUMB_SIZE` (default: 1000)
- Lower WebP quality in `generate_thumbnails.py`
- Use smaller `per_page` values
- Disable CamieTagger if not needed

### Performance issues

- Use SSD for `static/images` and `metadata/`
- Generate thumbnails in batch before processing
- Increase `CHECK_INTERVAL` for daemon
- Consider Redis for tag caching with 100k+ images

## Production Deployment

### With Gunicorn

```bash
pip install gunicorn

gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### With Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /static/ {
        alias /path/to/your/booru/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### Security

1. **Change reload secret**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Restrict /api/reload**
   ```nginx
   location /api/reload {
       allow 127.0.0.1;
       deny all;
       proxy_pass http://localhost:5000;
   }
   ```

3. **Add authentication** if hosting publicly

4. **Review content** before hosting (boorus contain NSFW)

## Performance Tips

- Use SSD for image storage
- Generate thumbnails during off-peak hours
- Prefetch is aggressive (2 pages ahead) - adjust if needed
- Use CDN for static assets in production
- Consider database (PostgreSQL) instead of tags.json for 100k+ images
- Enable gzip compression in nginx

## Credits

- Booru APIs: Danbooru, e621, Gelbooru, Yandere
- AI Model: CamieTagger by KBlueLeaf
- Reverse Search: SauceNao
- Built with Flask, Pillow, ONNX Runtime

## License

Personal use. Respect booru API rate limits and terms of service.

# HomeBooru

Self-hosted image gallery with automatic tag fetching from multiple booru sources (Danbooru, e621, Gelbooru, Yandere) and AI tagging fallback. Features built-in monitoring, infinite scroll, tag editing, similarity search, and real-time statistics.

## Features

- **Built-in Monitoring**: Automatic background scanning for new images every 5 minutes
- **System Control Panel**: Web-based controls for scan, rebuild, thumbnails, and monitor
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
- **Hot Reload**: Update without restarting Flask

## Directory Structure

```
.
├── app.py                          # Flask application with built-in monitoring
├── fetch_metadata.py               # Fetch tags from boorus + AI tagging
├── rebuild_tags_from_metadata.py   # Regenerate tags.json from metadata
├── generate_thumbnails.py          # Batch thumbnail generation
├── README.md
├── tags.json                       # Generated: Tag index
├── static/
│   ├── css/
│   │   ├── main.css
│   │   ├── image.css
│   │   ├── actions.css
│   │   ├── stats-tabs.css
│   │   ├── carousel.css
│   │   └── system-panel.css        # System control panel styles
│   ├── js/
│   │   ├── autocomplete.js
│   │   ├── tag-editor.js
│   │   ├── infinite-scroll.js
│   │   ├── stats-tabs.js
│   │   ├── carousel.js
│   │   ├── image-preloader.js
│   │   └── system-panel.js         # System control panel logic
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

The built-in monitor will automatically start and check for new images every 5 minutes.

## Configuration

### app.py

```python
# Monitoring
MONITOR_ENABLED = True
MONITOR_INTERVAL = 300  # seconds (5 minutes)

# Security
RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')
```

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

## Built-in Monitoring

The Flask app includes automatic background monitoring that:

1. **Runs continuously** in a daemon thread
2. **Checks every 5 minutes** for new images (configurable)
3. **Compares against tags.json** to find unprocessed images
4. **Automatically processes** new images using fetch_metadata.py
5. **Reloads data** after processing completes
6. **Tracks statistics** (total processed, last scan results)

### Monitor Behavior

- Starts automatically when Flask starts
- Runs in background without blocking web requests
- Sleeps between checks to minimize resource usage
- Can be stopped/started via System Control Panel
- Survives Flask debug reloads (daemon thread)

### Disable Monitoring

To run without automatic monitoring:

```python
# In app.py
MONITOR_ENABLED = False
```

Or use the System Control Panel to stop it at runtime.

## System Control Panel

Access via the **System** tab on the home page (requires RELOAD_SECRET).

### Status Display (Auto-refreshes every 5 seconds)

- **Monitor Status**: Running (green) or Stopped (red)
- **Check Interval**: Time between automatic scans
- **Last Check**: Timestamp of last scan
- **Last Scan Found**: Number of images found in last scan
- **Total Processed**: Total images processed by monitor
- **Total Images**: Total images in collection
- **With Metadata**: Images with tag data
- **Unprocessed**: Images awaiting processing (orange if > 0)

### Action Buttons

**Scan & Process New Images**
- Manually trigger immediate scan
- Runs fetch_metadata.py on all unprocessed images
- Automatically reloads data

**Rebuild Tags from Metadata**
- Regenerates tags.json from metadata/*.json files
- Use if metadata files were modified externally

**Generate Thumbnails**
- Runs generate_thumbnails.py
- Creates WebP thumbnails for all images

**Reload Data**
- Reloads tags.json into memory
- Use after manual edits

**Start/Stop Monitor**
- Control background monitoring thread
- Useful for manual processing workflows

### First Time Setup

When opening System tab for the first time:
1. You'll be prompted for the system secret
2. Enter your `RELOAD_SECRET` value
3. Secret is saved to localStorage
4. To reset: `localStorage.removeItem('system_secret')` in browser console

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

## Manual Operations

### Process New Images

```bash
python3 fetch_metadata.py
```

Processes images that don't have metadata yet or were marked "not_found". The built-in monitor does this automatically, but you can run it manually for immediate processing.

### Regenerate tags.json

```bash
python3 rebuild_tags_from_metadata.py
```

Rebuilds the search index from existing metadata files. Also available via System Control Panel.

### Generate Thumbnails

```bash
python3 generate_thumbnails.py
```

Creates WebP thumbnails for all images. Also available via System Control Panel.

### Reload Flask

Via System Control Panel:
- Click **Reload Data** button

Via API:
```bash
curl -X POST http://localhost:5000/api/reload -d "secret=YOUR_SECRET"
```

Via Python (for scripts):
```python
import requests
requests.post('http://localhost:5000/api/reload', data={'secret': 'YOUR_SECRET'})
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

### GET `/api/system/status`
Get monitoring and collection status (no auth required)

**Returns:**
```json
{
  "monitor": {
    "enabled": true,
    "running": true,
    "last_check": "2025-01-15 14:30:00",
    "last_scan_found": 5,
    "total_processed": 123,
    "interval_seconds": 300
  },
  "collection": {
    "total_images": 1000,
    "with_metadata": 950,
    "unprocessed": 50
  }
}
```

### POST `/api/system/scan`
Manually trigger scan and processing (requires secret)

### POST `/api/system/rebuild`
Rebuild tags.json from metadata (requires secret)

### POST `/api/system/thumbnails`
Generate thumbnails (requires secret)

### POST `/api/system/monitor/start`
Start monitoring thread (requires secret)

### POST `/api/system/monitor/stop`
Stop monitoring thread (requires secret)

### POST `/api/reload`
Reload tags.json without restarting Flask (requires secret)

### POST `/api/edit_tags`
Update tags for an image

### POST `/api/delete_image`
Delete image, thumbnail, and metadata

### GET `/api/autocomplete?q=<query>`
Tag suggestions for autocomplete

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
- **System**: Monitoring status and manual controls

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

### Monitor not running

- Check System Control Panel status
- Click **Start Monitor** button
- Verify `MONITOR_ENABLED = True` in app.py
- Check Flask console for errors

### Monitor not finding new images

- Images must be in `static/images/` directory
- Check that images have valid extensions (.jpg, .jpeg, .png, .gif, .webp)
- Verify images aren't already in tags.json
- Check Flask console logs during scan

### System Control Panel shows "Unauthorized"

- Ensure you entered the correct RELOAD_SECRET
- Reset: `localStorage.removeItem('system_secret')` in browser console
- Verify RELOAD_SECRET in environment or app.py

### Flask not showing new images after processing

- Monitor automatically reloads data after processing
- Manual: Click **Reload Data** in System Control Panel
- Or restart Flask

### Memory issues

- Reduce `THUMB_SIZE` (default: 1000)
- Lower WebP quality in `generate_thumbnails.py`
- Use smaller `per_page` values
- Disable CamieTagger if not needed
- Reduce `MONITOR_INTERVAL` to process smaller batches

### Performance issues

- Use SSD for `static/images` and `metadata/`
- Generate thumbnails in batch before processing
- Increase `MONITOR_INTERVAL` for less frequent checks
- Consider Redis for tag caching with 100k+ images

## Production Deployment

### With Gunicorn

```bash
pip install gunicorn

gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

The monitoring thread works with Gunicorn, but runs only in the master process.

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

2. **Restrict system endpoints**
   ```nginx
   location /api/system/ {
       allow 192.168.1.0/24;  # Your internal network
       deny all;
       proxy_pass http://localhost:5000;
   }
   ```

3. **Add authentication** if hosting publicly

4. **Review content** before hosting (boorus contain NSFW)

### Systemd Service

Create `/etc/systemd/system/homebooru.service`:

```ini
[Unit]
Description=HomeBooru Image Gallery
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/homebooru
Environment="RELOAD_SECRET=your-secret-here"
Environment="SAUCENAO_API_KEY=your-key-here"
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable homebooru
sudo systemctl start homebooru
sudo systemctl status homebooru
```

View logs:
```bash
sudo journalctl -u homebooru -f
```

## Performance Tips

- Use SSD for image storage
- Generate thumbnails during off-peak hours
- Monitor interval can be adjusted based on how frequently you add images
- Use CDN for static assets in production
- Consider database (PostgreSQL) instead of tags.json for 100k+ images
- Enable gzip compression in nginx
- The built-in monitor is lightweight and won't impact normal operations

## Migration from tag_watcher_daemon.py

If you were using the old separate daemon:

1. **Stop the old daemon**
   ```bash
   pkill -f tag_watcher_daemon.py
   # or
   sudo systemctl stop tag-watcher
   sudo systemctl disable tag-watcher
   ```

2. **Remove systemd service** (if installed)
   ```bash
   sudo rm /etc/systemd/system/tag-watcher.service
   sudo systemctl daemon-reload
   ```

3. **Update app.py** to the new version with built-in monitoring

4. **Restart Flask** - monitoring starts automatically

The new system is more efficient because:
- No separate process to manage
- Shares memory with Flask app
- Can be controlled via web interface
- Automatic data reload after processing
- Real-time status display

## Credits

- Booru APIs: Danbooru, e621, Gelbooru, Yandere
- AI Model: CamieTagger by KBlueLeaf
- Reverse Search: SauceNao
- Built with Flask, Pillow, ONNX Runtime

## License

Personal use. Respect booru API rate limits and terms of service.

# My Booru

A self-hosted image gallery with automatic tag fetching from multiple booru sources (Danbooru, e621, Gelbooru, Yandere). Features a clean dark-themed interface with tag-based search, autocomplete, and automatic metadata management.

## Features

- **Automatic Tag Fetching**: Searches multiple booru APIs by MD5 hash
- **Categorized Tags**: Character, Copyright, Artist, Meta, and General tags
- **Smart Search**: Multi-tag search with autocomplete
- **Image Relationships**: Parent/child image linking
- **Thumbnails**: Automatic WebP thumbnail generation
- **Metadata Storage**: Complete metadata from all sources saved locally
- **Live Monitoring**: Daemon automatically processes new images
- **Hot Reload**: Web interface updates without restart

## Directory Structure

```
.
├── app.py                          # Flask web application
├── tag_finder_simple.py            # Fetch tags from booru APIs
├── rebuild_tags_from_metadata.py   # Regenerate tags.json from metadata
├── generate_thumbnails.py          # Generate all thumbnails at once
├── tag_watcher_daemon.py           # Background daemon for monitoring
├── README.md                       # This file
├── tags.json                       # Generated: Tag index for fast search
├── static/
│   ├── images/                     # Your image collection
│   └── thumbnails/                 # Generated WebP thumbnails
├── metadata/                       # Generated: Full booru metadata by MD5
└── templates/
    ├── index.html                  # Gallery view
    └── image.html                  # Image detail view
```

## Installation

### Requirements

- Python 3.7+
- pip

### Setup

1. **Clone or download this project**

2. **Install dependencies**
```bash
pip install flask pillow requests tqdm
```

3. **Create directories**
```bash
mkdir -p static/images static/thumbnails metadata
```

4. **Add your images**
```bash
# Place images in static/images/
# Subdirectories are supported
cp -r ~/my-images/* static/images/
```

5. **Initial processing**
```bash
# Fetch tags and generate thumbnails
python3 tag_finder_simple.py

# Or generate thumbnails separately first
python3 generate_thumbnails.py
python3 tag_finder_simple.py
```

6. **Run the web interface**
```bash
python3 app.py
```

Visit http://localhost:5000

## Configuration

### Environment Variables

```bash
# Reload secret for API endpoint (generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
export RELOAD_SECRET="your-secure-random-string"

# Flask app URL for daemon to trigger reloads
export FLASK_URL="http://localhost:5000"
```

### Script Settings

**tag_finder_simple.py:**
```python
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000
IMAGE_DIRECTORY = "./static/images"
TAGS_FILE = "./tags.json"
METADATA_DIR = "./metadata"
```

**tag_watcher_daemon.py:**
```python
CHECK_INTERVAL = 300  # Check for new images every 5 minutes
```

## Running the Daemon

### Manual (Foreground)

```bash
# Run with Ctrl+C to stop
python3 tag_watcher_daemon.py
```

### Background

```bash
# Run in background
nohup python3 tag_watcher_daemon.py > /dev/null 2>&1 &

# Check if running
ps aux | grep tag_watcher

# Stop
pkill -f tag_watcher_daemon.py
```

### Systemd Service (Production)

1. **Edit service file**
```bash
nano tag-watcher.service
# Update paths and username
```

2. **Install service**
```bash
sudo cp tag-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tag-watcher
sudo systemctl start tag-watcher
```

3. **Manage service**
```bash
sudo systemctl status tag-watcher    # Check status
sudo systemctl restart tag-watcher   # Restart
sudo systemctl stop tag-watcher      # Stop
sudo journalctl -u tag-watcher -f    # View logs
```

## Manual Operations

### Process New Images Only
```bash
python3 tag_finder_simple.py
```

### Regenerate tags.json from Existing Metadata
```bash
python3 rebuild_tags_from_metadata.py
```

### Generate All Thumbnails
```bash
python3 generate_thumbnails.py
```

### Reload Flask Without Restart
```bash
curl -X POST http://localhost:5000/api/reload \
  -d "secret=your-secure-random-string"
```

## Data Flow

### Initial Setup
```
1. Add images to static/images/
2. Run tag_finder_simple.py
   ├─> Calculates MD5 for each image
   ├─> Searches Danbooru, e621, Gelbooru, Yandere
   ├─> Saves full metadata to metadata/{md5}.json
   ├─> Generates WebP thumbnails
   └─> Builds tags.json index
3. Run app.py
   └─> Loads tags.json into memory
```

### Adding New Images
```
1. Copy images to static/images/
2. Daemon detects new images (or run tag_finder_simple.py manually)
3. Fetches metadata for new images only
4. Rebuilds tags.json from all metadata
5. Triggers Flask reload via /api/reload
6. New images appear immediately
```

### Changing Code Logic
```
1. Modify rebuild_tags_from_metadata.py
2. Run: python3 rebuild_tags_from_metadata.py
3. Reload Flask (automatic if daemon is running)
```

## API Endpoints

### `GET /`
Gallery view with search and pagination

**Parameters:**
- `query`: Space-separated tags (e.g., `character_name blue_eyes`)
- `page`: Page number (default: 1)
- `per_page`: Results per page (25, 50, 100, 200)

### `GET /image/<path:filepath>`
Individual image view with tags and metadata

### `GET /api/autocomplete?q=<query>`
Tag autocomplete suggestions

**Returns:** JSON array of `{tag, count}` objects

### `POST /api/reload`
Reload tags.json without restarting Flask

**Parameters:**
- `secret`: Reload secret from environment

**Returns:** `{status, images, tags}` or `{error}`

## Search Syntax

- **Single tag**: `solo`
- **Multiple tags (AND)**: `1girl blue_eyes long_hair`
- **Autocomplete**: Start typing, press Tab or click suggestion
- **Arrow keys**: Navigate suggestions
- **Enter**: Insert selected tag

## Metadata Sources

Images are searched across multiple boorus by MD5:

| Source | Tags | Categorization | Parent/Child |
|--------|------|----------------|--------------|
| Danbooru | ✅ | ✅ Full | ✅ |
| e621 | ✅ | ✅ Full | ✅ |
| Gelbooru | ✅ | ❌ | ✅ |
| Yandere | ✅ | ❌ | ✅ |

The system:
- Searches all sources in parallel
- Prefers Danbooru/e621 for categorized tags
- Merges tags from all found sources
- Saves complete metadata from every source

## Troubleshooting

### No tags found for images
- Check if images are from booru sources
- Verify MD5 hasn't changed (re-encoding changes hash)
- Check API rate limits in logs

### Flask not showing new images
```bash
# Manually trigger reload
curl -X POST http://localhost:5000/api/reload -d "secret=YOUR_SECRET"

# Or restart Flask
sudo systemctl restart your-flask-service
```

### Daemon lock file error
```bash
# Remove stale lock file
rm tag_watcher.lock

# Restart daemon
python3 tag_watcher_daemon.py
```

### Thumbnails not loading
```bash
# Regenerate all thumbnails
python3 generate_thumbnails.py
```

### Memory issues with large collections
- Reduce `THUMB_SIZE` in scripts
- Lower WebP quality setting
- Use pagination with smaller `per_page` values
- Consider splitting into multiple instances

## Production Deployment

### With Gunicorn

```bash
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### With Nginx Reverse Proxy

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
    }
}
```

### Security Considerations

1. **Change default reload secret**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Restrict access to /api/reload**
   - Use strong secret
   - Consider IP whitelist in nginx

3. **Content warnings**
   - Review booru content before hosting
   - Implement authentication if needed
   - Add content rating filters

## Performance Tips

- Use SSD for `static/images` and `metadata/`
- Increase `CHECK_INTERVAL` for large collections
- Generate thumbnails during off-peak hours
- Use CDN for static assets in production
- Consider database instead of tags.json for 100k+ images

## License

This project is provided as-is for personal use.

Metadata is fetched from public booru APIs. Respect their terms of service and rate limits.

## Credits

- Booru APIs: Danbooru, e621, Gelbooru, Yandere
- Built with Flask, Pillow, and requests
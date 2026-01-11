"""
Metadata fetching from various sources (Danbooru, E621, SauceNAO, Pixiv, etc.).
"""

import os
import re
import requests
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import config
from .rate_limiter import saucenao_rate_limiter
from .constants import (
    DANBOORU_TIMEOUT,
    E621_TIMEOUT,
    GELBOORU_TIMEOUT,
    YANDERE_TIMEOUT,
    PIXIV_TIMEOUT,
    SAUCENAO_TIMEOUT,
    PIXIV_DOWNLOAD_TIMEOUT,
    SAUCENAO_MAX_SIZE_BYTES,
    SAUCENAO_MIN_QUALITY,
    SAUCENAO_QUALITY_STEP,
    SAUCENAO_INITIAL_QUALITY,
    SAUCENAO_SIMILARITY_THRESHOLD,
    SAUCENAO_NUM_RESULTS,
    SAUCENAO_STATS_REPORT_INTERVAL,
)

# Load from config
SAUCENAO_API_KEY = config.SAUCENAO_API_KEY
GELBOORU_API_KEY = config.GELBOORU_API_KEY
GELBOORU_USER_ID = config.GELBOORU_USER_ID


def search_danbooru(md5):
    try:
        url = f"https://danbooru.donmai.us/posts.json?tags=md5:{md5}"
        response = requests.get(url, timeout=DANBOORU_TIMEOUT)
        if response.status_code == 200 and response.json():
            return {"source": "danbooru", "data": response.json()[0]}
    except requests.RequestException:
        return None
    return None


def search_e621(md5):
    try:
        headers = {"User-Agent": "ChibiBooru/1.0"}
        url = f"https://e621.net/posts.json?tags=md5:{md5}"
        response = requests.get(url, headers=headers, timeout=E621_TIMEOUT)
        if response.status_code == 200 and response.json()["posts"]:
            return {"source": "e621", "data": response.json()["posts"][0]}
    except requests.RequestException:
        return None
    return None


def search_all_sources(md5):
    search_functions = [search_danbooru, search_e621]
    results = {}
    with ThreadPoolExecutor(max_workers=len(search_functions)) as executor:
        future_to_func = {executor.submit(func, md5): func for func in search_functions}
        for future in as_completed(future_to_func):
            try:
                result = future.result()
                if result:
                    results[result['source']] = result['data']
            except Exception as e:
                print(f"Booru search error: {e}")
    return results


def search_saucenao(filepath):
    if not SAUCENAO_API_KEY:
        return None
    try:
        # Check file size - SauceNAO has a ~15MB limit
        file_size = os.path.getsize(filepath)
        max_size = SAUCENAO_MAX_SIZE_BYTES

        # For GIFs and very large files, extract a frame or resize
        temp_file = None
        file_to_upload = filepath

        if filepath.lower().endswith('.gif') or file_size > max_size:
            try:
                # Open image and extract first frame or resize
                img = Image.open(filepath)

                # For GIFs, get first frame
                if filepath.lower().endswith('.gif'):
                    img.seek(0)  # Go to first frame
                    # Convert to RGB if needed
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                # Resize if still too large
                # SauceNAO accepts up to 15MB, but we'll target ~5MB for safety
                # Reduce quality/size until it fits
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                quality = SAUCENAO_INITIAL_QUALITY
                while True:
                    temp_file.seek(0)
                    temp_file.truncate()
                    img.save(temp_file.name, 'JPEG', quality=quality)
                    temp_size = os.path.getsize(temp_file.name)
                    if temp_size < max_size or quality <= SAUCENAO_MIN_QUALITY:
                        break
                    quality -= SAUCENAO_QUALITY_STEP

                file_to_upload = temp_file.name
                print(f"[SauceNAO] Converted {os.path.basename(filepath)} ({file_size/1024/1024:.1f}MB) to JPEG ({temp_size/1024/1024:.1f}MB)")

            except Exception as e:
                print(f"[SauceNAO] Failed to convert {filepath}: {e}")
                # If file is too large and we can't convert, skip it
                if file_size > max_size:
                    print(f"[SauceNAO] File too large ({file_size/1024/1024:.1f}MB), skipping")
                    return None

        # Wait for rate limiter before making request
        saucenao_rate_limiter.wait_if_needed()

        with open(file_to_upload, 'rb') as f:
            files = {'file': f}
            params = {'api_key': SAUCENAO_API_KEY, 'output_type': 2, 'numres': SAUCENAO_NUM_RESULTS}
            response = requests.post('https://saucenao.com/search.php', files=files, params=params, timeout=SAUCENAO_TIMEOUT)
            response.raise_for_status()

            response_json = response.json()
            
            # Try to extract explicit limits from the response header
            # SauceNAO returns a 'header' object with 'short_limit', 'long_limit', etc.
            actual_limit = None
            if 'header' in response_json:
                try:
                    # short_limit is usually a string, e.g. "17"
                    short_limit_val = response_json['header'].get('short_limit')
                    if short_limit_val:
                        actual_limit = int(short_limit_val)
                except (ValueError, TypeError):
                    pass

            # Record successful request with the explicit limit if found
            saucenao_rate_limiter.record_success(actual_limit)

            # Print current stats (only every N requests to reduce spam)
            stats = saucenao_rate_limiter.get_stats()
            if stats['requests_in_window'] % SAUCENAO_STATS_REPORT_INTERVAL == 0 or stats['current_limit'] is not None:
                limit_str = f"{stats['current_limit']}" if stats['current_limit'] else "unlimited"
                print(f"[SauceNAO Adaptive] OK ({stats['requests_in_window']} in window, limit: {limit_str})")

            return response_json
    except requests.exceptions.HTTPError as e:
        # Check if it's a 429 (Too Many Requests) error
        if e.response.status_code == 429:
            print(f"Saucenao search error: {e}")
            # Record the rate limit hit - this will adjust our limits
            saucenao_rate_limiter.record_rate_limit_hit()
        elif e.response.status_code == 413:
            # Payload too large - shouldn't happen with our pre-check, but handle it anyway
            print(f"Saucenao search error: File too large for SauceNAO (413)")
        else:
            print(f"Saucenao search error: {e}")
        return None
    except Exception as e:
        print(f"Saucenao search error: {e}")
        return None
    finally:
        # Clean up temp file if created
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except (OSError, IOError) as e:
                pass  # Temp file cleanup failure is not critical


def fetch_by_post_id(source, post_id):
    try:
        if "http" in str(post_id):
            post_id = os.path.basename(post_id).split('?')[0]

        if source == "danbooru":
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            response = requests.get(url, timeout=DANBOORU_TIMEOUT)
            response.raise_for_status()
            return {"source": "danbooru", "data": response.json()}
        
        elif source == "e621":
            headers = {"User-Agent": "ChibiBooru/1.0"}
            url = f"https://e621.net/posts/{post_id}.json"
            response = requests.get(url, headers=headers, timeout=E621_TIMEOUT)
            response.raise_for_status()
            return {"source": "e621", "data": response.json()["post"]}
            
        elif source == "gelbooru":
            if not GELBOORU_API_KEY or not GELBOORU_USER_ID:
                print("Warning: GELBOORU_API_KEY or GELBOORU_USER_ID not set. Gelbooru search may fail.")
            
            url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&id={post_id}&api_key={GELBOORU_API_KEY}&user_id={GELBOORU_USER_ID}"
            response = requests.get(url, timeout=GELBOORU_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            if "post" in data and data["post"]:
                return {"source": "gelbooru", "data": data["post"][0]}
            elif isinstance(data, list) and data:
                 return {"source": "gelbooru", "data": data[0]}

        elif source == "yandere":
            url = f"https://yande.re/post.json?tags=id:{post_id}"
            response = requests.get(url, timeout=YANDERE_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if data:
                return {"source": "yandere", "data": data[0]}
                
    except Exception as e:
        print(f"Error fetching {source} post {post_id}: {e}")
    return None


def extract_pixiv_id_from_filename(filename):
    """
    Extract Pixiv illustration ID from filename.

    Supports various Pixiv naming patterns:
    - 131010854_p0.png (standard pattern)
    - 131010854.png (without page number)
    - pixiv_131010854.jpg (with prefix)
    - any filename containing _p[n]. pattern where n is a digit

    Args:
        filename: The filename to extract from

    Returns:
        Pixiv ID as string, or None if no valid ID found
    """
    # Pattern 1: [id]_p[page].[ext] (e.g., 131010854_p0.png)
    match = re.search(r'(\d{6,})_p\d+\.', filename)
    if match:
        return match.group(1)

    # Pattern 2: pixiv_[id].[ext] or similar prefix patterns
    match = re.search(r'pixiv[_-](\d{6,})\.', filename, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Just the ID with extension (e.g., 131010854.png)
    # Only if it's a reasonable Pixiv ID length (6-9 digits)
    basename = os.path.splitext(filename)[0]
    if basename.isdigit() and 6 <= len(basename) <= 9:
        return basename

    return None


def fetch_pixiv_metadata(pixiv_id):
    """
    Fetch metadata for a Pixiv illustration using unofficial API.

    Args:
        pixiv_id: Pixiv illustration ID

    Returns:
        Dict with source='pixiv' and data containing tags and metadata, or None if failed
    """
    try:
        # Use the unofficial Pixiv API endpoint (doesn't require authentication)
        # This endpoint is used by the Pixiv website itself
        url = f"https://www.pixiv.net/ajax/illust/{pixiv_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.pixiv.net/"
        }

        response = requests.get(url, headers=headers, timeout=PIXIV_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if data.get('error'):
            print(f"[Pixiv] API error for ID {pixiv_id}: {data.get('message', 'Unknown error')}")
            return None

        if not data.get('body'):
            print(f"[Pixiv] No data found for ID {pixiv_id}")
            return None

        body = data['body']

        # Extract tags - Pixiv provides tags as a list with translations
        tags_general = []
        if 'tags' in body and 'tags' in body['tags']:
            for tag_obj in body['tags']['tags']:
                # Prefer English translation if available, otherwise use original tag
                tag_name = tag_obj.get('translation', {}).get('en', tag_obj.get('tag', ''))
                if tag_name:
                    # Replace spaces with underscores to match booru format
                    tag_name = tag_name.replace(' ', '_').lower()
                    tags_general.append(tag_name)

        # Extract artist name
        artist_name = body.get('userName', '').replace(' ', '_').lower()
        artist_id = body.get('userId', '')

        # Get image URL (original)
        image_url = body.get('urls', {}).get('original')

        print(f"[Pixiv] Found illustration {pixiv_id}: {len(tags_general)} tags, artist: {artist_name}")

        return {
            "source": "pixiv",
            "data": {
                "tags": {
                    "general": tags_general,
                    "artist": [artist_name] if artist_name else [],
                    "character": [],
                    "copyright": [],
                    "meta": [],
                    "species": []
                },
                "pixiv_id": pixiv_id,
                "title": body.get('title', ''),
                "artist_name": artist_name,
                "artist_id": artist_id,
                "image_url": image_url,
                "width": body.get('width'),
                "height": body.get('height')
            }
        }

    except requests.exceptions.RequestException as e:
        print(f"[Pixiv] Network error fetching ID {pixiv_id}: {e}")
        return None
    except Exception as e:
        print(f"[Pixiv] Error fetching Pixiv ID {pixiv_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def download_pixiv_image(pixiv_id, image_url, output_dir="./ingest"):
    """
    Download the original image from Pixiv.

    Args:
        pixiv_id: Pixiv illustration ID
        image_url: URL to the original image
        output_dir: Directory to save the image (defaults to ingest folder for auto-processing)

    Returns:
        Path to downloaded file, or None if failed
    """
    try:
        if not image_url:
            print(f"[Pixiv] No image URL provided for ID {pixiv_id}")
            return None

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Extract filename from URL
        filename = os.path.basename(image_url.split('?')[0])
        output_path = os.path.join(output_dir, f"{pixiv_id}_{filename}")

        # Check if already downloaded
        if os.path.exists(output_path):
            print(f"[Pixiv] Image already exists: {output_path}")
            return output_path

        # Download with proper headers (Pixiv requires referer)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://www.pixiv.net/artworks/{pixiv_id}"
        }

        response = requests.get(image_url, headers=headers, timeout=PIXIV_DOWNLOAD_TIMEOUT)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

        print(f"[Pixiv] Downloaded original image: {output_path}")
        return output_path

    except Exception as e:
        print(f"[Pixiv] Error downloading image for ID {pixiv_id}: {e}")
        return None

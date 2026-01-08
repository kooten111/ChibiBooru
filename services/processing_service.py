# processing.py
import config
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, UnidentifiedImageError
import numpy as np
from database import models
from database import get_db_connection
from utils.deduplication import remove_duplicate
from utils.file_utils import get_file_md5
from utils.tag_extraction import (
    extract_tags_from_source,
    extract_rating_from_source,
    merge_tag_sources,
    deduplicate_categorized_tags
)
import time
from collections import deque
from threading import Lock
import fcntl
import shutil

# ML Worker client - always import (no fallback to local loading)
try:
    from ml_worker.client import get_ml_worker_client
    ML_WORKER_AVAILABLE = True
except ImportError:
    ML_WORKER_AVAILABLE = False
    print("ERROR: ML Worker client not available. ML operations will fail.")
    print("Ensure ml_worker module is installed and accessible.")

# Load from config
SAUCENAO_API_KEY = config.SAUCENAO_API_KEY
GELBOORU_API_KEY = config.GELBOORU_API_KEY
GELBOORU_USER_ID = config.GELBOORU_USER_ID
THUMB_DIR = config.THUMB_DIR
THUMB_SIZE = config.THUMB_SIZE

# Local tagger configuration
tagger_config = config.get_local_tagger_config()


class AdaptiveSauceNAORateLimiter:
    """
    Adaptive rate limiter for SauceNAO API requests.

    Automatically learns the rate limits by:
    - Starting with no limits (unlimited requests)
    - When hitting 429 error, backs off to conservative limit
    - Periodically tests if limits can be increased
    - Adjusts down immediately on 429, adjusts up gradually
    """

    def __init__(self):
        """Initialize the adaptive rate limiter."""
        # Current rate limit (None = unlimited)
        self.current_limit = None  # requests per 30 seconds
        self.window_duration = 30  # seconds

        # Track request timestamps in current window
        self.requests = deque()

        # Rate limit learning
        self.last_rate_limit_hit = None  # timestamp of last 429 error
        self.consecutive_successes = 0   # successful requests since last 429
        self.test_threshold = 50         # test limit increase every N successful requests

        # Backoff state
        self.in_backoff = False
        self.backoff_until = None

        # Thread safety
        self.lock = Lock()

    def _clean_old_requests(self):
        """Remove requests older than the window."""
        current_time = time.time()
        cutoff_time = current_time - self.window_duration

        while self.requests and self.requests[0] < cutoff_time:
            self.requests.popleft()

    def should_wait(self):
        """
        Check if we should wait before making a request.

        Returns:
            tuple: (should_wait: bool, wait_time: float)
        """
        with self.lock:
            current_time = time.time()

            # Check if we're in backoff period
            if self.in_backoff and self.backoff_until:
                if current_time < self.backoff_until:
                    return True, self.backoff_until - current_time
                else:
                    self.in_backoff = False
                    self.backoff_until = None

            # Clean old requests
            self._clean_old_requests()

            # If no limit set, don't wait
            if self.current_limit is None:
                return False, 0

            # Check if we're at the limit
            if len(self.requests) >= self.current_limit:
                oldest_request = self.requests[0]
                wait_time = (oldest_request + self.window_duration) - current_time
                return True, max(0, wait_time)

            return False, 0

    def wait_if_needed(self):
        """Block until a request can be made."""
        should_wait, wait_time = self.should_wait()

        if should_wait and wait_time > 0:
            with self.lock:
                limit_str = f"{self.current_limit}/{self.window_duration}s" if self.current_limit else "unlimited"
            print(f"[SauceNAO Adaptive] Waiting {wait_time:.1f}s (current limit: {limit_str})")
            time.sleep(wait_time)

    def record_success(self, actual_limit=None):
        """
        Record a successful request.
        
        Args:
            actual_limit (int, optional): The actual short_limit returned by the API.
        """
        with self.lock:
            current_time = time.time()
            self.requests.append(current_time)
            self.consecutive_successes += 1

            # specific update logic: if the API gave us an explicit limit, use it!
            if actual_limit is not None:
                # If we were guessing, or if the limit changed, update it
                if self.current_limit != actual_limit:
                    print(f"[SauceNAO Adaptive] Updating limit from API header: {self.current_limit} -> {actual_limit}")
                    self.current_limit = actual_limit
                    # We can trust this limit, so we don't need to be in "testing" mode
            
            # Fallback to adaptive probing ONLY if we don't have an explicit limit
            # (This shouldn't happen often if we're parsing headers correctly)
            elif (self.current_limit is not None and
                self.consecutive_successes >= self.test_threshold and
                self.last_rate_limit_hit and
                (current_time - self.last_rate_limit_hit) > 300):  # 5 minutes since last 429

                old_limit = self.current_limit
                self.current_limit += 1
                self.consecutive_successes = 0
                print(f"[SauceNAO Adaptive] Testing higher limit: {old_limit} -> {self.current_limit}")

    def record_rate_limit_hit(self):
        """Record that we hit a 429 rate limit error."""
        with self.lock:
            current_time = time.time()
            self.last_rate_limit_hit = current_time
            self.consecutive_successes = 0

            # Clean old requests to see how many we made in the window
            self._clean_old_requests()
            requests_in_window = len(self.requests)

            if self.current_limit is None:
                # First time hitting limit - set conservative limit
                new_limit = max(1, requests_in_window - 1)
                print(f"[SauceNAO Adaptive] Rate limit detected! Setting limit to {new_limit}/{self.window_duration}s")
                self.current_limit = new_limit
            else:
                # We hit the limit again - decrease
                old_limit = self.current_limit
                self.current_limit = max(1, self.current_limit - 1)
                print(f"[SauceNAO Adaptive] Rate limit hit again! Reducing: {old_limit} -> {self.current_limit}")

            # Enter backoff period
            self.in_backoff = True
            self.backoff_until = current_time + self.window_duration
            print(f"[SauceNAO Adaptive] Entering {self.window_duration}s cooldown period")

    def get_stats(self):
        """Get current rate limiter statistics."""
        with self.lock:
            self._clean_old_requests()

            return {
                "current_limit": self.current_limit,
                "requests_in_window": len(self.requests),
                "window_duration": self.window_duration,
                "consecutive_successes": self.consecutive_successes,
                "in_backoff": self.in_backoff,
                "last_limit_hit": self.last_rate_limit_hit
            }


# Global adaptive SauceNAO rate limiter instance
saucenao_rate_limiter = AdaptiveSauceNAORateLimiter()

# Lock directory for preventing concurrent processing of the same file across workers
LOCK_DIR = ".processing_locks"
os.makedirs(LOCK_DIR, exist_ok=True)

def acquire_processing_lock(md5):
    """
    Try to acquire a file-based lock for processing an image with the given MD5.
    Returns (lock_fd, acquired) where lock_fd is the file descriptor (or None) and acquired is a boolean.
    """
    lock_file = os.path.join(LOCK_DIR, f"{md5}.lock")
    try:
        fd = open(lock_file, 'w')
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return (fd, True)
    except (IOError, OSError):
        # Lock is held by another process
        if 'fd' in locals():
            fd.close()
        return (None, False)

def release_processing_lock(lock_fd):
    """Release a processing lock."""
    if lock_fd:
        try:
            lock_file = lock_fd.name
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
            os.remove(lock_file)
        except Exception as e:
            pass  # Lock cleanup failure is not critical


def tag_with_local_tagger(filepath):
    """
    Tag an image using the local tagger via ML Worker.

    Returns dict with:
      - source: 'local_tagger'
      - data: {tags, tagger_name, all_predictions}
        - tags: categorized tags above display threshold (for active_source use)
        - all_predictions: list of {tag_name, category, confidence} above storage threshold
    """
    if not ML_WORKER_AVAILABLE:
        print(f"[Local Tagger] ERROR: ML Worker not available. Cannot process {os.path.basename(filepath)}")
        return None
    
    print(f"[Local Tagger] Analyzing (via ML Worker): {os.path.basename(filepath)}")
    try:
        client = get_ml_worker_client()
        result = client.tag_image(
            image_path=filepath,
            model_path=tagger_config['model_path'],
            threshold=tagger_config.get('threshold', 0.50),
            character_threshold=0.85,
            metadata_path=tagger_config.get('metadata_path')
        )

        return {
            "source": "local_tagger",
            "data": {
                "tags": result['tags'],
                "tagger_name": result['tagger_name'],
                "all_predictions": result['all_predictions']
            }
        }
    except Exception as e:
        print(f"[Local Tagger] ML Worker error for {filepath}: {e}")
        print(f"[Local Tagger] ERROR: ML Worker failed. Skipping file.")
        return None  # ML Worker is required - no fallback available


def check_ffmpeg_available():
    """
    Check if ffmpeg and ffprobe are available in PATH.

    Returns:
        Tuple of (ffmpeg_path, ffprobe_path) if both found, or (None, None) with error message printed
    """
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')

    if not ffmpeg_path or not ffprobe_path:
        missing = []
        if not ffmpeg_path:
            missing.append('ffmpeg')
        if not ffprobe_path:
            missing.append('ffprobe')

        print(f"[Video Tagger] ERROR: {' and '.join(missing)} not found in PATH.")
        print(f"[Video Tagger] FFmpeg is required for video processing.")
        print(f"[Video Tagger] Install it using:")
        print(f"[Video Tagger]   - Arch/CachyOS: sudo pacman -S ffmpeg")
        print(f"[Video Tagger]   - Ubuntu/Debian: sudo apt install ffmpeg")
        print(f"[Video Tagger]   - macOS: brew install ffmpeg")
        return None, None

    return ffmpeg_path, ffprobe_path


def tag_video_with_frames(video_filepath, num_frames=5):
    """
    Tag a video by extracting multiple frames and merging the tags using ML Worker.

    Args:
        video_filepath: Path to the video file
        num_frames: Number of frames to extract and analyze (default: 5)

    Returns:
        Dictionary with source and merged tag data, or None on failure
    """
    if not ML_WORKER_AVAILABLE:
        print("[Video Tagger] ERROR: ML Worker not available. Cannot process video.")
        return None

    print(f"[Video Tagger] Analyzing video via ML Worker: {os.path.basename(video_filepath)}")

    try:
        from ml_worker.client import get_ml_worker_client
        client = get_ml_worker_client()
        
        # Call ML Worker to handle extraction and tagging
        result = client.tag_video(
            video_path=os.path.abspath(video_filepath), # Use absolute path
            num_frames=num_frames,
            model_path=tagger_config['model_path'],
            threshold=tagger_config.get('threshold', 0.50),
            character_threshold=0.85,
            metadata_path=tagger_config.get('metadata_path')
        )
        
        return {
            "source": "local_tagger",
            "data": result
        }

    except Exception as e:
        print(f"[Video Tagger] ERROR during video analysis via ML Worker: {e}")
        return None

def extract_tag_data(data, source):
    """Extract categorized tags and metadata from a raw API response."""
    tags_dict = { "character": "", "copyright": "", "artist": "", "meta": "", "general": "" }
    image_url, preview_url = None, None
    width, height, file_size = None, None, None

    if source == 'danbooru':
        tags_dict["character"] = data.get("tag_string_character", "")
        tags_dict["copyright"] = data.get("tag_string_copyright", "")
        tags_dict["artist"] = data.get("tag_string_artist", "")
        tags_dict["meta"] = data.get("tag_string_meta", "")
        tags_dict["general"] = data.get("tag_string_general", "")
        image_url = data.get('file_url')
        preview_url = data.get('large_file_url') or data.get('preview_file_url')
        width, height, file_size = data.get('image_width'), data.get('image_height'), data.get('file_size')

    elif source == 'e621':
        tag_data = data.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        image_url = data.get('file', {}).get('url')
        preview_url = data.get('preview', {}).get('url')
        width, height, file_size = data.get('file', {}).get('width'), data.get('file', {}).get('height'), data.get('file', {}).get('size')

    elif source in ['gelbooru', 'yandere']:
        tags_dict["general"] = data.get("tags", "")
        image_url = data.get('file_url')
        preview_url = data.get('preview_url')  # Works for both
        width, height, file_size = data.get('width'), data.get('height'), data.get('file_size')

    elif source == 'pixiv':
        tag_data = data.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        tags_dict["species"] = " ".join(tag_data.get("species", []))
        image_url = data.get('image_url')
        preview_url = None  # Pixiv doesn't provide direct preview URLs
        width, height = data.get('width'), data.get('height')
        file_size = None  # Not provided by Pixiv API

    return {
        "tags": tags_dict,
        "image_url": image_url,
        "preview_url": preview_url,
        "width": width, "height": height, "file_size": file_size
    }

def ensure_thumbnail(filepath, image_dir="./static/images", md5=None):
    """
    Create a thumbnail for an image, video, or zip animation.
    Handles both bucketed and legacy flat paths.
    
    Args:
        filepath: Path to the media file
        image_dir: Base image directory
        md5: Optional MD5 hash (required for zip animations)
    """
    from utils.file_utils import get_hash_bucket

    # Get just the filename
    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]

    # Use bucketed structure for thumbnails
    # Try to extract bucket from input filepath first to support collision buckets
    from utils.file_utils import extract_bucket_from_path, get_hash_bucket
    
    path_bucket = extract_bucket_from_path(filepath)
    bucket = path_bucket if path_bucket else get_hash_bucket(filename)
    
    thumb_path = os.path.join(THUMB_DIR, bucket, base_name + '.webp')

    if not os.path.exists(thumb_path):
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        
        # Try using ML Worker first
        if ML_WORKER_AVAILABLE:
            try:
                from ml_worker.client import get_ml_worker_client
                client = get_ml_worker_client()
                
                # Use ML Worker for all types (zip, video, image)
                # It handles logic internally
                print(f"[Thumbnail] Generating via ML Worker: {filename}")
                result = client.generate_thumbnail(
                    filepath=os.path.abspath(filepath),
                    output_path=os.path.abspath(thumb_path),
                    size=THUMB_SIZE
                )
                
                if result and result.get('success'):
                    return
            except Exception as e:
                print(f"[Thumbnail] ML Worker generation failed: {e}. Falling back to local.")
                # Fall through to local logic

        try:
            # Check if this is a zip animation
            if filepath.lower().endswith('.zip'):
                if md5:
                    from services import zip_animation_service
                    # Get the first frame from the extracted animation
                    first_frame = zip_animation_service.get_frame_path(md5, 0)
                    if first_frame and os.path.exists(first_frame):
                        # Create thumbnail from first frame
                        with Image.open(first_frame) as img:
                            if img.mode in ('RGBA', 'LA', 'P'):
                                background = Image.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'P': img = img.convert('RGBA')
                                background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                                img = background
                            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                            img.save(thumb_path, 'WEBP', quality=85, method=6)
                        print(f"[Thumbnail] Created thumbnail for zip animation: {os.path.basename(filepath)}")
                    else:
                        print(f"[Thumbnail] ERROR: Could not find first frame for zip animation: {os.path.basename(filepath)}")
                else:
                    print(f"[Thumbnail] ERROR: MD5 required for zip animation thumbnail: {os.path.basename(filepath)}")
            # Check if this is a video file
            elif filepath.lower().endswith(('.mp4', '.webm')):
                # Extract first frame from video using ffmpeg
                import subprocess
                import tempfile

                # Check if ffmpeg is available
                ffmpeg_path = shutil.which('ffmpeg')
                if not ffmpeg_path:
                    print(f"[Thumbnail] ERROR: ffmpeg not found. Cannot create thumbnail for video: {os.path.basename(filepath)}")
                    print(f"[Thumbnail] Install ffmpeg to enable video thumbnail generation.")
                    return  # Skip thumbnail creation for this video

                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                    temp_frame_path = temp_frame.name
                try:
                    # Extract frame at 0.1 seconds (works for short videos too)
                    subprocess.run([
                        ffmpeg_path, '-ss', '0.1', '-i', filepath, '-vframes', '1',
                        '-strict', 'unofficial', '-y', temp_frame_path
                    ], check=True, capture_output=True)
                    # Now process the extracted frame as an image
                    with Image.open(temp_frame_path) as img:
                        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                        img.save(thumb_path, 'WEBP', quality=85, method=6)
                finally:
                    if os.path.exists(temp_frame_path):
                        os.unlink(temp_frame_path)
            else:
                # Regular image processing
                with Image.open(filepath) as img:
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P': img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
                        img = background
                    img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                    img.save(thumb_path, 'WEBP', quality=85, method=6)
        except Exception as e:
            print(f"Thumbnail error for {filepath}: {e}")

def search_danbooru(md5):
    try:
        url = f"https://danbooru.donmai.us/posts.json?tags=md5:{md5}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.json():
            return {"source": "danbooru", "data": response.json()[0]}
    except requests.RequestException:
        return None
    return None

def search_e621(md5):
    try:
        headers = {"User-Agent": "ChibiBooru/1.0"}
        url = f"https://e621.net/posts.json?tags=md5:{md5}"
        response = requests.get(url, headers=headers, timeout=10)
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
        max_size = 15 * 1024 * 1024  # 15MB in bytes

        # For GIFs and very large files, extract a frame or resize
        import tempfile
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
                quality = 95
                while True:
                    temp_file.seek(0)
                    temp_file.truncate()
                    img.save(temp_file.name, 'JPEG', quality=quality)
                    temp_size = os.path.getsize(temp_file.name)
                    if temp_size < max_size or quality <= 50:
                        break
                    quality -= 10

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
            params = {'api_key': SAUCENAO_API_KEY, 'output_type': 2, 'numres': 10}
            response = requests.post('https://saucenao.com/search.php', files=files, params=params, timeout=20)
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

            # Print current stats (only every 10 requests to reduce spam)
            stats = saucenao_rate_limiter.get_stats()
            if stats['requests_in_window'] % 10 == 0 or stats['current_limit'] is not None:
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
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return {"source": "danbooru", "data": response.json()}
        
        elif source == "e621":
            headers = {"User-Agent": "ChibiBooru/1.0"}
            url = f"https://e621.net/posts/{post_id}.json"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return {"source": "e621", "data": response.json()["post"]}
            
        elif source == "gelbooru":
            if not GELBOORU_API_KEY or not GELBOORU_USER_ID:
                print("Warning: GELBOORU_API_KEY or GELBOORU_USER_ID not set. Gelbooru search may fail.")
            
            url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&id={post_id}&api_key={GELBOORU_API_KEY}&user_id={GELBOORU_USER_ID}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if "post" in data and data["post"]:
                return {"source": "gelbooru", "data": data["post"][0]}
            elif isinstance(data, list) and data:
                 return {"source": "gelbooru", "data": data[0]}

        elif source == "yandere":
            url = f"https://yande.re/post.json?tags=id:{post_id}"
            response = requests.get(url, timeout=10)
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
    import re

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

        response = requests.get(url, headers=headers, timeout=10)
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

        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

        print(f"[Pixiv] Downloaded original image: {output_path}")
        return output_path

    except Exception as e:
        print(f"[Pixiv] Error downloading image for ID {pixiv_id}: {e}")
        return None

def process_image_file(filepath, move_from_ingest=True):
    """
    Process a single image file with unified flow.
    
    This is the main entry point for processing images. It handles:
    1. Pre-flight checks (file exists, MD5 calculation, duplicate detection)
    2. Metadata fetching (MD5 lookup, SauceNao, local tagger)
    3. Hash computation (phash, colorhash, embedding - all in one pass)
    4. File operations (move from ingest if needed)
    5. Database commit (single transaction)
    6. Post-processing (thumbnail, cache updates)
    
    Args:
        filepath: Path to the image file
        move_from_ingest: If True, move file from ingest folder to bucketed structure
        
    Returns:
        Tuple (success, message)
    """
    from utils.file_utils import ensure_bucket_dir
    import shutil
    
    # ========== STAGE 1: PRE-FLIGHT CHECKS ==========
    # Check if file exists (race condition check for concurrent processing)
    if not os.path.exists(filepath):
        msg = f"[Processing] File not found (likely processed by another thread): {filepath}"
        print(msg)
        return False, msg
    
    filename = os.path.basename(filepath)
    print(f"[Processing] Starting: {filename}")
    
    # Debug logging for investigation - REMOVED

    
    # Calculate MD5 immediately
    try:
        md5 = get_file_md5(filepath)
        if md5 is None:
            msg = f"[Processing] ERROR: Failed to calculate MD5 for {filename} (File not found or unreadable)"
            print(msg)
            return False, msg
    except Exception as e:
        msg = f"[Processing] ERROR: Failed to calculate MD5 for {filename}: {e}"
        print(msg)
        return False, msg
    
    # Check for duplicate in database (with lock)
    lock_fd, acquired = acquire_processing_lock(md5)
    if not acquired:
        msg = f"[Processing] Skipped: {filename} (already being processed by another thread)"
        print(msg)
        return False, msg
    
    try:
        # Re-check duplicate inside lock
        if models.md5_exists(md5):
            existing_filepath = None
            with get_db_connection() as conn:
                row = conn.execute('SELECT filepath FROM images WHERE md5 = ?', (md5,)).fetchone()
                if row:
                    existing_filepath = row['filepath']
            
            msg = f"[Processing] Duplicate detected: {filename} (same as {os.path.basename(existing_filepath) if existing_filepath else 'existing file'})"
            print(msg)
            
            # Remove duplicate file if it exists
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    print(f"[Processing] Removed duplicate file: {filename}")
                except Exception as e:
                    print(f"[Processing] WARNING: Could not remove duplicate file {filename}: {e}")
            
            return False, msg
        
        # ========== STAGE 2: METADATA FETCHING ==========
        is_video = filepath.lower().endswith(('.mp4', '.webm'))
        is_zip_animation = filepath.lower().endswith('.zip')
        
        # Parallel metadata fetching
        all_results = search_all_sources(md5)
        saucenao_used = False
        local_tagger_used = False
        
        if is_zip_animation:
            # Minimal processing for zip files
            pass
        elif is_video:
            # Video tagging via local tagger
            local_tagger_result = tag_video_with_frames(filepath)
            if local_tagger_result:
                all_results[local_tagger_result['source']] = local_tagger_result['data']
                local_tagger_used = True
            else:
                # FAIL-FAST: Video tagging failed
                msg = f"[Processing] ERROR: Video tagging failed for {filename}. File NOT ingested."
                print(msg)
                return False, msg
        else:
            # Standard image processing
            if not all_results:
                # Try SauceNao if no MD5 match
                saucenao_resp = search_saucenao(filepath)
                if saucenao_resp:
                    saucenao_used = True
                    if 'results' in saucenao_resp:
                        for r in saucenao_resp.get('results', []):
                            if float(r['header']['similarity']) > 80:
                                for url in r['data'].get('ext_urls', []):
                                    post_id, source = None, None
                                    # Parse URL to extract source and post ID
                                    # Use startswith for more secure URL matching
                                    if url.startswith('https://danbooru.donmai.us/'):
                                        post_id = url.split('/posts/')[-1].split('?')[0]
                                        source = 'danbooru'
                                    elif url.startswith('https://e621.net/'):
                                        post_id = url.split('/posts/')[-1].split('?')[0]
                                        source = 'e621'
                                    
                                    if post_id and source:
                                        fetched = fetch_by_post_id(source, post_id)
                                        if fetched:
                                            all_results[fetched['source']] = fetched['data']
                                            break
                                if all_results:
                                    break
                
                # Try Pixiv ID extraction
                if not all_results:
                    pixiv_id = extract_pixiv_id_from_filename(filename)
                    if pixiv_id:
                        pixiv_result = fetch_pixiv_metadata(pixiv_id)
                        if pixiv_result:
                            all_results[pixiv_result['source']] = pixiv_result['data']
            
            # Local tagger logic
            pixiv_found = 'pixiv' in all_results
            should_run_tagger = False
            if config.LOCAL_TAGGER_ALWAYS_RUN:
                should_run_tagger = True
            elif pixiv_found and config.LOCAL_TAGGER_COMPLEMENT_PIXIV:
                should_run_tagger = True
            elif not all_results:
                should_run_tagger = True
            
            if should_run_tagger:
                lt_res = tag_with_local_tagger(filepath)
                if lt_res:
                    all_results[lt_res['source']] = lt_res['data']
                    local_tagger_used = True
                else:
                    # FAIL-FAST: Local tagger was required but failed
                    msg = f"[Processing] ERROR: Local tagger failed for {filename}. File NOT ingested."
                    print(msg)
                    return False, msg
        
        # ========== STAGE 3: HASH COMPUTATION (ALL IN ONE PASS) ==========
        hashes = {}
        from services import similarity_service
        
        # Compute perceptual hash
        phash = similarity_service.compute_phash_for_file(filepath, md5)
        if phash:
            hashes['phash'] = phash
        else:
            # FAIL-FAST: Hash computation is required
            msg = f"[Processing] ERROR: Failed to compute perceptual hash for {filename}. File NOT ingested."
            print(msg)
            return False, msg
        
        # Compute color hash
        colorhash = similarity_service.compute_colorhash_for_file(filepath)
        if colorhash:
            hashes['colorhash'] = colorhash
        # Note: colorhash failure is not fatal, phash is sufficient
        
        # Compute semantic embedding if available
        if similarity_service.SEMANTIC_AVAILABLE:
            engine = similarity_service.get_semantic_engine()
            if not engine.load_model():
                # FAIL-FAST: Similarity is enabled but model failed to load
                print(f"[Processing] ERROR: Failed to load similarity model for {filename}. File NOT ingested.")
                return False
            
            embedding = engine.get_embedding(filepath)
            if embedding is not None:
                hashes['embedding'] = embedding
            else:
                # FAIL-FAST: Similarity is enabled but embedding failed
                msg = f"[Processing] ERROR: Failed to compute similarity embedding for {filename}. File NOT ingested."
                print(msg)
                return False, msg
        
        # ========== STAGE 4: FILE OPERATIONS ==========
        # ========== STAGE 4: FILE OPERATIONS ==========
        
        # Determine strict filename (renaming if necessary)
        # Strategy:
        # 1. If in subdirectory of ingest: ParentFolder_-_Filename.ext
        # 2. If in root of ingest: Filename_MD5.ext
        # 3. If not from ingest (e.g. upload): keep original name
        
        final_filename = filename
        if move_from_ingest:
            try:
                abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
                abs_filepath = os.path.abspath(filepath)
                
                # Check if file is inside ingest directory
                if abs_filepath.startswith(abs_ingest):
                    rel_path = os.path.relpath(abs_filepath, abs_ingest)
                    parent_dir = os.path.dirname(rel_path)
                    
                    name_base, name_ext = os.path.splitext(filename)
                    
                    if parent_dir and parent_dir != '.':
                        # Case 1: Subdirectory -> Use immediate parent folder
                        # Handle multiple levels if needed, but user asked for immediate parent
                        # e.g. "Pack/Char/Image.png" -> "Char"
                        immediate_parent = os.path.basename(parent_dir)
                        final_filename = f"{immediate_parent}_-_{filename}"
                    else:
                        # Case 2: Root of ingest -> Append MD5
                        final_filename = f"{name_base}_{md5}{name_ext}"
                        
                    print(f"[Processing] Renaming {filename} -> {final_filename}")

                    
            except Exception as e:
                print(f"[Processing] WARNING: Error calculating new filename: {e}")
                # Fallback to original filename
                pass

        file_dest = filepath
        if move_from_ingest:
            from utils.file_utils import get_hash_bucket
            
            # Canonical bucket attempt with NEW filename
            bucket_chars = 3
            canonical_bucket = get_hash_bucket(final_filename, bucket_chars)
            
            # Find a free filename/bucket
            attempt = 0
            target_filename = final_filename
            bucket_chars = 3
            canonical_bucket = get_hash_bucket(target_filename, bucket_chars)
            final_bucket = canonical_bucket
            
            while True:
                bucket_dir = os.path.join(config.IMAGE_DIRECTORY, final_bucket)
                os.makedirs(bucket_dir, exist_ok=True)
                new_path = os.path.join(bucket_dir, target_filename)
                
                if os.path.exists(new_path):
                    # File exists at this path
                    if get_file_md5(new_path) == md5:
                        # Same file, remove ingest copy
                        try:
                            os.remove(filepath)
                        except Exception as e:
                             print(f"[Processing] WARNING: Failed to remove source file {filepath}: {e}")
                             
                        file_dest = new_path
                        print(f"[Processing] File already at destination: {new_path}")
                        break
                    else:
                        # Different file! Collision!
                        print(f"[Processing] Collision for {target_filename} at bucket {final_bucket}.", 'warning')
                        
                        # Strategy: Append MD5 to filename if not already there
                        name_base, name_ext = os.path.splitext(target_filename)
                        
                        # check if md5 is already in the name to avoid infinite appending
                        if md5 in name_base:
                             # Fallback to bucket iteration if MD5 is already there
                             print(f"[Processing] MD5 already in filename, trying alternate bucket...")
                             attempt += 1
                             salt = f"_collision_{attempt}"
                             import hashlib
                             alt_hash = hashlib.md5((target_filename + salt).encode()).hexdigest()
                             final_bucket = alt_hash[:bucket_chars]
                        else:
                             # Append MD5 to filename and try again (this changes the canonical bucket)
                             print(f"[Processing] Appending MD5 to resolve collision...")
                             target_filename = f"{name_base}_{md5}{name_ext}"
                             # Recalculate bucket for the new filename
                             final_bucket = get_hash_bucket(target_filename, bucket_chars)
                        
                        if attempt > 50:
                            msg = f"[Processing] ERROR: Too many filename collisions for {filename} (gave up after 50 attempts)"
                            print(msg)
                            return False, msg
                else:
                    # Found a free slot!
                    try:
                        shutil.move(filepath, new_path)
                        file_dest = new_path
                        print(f"[Processing] Moved to: {new_path}")

                        break
                    except Exception as e:
                        return False, msg
                    except Exception as e:
                        msg = f"[Processing] ERROR: Failed to move file to {new_path}: {e}"
                        print(msg)

                        return False, msg
        
        db_path = os.path.relpath(file_dest, "static/images").replace('\\', '/')
        
        # ========== STAGE 5: DATABASE COMMIT ==========
        # Prepare metadata
        primary_source_data = None
        source_name = None
        priority = config.BOORU_PRIORITY
        for src in priority:
            if src in all_results:
                primary_source_data = all_results[src]
                source_name = src
                break
        
        extracted_tags = extract_tags_from_source(primary_source_data, source_name)
        
        # Merge Pixiv + Local Tagger if needed
        if source_name == 'pixiv' and 'local_tagger' in all_results:
            from utils.tag_extraction import merge_tag_sources, deduplicate_categorized_tags
            local_tagger_tags = extract_tags_from_source(all_results['local_tagger'], 'local_tagger')
            extracted_tags = merge_tag_sources(
                extracted_tags,
                local_tagger_tags,
                merge_categories=['character', 'copyright', 'species', 'meta', 'general']
            )
            extracted_tags = deduplicate_categorized_tags(extracted_tags)
        else:
            from utils.tag_extraction import deduplicate_categorized_tags
            extracted_tags = deduplicate_categorized_tags(extracted_tags)
        
        categorized_tags = {
            'character': extracted_tags['tags_character'].split(),
            'copyright': extracted_tags['tags_copyright'].split(),
            'artist': extracted_tags['tags_artist'].split(),
            'species': extracted_tags['tags_species'].split(),
            'meta': extracted_tags['tags_meta'].split(),
            'general': extracted_tags['tags_general'].split()
        }
        
        rating, rating_source = extract_rating_from_source(primary_source_data, source_name)
        
        parent_id = primary_source_data.get('parent_id') if primary_source_data else None
        if source_name == 'e621' and primary_source_data:
            parent_id = primary_source_data.get('relationships', {}).get('parent_id')
        
        image_info = {
            'filepath': db_path,
            'md5': md5,
            'post_id': primary_source_data.get('id') if primary_source_data else None,
            'parent_id': parent_id,
            'has_children': primary_source_data.get('has_children', False) if primary_source_data else False,
            'saucenao_lookup': saucenao_used,
            'rating': rating,
            'rating_source': rating_source,
            'image_width': None,
            'image_height': None,
        }
        
        # Get image dimensions using PIL
        try:
            if is_zip_animation:
                # For zip animations, get dimensions from first frame
                from services import zip_animation_service
                first_frame = zip_animation_service.get_frame_path(md5, 0)
                if first_frame and os.path.exists(first_frame):
                    with Image.open(first_frame) as img:
                        image_info['image_width'] = img.width
                        image_info['image_height'] = img.height
            elif is_video:
                # For videos, try to get dimensions using ffprobe
                import subprocess
                ffprobe_path = shutil.which('ffprobe')
                if ffprobe_path:
                    result = subprocess.run([
                        ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
                        file_dest
                    ], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        parts = result.stdout.strip().split(',')
                        if len(parts) == 2:
                            image_info['image_width'] = int(parts[0])
                            image_info['image_height'] = int(parts[1])
            else:
                # Regular image - read dimensions with PIL
                with Image.open(file_dest) as img:
                    image_info['image_width'] = img.width
                    image_info['image_height'] = img.height
        except Exception as e:
            print(f"[Processing] WARNING: Could not read dimensions for {filename}: {e}")
        
        # Add computed hashes to image_info
        if 'phash' in hashes:
            image_info['phash'] = hashes['phash']
        if 'colorhash' in hashes:
            image_info['colorhash'] = hashes['colorhash']
        
        raw_metadata_to_save = {
            "md5": md5,
            "relative_path": db_path,
            "saucenao_lookup": saucenao_used,
            "saucenao_response": None,  # Don't save full response to save space
            "local_tagger_lookup": local_tagger_used,
            "sources": all_results
        }
        
        # Insert into database
        success = models.add_image_with_metadata(
            image_info,
            list(all_results.keys()),
            categorized_tags,
            raw_metadata_to_save
        )
        
        if not success:
            msg = f"[Processing] ERROR: Database insert failed for {filename}"
            print(msg)

            return False, msg


        
        # ========== STAGE 6: POST-PROCESSING ==========
        # Save semantic embedding if computed
        if 'embedding' in hashes:
            try:
                from services import similarity_db
                # Get image ID
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                    row = cursor.fetchone()
                    if row:
                        similarity_db.save_embedding(row['id'], hashes['embedding'])
                        
                        # Compute and cache similarities if cache is enabled
                        if config.SIMILARITY_CACHE_ENABLED:
                            try:
                                from services import similarity_cache
                                # Queue for background processing to not block ingestion
                                # For now, do it inline since we're already in a background thread
                                similarity_cache.compute_and_cache_for_image(
                                    row['id'],
                                    similarity_type='blended',
                                    force=True
                                )
                                print(f"[Processing] Cached similarities for {filename}")
                            except Exception as e:
                                # Don't fail ingestion if caching fails
                                print(f"[Processing] WARNING: Failed to cache similarities for {filename}: {e}")
            except Exception as e:
                print(f"[Processing] WARNING: Failed to save embedding for {filename}: {e}")
        
        # Store tagger predictions if available
        if 'local_tagger' in all_results:
            local_data = all_results['local_tagger']
            all_predictions = local_data.get('all_predictions', [])
            if all_predictions:
                try:
                    from repositories import tagger_predictions_repository
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                        row = cursor.fetchone()
                        if row:
                            tagger_predictions_repository.store_predictions(
                                row['id'], 
                                all_predictions, 
                                local_data.get('tagger_name')
                            )
                except Exception as e:
                    print(f"[Processing] WARNING: Failed to save predictions for {filename}: {e}")
        
        # Generate thumbnail
        # Ensure thumbnail respects the final destination bucket
        ensure_thumbnail(file_dest, md5=md5)
        
        # Apply tag implications if enabled
        if config.APPLY_IMPLICATIONS_ON_INGEST:
            try:
                from repositories.tag_repository import apply_implications_for_image
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                    row = cursor.fetchone()
                    if row:
                        if apply_implications_for_image(row['id']):
                            print(f"[Processing] Applied tag implications for: {filename}")
            except Exception as e:
                print(f"[Processing] WARNING: Failed to apply implications for {filename}: {e}")
        
        print(f"[Processing] Successfully processed: {filename}")
        return True, "Successfully processed"
        
    except Exception as e:
        msg = f"[Processing] ERROR processing {filename}: {e}"
        print(msg)
        import traceback
        traceback.print_exc()
        return False, msg
    finally:
        release_processing_lock(lock_fd)

###############################################################################
# LEGACY ARCHITECTURE REMOVED
###############################################################################
# The old split-phase architecture with analyze_image_for_ingest() and 
# commit_image_ingest() has been consolidated into the unified process_image_file()
# function above. This eliminates the complexity of coordinating analysis and commit
# phases across process boundaries, and allows all hashes to be computed in a single
# pass during ingest.
#
# Key improvements in the unified approach:
# - Single MD5 check with lock (prevents duplicates)
# - All hashes computed before DB insert (no re-computation needed)
# - Single transaction for all database operations
# - Better error handling and cleanup
# - Compatible with ThreadPoolExecutor for I/O-bound tasks
###############################################################################
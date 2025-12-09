import os
import hashlib
from urllib.parse import quote


def get_hash_bucket(filename, bucket_chars=3):
    """
    Generate hash bucket directory for a filename.
    Uses MD5 hash of the filename to ensure uniform distribution.

    Args:
        filename: The filename to hash
        bucket_chars: Number of hex chars to use (default 3 = 4096 buckets)

    Returns:
        Bucket directory name (e.g., "a3f")
    """
    hash_hex = hashlib.md5(filename.encode()).hexdigest()
    return hash_hex[:bucket_chars]


def get_bucketed_path(filename, base_dir="images"):
    """
    Get the full bucketed path for a file.

    Args:
        filename: The filename
        base_dir: Base directory (e.g., "images" or "thumbnails")

    Returns:
        Full path like "images/a3f/filename.jpg"
    """
    bucket = get_hash_bucket(filename)
    return f"{base_dir}/{bucket}/{filename}"


def get_bucketed_filepath_on_disk(filename, base_dir="./static/images"):
    """
    Get the full filesystem path for a bucketed file.

    Args:
        filename: The filename
        base_dir: Base directory on disk

    Returns:
        Full path like "./static/images/a3f/filename.jpg"
    """
    bucket = get_hash_bucket(filename)
    return os.path.join(base_dir, bucket, filename)


def ensure_bucket_dir(filename, base_dir="./static/images"):
    """
    Ensure the bucket directory exists for a file.

    Args:
        filename: The filename
        base_dir: Base directory on disk

    Returns:
        The bucket directory path
    """
    bucket = get_hash_bucket(filename)
    bucket_dir = os.path.join(base_dir, bucket)
    os.makedirs(bucket_dir, exist_ok=True)
    return bucket_dir


def get_thumbnail_path(image_path):
    """
    Convert image path to thumbnail path.
    Handles both legacy flat structure and new bucketed structure.
    """
    # Remove "images/" prefix if present
    rel_path = image_path.replace("images/", "", 1)

    # Extract just the filename (handles both flat and bucketed paths)
    filename = os.path.basename(rel_path)

    # Generate thumbnail name
    thumb_filename = os.path.splitext(filename)[0] + '.webp'

    # Try bucketed path first
    bucket = get_hash_bucket(filename)
    bucketed_thumb = f"thumbnails/{bucket}/{thumb_filename}"
    if os.path.exists(f"static/{bucketed_thumb}"):
        return bucketed_thumb

    # Fall back to legacy flat thumbnail path
    legacy_thumb = f"thumbnails/{thumb_filename}"
    if os.path.exists(f"static/{legacy_thumb}"):
        return legacy_thumb

    # Return original image path as last resort
    return image_path


def get_file_md5(filepath):
    """Calculate MD5 hash of a file"""
    try:
        hash_md5 = hashlib.md5()
        with open(f"static/{filepath}", "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except:
        return None


def url_encode_path(filepath):
    """
    URL-encode a filepath, preserving forward slashes.
    Handles non-ASCII characters (Japanese, etc.) properly.

    Args:
        filepath: The filepath to encode (e.g., "images/abc/ファイル名.jpg")

    Returns:
        URL-encoded path (e.g., "images/abc/%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB%E5%90%8D.jpg")
    """
    if not filepath:
        return filepath

    # Split path into components and encode each part separately
    parts = filepath.split('/')
    encoded_parts = [quote(part, safe='') for part in parts]
    return '/'.join(encoded_parts)
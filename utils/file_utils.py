import os
import hashlib


def get_thumbnail_path(image_path):
    """Convert image path to thumbnail path"""
    rel_path = image_path.replace("images/", "", 1)
    thumb_path = os.path.splitext(rel_path)[0] + '.webp'
    full_thumb_path = f"thumbnails/{thumb_path}"
    
    if os.path.exists(f"static/{full_thumb_path}"):
        return full_thumb_path
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
import json
from .file_utils import get_file_md5


def load_metadata(filepath):
    """Load metadata for an image file"""
    lookup_path = filepath.replace("images/", "", 1)
    md5 = get_file_md5(filepath)
    
    if not md5:
        return None
    
    metadata_file = f"metadata/{md5}.json"
    try:
        with open(metadata_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def get_related_images(post_id, parent_id, raw_data, id_to_path):
    """Find parent and child images"""
    related = []
    
    # Add parent
    if parent_id and parent_id in id_to_path:
        related.append({
            "path": f"images/{id_to_path[parent_id]}",
            "type": "parent"
        })
    
    # Add children (find all images that have this as parent)
    if post_id:
        for path, data in raw_data.items():
            if data == "not_found" or isinstance(data, str):
                continue
            if data.get("parent_id") == post_id:
                related.append({
                    "path": f"images/{path}",
                    "type": "child"
                })
    
    return related
#!/usr/bin/env python3
"""
Utility to switch the active metadata source for an image
"""
import os
import json
import hashlib

METADATA_DIR = "./metadata"
TAGS_FILE = "./tags.json"

def get_md5_from_filepath(filepath):
    """Get MD5 for a file"""
    full_path = os.path.join("static", filepath) if not filepath.startswith("static") else filepath
    if not os.path.exists(full_path):
        return None
    
    hash_md5 = hashlib.md5()
    with open(full_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def extract_tags_from_source(source_data, source_name):
    """Extract tag data from a specific source"""
    if not source_data or not isinstance(source_data, dict):
        return None
    
    tags_dict = {
        "character": "",
        "copyright": "",
        "artist": "",
        "species": "",
        "meta": "",
        "general": ""
    }
    
    all_tags = set()
    parent_id = source_data.get("parent_id")
    has_children = source_data.get("has_children", False)
    post_id = source_data.get("id")
    
    if source_name == "danbooru":
        tags_dict["character"] = source_data.get("tag_string_character", "")
        tags_dict["copyright"] = source_data.get("tag_string_copyright", "")
        tags_dict["artist"] = source_data.get("tag_string_artist", "")
        tags_dict["meta"] = source_data.get("tag_string_meta", "")
        tags_dict["general"] = source_data.get("tag_string_general", "")
        
        # Collect all tags
        for category_tags in tags_dict.values():
            if category_tags:
                all_tags.update(category_tags.split())
                
    elif source_name == "e621":
        tag_data = source_data.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["species"] = " ".join(tag_data.get("species", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        
        # Collect all tags
        for category_tags in tags_dict.values():
            if category_tags:
                all_tags.update(category_tags.split())
        
        relationships = source_data.get("relationships", {})
        parent_id = relationships.get("parent_id")
        has_children = relationships.get("has_children", False)
        
    elif source_name in ["gelbooru", "yandere"]:
        # These sources don't have categorized tags
        tags_str = source_data.get("tags", "")
        if tags_str:
            all_tags.update(tags_str.split())
            tags_dict["general"] = tags_str
            
    elif source_name == "camie_tagger":
        # AI tagger should have categorized tags
        tags_dict["character"] = source_data.get("tag_string_character", "")
        tags_dict["copyright"] = source_data.get("tag_string_copyright", "")
        tags_dict["artist"] = source_data.get("tag_string_artist", "")
        tags_dict["meta"] = source_data.get("tag_string_meta", "")
        tags_dict["general"] = source_data.get("tag_string_general", "")
        
        for category_tags in tags_dict.values():
            if category_tags:
                all_tags.update(category_tags.split())
    
    return {
        "tags": " ".join(sorted(all_tags)),
        "tags_character": tags_dict["character"],
        "tags_copyright": tags_dict["copyright"],
        "tags_artist": tags_dict["artist"],
        "tags_species": tags_dict["species"],
        "tags_meta": tags_dict["meta"],
        "tags_general": tags_dict["general"],
        "id": post_id,
        "parent_id": parent_id,
        "has_children": has_children,
        "active_source": source_name
    }

def switch_metadata_source(filepath, source_name):
    """Switch the active metadata source for an image"""
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath
    elif filepath.startswith('static/images/'):
        filepath = filepath.replace('static/', '', 1)
    elif not filepath.startswith('images/'):
        filepath = f"images/{filepath}"
    
    # Get MD5
    md5 = get_md5_from_filepath(filepath)
    if not md5:
        return {"error": "Could not calculate MD5 for image"}
    
    # Load metadata file
    metadata_file = os.path.join(METADATA_DIR, f"{md5}.json")
    if not os.path.exists(metadata_file):
        return {"error": "No metadata file found for this image"}
    
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
    
    # Check if source exists
    if not metadata.get("sources") or source_name not in metadata["sources"]:
        available = list(metadata.get("sources", {}).keys()) if metadata.get("sources") else []
        return {"error": f"Source '{source_name}' not found. Available sources: {', '.join(available)}"}
    
    # Extract tags from the selected source
    source_data = metadata["sources"][source_name]
    tag_data = extract_tags_from_source(source_data, source_name)
    
    if not tag_data:
        return {"error": f"Could not extract tags from source '{source_name}'"}
    
    # Add metadata info
    tag_data["md5"] = md5
    tag_data["sources"] = list(metadata.get("sources", {}).keys())
    
    # Load tags.json
    if os.path.exists(TAGS_FILE):
        with open(TAGS_FILE, 'r') as f:
            tags_db = json.load(f)
    else:
        tags_db = {}
    
    # Update tags.json
    tags_db[filepath] = tag_data
    
    # Save tags.json
    with open(TAGS_FILE, 'w') as f:
        json.dump(tags_db, f, indent=4)
    
    return {
        "status": "success",
        "message": f"Switched to {source_name}",
        "source": source_name,
        "tag_count": len(tag_data["tags"].split())
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python switch_metadata_source.py <filepath> <source>")
        print("Example: python switch_metadata_source.py 'images/myimage.jpg' danbooru")
        sys.exit(1)
    
    filepath = sys.argv[1]
    source = sys.argv[2]
    
    result = switch_metadata_source(filepath, source)
    print(json.dumps(result, indent=2))
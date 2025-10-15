import os
import json
from pathlib import Path

METADATA_DIR = "./metadata"
TAGS_FILE = "./tags.json"
IMAGE_DIRECTORY = "./static/images"


def extract_tags_from_metadata(metadata):
    """Extract tag data from a metadata file"""
    if not metadata.get("sources"):
        return None
    
    # Check if sources is actually a dict
    if not isinstance(metadata["sources"], dict):
        return None
    
    # Get the first available source (prefer danbooru/e621 for categorized tags)
    preferred_sources = ["danbooru", "e621", "gelbooru", "yandere"]
    primary_source = None
    primary_source_name = None
    
    for source_name in preferred_sources:
        if source_name in metadata["sources"]:
            primary_source = metadata["sources"][source_name]
            primary_source_name = source_name
            break
    
    if not primary_source:
        # Fallback to any available source
        primary_source_name = list(metadata["sources"].keys())[0]
        primary_source = metadata["sources"][primary_source_name]
    
    # Collect all tags from all sources
    all_tags = set()
    for source_data in metadata["sources"].values():
        if not isinstance(source_data, dict):
            continue
            
        if primary_source_name == "danbooru":
            tags_str = source_data.get("tag_string", "")
        elif primary_source_name == "e621":
            tag_data = source_data.get("tags", {})
            if isinstance(tag_data, dict):
                tags_list = []
                for category in tag_data.values():
                    tags_list.extend(category)
                tags_str = " ".join(tags_list)
            else:
                tags_str = ""
        else:
            tags_str = source_data.get("tags", "")
        
        if tags_str:
            all_tags.update(tags_str.split())
    
    # Extract categorized tags from primary source
    tags_dict = {
        "character": "",
        "copyright": "",
        "artist": "",
        "meta": "",
        "general": ""
    }
    
    parent_id = None
    has_children = False
    post_id = primary_source.get("id")
    
    if primary_source_name == "danbooru":
        tags_dict["character"] = primary_source.get("tag_string_character", "")
        tags_dict["copyright"] = primary_source.get("tag_string_copyright", "")
        tags_dict["artist"] = primary_source.get("tag_string_artist", "")
        tags_dict["meta"] = primary_source.get("tag_string_meta", "")
        tags_dict["general"] = primary_source.get("tag_string_general", "")
        parent_id = primary_source.get("parent_id")
        has_children = primary_source.get("has_children", False)
    elif primary_source_name == "e621":
        tag_data = primary_source.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        relationships = primary_source.get("relationships", {})
        parent_id = relationships.get("parent_id")
        has_children = relationships.get("has_children", False)
    else:
        # Gelbooru/Yandere don't have categorized tags
        parent_id = primary_source.get("parent_id")
        has_children = primary_source.get("has_children", False)
    
    return {
        "tags": " ".join(sorted(all_tags)),
        "tags_character": tags_dict["character"],
        "tags_copyright": tags_dict["copyright"],
        "tags_artist": tags_dict["artist"],
        "tags_meta": tags_dict["meta"],
        "tags_general": tags_dict["general"],
        "id": post_id,
        "parent_id": parent_id,
        "has_children": has_children,
        "md5": metadata.get("md5"),
        "sources": list(metadata.get("sources", {}).keys())
    }


def rebuild_tags():
    """Rebuild tags.json from all metadata files"""
    if not os.path.isdir(METADATA_DIR):
        print(f"Error: Metadata directory not found at '{METADATA_DIR}'")
        return False
    
    # Load existing tags.json to preserve "not_found" entries
    try:
        with open(TAGS_FILE, "r") as f:
            existing_tags = json.load(f)
    except FileNotFoundError:
        existing_tags = {}
    
    # Build new tags dict
    new_tags = {}
    
    # First, preserve all "not_found" entries
    for path, data in existing_tags.items():
        if data == "not_found":
            new_tags[path] = "not_found"
    
    # Process all metadata files
    metadata_files = list(Path(METADATA_DIR).glob("*.json"))
    
    for metadata_file in metadata_files:
        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            
            relative_path = metadata.get("relative_path")
            if not relative_path:
                continue
            
            # Extract tag data
            tag_data = extract_tags_from_metadata(metadata)
            if tag_data:
                new_tags[relative_path] = tag_data
        
        except Exception as e:
            print(f"Error processing {metadata_file}: {e}")
            continue
    
    # Write new tags.json
    with open(TAGS_FILE, "w") as f:
        json.dump(new_tags, f, indent=4)
    
    print(f"Rebuilt {TAGS_FILE} with {len(new_tags)} entries")
    return True


if __name__ == "__main__":
    rebuild_tags()
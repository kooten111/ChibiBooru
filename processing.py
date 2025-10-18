# processing.py
import os
import hashlib
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import models
from database import get_db_connection
from utils.deduplication import remove_duplicate

# --- Configuration ---
SAUCENAO_API_KEY = os.environ.get('SAUCENAO_API_KEY', '')
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000

# --- Helper Functions ---

def get_md5(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def ensure_thumbnail(filepath, image_dir="./static/images"):
    rel_path = os.path.relpath(filepath, image_dir)
    thumb_path = os.path.join(THUMB_DIR, os.path.splitext(rel_path)[0] + '.webp')
    
    if not os.path.exists(thumb_path):
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        try:
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

# --- Booru & Saucenao Search Functions ---

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
        headers = {"User-Agent": "HomeBooru/1.0"}
        url = f"https://e621.net/posts.json?tags=md5:{md5}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and response.json()["posts"]:
            return {"source": "e621", "data": response.json()["posts"][0]}
    except requests.RequestException:
        return None
    return None

def search_all_sources(md5):
    """Search all boorus in parallel and return all results."""
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

# --- THIS BLOCK IS NEW/MOVED ---
def search_saucenao(filepath):
    """Search SauceNao and return the raw API response."""
    if not SAUCENAO_API_KEY:
        raise Exception("Saucenao API key is not configured.")
    
    with open(filepath, 'rb') as f:
        files = {'file': f}
        params = {'api_key': SAUCENAO_API_KEY, 'output_type': 2, 'numres': 10}
        response = requests.post('https://saucenao.com/search.php', files=files, params=params, timeout=20)
        response.raise_for_status()
        return response.json()

def fetch_by_post_id(source, post_id):
    """Fetch metadata for a specific post ID from a booru."""
    try:
        if source == "danbooru":
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        elif source == "e621":
            headers = {"User-Agent": "HomeBooru/1.0"}
            url = f"https://e621.net/posts/{post_id}.json"
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()["post"]
    except Exception as e:
        print(f"Error fetching {source} post {post_id}: {e}")
        return None
    return None
# --- END OF NEW BLOCK ---

# --- Main Processing Logic ---

def process_image_file(filepath):
    """
    Takes a single image filepath, fetches its metadata,
    and inserts it into the database. Returns True on success.
    """
    print(f"Processing: {filepath}")
    rel_path = os.path.relpath(filepath, "static/images").replace('\\', '/')
    md5 = get_md5(filepath)

    if models.md5_exists(md5):
        print(f"Duplicate detected (MD5: {md5}). Removing redundant file: {filepath}")
        remove_duplicate(filepath)
        return False

    all_results = search_all_sources(md5)

    # --- START DEBUGGING ---
    print("\n" + "="*20 + " DEBUGGING START " + "="*20)
    print(f"File: {rel_path} | MD5: {md5}")
    print("\n[1] RAW DATA FROM BOORUS:")
    if 'danbooru' in all_results:
        print("\n--- Danbooru Data ---")
        print(json.dumps(all_results['danbooru'], indent=2))
    if 'e621' in all_results:
        print("\n--- e621 Data ---")
        print(json.dumps(all_results['e621'], indent=2))
    print("\n" + "="*50)
    # --- END DEBUGGING ---

    primary_source_data = None
    source_name = None
    if 'danbooru' in all_results:
        primary_source_data = all_results['danbooru']
        source_name = 'danbooru'
    elif 'e621' in all_results:
        primary_source_data = all_results['e621']
        source_name = 'e621'

    if not primary_source_data:
        print(f"No metadata found for {rel_path}")
        return False
        
    tags_character = ""
    tags_copyright = ""
    tags_artist = ""
    tags_species = ""
    tags_meta = ""
    tags_general = ""

    if source_name == 'danbooru':
        tags_character = primary_source_data.get("tag_string_character", "")
        tags_copyright = primary_source_data.get("tag_string_copyright", "")
        tags_artist = primary_source_data.get("tag_string_artist", "")
        tags_meta = primary_source_data.get("tag_string_meta", "")
        tags_general = primary_source_data.get("tag_string_general", "")
    elif source_name == 'e621':
        tags = primary_source_data.get("tags", {})
        tags_character = " ".join(tags.get("character", []))
        tags_copyright = " ".join(tags.get("copyright", []))
        tags_artist = " ".join(tags.get("artist", []))
        tags_species = " ".join(tags.get("species", []))
        tags_meta = " ".join(tags.get("meta", []))
        tags_general = " ".join(tags.get("general", []))

    # --- START DEBUGGING ---
    print("\n[2] EXTRACTED TAG STRINGS:")
    print(f"  Artist Tags:    '{tags_artist}'")
    print(f"  Character Tags: '{tags_character}'")
    print(f"  Copyright Tags: '{tags_copyright}'")
    print(f"  Meta Tags:      '{tags_meta}'")
    print(f"  General Tags:   '{tags_general}'")
    print("\n" + "="*50)
    # --- END DEBUGGING ---

    character_set = set(tags_character.split())
    copyright_set = set(tags_copyright.split())
    artist_set = set(tags_artist.split())
    species_set = set(tags_species.split()) 
    meta_set = set(tags_meta.split())
    general_set = set(tags_general.split())
    
    general_set -= (character_set | copyright_set | artist_set | meta_set)

    categorized_tags = {
        'character': list(character_set),
        'copyright': list(copyright_set),
        'artist': list(artist_set),
        'species': list(species_set),
        'meta': list(meta_set),
        'general': list(general_set)
    }

    # --- START DEBUGGING ---
    print("\n[3] FINAL CATEGORIZED TAGS (before sending to database):")
    print(json.dumps(categorized_tags, indent=2))
    print("\n" + "="*21 + " DEBUGGING END " + "="*22 + "\n")
    # --- END DEBUGGING ---

    image_info = {
        'filepath': rel_path,
        'md5': md5,
        'post_id': primary_source_data.get('id'),
        'parent_id': primary_source_data.get('parent_id'),
        'has_children': primary_source_data.get('has_children', False),
        'saucenao_lookup': False,
    }

    raw_metadata_to_save = {
        "md5": md5,
        "relative_path": rel_path,
        "saucenao_lookup": False,
        "saucenao_response": None,
        "camie_tagger_lookup": False,
        "sources": all_results
    }

    success = models.add_image_with_metadata(
        image_info,
        list(all_results.keys()),
        categorized_tags,
        raw_metadata_to_save
    )

    if success:
        ensure_thumbnail(filepath)
    
    return success
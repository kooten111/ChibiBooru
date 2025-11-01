# processing.py
import config
import os
import hashlib
import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, UnidentifiedImageError
import numpy as np
import models
from database import get_db_connection
from utils.deduplication import remove_duplicate

# Dependencies
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("Warning: onnxruntime not installed. Local Tagger will not be available.")

try:
    import torchvision.transforms as transforms
    TORCHVISION_AVAILABLE = True
except ImportError:
    TORCHVISION_AVAILABLE = False
    print("Warning: torchvision not installed. Local Tagger's image preprocessing will fail.")

# Load from config
SAUCENAO_API_KEY = config.SAUCENAO_API_KEY
GELBOORU_API_KEY = config.GELBOORU_API_KEY
GELBOORU_USER_ID = config.GELBOORU_USER_ID
THUMB_DIR = config.THUMB_DIR
THUMB_SIZE = config.THUMB_SIZE

# Local tagger
tagger_config = config.get_local_tagger_config()
local_tagger_session = None
local_tagger_metadata = None
idx_to_tag_map = {}
tag_to_category_map = {}


def load_local_tagger():
    """Load the local tagger model and metadata if not already loaded."""
    global local_tagger_session, local_tagger_metadata, idx_to_tag_map, tag_to_category_map
    if not ONNX_AVAILABLE or not TORCHVISION_AVAILABLE:
        print("[Local Tagger] Missing required libraries (onnxruntime or torchvision). Tagger cannot be used.")
        return

    if local_tagger_session: # Already loaded
        return

    print("[Local Tagger] Attempting to load model...")
    if not os.path.exists(tagger_config['model_path']) or not os.path.exists(tagger_config['metadata_path']):
        print(f"[Local Tagger] ERROR: Model files not found.")
        print(f"    - Searched for model at: {os.path.abspath(tagger_config['model_path'])}")
        print(f"    - Searched for metadata at: {os.path.abspath(tagger_config['metadata_path'])}")
        return

    try:
        # Load and parse the complex metadata structure
        with open(tagger_config['metadata_path'], 'r') as f:
            local_tagger_metadata = json.load(f)
        
        dataset_info = local_tagger_metadata['dataset_info']
        tag_mapping = dataset_info['tag_mapping']
        idx_to_tag_map = tag_mapping['idx_to_tag']
        tag_to_category_map = tag_mapping['tag_to_category']
        
        providers = ['CPUExecutionProvider']
        local_tagger_session = ort.InferenceSession(tagger_config['model_path'], providers=providers)
        
        print(f"[Local Tagger] SUCCESS: Model loaded. Provider: {local_tagger_session.get_providers()[0]}")
        print(f"    - Found {dataset_info['total_tags']} total tags.")

    except Exception as e:
        print(f"[Local Tagger] ERROR: Failed to load model files: {e}")
        local_tagger_session = None
        local_tagger_metadata = None
        idx_to_tag_map = {}
        tag_to_category_map = {}


def preprocess_image_for_local_tagger(image_path):
    """Process an image for the tagger with proper ImageNet normalization."""
    image_size = local_tagger_metadata.get('model_info', {}).get('img_size', 512)
    
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    
    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            width, height = img.size
            aspect_ratio = width / height
            
            if aspect_ratio > 1:
                new_width = image_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = image_size
                new_width = int(new_height * aspect_ratio)
                
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            pad_color = (124, 116, 104) # Corresponds to ImageNet mean
            new_image = Image.new('RGB', (image_size, image_size), pad_color)
            new_image.paste(img, ((image_size - new_width) // 2, (image_size - new_height) // 2))
            
            return transform(new_image).unsqueeze(0).numpy()
    except UnidentifiedImageError:
        print(f"[Local Tagger] ERROR: Cannot identify image file {image_path}")
        return None


def tag_with_local_tagger(filepath):
    """Tag an image using the local tagger."""
    load_local_tagger()
    if not local_tagger_session:
        print("[Local Tagger] Tagger not available, cannot process file.")
        return None

    print(f"[Local Tagger] Analyzing: {os.path.basename(filepath)}")
    try:
        img_numpy = preprocess_image_for_local_tagger(filepath)
        if img_numpy is None:
            return None
        input_name = local_tagger_session.get_inputs()[0].name
        
        raw_outputs = local_tagger_session.run(None, {input_name: img_numpy})
        
        # Use refined predictions if available (output index 1)
        logits = raw_outputs[1] if len(raw_outputs) > 1 else raw_outputs[0]
        probs = 1.0 / (1.0 + np.exp(-logits))
        
        tags_by_category = {"general": [], "character": [], "copyright": [], "artist": [], "meta": []}
        
        indices = np.where(probs[0] >= tagger_config['threshold'])[0]
        for idx in indices:
            idx_str = str(idx)
            tag_name = idx_to_tag_map.get(idx_str)
            if tag_name:
                category = tag_to_category_map.get(tag_name, "general")
                if category in tags_by_category:
                    tags_by_category[category].append(tag_name)
                else:
                    tags_by_category["general"].append(tag_name)
        
        return {
            "source": "local_tagger",
            "data": {
                "tags": tags_by_category,
                "tagger_name": tagger_config.get('name', 'Unknown')
            }
        }
    except Exception as e:
        print(f"[Local Tagger] ERROR during analysis for {filepath}: {e}")
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

    return {
        "tags": tags_dict,
        "image_url": image_url,
        "preview_url": preview_url,
        "width": width, "height": height, "file_size": file_size
    }

def get_md5(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def ensure_thumbnail(filepath, image_dir="./static/images"):
    """
    Create a thumbnail for an image.
    Handles both bucketed and legacy flat paths.
    """
    from utils.file_utils import get_hash_bucket

    # Get just the filename
    filename = os.path.basename(filepath)
    base_name = os.path.splitext(filename)[0]

    # Use bucketed structure for thumbnails
    bucket = get_hash_bucket(filename)
    thumb_path = os.path.join(THUMB_DIR, bucket, base_name + '.webp')

    if not os.path.exists(thumb_path):
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        try:
            # Check if this is a video file
            if filepath.lower().endswith('.mp4'):
                # Extract first frame from video using ffmpeg
                import subprocess
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                    temp_frame_path = temp_frame.name
                try:
                    # Extract frame at 1 seconds
                    subprocess.run([
                        'ffmpeg', '-i', filepath, '-ss', '1', '-vframes', '1',
                        '-y', temp_frame_path
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
        with open(filepath, 'rb') as f:
            files = {'file': f}
            params = {'api_key': SAUCENAO_API_KEY, 'output_type': 2, 'numres': 10}
            response = requests.post('https://saucenao.com/search.php', files=files, params=params, timeout=20)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"Saucenao search error: {e}")
        return None

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

def process_image_file(filepath, move_from_ingest=False):
    """
    Process an image file, fetch metadata, and add to database.

    Args:
        filepath: Path to the image file
        move_from_ingest: If True, move file from ingest folder to bucketed structure

    Returns:
        Boolean indicating success
    """
    from utils.file_utils import ensure_bucket_dir, get_bucketed_path
    import shutil

    print(f"Processing: {filepath}")

    # Get filename
    filename = os.path.basename(filepath)

    # Calculate MD5 before any moves
    md5 = get_md5(filepath)

    # Determine final destination path
    if move_from_ingest:
        # Move from ingest to bucketed structure
        bucket_dir = ensure_bucket_dir(filename, config.IMAGE_DIRECTORY)
        dest_filepath = os.path.join(bucket_dir, filename)

        # Move the file
        shutil.move(filepath, dest_filepath)
        filepath = dest_filepath
        print(f"Moved to bucketed location: {dest_filepath}")

    # Get relative path for database (relative to static/)
    if filepath.startswith("./static/"):
        rel_path = filepath[9:]  # Remove "./static/"
    elif filepath.startswith("static/"):
        rel_path = filepath[7:]  # Remove "static/"
    else:
        rel_path = os.path.relpath(filepath, "./static")

    # Normalize to forward slashes
    rel_path = rel_path.replace('\\', '/')

    # Remove "images/" prefix if present for storage
    if rel_path.startswith("images/"):
        db_path = rel_path[7:]  # Store without "images/" prefix
    else:
        db_path = rel_path

    if models.md5_exists(md5):
        print(f"Duplicate detected (MD5: {md5}). Removing redundant file: {filepath}")
        remove_duplicate(db_path)
        return False

    all_results = search_all_sources(md5)
    saucenao_response = None
    used_saucenao = False
    used_local_tagger = False

    if not all_results:
        print(f"MD5 lookup failed for {db_path}, trying SauceNao...")
        saucenao_response = search_saucenao(filepath)
        used_saucenao = True
        if saucenao_response and 'results' in saucenao_response:
            for result in saucenao_response.get('results', []):
                if float(result['header']['similarity']) > 80:
                    for url in result['data'].get('ext_urls', []):
                        post_id, source = None, None
                        if 'danbooru.donmai.us' in url:
                            post_id = url.split('/posts/')[-1].split('?')[0]
                            source = 'danbooru'
                        elif 'e621.net' in url:
                            post_id = url.split('/posts/')[-1].split('?')[0]
                            source = 'e621'
                        
                        if post_id and source:
                            print(f"Found high-confidence match on {source} via SauceNao.")
                            fetched_data = fetch_by_post_id(source, post_id)
                            if fetched_data:
                                all_results[fetched_data['source']] = fetched_data['data']
                                break
                if all_results:
                    break

    if not all_results:
        print(f"All online searches failed for {db_path}, trying local AI tagger...")
        local_tagger_result = tag_with_local_tagger(filepath)
        used_local_tagger = True
        if local_tagger_result:
            all_results[local_tagger_result['source']] = local_tagger_result['data']
            print(f"Tagged with Local Tagger: {len([t for v in local_tagger_result['data']['tags'].values() for t in v])} tags found.")

    if not all_results:
        print(f"No metadata found for {db_path}")
        return False

    primary_source_data = None
    source_name = None
    priority = config.BOORU_PRIORITY
    for src in priority:
        if src in all_results:
            primary_source_data = all_results[src]
            source_name = src
            break
    
    tags_character, tags_copyright, tags_artist, tags_species, tags_meta, tags_general = "", "", "", "", "", ""

    if source_name == 'danbooru':
        tags_character = primary_source_data.get("tag_string_character", "")
        tags_copyright = primary_source_data.get("tag_string_copyright", "")
        tags_artist = primary_source_data.get("tag_string_artist", "")
        tags_meta = primary_source_data.get("tag_string_meta", "")
        tags_general = primary_source_data.get("tag_string_general", "")
    elif source_name in ['e621', 'local_tagger']:
        tags = primary_source_data.get("tags", {})
        tags_character = " ".join(tags.get("character", []))
        tags_copyright = " ".join(tags.get("copyright", []))
        tags_artist = " ".join(tags.get("artist", []))
        tags_species = " ".join(tags.get("species", []))
        tags_meta = " ".join(tags.get("meta", []))
        tags_general = " ".join(tags.get("general", []))

    character_set = set(tags_character.split())
    copyright_set = set(tags_copyright.split())
    artist_set = set(tags_artist.split())
    species_set = set(tags_species.split()) 
    meta_set = set(tags_meta.split())
    general_set = set(tags_general.split())
    
    general_set -= (character_set | copyright_set | artist_set | meta_set | species_set)

    categorized_tags = {
        'character': list(character_set),
        'copyright': list(copyright_set),
        'artist': list(artist_set),
        'species': list(species_set),
        'meta': list(meta_set),
        'general': list(general_set)
    }

    parent_id = primary_source_data.get('parent_id')
    if source_name == 'e621':
        parent_id = primary_source_data.get('relationships', {}).get('parent_id')

    image_info = {
        'filepath': db_path,
        'md5': md5,
        'post_id': primary_source_data.get('id'),
        'parent_id': parent_id,
        'has_children': primary_source_data.get('has_children', False),
        'saucenao_lookup': used_saucenao,
    }

    raw_metadata_to_save = {
        "md5": md5,
        "relative_path": db_path,
        "saucenao_lookup": used_saucenao,
        "saucenao_response": saucenao_response,
        "local_tagger_lookup": used_local_tagger,
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
        return True
    else:
        print(f"Failed to add image {db_path} to DB. It might be a duplicate from a concurrent process. Removing file.")
        remove_duplicate(filepath)
        return False
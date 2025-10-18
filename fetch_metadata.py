import config
from dotenv import load_dotenv
load_dotenv()

import os
import hashlib
import requests
import json
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
from rebuild_tags_from_metadata import rebuild_tags
from utils.deduplication import build_md5_index, is_duplicate, remove_duplicate
import numpy as np

# Try to import onnxruntime (optional dependency)
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("Warning: onnxruntime not installed. Local Tagger will not be available.")
    print("Install with: pip install onnxruntime-gpu (or onnxruntime for CPU)")

# Use config
IMAGE_DIRECTORY = config.IMAGE_DIRECTORY
TAGS_FILE = config.TAGS_FILE
METADATA_DIR = config.METADATA_DIR
THUMB_DIR = config.THUMB_DIR
THUMB_SIZE = config.THUMB_SIZE
SAUCENAO_API_KEY = config.SAUCENAO_API_KEY

# Local tagger settings
tagger_config = config.get_local_tagger_config()

os.makedirs(METADATA_DIR, exist_ok=True)

def ensure_thumbnail(filepath):
    rel_path = os.path.relpath(filepath, IMAGE_DIRECTORY)
    thumb_path = os.path.join(THUMB_DIR, os.path.splitext(rel_path)[0] + '.webp')
    
    if not os.path.exists(thumb_path):
        os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
        try:
            with Image.open(filepath) as img:
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
                img.save(thumb_path, 'WEBP', quality=85, method=6)
        except Exception as e:
            print(f"Thumbnail error for {filepath}: {e}")


def get_md5(filepath):
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def search_danbooru(md5):
    try:
        url = f"https://danbooru.donmai.us/posts.json?tags=md5:{md5}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return {
                "tag_string": data.get("tag_string", ""),
                "full_data": data,
                "source": "danbooru"
            }
    except requests.RequestException:
        return None
    return None

def search_gelbooru(md5):
    try:
        url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&tags=md5:{md5}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and "post" in response.json():
            data = response.json()["post"][0]
            return {
                "tag_string": data.get("tags", ""),
                "full_data": data,
                "source": "gelbooru"
            }
    except (requests.RequestException, KeyError, IndexError):
        return None
    return None

def search_yandere(md5):
    try:
        url = f"https://yande.re/post.json?tags=md5:{md5}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.json():
            data = response.json()[0]
            return {
                "tag_string": data.get("tags", ""),
                "full_data": data,
                "source": "yandere"
            }
    except requests.RequestException:
        return None
    return None
    
def search_e621(md5):
    try:
        headers = {"User-Agent": "TagFetcher/1.0 (by YourUsername on e621)"}
        url = f"https://e621.net/posts.json?tags=md5:{md5}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and response.json()["posts"]:
            data = response.json()["posts"][0]
            tags_data = data["tags"]
            all_tags = []
            for category in tags_data.values():
                all_tags.extend(category)
            return {
                "tag_string": " ".join(all_tags),
                "full_data": data,
                "source": "e621"
            }
    except requests.RequestException:
        return None
    return None

def search_all_sources(md5):
    """Search all sources in parallel and return all results"""
    search_functions = {
        "danbooru": search_danbooru,
        "e621": search_e621,
        "gelbooru": search_gelbooru,
        "yandere": search_yandere
    }
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_source = {
            executor.submit(func, md5): source 
            for source, func in search_functions.items()
        }
        
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                result = future.result()
                if result:
                    results[source] = result
            except Exception as e:
                print(f"Error searching {source}: {e}")
    
    return results

def search_saucenao(filepath):
    """Search SauceNao and extract booru post IDs"""
    if not SAUCENAO_API_KEY:
        return None, None
    
    try:
        with open(filepath, 'rb') as f:
            files = {'file': f}
            params = {
                'api_key': SAUCENAO_API_KEY,
                'output_type': 2,
                'numres': 5
            }
            
            response = requests.post(
                'https://saucenao.com/search.php',
                files=files,
                params=params,
                timeout=15
            )
            
            if response.status_code != 200:
                return None, response.json() if response.content else None
            
            data = response.json()
            
            booru_posts = []
            for result in data.get('results', []):
                similarity = float(result['header']['similarity'])
                if similarity < 70:
                    continue
                
                urls = result['data'].get('ext_urls', [])
                for url in urls:
                    if 'danbooru.donmai.us/posts/' in url:
                        post_id = url.split('/posts/')[-1].split('?')[0]
                        booru_posts.append(('danbooru', post_id))
                    elif 'e621.net/posts/' in url:
                        post_id = url.split('/posts/')[-1].split('?')[0]
                        booru_posts.append(('e621', post_id))
                    elif 'gelbooru.com' in url and 'id=' in url:
                        post_id = url.split('id=')[-1].split('&')[0]
                        booru_posts.append(('gelbooru', post_id))
                    elif 'yande.re' in url and '/post/show/' in url:
                        post_id = url.split('/post/show/')[-1].split('?')[0]
                        booru_posts.append(('yandere', post_id))
            
            return booru_posts, data
            
    except Exception as e:
        print(f"SauceNao error: {e}")
        return None, None

def fetch_by_post_id(source, post_id):
    """Fetch metadata for a specific post ID from a booru"""
    try:
        if source == "danbooru":
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "tag_string": data.get("tag_string", ""),
                    "full_data": data,
                    "source": "danbooru"
                }
        elif source == "e621":
            headers = {"User-Agent": "TagFetcher/1.0 (by YourUsername on e621)"}
            url = f"https://e621.net/posts/{post_id}.json"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()["post"]
                tags_data = data["tags"]
                all_tags = []
                for category in tags_data.values():
                    all_tags.extend(category)
                return {
                    "tag_string": " ".join(all_tags),
                    "full_data": data,
                    "source": "e621"
                }
        elif source == "gelbooru":
            url = f"https://gelbooru.com/index.php?page=dapi&s=post&q=index&json=1&id={post_id}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and "post" in response.json():
                data = response.json()["post"][0]
                return {
                    "tag_string": data.get("tags", ""),
                    "full_data": data,
                    "source": "gelbooru"
                }
        elif source == "yandere":
            url = f"https://yande.re/post.json?tags=id:{post_id}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200 and response.json():
                data = response.json()[0]
                return {
                    "tag_string": data.get("tags", ""),
                    "full_data": data,
                    "source": "yandere"
                }
    except Exception as e:
        print(f"Error fetching {source} post {post_id}: {e}")
        return None
    
    return None

def merge_tag_data(all_results):
    """Merge tag data from multiple sources, prioritizing Danbooru/e621 for categories"""
    # Priority: danbooru > e621 > gelbooru > yandere > local_tagger
    priority_order = ["danbooru", "e621", "gelbooru", "yandere", "local_tagger"]
    
    # Find the highest priority source
    primary_source = None
    primary_source_name = None
    for source_name in priority_order:
        if source_name in all_results:
            primary_source = all_results[source_name]["full_data"]
            primary_source_name = source_name
            break
    
    if not primary_source:
        return None
    
    # Combine all tags
    all_tags = set()
    for result in all_results.values():
        all_tags.update(result["tag_string"].split())
    
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
    elif primary_source_name == "camie_tagger":
        tags_dict["character"] = primary_source.get("tag_string_character", "")
        tags_dict["copyright"] = primary_source.get("tag_string_copyright", "")
        tags_dict["artist"] = primary_source.get("tag_string_artist", "")
        tags_dict["meta"] = primary_source.get("tag_string_meta", "")
        tags_dict["general"] = primary_source.get("tag_string_general", "")
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
        "has_children": has_children
    }

def load_local_tagger():
    """Load Local Tagger model and metadata"""
    if not ONNX_AVAILABLE:
        return None, None
    
    if not os.path.exists(LOCAL_TAGGER_MODEL_PATH) or not os.path.exists(LOCAL_TAGGER_METADATA_PATH):
        print("Local Tagger model files not found. Skipping AI tagging.")
        return None, None
    
    try:
        # Load ONNX session
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        session = ort.InferenceSession(CAMIE_MODEL_PATH, providers=providers)
        
        # Load metadata (tag mappings)
        with open(LOCAL_TAGGER_METADATA_PATH, 'r') as f:
            metadata = json.load(f)
        
        print(f"Local Tagger loaded with {len(metadata['tags'])} tags")
        return session, metadata
    except Exception as e:
        print(f"Failed to load Local Tagger: {e}")
        return None, None

def preprocess_image_for_camie(image_path, target_size=512):
    """Preprocess image for Local Tagger inference"""
    img = Image.open(image_path).convert('RGB')
    
    # Resize maintaining aspect ratio
    img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
    
    # Pad to square
    new_img = Image.new('RGB', (target_size, target_size), (255, 255, 255))
    paste_x = (target_size - img.width) // 2
    paste_y = (target_size - img.height) // 2
    new_img.paste(img, (paste_x, paste_y))
    
    # Convert to numpy array and normalize
    img_array = np.array(new_img).astype(np.float32) / 255.0
    
    # Transpose to (C, H, W) and add batch dimension
    img_array = np.transpose(img_array, (2, 0, 1))
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array

def tag_with_camie(session, metadata, filepath):
    """Tag an image using Local Tagger"""
    if not session or not metadata:
        return None
    
    try:
        # Preprocess image
        img_tensor = preprocess_image_for_camie(filepath, CAMIE_TARGET_SIZE)
        
        # Run inference
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: img_tensor})
        
        # Process predictions
        predictions = outputs[0][0]  # Remove batch dimension
        
        # Apply sigmoid to get probabilities
        probs = 1 / (1 + np.exp(-predictions))
        
        # Get tags above threshold
        tags_by_category = {
            "general": [],
            "character": [],
            "copyright": [],
            "artist": [],
            "meta": [],
            "rating": []
        }
        
        tag_list = metadata['tags']
        
        for idx, prob in enumerate(probs):
            if prob >= CAMIE_THRESHOLD:
                tag_info = tag_list[idx]
                tag_name = tag_info['name']
                category = tag_info['category']
                
                if category == 0:
                    tags_by_category["general"].append(tag_name)
                elif category == 1:
                    tags_by_category["artist"].append(tag_name)
                elif category == 3:
                    tags_by_category["copyright"].append(tag_name)
                elif category == 4:
                    tags_by_category["character"].append(tag_name)
                elif category == 5:
                    tags_by_category["meta"].append(tag_name)
                elif category == 9:
                    tags_by_category["rating"].append(tag_name)
        
        # Combine all tags
        all_tags = (
            tags_by_category["general"] +
            tags_by_category["character"] +
            tags_by_category["copyright"] +
            tags_by_category["artist"] +
            tags_by_category["meta"]
        )
        
        return {
            "tag_string": " ".join(all_tags),
            "full_data": {
                "tags": " ".join(all_tags),
                "tag_string_character": " ".join(tags_by_category["character"]),
                "tag_string_copyright": " ".join(tags_by_category["copyright"]),
                "tag_string_artist": " ".join(tags_by_category["artist"]),
                "tag_string_general": " ".join(tags_by_category["general"]),
                "tag_string_meta": " ".join(tags_by_category["meta"]),
                "rating": tags_by_category["rating"][0] if tags_by_category["rating"] else None,
                "parent_id": None,
                "has_children": False,
                "source": None
            },
            "source": "camie_tagger"
        }
        
    except Exception as e:
        print(f"Local Tagger error for {filepath}: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    if not os.path.isdir(IMAGE_DIRECTORY):
        print(f"Error: Directory not found at '{IMAGE_DIRECTORY}'")
        return

    try:
        with open(TAGS_FILE, "r") as f:
            all_tags = json.load(f)
    except FileNotFoundError:
        all_tags = {}

    # Load Local Tagger at startup
    local_session, local_metadata = load_local_tagger()

    image_files = [
        os.path.join(root, file)
        for root, _, files in os.walk(IMAGE_DIRECTORY)
        for file in files
        if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))
    ]
    
    # Rerun files that were previously marked as "not_found"
    images_to_process = [
        f for f in image_files
        if os.path.relpath(f, IMAGE_DIRECTORY) not in all_tags or 
           all_tags.get(os.path.relpath(f, IMAGE_DIRECTORY)) == "not_found"
    ]
    
    if not images_to_process:
        print("All images have already been processed.")
        return

    # NEW: Build MD5 index once for batch checking
    print("Building MD5 index for deduplication...")
    md5_index = build_md5_index()
    
    # NEW: Check each image for duplicates before processing
    filtered_images = []
    duplicates_removed = 0
    
    for img_path in images_to_process:
        is_dup, existing_path, md5 = is_duplicate(img_path, md5_index)
        
        if is_dup:
            print(f"Duplicate detected: {img_path}")
            print(f"  → matches {existing_path} (MD5: {md5})")
            remove_duplicate(img_path)
            duplicates_removed += 1
        else:
            filtered_images.append(img_path)
    
    if duplicates_removed > 0:
        print(f"Removed {duplicates_removed} duplicate images")
    
    # Replace unprocessed with filtered_images
    images_to_process = filtered_images
    
    if not images_to_process:
        print("No new images to process.")
        return

    saucenao_count = 0
    camie_count = 0
    
    for filepath in tqdm(images_to_process, desc="Finding Tags"):
        md5 = get_md5(filepath)
        all_results = search_all_sources(md5)
        relative_path = os.path.relpath(filepath, IMAGE_DIRECTORY)
        
        used_saucenao = False
        saucenao_full_response = None
        used_camie = False
        
        if not all_results and SAUCENAO_API_KEY:
            print(f"\nMD5 lookup failed for {relative_path}, trying SauceNao...")
            used_saucenao = True
            
            booru_posts, saucenao_full_response = search_saucenao(filepath)
            
            if booru_posts:
                all_results = {}
                for source, post_id in booru_posts:
                    result = fetch_by_post_id(source, post_id)
                    if result:
                        all_results[source] = result
                
                if all_results:
                    print(f"Found via SauceNao: {list(all_results.keys())}")
                
                saucenao_count += 1
                time.sleep(5)
        
        # Try Local Tagger if all else failed
        if not all_results and camie_session:
            print(f"\nAll sources failed for {relative_path}, using Local Tagger...")
            used_camie = True
            tagger_result = tag_with_camie(camie_session, camie_metadata, filepath)
            if tagger_result:
                all_results = {"camie_tagger": tagger_result}
                print(f"Tagged with Local Tagger: {len(tagger_result['tag_string'].split())} tags")
                local_count += 1
        
        if all_results:
            merged_data = merge_tag_data(all_results)
            
            all_tags[relative_path] = {
                "tags": merged_data["tags"],
                "tags_character": merged_data["tags_character"],
                "tags_copyright": merged_data["tags_copyright"],
                "tags_artist": merged_data["tags_artist"],
                "tags_meta": merged_data["tags_meta"],
                "tags_general": merged_data["tags_general"],
                "id": merged_data["id"],
                "parent_id": merged_data["parent_id"],
                "has_children": merged_data["has_children"],
                "md5": md5,
                "sources": list(all_results.keys()),
                "saucenao_lookup": used_saucenao,
                "camie_tagger_lookup": used_camie
            }
            
            metadata_file = os.path.join(METADATA_DIR, f"{md5}.json")
            metadata_content = {
                "md5": md5,
                "relative_path": relative_path,
                "saucenao_lookup": used_saucenao,
                "saucenao_response": saucenao_full_response,
                "camie_tagger_lookup": used_camie,
                "sources": {}
            }
            
            for source, result in all_results.items():
                metadata_content["sources"][source] = result["full_data"]
            
            with open(metadata_file, "w") as f:
                json.dump(metadata_content, f, indent=2)
        else:
            all_tags[relative_path] = "not_found"
        
        ensure_thumbnail(filepath)

        if len(all_tags) % 10 == 0:
            with open(TAGS_FILE, "w") as f:
                json.dump(all_tags, f, indent=4)

        time.sleep(0.5)

    with open(TAGS_FILE, "w") as f:
        json.dump(all_tags, f, indent=4)

    print(f"\nFinished! Tags saved to {TAGS_FILE}, metadata in {METADATA_DIR}/")
    if saucenao_count > 0:
        print(f"Used SauceNao for {saucenao_count} images")
    if camie_count > 0:
        print(f"Used Local Tagger for {camie_count} images")

if __name__ == "__main__":
    main()
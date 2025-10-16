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
import numpy as np

# Try to import onnxruntime (optional dependency)
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    print("Warning: onnxruntime not installed. CamieTagger will not be available.")
    print("Install with: pip install onnxruntime-gpu (or onnxruntime for CPU)")

THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000

IMAGE_DIRECTORY = "./static/images" 
TAGS_FILE = "./tags.json"
METADATA_DIR = "./metadata"

SAUCENAO_API_KEY = os.environ.get('SAUCENAO_API_KEY', '')

# CamieTagger configuration
CAMIE_MODEL_PATH = "./models/CamieTagger/camie-tagger-v2.onnx"
CAMIE_METADATA_PATH = "./models/CamieTagger/metadata.json"
CAMIE_THRESHOLD = 0.5
CAMIE_TARGET_SIZE = 512  # Fixed to 512

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

def extract_tag_data(result):
    """Extract categorized tags and metadata from API result"""
    data = result["full_data"]
    source = result["source"]
    
    tags_dict = {
        "all": result["tag_string"],
        "character": "",
        "copyright": "",
        "artist": "",
        "meta": "",
        "general": ""
    }
    
    parent_id = None
    has_children = False
    
    if source == "danbooru":
        tags_dict["character"] = data.get("tag_string_character", "")
        tags_dict["copyright"] = data.get("tag_string_copyright", "")
        tags_dict["artist"] = data.get("tag_string_artist", "")
        tags_dict["meta"] = data.get("tag_string_meta", "")
        tags_dict["general"] = data.get("tag_string_general", "")
        parent_id = data.get("parent_id")
        has_children = data.get("has_children", False)
    elif source == "e621":
        tag_data = data.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        relationships = data.get("relationships", {})
        parent_id = relationships.get("parent_id")
        has_children = relationships.get("has_children", False)
    elif source == "camie_tagger":
        # CamieTagger already has the proper format
        tags_dict["character"] = data.get("tag_string_character", "")
        tags_dict["copyright"] = data.get("tag_string_copyright", "")
        tags_dict["artist"] = data.get("tag_string_artist", "")
        tags_dict["meta"] = data.get("tag_string_meta", "")
        tags_dict["general"] = data.get("tag_string_general", "")
        parent_id = data.get("parent_id")
        has_children = data.get("has_children", False)
    else:
        parent_id = data.get("parent_id")
        has_children = data.get("has_children", False)
    
    return {
        "tags": tags_dict,
        "id": data.get("id"),
        "parent_id": parent_id,
        "has_children": has_children
    }

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
                    elif 'yande.re/post/show/' in url:
                        post_id = url.split('/show/')[-1].split('/')[0]
                        booru_posts.append(('yandere', post_id))
            
            return (booru_posts if booru_posts else None), data
            
    except Exception as e:
        print(f"SauceNao error: {e}")
        return None, None

def fetch_by_post_id(source, post_id):
    """Fetch metadata directly by post ID"""
    try:
        if source == 'danbooru':
            url = f"https://danbooru.donmai.us/posts/{post_id}.json"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "tag_string": data.get("tag_string", ""),
                    "full_data": data,
                    "source": "danbooru"
                }
        
        elif source == 'e621':
            headers = {"User-Agent": "TagFetcher/1.0 (by YourUsername on e621)"}
            url = f"https://e621.net/posts/{post_id}.json"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()['post']
                tags_data = data["tags"]
                all_tags = []
                for category in tags_data.values():
                    all_tags.extend(category)
                return {
                    "tag_string": " ".join(all_tags),
                    "full_data": data,
                    "source": "e621"
                }
        
        elif source == 'gelbooru':
            # Gelbooru API is unreliable - skip it for now
            # Their API requires authentication and doesn't support direct post ID lookup
            print(f"Skipping Gelbooru post {post_id} - API requires authentication")
            return None
        
        elif source == 'yandere':
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
        import traceback
        traceback.print_exc()
        return None
    
    return None
    
def merge_tag_data(all_results):
    """Merge tag data from multiple sources, preferring sources with categorized tags"""
    if not all_results:
        return None
    
    preferred_sources = ["danbooru", "e621", "camie_tagger", "gelbooru", "yandere"]
    primary_result = None
    
    for source in preferred_sources:
        if source in all_results:
            primary_result = all_results[source]
            break
    
    if not primary_result:
        primary_result = list(all_results.values())[0]
    
    all_tags = set()
    for result in all_results.values():
        all_tags.update(result["tag_string"].split())
    
    extracted = extract_tag_data(primary_result)
    extracted["tags"]["all"] = " ".join(sorted(all_tags))
    
    return extracted

# CamieTagger functions
def load_camie_tagger():
    """Initialize CamieTagger model (call once at startup)"""
    if not ONNX_AVAILABLE:
        return None, None
    
    if not os.path.exists(CAMIE_MODEL_PATH) or not os.path.exists(CAMIE_METADATA_PATH):
        print(f"CamieTagger files not found at {CAMIE_MODEL_PATH}")
        return None, None
    
    try:
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        session = ort.InferenceSession(CAMIE_MODEL_PATH, providers=providers)
        
        with open(CAMIE_METADATA_PATH, 'r') as f:
            metadata = json.load(f)
        
        provider = session.get_providers()[0]
        print(f"CamieTagger loaded successfully. Using: {provider}")
        return session, metadata
    except Exception as e:
        print(f"Warning: Could not load CamieTagger: {e}")
        return None, None

def preprocess_image_for_camie(filepath, image_size=512):
    """Preprocess image for CamieTagger with proper aspect ratio handling"""
    try:
        with Image.open(filepath) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P', 'LA'):
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode in ('RGBA', 'LA'):
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get dimensions and calculate aspect ratio
            width, height = img.size
            aspect_ratio = width / height
            
            # Resize maintaining aspect ratio
            if aspect_ratio > 1:
                new_width = image_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = image_size
                new_width = int(new_height * aspect_ratio)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create padded image (white background)
            padded = Image.new('RGB', (image_size, image_size), (255, 255, 255))
            paste_x = (image_size - new_width) // 2
            paste_y = (image_size - new_height) // 2
            padded.paste(img, (paste_x, paste_y))
            
            # Convert to numpy array and normalize
            img_array = np.array(padded).astype(np.float32) / 255.0
            img_array = np.transpose(img_array, (2, 0, 1))  # HWC to CHW
            img_array = np.expand_dims(img_array, axis=0)   # Add batch dimension
            
            return img_array
            
    except Exception as e:
        raise Exception(f"Error preprocessing {filepath}: {e}")

def tag_with_camie(session, metadata, filepath):
    """Run CamieTagger inference on an image"""
    try:
        img_array = preprocess_image_for_camie(filepath, CAMIE_TARGET_SIZE)
        
        input_name = session.get_inputs()[0].name
        output = session.run(None, {input_name: img_array})[0][0]
        
        # Extract metadata structure properly
        try:
            dataset_info = metadata['dataset_info']
            tag_mapping = dataset_info['tag_mapping']
            idx_to_tag = tag_mapping['idx_to_tag']
            tag_to_category = tag_mapping['tag_to_category']
        except KeyError:
            # Fallback to old structure
            idx_to_tag = metadata.get("tags", {})
            tag_to_category = metadata.get("tag_type", {})
        
        # Parse results
        tags_by_category = {
            "rating": [],
            "copyright": [],
            "character": [],
            "artist": [],
            "general": [],
            "meta": []
        }
        
        for idx, prob in enumerate(output):
            if prob >= CAMIE_THRESHOLD:
                idx_str = str(idx)
                tag_name = idx_to_tag.get(idx_str)
                
                if not tag_name:
                    continue
                
                # Determine category
                if isinstance(tag_to_category, dict):
                    if idx_str in tag_to_category:
                        tag_type = tag_to_category[idx_str]
                    else:
                        # Try using tag_name as key
                        category_name = tag_to_category.get(tag_name, "general")
                        # Map string category to number if needed
                        category_map_reverse = {
                            "general": 0,
                            "character": 1,
                            "copyright": 2,
                            "artist": 3,
                            "meta": 4,
                            "rating": 5
                        }
                        tag_type = category_map_reverse.get(category_name, 0)
                else:
                    tag_type = 0
                
                category_map = {
                    0: "general",
                    1: "character", 
                    2: "copyright",
                    3: "artist",
                    4: "meta",
                    5: "rating"
                }
                
                category = category_map.get(tag_type, "general")
                
                if category == "rating":
                    # Extract rating from tag_name (e.g., "rating explicit" -> "explicit")
                    rating = tag_name.replace("rating ", "").replace("rating:", "").strip()
                    tags_by_category["rating"].append(rating)
                else:
                    tags_by_category[category].append(tag_name)
        
        # Build result structure matching booru format
        all_tags = []
        for category in ["character", "copyright", "artist", "general", "meta"]:
            all_tags.extend(tags_by_category[category])
        
        return {
            "tag_string": " ".join(all_tags),
            "full_data": {
                "id": None,
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
        print(f"CamieTagger error for {filepath}: {e}")
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

    # Load CamieTagger at startup
    camie_session, camie_metadata = load_camie_tagger()

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
        
        # Try CamieTagger if all else failed
        if not all_results and camie_session:
            print(f"\nAll sources failed for {relative_path}, using CamieTagger...")
            used_camie = True
            camie_result = tag_with_camie(camie_session, camie_metadata, filepath)
            if camie_result:
                all_results = {"camie_tagger": camie_result}
                print(f"Tagged with CamieTagger: {len(camie_result['tag_string'].split())} tags")
                camie_count += 1
        
        if all_results:
            merged_data = merge_tag_data(all_results)
            
            all_tags[relative_path] = {
                "tags": merged_data["tags"]["all"],
                "tags_character": merged_data["tags"]["character"],
                "tags_copyright": merged_data["tags"]["copyright"],
                "tags_artist": merged_data["tags"]["artist"],
                "tags_meta": merged_data["tags"]["meta"],
                "tags_general": merged_data["tags"]["general"],
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
        
        rebuild_tags()

        time.sleep(0.5)

    with open(TAGS_FILE, "w") as f:
        json.dump(all_tags, f, indent=4)

    print(f"\nFinished! Tags saved to {TAGS_FILE}, metadata in {METADATA_DIR}/")
    if saucenao_count > 0:
        print(f"Used SauceNao for {saucenao_count} images")
    if camie_count > 0:
        print(f"Used CamieTagger for {camie_count} images")

if __name__ == "__main__":
    main()
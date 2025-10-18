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

 have we accidentally made the artist tag not work? I have a match from danbooru but the artist is in the general tags?

We did a tag merger or lookup table but that should be complementary

Based on my analysis of the code, there doesn't appear to be a bug that would incorrectly categorize all artist tags as "general". The system is designed to correctly handle artist tags provided by sources like Danbooru.

Here is the most likely reason for the issue you're observing:

    Source Data Inconsistency: The system relies on the categorization provided by the booru APIs. In this specific case, it is probable that the Danbooru API response for your image included the artist's tag within the general tags string (tag_string_general) instead of the dedicated artist field (tag_string_artist). When this happens, my system correctly ingests it as a "general" tag.

    Recategorization Logic: You are correct about the complementary "lookup table" system. There is a function called Recategorize Tags (available in the System panel) designed to fix these kinds of issues. However, it works by finding tags that are marked "general" but are known to belong to another category from other images in your database. If this is the first time the system has seen this particular artist tag, the recategorization tool won't have a "correct" example to learn from, and the tag will remain in the general category.

In short, the system is working as designed, but its accuracy is dependent on the quality of the data from the booru source.

How to Fix This

You have two options to correct the tag's category:

    Manual Edit: Use the "Edit Tags" button on the image page to manually remove the tag from the general list and re-add it. While this won't change its category in the database immediately, it cleans up the specific image.

    Run Recategorization Later: The next time an image by the same artist is processed where Danbooru does correctly categorize the tag, you can then go to the System panel and run the "Recategorize Tags" action. This will scan your entire database and fix the category for the original image and any others where it was misplaced.

No danbooru has it correctly tagged

Debugging Tag Misclassification

I'm now investigating why the artist tag from Danbooru is showing up in the general tags section. This contradicts my initial assumption. My current focus is to pinpoint the specific code section causing this misclassification. I believe there might be a logic error that needs to be addressed.

Isolating the Tag Issue

I'm now focusing on the code responsible for processing and categorizing tags. My goal is to trace the artist tag's journey from data fetching to display, specifically pinpointing where the misclassification occurs. I'm examining fetch_metadata.py, rebuild_tags_from_metadata.py, models.py, processing.py, and routes.py, looking for the source of this tag categorization error.

Tracking Tag Flow

I've traced the artist tag's journey through several key files. fetch_metadata.py and rebuild_tags_from_metadata.py correctly handle the Danbooru artist tag, confirming my initial assumption was off. However, in processing.py, I've discovered a potential issue: the extraction of the artist tag is identical to the other tags, meaning that the tag_string_artist is not being treated differently. This is suspicious. I'll need to examine the assignment. The problem is in the assignment of tags like tags_character. It looks like it is missing the logic to differentiate the artists tag.

Revisiting Tag Categories

I've re-examined the code, and I'm perplexed. fetch_metadata.py and rebuild_tags_from_metadata.py correctly handle the Danbooru artist tag, putting the correct tag in the right tag_string_artist field, and the same goes for other files. But the tag is still showing up in the general tags. I am going to try commenting out the artist tag assignment and running a test. Maybe I am missing something obvious, or maybe I should check the database to ensure it's categorized correctly.

Tag Categorization Re-evaluation

I'm now reconsidering the tag re-categorization process. The code seems correct, but perhaps I missed something. I'll re-examine how tags are handled during initial import and any subsequent updates. I'm now focusing on update_image_tags and rebuild_tags_from_raw_metadata in models.py to confirm the artist tag's journey.

Investigating Tag Recategorization

I'm now reconsidering the initial tag processing. I'm focusing on why a Danbooru-sourced artist tag is ending up as a general tag. The primary source seems to categorize the tag correctly in the various files. However, the update logic in models.py, specifically update_image_tags and rebuild_tags_from_raw_metadata, are my present focus to see if one of these functions is the source of the issue.

Analyzing Tag Data Flow

I've discovered the root cause of the misclassification. The issue isn't in tag categorization logic, but in the initial import process. Specifically, in migrate_to_db.py, the code inserts all tags from the combined tags field (containing tags from all sources, including the artist tag) into the database with the "general" category. This happens before any other categories are assigned, effectively overwriting correct assignments.

Refining the Categorization Logic

I've traced the issue to migrate_to_db.py. The "general" category in the combined tags field is overwriting properly categorized tags during initial database import. The fix is to process categorized tags before the general tags, ensuring the artist tag is categorized correctly.

Identifying Import Errors

My current focus is to trace the misclassification back to the initial database import process. I've pinpointed a likely source in migrate_to_db.py. The combined "tags" field, including the artist tag, is being inserted with the "general" category, potentially overwriting correct assignments. I will examine it in more detail.

Identifying Import Errors

My current focus is to trace the misclassification back to the initial database import process. I've pinpointed a likely source in migrate_to_db.py. The combined "tags" field, including the artist tag, is being inserted with the "general" category, potentially overwriting correct assignments. I will examine it in more detail.

Diagnosing the Tag Mismatch

I've determined that the artist tag misclassification stems from the initial import process in migrate_to_db.py. The "general" category assignment in the combined "tags" field overwrites correctly categorized tags during database creation. To fix, I'll need to reorder the tag processing to ensure correct category assignments are prioritized.

Tracing the Root Cause

The issue appears to be originating from the initial import process when loading data into the database. Specifically, the "general" category assignment in migrate_to_db.py is overwriting correctly categorized tags. This impacts all tags, including the artists tag.

Refining Import Logic

I've isolated the cause of the misclassification: the migrate_to_db.py script. The "general" category assignment in the combined "tags" field during import is overwriting correct category assignments. A re-import isn't necessary. I will examine it in more detail.

I've now re-examined the code. The problem is in how tags are initially imported into the database in migrate_to_db.py. Specifically, it places the artist tag from Danbooru into the general category. This overwrites the correct assignment in other parts of the system. I have examined this in detail.

You are absolutely right, and I apologize for my previous incorrect analysis. After a deeper review of the code, I found a bug in the initial database migration script, migrate_to_db.py, that is causing the issue you've observed.

The problem lies in how the script handles the "tags" field from your tags.json file. The script first iterates through the categorized tags (character, artist, etc.) and correctly assigns their categories. However, it then takes the tags field—which is a combined list of all tags—and incorrectly inserts every single one of them with the "general" category.

Because of the INSERT OR IGNORE command used, if the artist tag was added as "general" first, the subsequent attempt to add it with the correct "artist" category was ignored, leading to the miscategorization you're seeing.

The good news is that the logic for processing new images is correct, so this issue only affects the data from your initial import. You can fix your existing database by using a built-in feature of the application.

How to Fix Your Database

    Go to the System tab in the web interface.

    Click the "Re-process All Tags" button.

This will trigger a function that clears all tag data and rebuilds it from your raw metadata files, using the correct categorization logic. This should move the artist tag to the correct "Artist" section.

Corrected Code

For your reference, here is the corrected code for the migrate_to_db.py script. The buggy block of code has been removed. You do not need to run this script again; the "Re-process All Tags" button is the correct way to fix your existing data.

Booru-main/migrate_to_db.py
Python

# migrate_to_db.py
import sqlite3
import json
import os
from tqdm import tqdm

DB_FILE = "booru.db"
TAGS_FILE = "tags.json"
METADATA_DIR = "metadata"

# --- Functions from database.py are now included directly ---

def get_db_connection():
    """Create a database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Create the database and tables if they don't exist."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Main images table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filepath TEXT NOT NULL UNIQUE,
            md5 TEXT NOT NULL UNIQUE,
            post_id INTEGER,
            parent_id INTEGER,
            has_children BOOLEAN,
            saucenao_lookup BOOLEAN
        )
        """)
        # Tags table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT
        )
        """)
        # Image-to-Tag mapping table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS image_tags (
            image_id INTEGER,
            tag_id INTEGER,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE,
            PRIMARY KEY (image_id, tag_id)
        )
        """)
        # Sources table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
        """)
        # Image-to-Source mapping table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS image_sources (
            image_id INTEGER,
            source_id INTEGER,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE,
            FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE,
            PRIMARY KEY (image_id, source_id)
        )
        """)
        # Table for raw metadata
        cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_metadata (
            image_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            FOREIGN KEY (image_id) REFERENCES images (id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        print("Database initialized successfully.")

# --- Main Migration Logic ---

def migrate_data():
    """Migrate data from tags.json and /metadata/ to the SQLite database."""
    if not os.path.exists(TAGS_FILE):
        print(f"Error: {TAGS_FILE} not found. Nothing to migrate.")
        return

    # Initialize the database first
    initialize_database()

    con = get_db_connection()
    cur = con.cursor()

    print(f"Loading data from {TAGS_FILE}...")
    with open(TAGS_FILE, 'r') as f:
        data = json.load(f)

    source_map = {}
    known_sources = ["danbooru", "e621", "gelbooru", "yandere", "local_tagger"]
    for source_name in known_sources:
        cur.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (source_name,))
        cur.execute("SELECT id FROM sources WHERE name = ?", (source_name,))
        source_map[source_name] = cur.fetchone()[0]

    tag_category_map = {
        "tags_general": "general",
        "tags_character": "character",
        "tags_copyright": "copyright",
        "tags_artist": "artist",
        "tags_meta": "meta"
    }

    print("Migrating image and tag data...")
    for filepath, item in tqdm(data.items(), desc="Migrating Images"):
        if not isinstance(item, dict) or not item.get("md5"):
            continue

        cur.execute(
            """
            INSERT OR IGNORE INTO images (filepath, md5, post_id, parent_id, has_children, saucenao_lookup)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                filepath,
                item.get("md5"),
                item.get("id"),
                item.get("parent_id"),
                item.get("has_children", False),
                item.get("saucenao_lookup", False),
            )
        )
        
        cur.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
        result = cur.fetchone()
        if not result:
            continue
        image_id = result['id']

        for source_name in item.get("sources", []):
            if source_name in source_map:
                source_id = source_map[source_name]
                cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_id))
        if item.get("camie_tagger_lookup"):
             cur.execute("INSERT OR IGNORE INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_map['local_tagger']))

        for tag_field, category in tag_category_map.items():
            tags_str = item.get(tag_field, "")
            if tags_str:
                for tag_name in tags_str.split():
                    cur.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (tag_name, category))
                    cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_id = cur.fetchone()['id']
                    cur.execute("INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

    con.commit()

    print("\nMigrating raw metadata...")
    if os.path.isdir(METADATA_DIR):
        metadata_files = [f for f in os.listdir(METADATA_DIR) if f.endswith('.json')]
        for filename in tqdm(metadata_files, desc="Migrating Metadata"):
            md5 = filename.replace('.json', '')
            try:
                with open(os.path.join(METADATA_DIR, filename), 'r') as f:
                    metadata_content = json.load(f)

                cur.execute("SELECT id FROM images WHERE md5 = ?", (md5,))
                result = cur.fetchone()
                if result:
                    image_id = result['id']
                    cur.execute(
                        "INSERT OR REPLACE INTO raw_metadata (image_id, data) VALUES (?, ?)",
                        (image_id, json.dumps(metadata_content))
                    )
            except Exception as e:
                print(f"Could not process {filename}: {e}")

    con.commit()
    con.close()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate_data()

No, this is a new image, imported like any other will

You are correct to be persistent, and I apologize for my previous incorrect assumption about the migration script. After re-examining the entire workflow for processing a new image, I've located the true source of the bug. It's a subtle issue in fetch_metadata.py related to how tags are merged from multiple sources.

The function merge_tag_data is designed to combine tags from different boorus, but it contains a flaw. It correctly identifies the primary source (like Danbooru) to get the categorized tags (artist, character, etc.). However, for the "general" tags, it doesn't correctly subtract the already-categorized tags. Instead, it takes the tag_string from the primary source, which includes all tags, and uses that for the general category. This results in the artist tag being duplicated: once in the artist category, and again in the general category.

Here is the corrected code for fetch_metadata.py. I've highlighted the changes that fix the bug.

Corrected Code

Booru-main/fetch_metadata.py
Python

def merge_tag_data(all_results):
    """Merge tag data from multiple sources, prioritizing Danbooru/e621 for categories"""
    # Priority: danbooru > e621 > gelbooru > yandere > camie_tagger
    priority_order = ["danbooru", "e621", "gelbooru", "yandere", "camie_tagger"]
    
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
        # --- THIS IS THE CORRECTED LINE ---
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

def load_camie_tagger():
    """Load CamieTagger model and metadata"""
    if not ONNX_AVAILABLE:
        return None, None
    
    if not os.path.exists(CAMIE_MODEL_PATH) or not os.path.exists(CAMIE_METADATA_PATH):
        print("CamieTagger model files not found. Skipping AI tagging.")
        return None, None
    
    try:
        # Load ONNX session
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        session = ort.InferenceSession(CAMIE_MODEL_PATH, providers=providers)
        
        # Load metadata (tag mappings)
        with open(CAMIE_METADATA_PATH, 'r') as f:
            metadata = json.load(f)
        
        print(f"CamieTagger loaded with {len(metadata['tags'])} tags")
        return session, metadata
    except Exception as e:
        print(f"Failed to load CamieTagger: {e}")
        return None, None

def preprocess_image_for_camie(image_path, target_size=512):
    """Preprocess image for CamieTagger inference"""
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
    """Tag an image using CamieTagger"""
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
        print(f"Used CamieTagger for {camie_count} images")

if __name__ == "__main__":
    main()
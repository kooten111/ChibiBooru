from dotenv import load_dotenv
load_dotenv(override=True)

import onnxruntime
onnxruntime.preload_dlls()

import os
import json
import random
import threading
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, render_template, request, url_for, jsonify
from utils import get_thumbnail_path, load_metadata, get_related_images
from utils.deduplication import is_duplicate, remove_duplicate

app = Flask(__name__)

# Global data structures
raw_data = {}
tag_counts = {}
id_to_path = {}
image_data = []
data_lock = threading.Lock()

# Optional: Set a reload secret key for security
RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')

# Monitoring configuration
MONITOR_ENABLED = True
MONITOR_INTERVAL = 300  # seconds (5 minutes)
monitor_thread = None
monitor_status = {
    "running": False,
    "last_check": None,
    "last_scan_found": 0,
    "total_processed": 0
}

def looks_like_filename(query):
    """Check if query looks like a filename"""
    # Check for common image extensions
    if any(query.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        return True
    # Check for typical booru filename patterns (numbers with underscores)
    import re
    if re.match(r'^\d+_p\d+', query):  # Pixiv pattern
        return True
    if re.match(r'^[a-f0-9]{32}', query):  # MD5 pattern
        return True
    return False

def get_image_md5(filepath):
    """Calculate MD5 hash of an image file"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def find_unprocessed_images():
    """Find images that don't have metadata yet"""
    if not os.path.isdir("./static/images"):
        return []
    
    unprocessed = []
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    
    for root, _, files in os.walk("./static/images"):
        for file in files:
            if not file.lower().endswith(image_extensions):
                continue
            
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, "./static/images")
            
            # Check if in tags.json
            if rel_path not in raw_data:
                unprocessed.append(filepath)
            # Check if marked as not_found
            elif raw_data[rel_path] == "not_found":
                unprocessed.append(filepath)
    
    return unprocessed

def process_new_images():
    """Process new images by calling fetch_metadata"""
    try:
        import fetch_metadata
        fetch_metadata.main()
        return True
    except Exception as e:
        print(f"Error processing images: {e}")
        return False

def monitor_images():
    """Background thread to monitor for new images"""
    global monitor_status
    
    while monitor_status["running"]:
        try:
            print("Checking for new images...")
            monitor_status["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            unprocessed = find_unprocessed_images()
            
            if unprocessed:
                print(f"Found {len(unprocessed)} new images, processing...")
                monitor_status["last_scan_found"] = len(unprocessed)
                
                if process_new_images():
                    monitor_status["total_processed"] += len(unprocessed)
                    print("Processing complete, reloading data...")
                    load_data()
            else:
                print("No new images found")
                monitor_status["last_scan_found"] = 0
            
        except Exception as e:
            print(f"Monitor error: {e}")
        
        # Sleep in small intervals to allow stopping
        for _ in range(MONITOR_INTERVAL):
            if not monitor_status["running"]:
                break
            time.sleep(1)

def start_monitor():
    """Start the background monitoring thread"""
    global monitor_thread, monitor_status
    
    if not MONITOR_ENABLED:
        return
    
    if monitor_thread and monitor_thread.is_alive():
        print("Monitor already running")
        return
    
    monitor_status["running"] = True
    monitor_thread = threading.Thread(target=monitor_images, daemon=True)
    monitor_thread.start()
    print("Image monitor started")

def stop_monitor():
    """Stop the background monitoring thread"""
    global monitor_status
    
    monitor_status["running"] = False
    print("Image monitor stopped")

def load_data():
    """Load or reload tags.json data"""
    global raw_data, tag_counts, id_to_path, image_data
    
    with data_lock:
        raw_data = {}
        tag_counts = {}
        id_to_path = {}
        image_data = []
        
        try:
            with open('tags.json', 'r') as f:
                raw_data = json.load(f)
                
                for path, data in raw_data.items():
                    if data == "not_found":
                        continue
                    
                    # Handle both old and new format
                    if isinstance(data, str):
                        tags = data
                        post_id = None
                        sources = []
                    else:
                        tags = data.get("tags", "")
                        post_id = data.get("id")
                        sources = data.get("sources", [])
                        
                        # Build ID to path mapping
                        if post_id:
                            id_to_path[post_id] = path
                    
                    image_data.append({
                        "path": f"images/{path}",
                        "tags": tags,
                        "sources": sources
                    })
                    
                    # Build tag counts
                    for tag in tags.split():
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
                        
            print(f"Loaded {len(raw_data)} images, {len(tag_counts)} unique tags")
            return True
        except FileNotFoundError:
            print("Error: tags.json not found!")
            return False
        except Exception as e:
            print(f"Error loading data: {e}")
            return False


def get_enhanced_stats():
    """Get detailed statistics about the collection"""
    total_images = len(raw_data)
    images_with_metadata = sum(1 for data in raw_data.values() if data != "not_found")
    images_without_metadata = total_images - images_with_metadata
    
    # Source breakdown
    source_counts = {}
    for data in raw_data.values():
        if isinstance(data, dict) and data != "not_found":
            sources = data.get("sources", [])
            for source in sources:
                source_name = source.split('.')[0] if '.' in source else source
                if source_name == "camie_tagger_lookup":
                    source_name = "camie_tagger"
                source_counts[source_name] = source_counts.get(source_name, 0) + 1

    
    # Tag statistics
    total_tags = len(tag_counts)
    tags_per_image = []
    category_counts = {"character": 0, "copyright": 0, "artist": 0, "meta": 0, "general": 0}
    
    for data in raw_data.values():
        if data == "not_found":
            continue
        if isinstance(data, dict):
            tags = data.get("tags", "").split()
            tags_per_image.append(len(tags))
            
            # Count categorized tags
            for cat in category_counts:
                cat_tags = data.get(f"tags_{cat}", "").split()
                category_counts[cat] += len(cat_tags)
        else:
            tags = data.split()
            tags_per_image.append(len(tags))
    
    avg_tags = sum(tags_per_image) / len(tags_per_image) if tags_per_image else 0
    
    # Top tags
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    
    # SauceNao/CamieTagger usage
    saucenao_count = sum(1 for data in raw_data.values() 
                         if isinstance(data, dict) and data.get("saucenao_lookup"))
    camie_count = sum(1 for data in raw_data.values() 
                      if isinstance(data, dict) and data.get("camie_tagger_lookup"))
    
    return {
        'total': total_images,
        'with_metadata': images_with_metadata,
        'without_metadata': images_without_metadata,
        'total_tags': total_tags,
        'avg_tags_per_image': round(avg_tags, 1),
        'source_breakdown': source_counts,
        'top_tags': top_tags,
        'category_counts': category_counts,
        'saucenao_used': saucenao_count,
        'camie_used': camie_count
    }

def _perform_search(search_query):
    """Helper function to perform a search and return results."""
    # Handle special queries that should not be shuffled
    if search_query == 'metadata:missing':
        search_results = [
            {"path": f"images/{path}", "tags": "", "sources": []}
            for path, data in raw_data.items()
            if data == "not_found"
        ]
        return search_results, False

    search_results = []
    if looks_like_filename(search_query):
        search_results = [
            img for img in image_data
            if search_query.lower() in img['path'].lower()
        ]
    elif search_query == 'metadata:found':
        search_results = image_data.copy()
    elif search_query.startswith('filename:'):
        filename_query = search_query.replace('filename:', '', 1).strip()
        search_results = [
            img for img in image_data
            if filename_query in img['path'].lower()
        ]
    elif search_query.startswith('source:'):
        source_query = search_query.replace('source:', '', 1).strip()
        search_results = [
            img for img in image_data
            if any(source_query in s for s in img.get('sources', []))
        ]
    elif search_query.startswith('category:'):
        category_query = search_query.replace('category:', '', 1).strip()
        valid_categories = ["character", "copyright", "artist", "meta", "general"]
        if category_query in valid_categories:
            tag_field = f"tags_{category_query}"
            for img in image_data:
                rel_path = img['path'].replace('images/', '', 1)
                img_metadata = raw_data.get(rel_path)
                if isinstance(img_metadata, dict) and img_metadata.get(tag_field):
                    search_results.append(img)
    elif search_query:
        # Regular tag search
        query_tags = search_query.split()
        search_results = [
            img for img in image_data 
            if all(q_tag in img['tags'] for q_tag in query_tags)
        ]
    else:
        # No search - return all images
        search_results = image_data.copy()

    return search_results, True


# Load data on startup
load_data()

# Start monitor on startup
start_monitor()

@app.route('/api/images')
def get_images():
    """API endpoint for infinite scroll - returns JSON image data"""
    search_query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Hardcoded per_page
    seed = request.args.get('seed', default=None, type=int)
    
    search_results, should_shuffle = _perform_search(search_query)

    # Apply seeded shuffle if a seed is provided and shuffling is enabled
    if should_shuffle and seed is not None:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    total_pages = (total_results + per_page - 1) // per_page
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    images_page = [
        {
            "path": img['path'],
            "thumb": get_thumbnail_path(img['path']),
            "tags": img.get('tags', '') # Use .get for safety
        }
        for img in search_results[start_idx:end_idx]
    ]
    
    return jsonify({
        "images": images_page,
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results,
        "has_more": page < total_pages
    })

@app.route('/api/reload', methods=['POST'])
def reload_data():
    """Endpoint to trigger data reload"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    success = load_data()
    if success:
        return jsonify({
            "status": "success",
            "images": len(raw_data),
            "tags": len(tag_counts)
        })
    else:
        return jsonify({"error": "Failed to reload data"}), 500


@app.route('/api/system/status')
def system_status():
    """Get system status"""
    unprocessed = find_unprocessed_images()
    
    return jsonify({
        "monitor": {
            "enabled": MONITOR_ENABLED,
            "running": monitor_status["running"],
            "last_check": monitor_status["last_check"],
            "last_scan_found": monitor_status["last_scan_found"],
            "total_processed": monitor_status["total_processed"],
            "interval_seconds": MONITOR_INTERVAL
        },
        "collection": {
            "total_images": len(raw_data),
            "with_metadata": sum(1 for d in raw_data.values() if d != "not_found"),
            "unprocessed": len(unprocessed)
        }
    })

@app.route('/api/system/scan', methods=['POST'])
def trigger_scan():
    print(f"Args: {dict(request.args)}")
    print(f"Form: {dict(request.form)}")
    print(f"Expected: {repr(RELOAD_SECRET)}")
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    print(f"Got: {repr(secret)}")
    print(f"Match: {secret == RELOAD_SECRET}")
    
    """Manually trigger a scan for new images"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    unprocessed = find_unprocessed_images()
    
    if not unprocessed:
        return jsonify({
            "status": "success",
            "message": "No new images found",
            "processed": 0
        })
    
    try:
        success = process_new_images()
        if success:
            load_data()
            return jsonify({
                "status": "success",
                "message": f"Processed {len(unprocessed)} images",
                "processed": len(unprocessed)
            })
        else:
            return jsonify({"error": "Processing failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/rebuild', methods=['POST'])
def trigger_rebuild():
    """Manually trigger tags.json rebuild"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        import rebuild_tags_from_metadata
        success = rebuild_tags_from_metadata.rebuild_tags()
        if success:
            load_data()
            return jsonify({
                "status": "success",
                "message": "Tags rebuilt successfully"
            })
        else:
            return jsonify({"error": "Rebuild failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/thumbnails', methods=['POST'])
def trigger_thumbnails():
    """Manually trigger thumbnail generation"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    try:
        import generate_thumbnails
        generate_thumbnails.main()
        return jsonify({
            "status": "success",
            "message": "Thumbnails generated"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/deduplicate', methods=['POST'])
def deduplicate():
    """Run MD5 deduplication scan"""
    data = request.json or {}
    secret = data.get('secret', '')
    
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    dry_run = data.get('dry_run', True)
    
    try:
        from utils.deduplication import scan_and_remove_duplicates
        results = scan_and_remove_duplicates(dry_run=dry_run)
        
        # Reload data if we actually removed files
        if not dry_run and results['removed'] > 0:
            load_data()
        
        return jsonify({
            "status": "success",
            "results": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/system/monitor/start', methods=['POST'])
def start_monitor_endpoint():
    """Start the monitoring thread"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    start_monitor()
    return jsonify({"status": "success", "message": "Monitor started"})

@app.route('/api/system/monitor/stop', methods=['POST'])
def stop_monitor_endpoint():
    """Stop the monitoring thread"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    stop_monitor()
    return jsonify({"status": "success", "message": "Monitor stopped"})


@app.route('/api/edit_tags', methods=['POST'])
def edit_tags():
    """Update tags for an image"""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    new_tags = data.get('tags', '').strip()
    
    if not filepath or filepath not in raw_data:
        return jsonify({"error": "Image not found"}), 404
    
    try:
        with data_lock:
            # Update tags.json in memory
            if isinstance(raw_data[filepath], str):
                raw_data[filepath] = new_tags
            else:
                raw_data[filepath]['tags'] = new_tags
            
            # Write the updated data to the file
            with open('tags.json', 'w') as f:
                json.dump(raw_data, f, indent=4)
        
        # Reload data from the file after the lock is released
        load_data()
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete_image', methods=['POST'])
def delete_image():
    """Delete an image and its metadata"""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    
    if not filepath or filepath not in raw_data:
        return jsonify({"error": "Image not found"}), 404
    
    try:
        with data_lock:
            # Get MD5 for metadata deletion
            image_md5 = None
            if isinstance(raw_data[filepath], dict):
                image_md5 = raw_data[filepath].get('md5')
            
            # Delete from tags.json
            del raw_data[filepath]
            with open('tags.json', 'w') as f:
                json.dump(raw_data, f, indent=4)
            
            # Delete image file
            image_path = f"static/images/{filepath}"
            if os.path.exists(image_path):
                os.remove(image_path)
            
            # Delete thumbnail
            thumb_path = get_thumbnail_path(f"images/{filepath}")
            full_thumb = f"static/{thumb_path}"
            if os.path.exists(full_thumb):
                os.remove(full_thumb)
            
            # Delete metadata
            if image_md5:
                metadata_path = f"metadata/{image_md5}.json"
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
        
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/autocomplete')
def autocomplete():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    
    # Split query into tokens to handle multi-tag searches
    tokens = query.split()
    last_token = tokens[-1] if tokens else ""
    
    # Find matching tags
    matches = []
    for tag, count in tag_counts.items():
        if tag.startswith(last_token):
            matches.append({"tag": tag, "count": count})
    
    # Sort by count descending, then alphabetically
    matches.sort(key=lambda x: (-x["count"], x["tag"]))
    
    # Return top 10 matches
    return jsonify(matches[:10])


def calculate_similarity(tags1, tags2):
    """Calculate Jaccard similarity between two tag sets"""
    set1 = set(tags1.split())
    set2 = set(tags2.split())
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0

def find_related_by_tags(filepath, limit=20):
    """Find related images weighted by character > copyright > artist > similar tags"""
    lookup_path = filepath.replace("images/", "", 1)
    
    if lookup_path not in raw_data:
        return []
    
    ref_data = raw_data[lookup_path]
    if ref_data == "not_found":
        return []
    
    # Extract reference tags
    if isinstance(ref_data, dict):
        ref_chars = set(ref_data.get("tags_character", "").split())
        ref_copy = set(ref_data.get("tags_copyright", "").split())
        ref_artist = set(ref_data.get("tags_artist", "").split())
        ref_general = set(ref_data.get("tags_general", "").split())
    else:
        ref_chars = ref_copy = ref_artist = ref_general = set()
    
    # Score all images
    scored_images = []
    
    for path, data in raw_data.items():
        if path == lookup_path or data == "not_found":
            continue
        
        if isinstance(data, dict):
            img_chars = set(data.get("tags_character", "").split())
            img_copy = set(data.get("tags_copyright", "").split())
            img_artist = set(data.get("tags_artist", "").split())
            img_general = set(data.get("tags_general", "").split())
        else:
            continue
        
        # Calculate weighted score
        score = 0
        match_type = "similar"
        
        # Character match (highest priority)
        char_overlap = len(ref_chars & img_chars)
        if char_overlap > 0:
            score += char_overlap * 100
            match_type = "character"
        
        # Copyright match
        copy_overlap = len(ref_copy & img_copy)
        if copy_overlap > 0:
            score += copy_overlap * 50
            if match_type == "similar":
                match_type = "copyright"
        
        # Artist match
        artist_overlap = len(ref_artist & img_artist)
        if artist_overlap > 0:
            score += artist_overlap * 30
            if match_type == "similar":
                match_type = "artist"
        
        # General tag similarity
        if ref_general and img_general:
            general_sim = len(ref_general & img_general) / len(ref_general | img_general)
            score += general_sim * 10
        
        if score > 0:
            scored_images.append({
                "path": f"images/{path}",
                "score": score,
                "match_type": match_type
            })
    
    # Sort by score
    scored_images.sort(key=lambda x: x['score'], reverse=True)
    
    return scored_images[:limit]

@app.route('/similar/<path:filepath>')
def find_similar(filepath):
    """Find images similar to the given one"""
    lookup_path = filepath.replace("images/", "", 1)
    
    if lookup_path not in raw_data:
        return "Image not found", 404
    
    # Get tags for the reference image
    ref_data = raw_data[lookup_path]
    ref_tags = ref_data.get("tags", "") if isinstance(ref_data, dict) else ref_data
    
    if ref_data == "not_found" or not ref_tags:
        return render_template('index.html', 
                             images=[], 
                             query=f"similar:{filepath}",
                             stats=get_enhanced_stats())
    
    # Calculate similarity for all images
    similarities = []
    for img in image_data:
        if img['path'] == f"images/{lookup_path}":
            continue
        
        similarity = calculate_similarity(ref_tags, img['tags'])
        if similarity > 0:
            similarities.append((img, similarity))
    
    # Sort by similarity
    similarities.sort(key=lambda x: x[1], reverse=True)
    
    # Take top 50
    similar_images = [
        {
            "path": img['path'],
            "thumb": get_thumbnail_path(img['path']),
            "tags": img['tags'],
            "similarity": sim
        }
        for img, sim in similarities[:50]
    ]
    
    return render_template('index.html', 
                         images=similar_images, 
                         query=f"similar:{filepath}",
                         stats=get_enhanced_stats(),
                         show_similarity=True)

@app.route('/api/saucenao/search', methods=['POST'])
def saucenao_search():
    """Search SauceNao for an image"""
    data = request.json
    secret = data.get('secret', '')
    
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    filepath = data.get('filepath', '').replace('images/', '', 1)
    
    if not filepath:
        return jsonify({"error": "No filepath provided"}), 400
    
    full_path = f"static/images/{filepath}"
    if not os.path.exists(full_path):
        return jsonify({"error": "Image not found"}), 404
    
    try:
        # Import the search functions
        import fetch_metadata
        
        # Run SauceNao search
        booru_posts, saucenao_response = fetch_metadata.search_saucenao(full_path)
        
        if not saucenao_response or 'results' not in saucenao_response:
            return jsonify({
                "status": "success",
                "found": False,
                "message": "No results found"
            })
        
        # Parse results
        results = []
        for result in saucenao_response.get('results', [])[:10]:  # Check more results
            similarity = float(result['header']['similarity'])
            
            if similarity < 60:  # Lower threshold to catch more
                continue
            
            result_data = {
                "similarity": similarity,
                "thumbnail": result['header'].get('thumbnail'),
                "sources": []
            }
            
            # Extract booru sources
            urls = result['data'].get('ext_urls', [])
            
            # Also check for index_id to determine source
            index_id = result['header'].get('index_id')
            index_name = result['header'].get('index_name', '')
            
            print(f"SauceNao result: similarity={similarity}, index_id={index_id}, index_name={index_name}, urls={urls}")
            
            for url in urls:
                source_info = None
                
                # Danbooru - handle both /posts/ and /post/show/ formats
                if 'danbooru.donmai.us' in url:
                    if '/posts/' in url:
                        post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0]
                    elif '/post/show/' in url:
                        post_id = url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    else:
                        continue
                    source_info = {
                        "type": "danbooru",
                        "url": url,
                        "post_id": post_id
                    }
                
                # e621
                elif 'e621.net' in url:
                    if '/posts/' in url:
                        post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0]
                    elif '/post/show/' in url:
                        post_id = url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    else:
                        continue
                    source_info = {
                        "type": "e621",
                        "url": url,
                        "post_id": post_id
                    }
                
                # Gelbooru
                elif 'gelbooru.com' in url:
                    if 'id=' in url:
                        post_id = url.split('id=')[-1].split('&')[0]
                    else:
                        continue
                    source_info = {
                        "type": "gelbooru",
                        "url": url,
                        "post_id": post_id
                    }
                
                # Yandere
                elif 'yande.re' in url:
                    if '/post/show/' in url:
                        post_id = url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    elif '/post/' in url:
                        post_id = url.split('/post/')[-1].split('?')[0].split('/')[0]
                    else:
                        continue
                    source_info = {
                        "type": "yandere",
                        "url": url,
                        "post_id": post_id
                    }
                
                if source_info:
                    print(f"Extracted: {source_info}")
                    result_data["sources"].append(source_info)
            
            # Deduplicate sources by type (keep first occurrence)
            seen_types = set()
            unique_sources = []
            for source in result_data["sources"]:
                if source["type"] not in seen_types:
                    seen_types.add(source["type"])
                    unique_sources.append(source)
            result_data["sources"] = unique_sources
            
            if result_data["sources"]:
                results.append(result_data)
        
        return jsonify({
            "status": "success",
            "found": len(results) > 0,
            "results": results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/saucenao/fetch_metadata', methods=['POST'])
def saucenao_fetch_metadata():
    """Fetch full metadata from a booru source"""
    data = request.json
    secret = data.get('secret', '')
    
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    source = data.get('source')
    post_id = data.get('post_id')
    
    if not source or not post_id:
        return jsonify({"error": "Missing source or post_id"}), 400
    
    try:
        import fetch_metadata
        
        print(f"Fetching metadata for {source} post {post_id}")  # DEBUG
        result = fetch_metadata.fetch_by_post_id(source, post_id)
        
        if not result:
            print(f"fetch_by_post_id returned None for {source} {post_id}")  # DEBUG
            return jsonify({"error": f"Failed to fetch metadata from {source}"}), 404
        
        print(f"Successfully fetched from {source}, extracting tags...")  # DEBUG
        # Extract tag data
        tag_data = fetch_metadata.extract_tag_data(result)
        
        # Get image URL
        full_data = result['full_data']
        image_url = None
        preview_url = None  # Smaller preview image
        
        if source == 'danbooru':
            image_url = full_data.get('file_url') or full_data.get('large_file_url')
            preview_url = full_data.get('preview_file_url') or full_data.get('preview_url')
        elif source == 'e621':
            image_url = full_data.get('file', {}).get('url')
            preview_url = full_data.get('preview', {}).get('url') or full_data.get('sample', {}).get('url')
        elif source == 'gelbooru':
            image_url = full_data.get('file_url')
            preview_url = full_data.get('preview_url')
        elif source == 'yandere':
            image_url = full_data.get('file_url')
            preview_url = full_data.get('preview_url') or full_data.get('sample_url')
        
        print(f"Returning metadata for {source}")  # DEBUG
        return jsonify({
            "status": "success",
            "tags": tag_data['tags'],
            "image_url": image_url,
            "preview_url": preview_url,
            "file_size": full_data.get('file_size'),
            "width": full_data.get('image_width') or full_data.get('width'),
            "height": full_data.get('image_height') or full_data.get('height'),
            "rating": full_data.get('rating'),
            "score": full_data.get('score'),
            "raw_data": full_data
        })
        
    except Exception as e:
        print(f"Error fetching metadata for {source} {post_id}: {e}")  # DEBUG
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/saucenao/apply', methods=['POST'])
def saucenao_apply():
    """Apply selected metadata and optionally download a new image, replacing the old one."""
    data = request.json
    secret = data.get('secret', '')
    
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    original_filepath = data.get('filepath', '').replace('images/', '', 1)
    source = data.get('source')
    post_id = data.get('post_id')
    selected_tags = data.get('tags', {})
    download_image = data.get('download_image', False)
    image_url = data.get('image_url')
    
    if not original_filepath or not source or not post_id:
        return jsonify({"error": "Missing required parameters"}), 400
    
    try:
        import fetch_metadata
        
        result = fetch_metadata.fetch_by_post_id(source, post_id)
        if not result:
            return jsonify({"error": "Failed to fetch metadata"}), 404
            
        redirect_url = None
        final_filepath = original_filepath

        if download_image and image_url:
            import requests

            # 1. Determine new filename from URL
            parsed_url = urlparse(image_url)
            new_filename = os.path.basename(parsed_url.path)
            if not new_filename:
                return jsonify({"error": "Could not determine filename from URL."}), 400

            new_relative_path = new_filename
            new_full_path = f"static/images/{new_relative_path}"

            # 2. Check if a file with the new name already exists
            if os.path.exists(new_full_path):
                return jsonify({"error": f"File '{new_filename}' already exists."}), 409

            # 3. Download the new image
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(new_full_path, 'wb') as f:
                f.write(response.content)

            # NEW: Check for duplicate BEFORE creating thumbnail and metadata
            is_dup, existing_path, md5 = is_duplicate(new_full_path)
            if is_dup:
                # Remove the just-downloaded duplicate
                os.remove(new_full_path)
                return jsonify({
                    "error": f"Duplicate image detected. MD5 matches existing file: {existing_path}",
                    "duplicate_of": existing_path,
                    "md5": md5
                }), 409

            fetch_metadata.ensure_thumbnail(new_full_path)

            # 4. Clean up old files (image, thumbnail, metadata)
            old_full_path = f"static/images/{original_filepath}"
            if os.path.exists(old_full_path):
                old_md5 = raw_data.get(original_filepath, {}).get('md5') or fetch_metadata.get_md5(old_full_path)
                os.remove(old_full_path)
                
                old_thumb_path = f"static/{get_thumbnail_path(f'images/{original_filepath}')}"
                if os.path.exists(old_thumb_path):
                    os.remove(old_thumb_path)
                
                if old_md5:
                    old_metadata_path = f"metadata/{old_md5}.json"
                    if os.path.exists(old_metadata_path):
                        os.remove(old_metadata_path)

            final_filepath = new_relative_path
            redirect_url = url_for('show_image', filepath=f"images/{new_relative_path}")

        # --- COMMON LOGIC FOR BOTH SCENARIOS ---
        
        # Calculate MD5 for the final image
        md5 = fetch_metadata.get_md5(f"static/images/{final_filepath}")

        # Save metadata to its own .json file
        metadata_content = {
            "md5": md5, "relative_path": final_filepath, "saucenao_lookup": True,
            "camie_tagger_lookup": False, "sources": {source: result['full_data']}
        }
        with open(f"metadata/{md5}.json", 'w') as f:
            json.dump(metadata_content, f, indent=2)
        
        # Build the new entry for tags.json
        tag_data = fetch_metadata.extract_tag_data(result)
        tags_entry = {
            "tags": selected_tags.get('all', tag_data['tags']['all']),
            "tags_character": selected_tags.get('character', tag_data['tags']['character']),
            "tags_copyright": selected_tags.get('copyright', tag_data['tags']['copyright']),
            "tags_artist": selected_tags.get('artist', tag_data['tags']['artist']),
            "tags_meta": selected_tags.get('meta', tag_data['tags']['meta']),
            "tags_general": selected_tags.get('general', tag_data['tags']['general']),
            "id": tag_data['id'], "parent_id": tag_data['parent_id'], "has_children": tag_data['has_children'],
            "md5": md5, "sources": [source], "saucenao_lookup": True, "camie_tagger_lookup": False
        }

        # Update tags.json safely
        with data_lock:
            # If we downloaded a new file, remove the old entry
            if download_image and original_filepath in raw_data:
                del raw_data[original_filepath]
            
            # Add or update the entry for the final file
            raw_data[final_filepath] = tags_entry
            
            with open('tags.json', 'w') as f:
                json.dump(raw_data, f, indent=4)
        
        load_data()
        
        # Construct the final response
        response_data = { "status": "success", "message": "Metadata applied successfully.", "downloaded": download_image }
        if redirect_url:
            response_data["redirect_url"] = redirect_url
        
        return jsonify(response_data)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Network error downloading image: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    search_query = request.args.get('query', '').strip().lower()
    per_page = 50 # Hardcoded per_page
    stats = get_enhanced_stats()
    
    seed = random.randint(1, 1_000_000)
    
    search_results, should_shuffle = _perform_search(search_query)

    # Shuffle the results using the generated seed if shuffling is enabled
    if should_shuffle:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    
    images_to_show = [
        {
            "path": img['path'],
            "thumb": get_thumbnail_path(img['path']),
            "tags": img.get('tags', '')
        }
        for img in search_results[:per_page]
    ]
    
    random_tags = []
    if not search_query and tag_counts:
        available_tags = list(tag_counts.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))
    
    return render_template('index.html', 
                         images=images_to_show, 
                         query=search_query,
                         per_page=per_page,
                         random_tags=random_tags,
                         stats=stats,
                         total_results=total_results,
                         seed=seed)

@app.route('/image/<path:filepath>')
def show_image(filepath):
    lookup_path = filepath.replace("images/", "", 1)
    data = raw_data.get(lookup_path, "")
    
    # Handle both old and new format
    if isinstance(data, str):
        tag_list = sorted(data.split())
        tags_with_counts = [(tag, tag_counts.get(tag, 0)) for tag in tag_list]
        categorized_tags = None
        post_id = None
        parent_id = None
    else:
        # New format with categories
        general_tags = sorted(data.get("tags_general", "").split())
        
        # FALLBACK: If tags_general is empty, use tags field
        if not general_tags or all(not t for t in general_tags):
            general_tags = sorted(data.get("tags", "").split())
        
        tags_with_counts = [(tag, tag_counts.get(tag, 0)) for tag in general_tags if tag]
        
        categorized_tags = {
            "character": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_character", "").split()) if t],
            "copyright": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_copyright", "").split()) if t],
            "artist": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_artist", "").split()) if t],
            "meta": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_meta", "").split()) if t]
        }
        
        post_id = data.get("id")
        parent_id = data.get("parent_id")
    
    # Load full metadata
    metadata = load_metadata(filepath)
    
    # Find related images
    related_images = get_related_images(post_id, parent_id, raw_data, id_to_path)
    
    # Find similar images by tags
    similar_by_tags = find_related_by_tags(filepath, limit=20)
    carousel_images = [
        {
            "path": img['path'],
            "thumb": get_thumbnail_path(img['path']),
            "match_type": img['match_type']
        }
        for img in similar_by_tags
    ]


    return render_template('image.html', 
                          filepath=filepath, 
                          tags=tags_with_counts,
                          categorized_tags=categorized_tags,
                          metadata=metadata,
                          related_images=related_images,
                          carousel_images=carousel_images)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
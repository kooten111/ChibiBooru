import os
import json
import random
import threading
import time
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from flask import request, jsonify, render_template, url_for
from models import load_data, get_raw_data, get_tag_counts, get_id_to_path, get_image_data
from utils import get_thumbnail_path, load_metadata, get_related_images
from utils.deduplication import is_duplicate, remove_duplicate
import fetch_metadata
import rebuild_tags_from_metadata
import generate_thumbnails
from utils.deduplication import scan_and_remove_duplicates

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
    "total_processed": 0,
}

def looks_like_filename(query):
    """Check if query looks like a filename"""
    if any(query.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        return True
    import re
    if re.match(r'^\d+_p\d+', query) or re.match(r'^[a-f0-9]{32}', query):
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
    raw_data = get_raw_data()

    for root, _, files in os.walk("./static/images"):
        for file in files:
            if not file.lower().endswith(image_extensions):
                continue

            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, "./static/images")

            if rel_path not in raw_data or raw_data[rel_path] == "not_found":
                unprocessed.append(filepath)

    return unprocessed

def process_new_images():
    """Process new images by calling fetch_metadata"""
    try:
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

def get_enhanced_stats():
    """Get detailed statistics about the collection"""
    raw_data = get_raw_data()
    tag_counts = get_tag_counts()
    total_images = len(raw_data)
    images_with_metadata = sum(1 for data in raw_data.values() if data != "not_found")
    images_without_metadata = total_images - images_with_metadata

    source_counts = {}
    for data in raw_data.values():
        if isinstance(data, dict) and data != "not_found":
            sources = data.get("sources", [])
            for source in sources:
                source_name = source.split('.')[0] if '.' in source else source
                if source_name == "camie_tagger_lookup":
                    source_name = "camie_tagger"
                source_counts[source_name] = source_counts.get(source_name, 0) + 1

    total_tags = len(tag_counts)
    tags_per_image = []
    category_counts = {"character": 0, "copyright": 0, "artist": 0, "meta": 0, "general": 0}

    for data in raw_data.values():
        if data == "not_found":
            continue
        if isinstance(data, dict):
            tags = data.get("tags", "").split()
            tags_per_image.append(len(tags))
            for cat in category_counts:
                cat_tags = data.get(f"tags_{cat}", "").split()
                category_counts[cat] += len(cat_tags)
        else:
            tags = data.split()
            tags_per_image.append(len(tags))

    avg_tags = sum(tags_per_image) / len(tags_per_image) if tags_per_image else 0
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    saucenao_count = sum(1 for data in raw_data.values() if isinstance(data, dict) and data.get("saucenao_lookup"))
    camie_count = sum(1 for data in raw_data.values() if isinstance(data, dict) and data.get("camie_tagger_lookup"))

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
        'camie_used': camie_count,
    }

def perform_search(search_query):
    """Helper function to perform a search and return results."""
    raw_data = get_raw_data()
    image_data = get_image_data()

    if search_query == 'metadata:missing':
        search_results = [
            {"path": f"images/{path}", "tags": "", "sources": []}
            for path, data in raw_data.items()
            if data == "not_found"
        ]
        return search_results, False

    search_results = []
    if looks_like_filename(search_query):
        search_results = [img for img in image_data if search_query.lower() in img['path'].lower()]
    elif search_query == 'metadata:found':
        search_results = image_data.copy()
    elif search_query.startswith('filename:'):
        filename_query = search_query.replace('filename:', '', 1).strip()
        search_results = [img for img in image_data if filename_query in img['path'].lower()]
    elif search_query.startswith('source:'):
        source_query = search_query.replace('source:', '', 1).strip()
        search_results = [img for img in image_data if any(source_query in s for s in img.get('sources', []))]
    elif search_query.startswith('category:'):
        category_query = search_query.replace('category:', '', 1).strip()
        if category_query in ["character", "copyright", "artist", "meta", "general"]:
            tag_field = f"tags_{category_query}"
            for img in image_data:
                rel_path = img['path'].replace('images/', '', 1)
                img_metadata = raw_data.get(rel_path)
                if isinstance(img_metadata, dict) and img_metadata.get(tag_field):
                    search_results.append(img)
    elif search_query:
        query_tags = search_query.split()
        search_results = [img for img in image_data if all(q_tag in img['tags'] for q_tag in query_tags)]
    else:
        search_results = image_data.copy()

    return search_results, True


def calculate_similarity(tags1, tags2):
    """Calculate Jaccard similarity between two tag sets"""
    set1, set2 = set(tags1.split()), set(tags2.split())
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2) if len(set1 | set2) > 0 else 0.0


def find_related_by_tags(filepath, limit=20):
    """Find related images weighted by character > copyright > artist > similar tags"""
    lookup_path = filepath.replace("images/", "", 1)
    raw_data = get_raw_data()

    if lookup_path not in raw_data:
        return []

    ref_data = raw_data[lookup_path]
    if ref_data == "not_found":
        return []

    ref_chars = set(ref_data.get("tags_character", "").split())
    ref_copy = set(ref_data.get("tags_copyright", "").split())
    ref_artist = set(ref_data.get("tags_artist", "").split())
    ref_general = set(ref_data.get("tags_general", "").split())

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

        score = 0
        match_type = "similar"
        char_overlap = len(ref_chars & img_chars)
        if char_overlap > 0:
            score += char_overlap * 100
            match_type = "character"
        copy_overlap = len(ref_copy & img_copy)
        if copy_overlap > 0:
            score += copy_overlap * 50
            if match_type == "similar":
                match_type = "copyright"
        artist_overlap = len(ref_artist & img_artist)
        if artist_overlap > 0:
            score += artist_overlap * 30
            if match_type == "similar":
                match_type = "artist"
        if ref_general and img_general:
            score += (len(ref_general & img_general) / len(ref_general | img_general)) * 10
        if score > 0:
            scored_images.append({"path": f"images/{path}", "score": score, "match_type": match_type})

    scored_images.sort(key=lambda x: x['score'], reverse=True)
    return scored_images[:limit]


def reload_data():
    """Endpoint to trigger data reload"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    success = load_data()
    if success:
        return jsonify({"status": "success", "images": len(get_raw_data()), "tags": len(get_tag_counts())})
    else:
        return jsonify({"error": "Failed to reload data"}), 500


def get_system_status():
    """Get system status"""
    unprocessed = find_unprocessed_images()
    return jsonify({
        "monitor": {
            "enabled": MONITOR_ENABLED,
            "running": monitor_status["running"],
            "last_check": monitor_status["last_check"],
            "last_scan_found": monitor_status["last_scan_found"],
            "total_processed": monitor_status["total_processed"],
            "interval_seconds": MONITOR_INTERVAL,
        },
        "collection": {
            "total_images": len(get_raw_data()),
            "with_metadata": sum(1 for d in get_raw_data().values() if d != "not_found"),
            "unprocessed": len(unprocessed),
        },
    })


def trigger_scan():
    """Manually trigger a scan for new images"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    unprocessed = find_unprocessed_images()
    if not unprocessed:
        return jsonify({"status": "success", "message": "No new images found", "processed": 0})

    try:
        if process_new_images():
            load_data()
            return jsonify({"status": "success", "message": f"Processed {len(unprocessed)} images", "processed": len(unprocessed)})
        else:
            return jsonify({"error": "Processing failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def trigger_rebuild():
    """Manually trigger tags.json rebuild"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        if rebuild_tags_from_metadata.rebuild_tags():
            load_data()
            return jsonify({"status": "success", "message": "Tags rebuilt successfully"})
        else:
            return jsonify({"error": "Rebuild failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def trigger_thumbnails():
    """Manually trigger thumbnail generation"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        generate_thumbnails.main()
        return jsonify({"status": "success", "message": "Thumbnails generated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def find_orphan_metadata():
    """Find metadata entries that don't have a corresponding image file."""
    raw_data = get_raw_data()
    orphans = []
    for path in raw_data.keys():
        full_path = os.path.join("static/images", path)
        if not os.path.exists(full_path):
            orphans.append(path)
    return orphans

def clean_orphan_metadata_entries(orphans_to_clean):
    """Remove specified orphan metadata entries from tags.json."""
    raw_data = get_raw_data().copy()
    cleaned_count = 0
    for path in orphans_to_clean:
        if path in raw_data:
            del raw_data[path]
            cleaned_count += 1
    
    if cleaned_count > 0:
        with open('tags.json', 'w') as f:
            json.dump(raw_data, f, indent=4)
    return cleaned_count

def deduplicate():
    """Run MD5 deduplication scan"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    dry_run = data.get('dry_run', True)

    try:
        results = scan_and_remove_duplicates(dry_run=dry_run)
        if not dry_run and results['removed'] > 0:
            load_data()
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def clean_orphans():
    """Service to find and clean orphan metadata."""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json or {}
    dry_run = data.get('dry_run', True)
    
    try:
        orphans = find_orphan_metadata()
        
        if dry_run:
            return jsonify({
                "status": "success",
                "orphans_found": len(orphans),
                "orphans": orphans,
                "cleaned": 0
            })
        else:
            cleaned_count = clean_orphan_metadata_entries(orphans)
            if cleaned_count > 0:
                load_data()
            return jsonify({
                "status": "success",
                "orphans_found": len(orphans),
                "orphans": orphans,
                "cleaned": cleaned_count
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_monitor_service():
    """Start the monitoring thread"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    start_monitor()
    return jsonify({"status": "success", "message": "Monitor started"})


def stop_monitor_service():
    """Stop the monitoring thread"""
    secret = request.args.get('secret', '') or request.form.get('secret', '')
    if secret != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    stop_monitor()
    return jsonify({"status": "success", "message": "Monitor stopped"})


def edit_tags():
    """Update tags for an image"""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    new_tags = data.get('tags', '').strip()
    raw_data = get_raw_data()

    if not filepath or filepath not in raw_data:
        return jsonify({"error": "Image not found"}), 404

    try:
        if isinstance(raw_data[filepath], str):
            raw_data[filepath] = new_tags
        else:
            raw_data[filepath]['tags'] = new_tags
        with open('tags.json', 'w') as f:
            json.dump(raw_data, f, indent=4)
        load_data()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def delete_image():
    """Delete an image and its metadata"""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    raw_data = get_raw_data()

    if not filepath or filepath not in raw_data:
        return jsonify({"error": "Image not found"}), 404

    try:
        image_md5 = raw_data[filepath].get('md5') if isinstance(raw_data[filepath], dict) else None
        del raw_data[filepath]
        with open('tags.json', 'w') as f:
            json.dump(raw_data, f, indent=4)

        image_path = f"static/images/{filepath}"
        if os.path.exists(image_path):
            os.remove(image_path)
        thumb_path = f"static/{get_thumbnail_path(f'images/{filepath}')}"
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        if image_md5:
            metadata_path = f"metadata/{image_md5}.json"
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def autocomplete():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])
    
    tokens = query.split()
    last_token = tokens[-1] if tokens else ""
    tag_counts = get_tag_counts()
    matches = [{"tag": tag, "count": count} for tag, count in tag_counts.items() if tag.startswith(last_token)]
    matches.sort(key=lambda x: (-x["count"], x["tag"]))
    return jsonify(matches[:10])


def find_similar(filepath):
    """Find images similar to the given one"""
    lookup_path = filepath.replace("images/", "", 1)
    raw_data = get_raw_data()
    image_data = get_image_data()

    if lookup_path not in raw_data:
        return "Image not found", 404

    ref_data = raw_data[lookup_path]
    ref_tags = ref_data.get("tags", "") if isinstance(ref_data, dict) else ref_data

    if ref_data == "not_found" or not ref_tags:
        return render_template('index.html', images=[], query=f"similar:{filepath}", stats=get_enhanced_stats())

    similarities = []
    for img in image_data:
        if img['path'] == f"images/{lookup_path}":
            continue
        similarity = calculate_similarity(ref_tags, img['tags'])
        if similarity > 0:
            similarities.append((img, similarity))

    similarities.sort(key=lambda x: x[1], reverse=True)
    similar_images = [
        {"path": img['path'], "thumb": get_thumbnail_path(img['path']), "tags": img['tags'], "similarity": sim}
        for img, sim in similarities[:50]
    ]

    return render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=get_enhanced_stats(), show_similarity=True)


def saucenao_search():
    """Search SauceNao for an image"""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    filepath = data.get('filepath', '').replace('images/', '', 1)
    if not filepath:
        return jsonify({"error": "No filepath provided"}), 400

    full_path = f"static/images/{filepath}"
    if not os.path.exists(full_path):
        return jsonify({"error": "Image not found"}), 404

    try:
        booru_posts, saucenao_response = fetch_metadata.search_saucenao(full_path)
        if not saucenao_response or 'results' not in saucenao_response:
            return jsonify({"status": "success", "found": False, "message": "No results found"})

        results = []
        for result in saucenao_response.get('results', [])[:10]:
            similarity = float(result['header']['similarity'])
            if similarity < 60:
                continue

            result_data = {"similarity": similarity, "thumbnail": result['header'].get('thumbnail'), "sources": []}
            urls = result['data'].get('ext_urls', [])

            for url in urls:
                source_info = None
                if 'danbooru.donmai.us' in url:
                    post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0] if '/posts/' in url else url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "danbooru", "url": url, "post_id": post_id}
                elif 'e621.net' in url:
                    post_id = url.split('/posts/')[-1].split('?')[0].split('/')[0] if '/posts/' in url else url.split('/post/show/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "e621", "url": url, "post_id": post_id}
                elif 'gelbooru.com' in url and 'id=' in url:
                    source_info = {"type": "gelbooru", "url": url, "post_id": url.split('id=')[-1].split('&')[0]}
                elif 'yande.re' in url:
                    post_id = url.split('/post/show/')[-1].split('?')[0].split('/')[0] if '/post/show/' in url else url.split('/post/')[-1].split('?')[0].split('/')[0]
                    source_info = {"type": "yandere", "url": url, "post_id": post_id}
                if source_info:
                    result_data["sources"].append(source_info)
            
            seen_types = set()
            unique_sources = []
            for source in result_data["sources"]:
                if source["type"] not in seen_types:
                    seen_types.add(source["type"])
                    unique_sources.append(source)
            result_data["sources"] = unique_sources

            if result_data["sources"]:
                results.append(result_data)

        return jsonify({"status": "success", "found": len(results) > 0, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def saucenao_fetch_metadata():
    """Fetch full metadata from a booru source"""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    source, post_id = data.get('source'), data.get('post_id')
    if not source or not post_id:
        return jsonify({"error": "Missing source or post_id"}), 400

    try:
        result = fetch_metadata.fetch_by_post_id(source, post_id)
        if not result:
            return jsonify({"error": f"Failed to fetch metadata from {source}"}), 404

        tag_data = fetch_metadata.extract_tag_data(result)
        full_data = result['full_data']
        image_url, preview_url = None, None

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
        
        return jsonify({
            "status": "success", "tags": tag_data['tags'], "image_url": image_url, "preview_url": preview_url,
            "file_size": full_data.get('file_size'), "width": full_data.get('image_width') or full_data.get('width'),
            "height": full_data.get('image_height') or full_data.get('height'), "rating": full_data.get('rating'),
            "score": full_data.get('score'), "raw_data": full_data
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def saucenao_apply():
    """Apply selected metadata and optionally download a new image, replacing the old one."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    original_filepath, source, post_id, selected_tags, download_image, image_url = (
        data.get('filepath', '').replace('images/', '', 1), data.get('source'), data.get('post_id'),
        data.get('tags', {}), data.get('download_image', False), data.get('image_url')
    )

    if not all([original_filepath, source, post_id]):
        return jsonify({"error": "Missing required parameters"}), 400

    try:
        result = fetch_metadata.fetch_by_post_id(source, post_id)
        if not result:
            return jsonify({"error": "Failed to fetch metadata"}), 404

        redirect_url, final_filepath = None, original_filepath
        raw_data = get_raw_data()

        if download_image and image_url:
            import requests
            new_filename = os.path.basename(urlparse(image_url).path)
            if not new_filename:
                return jsonify({"error": "Could not determine filename from URL."}), 400

            new_full_path = f"static/images/{new_filename}"
            if os.path.exists(new_full_path):
                return jsonify({"error": f"File '{new_filename}' already exists."}), 409

            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(new_full_path, 'wb') as f:
                f.write(response.content)

            is_dup, existing_path, md5 = is_duplicate(new_full_path)
            if is_dup:
                os.remove(new_full_path)
                return jsonify({"error": f"Duplicate image detected. MD5 matches: {existing_path}", "duplicate_of": existing_path, "md5": md5}), 409

            fetch_metadata.ensure_thumbnail(new_full_path)
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
            
            final_filepath = new_filename
            redirect_url = url_for('main.show_image', filepath=f"images/{new_filename}")

        md5 = fetch_metadata.get_md5(f"static/images/{final_filepath}")
        metadata_content = {
            "md5": md5, "relative_path": final_filepath, "saucenao_lookup": True, "camie_tagger_lookup": False,
            "sources": {source: result['full_data']}
        }
        with open(f"metadata/{md5}.json", 'w') as f:
            json.dump(metadata_content, f, indent=2)

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

        if download_image and original_filepath in raw_data:
            del raw_data[original_filepath]
        raw_data[final_filepath] = tags_entry
        with open('tags.json', 'w') as f:
            json.dump(raw_data, f, indent=4)
        
        load_data()
        response_data = {"status": "success", "message": "Metadata applied.", "downloaded": download_image}
        if redirect_url:
            response_data["redirect_url"] = redirect_url
        return jsonify(response_data)
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Network error downloading image: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Load data at startup
load_data()
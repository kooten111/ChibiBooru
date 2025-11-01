# services/api_service.py
from flask import request, jsonify, url_for
import models
import random
import sys
import os
import json
import requests
from urllib.parse import urlparse
from utils import get_thumbnail_path
import processing
from database import get_db_connection

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

RELOAD_SECRET = os.environ.get('RELOAD_SECRET', 'change-this-secret')


def get_images_for_api():
    """Service for the infinite scroll API."""
    from services import query_service  # Import here to avoid circular import
    
    search_query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    seed = request.args.get('seed', default=None, type=int)

    # Use the same search logic as the main page for consistency
    search_results, should_shuffle = query_service.perform_search(search_query)

    if should_shuffle and seed is not None:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    total_pages = (total_results + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    images_page = [
        {"path": f"images/{img['filepath']}", "thumb": get_thumbnail_path(f"images/{img['filepath']}"), "tags": img.get('tags', '')}
        for img in search_results[start_idx:end_idx]
    ]

    return jsonify({
        "images": images_page,
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results,
        "has_more": page < total_pages
    })


def update_image_tags_categorized(filepath, categorized_tags):
    """Update image tags by category in the database."""
    # Normalize filepath
    if filepath.startswith('images/'):
        filepath = filepath[7:]
    elif filepath.startswith('static/images/'):
        filepath = filepath[14:]
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get image_id
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            if not result:
                print(f"Image not found: {filepath}")
                return False
            
            image_id = result['id']
            
            # Update the categorized tag columns in images table
            cursor.execute("""
                UPDATE images 
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?
                WHERE id = ?
            """, (
                categorized_tags.get('tags_character', ''),
                categorized_tags.get('tags_copyright', ''),
                categorized_tags.get('tags_artist', ''),
                categorized_tags.get('tags_species', ''),
                categorized_tags.get('tags_meta', ''),
                categorized_tags.get('tags_general', ''),
                image_id
            ))
            
            # Delete old image_tags entries
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            
            # Insert new tags for each category
            for category_key, tags_str in categorized_tags.items():
                if not tags_str or not tags_str.strip():
                    continue
                    
                # Remove 'tags_' prefix from category name
                category_name = category_key.replace('tags_', '')
                
                tags = [t.strip() for t in tags_str.split() if t.strip()]
                for tag_name in tags:
                    # Get or create tag with proper category
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_result = cursor.fetchone()
                    
                    if tag_result:
                        tag_id = tag_result['id']
                        # Update category if tag exists
                        cursor.execute("UPDATE tags SET category = ? WHERE id = ?", (category_name, tag_id))
                    else:
                        # Insert new tag with category
                        cursor.execute(
                            "INSERT INTO tags (name, category) VALUES (?, ?)",
                            (tag_name, category_name)
                        )
                        tag_id = cursor.lastrowid
                    
                    # Link tag to image
                    cursor.execute(
                        "INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                        (image_id, tag_id)
                    )
            
            conn.commit()
            print(f"Successfully updated tags for {filepath}")
            return True
            
    except Exception as e:
        print(f"Error updating categorized tags for {filepath}: {e}")
        import traceback
        traceback.print_exc()
        if 'conn' in locals():
            conn.rollback()
        return False

def edit_tags_service():
    """Service to update tags for an image with category support."""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    
    # Check if we have categorized tags (new format) or plain tags (old format)
    categorized_tags = data.get('categorized_tags')
    
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        if categorized_tags:
            # New categorized format
            success = models.update_image_tags_categorized(filepath, categorized_tags)
        else:
            # Old format for backwards compatibility
            new_tags_str = data.get('tags', '').strip()
            success = models.update_image_tags(filepath, new_tags_str)

        if success:
            # Selective reload: only update this image and tag counts
            models.reload_single_image(filepath)
            models.reload_tag_counts()
            from repositories.data_access import get_image_details
            get_image_details.cache_clear()
            return jsonify({"status": "success"})
        else:
            return jsonify({"error": "Failed to update tags in the database"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def delete_image_service():
    """Service to delete an image and its data."""
    data = request.json
    # The filepath from the frontend is 'images/folder/image.jpg'
    # We need the path relative to the 'static/images' directory, which is 'folder/image.jpg'
    filepath = data.get('filepath', '').replace('images/', '', 1)

    print(f"[DELETE] Received filepath from frontend: {data.get('filepath')}")
    print(f"[DELETE] Processed filepath for deletion: {filepath}")

    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        # First, remove the database entry.
        db_success = models.delete_image(filepath)
        print(f"[DELETE] Database deletion result: {db_success}")
        if not db_success:
            # This isn't a fatal error; the file might still exist on disk without a DB entry.
            print(f"[DELETE] WARNING: Image {filepath} was not found in the database.")

        # Construct the full path to the image file.
        full_image_path = os.path.join("static/images", filepath)
        
        # Construct the thumbnail path directly and more reliably.
        # This creates 'static/thumbnails/folder/image.webp'
        thumb_path = os.path.join("static/thumbnails", os.path.splitext(filepath)[0] + '.webp')

        # --- Attempt to delete the files ---
        image_deleted = False
        thumb_deleted = False

        if os.path.exists(full_image_path):
            print(f"Deleting image file: {full_image_path}")
            os.remove(full_image_path)
            image_deleted = True
        else:
            print(f"Image file not found, skipping deletion: {full_image_path}")

        if os.path.exists(thumb_path):
            print(f"Deleting thumbnail file: {thumb_path}")
            os.remove(thumb_path)
            thumb_deleted = True
        else:
            print(f"Thumbnail file not found, skipping deletion: {thumb_path}")

        # If anything was actually deleted, update the in-memory data.
        if db_success or image_deleted or thumb_deleted:
            print("Updating cache after deletion.")
            models.remove_image_from_cache(filepath)
            models.reload_tag_counts()
        else:
            print("No database entry or files were found to delete.")


        return jsonify({"status": "success", "message": "Deletion process completed."})
    except Exception as e:
        # Log the full error to the console for easier debugging in the future.
        import traceback
        traceback.print_exc()
        print(f"Error deleting image {filepath}: {e}")
        return jsonify({"error": "An unexpected error occurred during deletion."}), 500

def delete_images_bulk_service():
    """Service to delete multiple images at once."""
    data = request.json
    filepaths = data.get('filepaths', [])

    if not filepaths or not isinstance(filepaths, list):
        return jsonify({"error": "filepaths array is required"}), 400

    results = {
        "total": len(filepaths),
        "deleted": 0,
        "failed": 0,
        "errors": []
    }

    for filepath in filepaths:
        # The filepath from the frontend is 'images/folder/image.jpg'
        # We need the path relative to the 'static/images' directory
        clean_filepath = filepath.replace('images/', '', 1)

        try:
            # Remove from database
            db_success = models.delete_image(clean_filepath)

            # Construct file paths
            full_image_path = os.path.join("static/images", clean_filepath)
            thumb_path = os.path.join("static/thumbnails", os.path.splitext(clean_filepath)[0] + '.webp')

            # Delete files
            image_deleted = False
            thumb_deleted = False

            if os.path.exists(full_image_path):
                os.remove(full_image_path)
                image_deleted = True

            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                thumb_deleted = True

            # Update cache
            if db_success or image_deleted or thumb_deleted:
                models.remove_image_from_cache(clean_filepath)
                results["deleted"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{clean_filepath}: Not found in database or filesystem")

        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{clean_filepath}: {str(e)}")
            print(f"Error deleting image {clean_filepath}: {e}")

    # Reload tag counts once after all deletions
    if results["deleted"] > 0:
        models.reload_tag_counts()

    return jsonify({
        "status": "success" if results["failed"] == 0 else "partial",
        "message": f"Deleted {results['deleted']} of {results['total']} images",
        "results": results
    })

# --- THIS IS THE CORRECTED SAUCENAO BLOCK ---

def saucenao_search_service():
    """Service to search SauceNao for an image."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    filepath = data.get('filepath', '')
    if not filepath:
        return jsonify({"error": "No filepath provided"}), 400

    full_path = os.path.join("static", filepath)
    if not os.path.exists(full_path):
        return jsonify({"error": "Image file not found"}), 404
    
    try:
        saucenao_response = processing.search_saucenao(full_path)
        if not saucenao_response or 'results' not in saucenao_response:
            return jsonify({"status": "success", "found": False, "message": "No results found"})

        results = []
        for result in saucenao_response.get('results', []):
            similarity = float(result['header']['similarity'])
            if similarity < 60: continue

            result_data = {"similarity": similarity, "thumbnail": result['header'].get('thumbnail'), "sources": []}
            for url in result['data'].get('ext_urls', []):
                source_info = None
                # Restore robust URL parsing for all boorus
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

            if result_data["sources"]:
                results.append(result_data)

        return jsonify({"status": "success", "found": len(results) > 0, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def saucenao_fetch_metadata_service():
    """Service to fetch full metadata from a booru source."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    source, post_id = data.get('source'), data.get('post_id')
    if not source or not post_id:
        return jsonify({"error": "Missing source or post_id"}), 400

    try:
        result = processing.fetch_by_post_id(source, post_id)
        if not result or 'data' not in result:
            return jsonify({"error": f"Failed to fetch metadata from {source}"}), 404

        full_data = result['data']
        tags_data = processing.extract_tag_data(full_data, source)

        return jsonify({
            "status": "success",
            "source": source,
            "tags": tags_data['tags'],
            "image_url": tags_data.get('image_url'),
            "preview_url": tags_data.get('preview_url'),
            "width": tags_data.get('width'),
            "height": tags_data.get('height'),
            "file_size": tags_data.get('file_size'),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def autocomplete():
    """Enhanced autocomplete with grouped suggestions by type and category."""
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify({"groups": []})

    tag_counts = models.get_tag_counts()
    last_token = query.split()[-1].lower()

    # Strip the '-' prefix for negative searches so autocomplete works
    is_negative_search = last_token.startswith('-')
    search_token = last_token[1:] if is_negative_search else last_token

    # Need at least 2 characters for the actual search term
    if len(search_token) < 2:
        return jsonify({"groups": []})

    # Initialize groups
    groups = {
        "Filters": [],
        "Tags": [],
        "Files": []
    }

    # File extension search (only if not a negative search)
    if not is_negative_search and search_token.startswith('.'):
        ext = search_token[1:]
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp']:
            groups["Filters"].append({
                "tag": search_token,
                "display": f"All {search_token} files",
                "count": None,
                "type": "extension"
            })

    # Special filter suggestions (only if not a negative search)
    if not is_negative_search:
        filters = [
            ("source:danbooru", "Danbooru images", "danbooru"),
            ("source:e621", "E621 images", "e621"),
            ("source:gelbooru", "Gelbooru images", "gelbooru"),
            ("source:yandere", "Yandere images", "yandere"),
            ("source:local_tagger", "Locally tagged images", "local"),
            ("has:parent", "Images with parent", "parent"),
            ("has:child", "Images with children", "child"),
            ("pool:", "Search pools", "pool")
        ]

        for tag, display, keyword in filters:
            if keyword in search_token or search_token in keyword:
                groups["Filters"].append({
                    "tag": tag,
                    "display": display,
                    "count": None,
                    "type": "filter"
                })

    # Get tag categories from database
    with get_db_connection() as conn:
        cursor = conn.execute("""
            SELECT t.name, t.category, COUNT(it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE LOWER(t.name) LIKE ?
            GROUP BY t.name, t.category
            ORDER BY count DESC
            LIMIT 20
        """, (f"%{search_token}%",))
        tag_results = cursor.fetchall()

    # Group tags by category
    tag_categories = {}
    for row in tag_results:
        tag_name = row['name']
        category = row['category'] or 'general'
        count = row['count']

        if category not in tag_categories:
            tag_categories[category] = []

        tag_lower = tag_name.lower()
        is_prefix = tag_lower.startswith(search_token)

        # If this was a negative search, prepend '-' to the tag and don't use category
        if is_negative_search:
            final_tag = f"-{tag_name}"
            final_display = f"-{tag_name}"
            final_category = None  # Don't use category prefix for negative tags
        else:
            final_tag = tag_name
            final_display = tag_name
            final_category = category

        tag_categories[category].append({
            "tag": final_tag,
            "display": final_display,
            "count": count,
            "category": final_category,
            "type": "tag",
            "is_prefix": is_prefix
        })

    # Sort categories by priority and build tag groups
    category_priority = ['character', 'copyright', 'artist', 'species', 'general', 'meta']

    for category in category_priority:
        if category not in tag_categories:
            continue

        # Sort: prefix matches first, then by count
        sorted_tags = sorted(
            tag_categories[category],
            key=lambda x: (not x['is_prefix'], -x['count'])
        )

        groups["Tags"].extend(sorted_tags[:5])

    # Build response with only non-empty groups
    response_groups = []
    for group_name, items in groups.items():
        if items:
            response_groups.append({
                "name": group_name,
                "items": items[:10]
            })

    return jsonify({"groups": response_groups})


def saucenao_apply_service():
    """Service to apply selected metadata and download the new image."""
    data = request.json
    if data.get('secret', '') != RELOAD_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    original_filepath = data.get('filepath', '').replace('images/', '', 1)
    source = data.get('source')
    post_id = data.get('post_id')
    download_image = data.get('download_image', False)
    image_url = data.get('image_url')

    if not all([original_filepath, source, post_id]):
        return jsonify({"error": "Missing required parameters"}), 400

    new_full_path = None
    redirect_url = None
    
    try:
        # Step 1: Delete the old database entry
        models.delete_image(original_filepath)
        
        # Step 2: Handle the image file
        old_full_path = os.path.join("static/images", original_filepath)
        
        if download_image and image_url:
            # Download new image to a new path
            new_filename = os.path.basename(urlparse(image_url).path)
            new_full_path = os.path.join("static/images", new_filename)
            
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            with open(new_full_path, 'wb') as f:
                f.write(response.content)

            # If download is successful, remove the old file and its thumbnail
            if os.path.exists(old_full_path):
                os.remove(old_full_path)
            old_thumb_path = os.path.join("static", get_thumbnail_path(f"images/{original_filepath}"))
            if os.path.exists(old_thumb_path):
                os.remove(old_thumb_path)
            
            # Set the path to be processed to the new file
            path_to_process = new_full_path
            redirect_url = url_for('main.show_image', filepath=os.path.join("images", new_filename))

        else:
            # Use the existing file
            path_to_process = old_full_path
            redirect_url = url_for('main.show_image', filepath=os.path.join("images", original_filepath))

        # Step 3: Process the image file (either the new one or the old one)
        if processing.process_image_file(path_to_process):
            # Selective reload: only update this image and tag counts
            rel_path = os.path.relpath(path_to_process, "static/images").replace('\\', '/')
            models.reload_single_image(rel_path)
            models.reload_tag_counts()
            from repositories.data_access import get_image_details
            get_image_details.cache_clear()
            return jsonify({
                "status": "success",
                "redirect_url": redirect_url
            })
        else:
            raise Exception("Failed to process and save the new image to the database.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Clean up downloaded file on failure
        if new_full_path and os.path.exists(new_full_path):
            os.remove(new_full_path)
        return jsonify({"error": str(e)}), 500


def retry_tagging_service():
    """Service to retry tagging for an image that was previously tagged with local_tagger."""
    data = request.json
    filepath = data.get('filepath', '').replace('images/', '', 1)
    skip_local_fallback = data.get('skip_local_fallback', False)

    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400

    try:
        # Check if the image exists and was tagged with local_tagger
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, md5, active_source, filepath
                FROM images
                WHERE filepath = ?
            """, (filepath,))
            result = cursor.fetchone()

            if not result:
                return jsonify({"error": "Image not found in database"}), 404

            image_id = result['id']
            md5 = result['md5']
            active_source = result['active_source']

            # Log the retry attempt
            mode = "online-only" if skip_local_fallback else "with fallback"
            print(f"[Retry Tagging] Processing: {filepath} (current source: {active_source}, mode: {mode})")

        # Construct full filepath
        full_path = os.path.join("static/images", filepath)
        if not os.path.exists(full_path):
            return jsonify({"error": "Image file not found on disk"}), 404

        # Try to fetch metadata from online sources first
        all_results = processing.search_all_sources(md5)
        saucenao_response = None
        used_saucenao = False
        used_local_tagger = False

        # If MD5 lookup failed, try SauceNao
        if not all_results:
            print(f"[Retry Tagging] MD5 lookup failed, trying SauceNao...")
            saucenao_response = processing.search_saucenao(full_path)
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
                                print(f"[Retry Tagging] Found high-confidence match on {source} via SauceNao.")
                                fetched_data = processing.fetch_by_post_id(source, post_id)
                                if fetched_data:
                                    all_results[fetched_data['source']] = fetched_data['data']
                                    break
                        if all_results:
                            break

        # If still no results and fallback is allowed, use local tagger
        if not all_results and not skip_local_fallback:
            print(f"[Retry Tagging] All online searches failed, falling back to local AI tagger...")
            local_tagger_result = processing.tag_with_local_tagger(full_path)
            used_local_tagger = True
            if local_tagger_result:
                all_results[local_tagger_result['source']] = local_tagger_result['data']
                print(f"[Retry Tagging] Tagged with Local Tagger.")

        if not all_results:
            if skip_local_fallback:
                return jsonify({
                    "error": "No online sources found. Current tags preserved.",
                    "status": "no_online_results"
                }), 200
            else:
                return jsonify({
                    "error": "No metadata found from any source",
                    "status": "no_results"
                }), 200

        # Determine the primary source based on priority
        import config
        primary_source_data = None
        source_name = None
        priority = config.BOORU_PRIORITY
        for src in priority:
            if src in all_results:
                primary_source_data = all_results[src]
                source_name = src
                break

        # Extract tags from the primary source
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

        # Deduplicate tags across categories
        character_set = set(tags_character.split())
        copyright_set = set(tags_copyright.split())
        artist_set = set(tags_artist.split())
        species_set = set(tags_species.split())
        meta_set = set(tags_meta.split())
        general_set = set(tags_general.split())

        general_set -= (character_set | copyright_set | artist_set | meta_set | species_set)

        categorized_tags = {
            'tags_character': ' '.join(sorted(character_set)),
            'tags_copyright': ' '.join(sorted(copyright_set)),
            'tags_artist': ' '.join(sorted(artist_set)),
            'tags_species': ' '.join(sorted(species_set)),
            'tags_meta': ' '.join(sorted(meta_set)),
            'tags_general': ' '.join(sorted(general_set))
        }

        # Update the database
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Update the images table with new tags and active source
            cursor.execute("""
                UPDATE images
                SET tags_character = ?,
                    tags_copyright = ?,
                    tags_artist = ?,
                    tags_species = ?,
                    tags_meta = ?,
                    tags_general = ?,
                    active_source = ?,
                    saucenao_lookup = ?
                WHERE id = ?
            """, (
                categorized_tags['tags_character'],
                categorized_tags['tags_copyright'],
                categorized_tags['tags_artist'],
                categorized_tags['tags_species'],
                categorized_tags['tags_meta'],
                categorized_tags['tags_general'],
                source_name,
                used_saucenao,
                image_id
            ))

            # Update or create raw_metadata entry
            raw_metadata_to_save = {
                "md5": md5,
                "relative_path": filepath,
                "saucenao_lookup": used_saucenao,
                "saucenao_response": saucenao_response,
                "local_tagger_lookup": used_local_tagger,
                "sources": all_results
            }

            cursor.execute("SELECT image_id FROM raw_metadata WHERE image_id = ?", (image_id,))
            raw_meta_result = cursor.fetchone()

            if raw_meta_result:
                cursor.execute("""
                    UPDATE raw_metadata
                    SET data = ?
                    WHERE image_id = ?
                """, (json.dumps(raw_metadata_to_save), image_id))
            else:
                cursor.execute("""
                    INSERT INTO raw_metadata (image_id, data)
                    VALUES (?, ?)
                """, (image_id, json.dumps(raw_metadata_to_save)))

            # Delete old image_tags entries and insert new ones
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))

            # Insert new tags for each category
            for category_key, tags_str in categorized_tags.items():
                if not tags_str or not tags_str.strip():
                    continue

                category_name = category_key.replace('tags_', '')
                tags = [t.strip() for t in tags_str.split() if t.strip()]

                for tag_name in tags:
                    # Get or create tag with proper category
                    cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                    tag_result = cursor.fetchone()

                    if tag_result:
                        tag_id = tag_result['id']
                        cursor.execute("UPDATE tags SET category = ? WHERE id = ?", (category_name, tag_id))
                    else:
                        cursor.execute(
                            "INSERT INTO tags (name, category) VALUES (?, ?)",
                            (tag_name, category_name)
                        )
                        tag_id = cursor.lastrowid

                    # Link tag to image
                    cursor.execute(
                        "INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                        (image_id, tag_id)
                    )

            # Update image_sources table
            cursor.execute("DELETE FROM image_sources WHERE image_id = ?", (image_id,))
            for src_name in all_results.keys():
                cursor.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (src_name,))
                cursor.execute("SELECT id FROM sources WHERE name = ?", (src_name,))
                source_id = cursor.fetchone()['id']
                cursor.execute(
                    "INSERT INTO image_sources (image_id, source_id) VALUES (?, ?)",
                    (image_id, source_id)
                )

            conn.commit()

        # Reload the image data in memory
        models.reload_single_image(filepath)
        models.reload_tag_counts()
        from repositories.data_access import get_image_details
        get_image_details.cache_clear()

        print(f"[Retry Tagging] Successfully updated tags for {filepath} (new source: {source_name})")

        return jsonify({
            "status": "success",
            "message": f"Successfully retagged from {source_name}",
            "new_source": source_name,
            "old_source": active_source,
            "tag_count": sum(len(tags_str.split()) for tags_str in categorized_tags.values() if tags_str)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def bulk_retry_tagging_service():
    """Service to retry tagging for all images that were tagged with local_tagger."""
    data = request.json or {}
    skip_local_fallback = data.get('skip_local_fallback', False)

    try:
        # Get all images that were tagged with local_tagger
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, filepath, md5, active_source
                FROM images
                WHERE active_source IN ('local_tagger', 'camie_tagger')
                ORDER BY id
            """)
            local_tagged_images = cursor.fetchall()

        if not local_tagged_images:
            return jsonify({
                "status": "success",
                "message": "No locally tagged images found",
                "total": 0,
                "success": 0,
                "failed": 0,
                "still_local": 0
            })

        total = len(local_tagged_images)
        success_count = 0
        failed_count = 0
        still_local_count = 0
        results = []

        mode = "online-only" if skip_local_fallback else "with fallback"
        print(f"[Bulk Retry Tagging] Starting bulk retry for {total} images (mode: {mode})...")

        for image in local_tagged_images:
            filepath = image['filepath']
            md5 = image['md5']
            image_id = image['id']

            try:
                print(f"[Bulk Retry Tagging] Processing: {filepath}")

                # Construct full filepath
                full_path = os.path.join("static/images", filepath)
                if not os.path.exists(full_path):
                    print(f"[Bulk Retry Tagging] File not found: {filepath}")
                    failed_count += 1
                    results.append({"filepath": filepath, "status": "file_not_found"})
                    continue

                # Try to fetch metadata from online sources
                all_results = processing.search_all_sources(md5)
                used_saucenao = False
                saucenao_response = None

                # If MD5 lookup failed, try SauceNao
                if not all_results:
                    saucenao_response = processing.search_saucenao(full_path)
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
                                        fetched_data = processing.fetch_by_post_id(source, post_id)
                                        if fetched_data:
                                            all_results[fetched_data['source']] = fetched_data['data']
                                            break
                                if all_results:
                                    break

                # If still no results and fallback allowed, try local tagger
                if not all_results and not skip_local_fallback:
                    local_tagger_result = processing.tag_with_local_tagger(full_path)
                    if local_tagger_result:
                        all_results[local_tagger_result['source']] = local_tagger_result['data']
                        print(f"[Bulk Retry Tagging] Re-tagged with Local Tagger: {filepath}")

                # If still no results, skip (keep as local)
                if not all_results:
                    print(f"[Bulk Retry Tagging] No sources found for {filepath}, keeping as local")
                    still_local_count += 1
                    results.append({"filepath": filepath, "status": "still_local"})
                    continue

                # Determine the primary source based on priority
                import config
                primary_source_data = None
                source_name = None
                priority = config.BOORU_PRIORITY
                for src in priority:
                    if src in all_results:
                        primary_source_data = all_results[src]
                        source_name = src
                        break

                # Extract and update tags (same as single retry)
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

                # Deduplicate tags
                character_set = set(tags_character.split())
                copyright_set = set(tags_copyright.split())
                artist_set = set(tags_artist.split())
                species_set = set(tags_species.split())
                meta_set = set(tags_meta.split())
                general_set = set(tags_general.split())
                general_set -= (character_set | copyright_set | artist_set | meta_set | species_set)

                categorized_tags = {
                    'tags_character': ' '.join(sorted(character_set)),
                    'tags_copyright': ' '.join(sorted(copyright_set)),
                    'tags_artist': ' '.join(sorted(artist_set)),
                    'tags_species': ' '.join(sorted(species_set)),
                    'tags_meta': ' '.join(sorted(meta_set)),
                    'tags_general': ' '.join(sorted(general_set))
                }

                # Update database
                with get_db_connection() as conn:
                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE images
                        SET tags_character = ?,
                            tags_copyright = ?,
                            tags_artist = ?,
                            tags_species = ?,
                            tags_meta = ?,
                            tags_general = ?,
                            active_source = ?,
                            saucenao_lookup = ?
                        WHERE id = ?
                    """, (
                        categorized_tags['tags_character'],
                        categorized_tags['tags_copyright'],
                        categorized_tags['tags_artist'],
                        categorized_tags['tags_species'],
                        categorized_tags['tags_meta'],
                        categorized_tags['tags_general'],
                        source_name,
                        used_saucenao,
                        image_id
                    ))

                    # Update raw_metadata
                    raw_metadata_to_save = {
                        "md5": md5,
                        "relative_path": filepath,
                        "saucenao_lookup": used_saucenao,
                        "saucenao_response": saucenao_response,
                        "local_tagger_lookup": False,
                        "sources": all_results
                    }

                    cursor.execute("SELECT image_id FROM raw_metadata WHERE image_id = ?", (image_id,))
                    if cursor.fetchone():
                        cursor.execute("UPDATE raw_metadata SET data = ? WHERE image_id = ?",
                                     (json.dumps(raw_metadata_to_save), image_id))
                    else:
                        cursor.execute("INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)",
                                     (image_id, json.dumps(raw_metadata_to_save)))

                    # Update tags
                    cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
                    for category_key, tags_str in categorized_tags.items():
                        if not tags_str or not tags_str.strip():
                            continue
                        category_name = category_key.replace('tags_', '')
                        tags_list = [t.strip() for t in tags_str.split() if t.strip()]
                        for tag_name in tags_list:
                            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                            tag_result = cursor.fetchone()
                            if tag_result:
                                tag_id = tag_result['id']
                                cursor.execute("UPDATE tags SET category = ? WHERE id = ?", (category_name, tag_id))
                            else:
                                cursor.execute("INSERT INTO tags (name, category) VALUES (?, ?)", (tag_name, category_name))
                                tag_id = cursor.lastrowid
                            cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)", (image_id, tag_id))

                    # Update image_sources
                    cursor.execute("DELETE FROM image_sources WHERE image_id = ?", (image_id,))
                    for src_name in all_results.keys():
                        cursor.execute("INSERT OR IGNORE INTO sources (name) VALUES (?)", (src_name,))
                        cursor.execute("SELECT id FROM sources WHERE name = ?", (src_name,))
                        source_id = cursor.fetchone()['id']
                        cursor.execute("INSERT INTO image_sources (image_id, source_id) VALUES (?, ?)", (image_id, source_id))

                    conn.commit()

                success_count += 1
                results.append({"filepath": filepath, "status": "success", "new_source": source_name})
                print(f"[Bulk Retry Tagging] Success: {filepath} -> {source_name}")

            except Exception as e:
                print(f"[Bulk Retry Tagging] Error processing {filepath}: {e}")
                failed_count += 1
                results.append({"filepath": filepath, "status": "error", "error": str(e)})

        # Reload data after bulk operation
        print(f"[Bulk Retry Tagging] Reloading data...")
        models.reload_single_image(None)  # Reload all
        models.reload_tag_counts()
        from repositories.data_access import get_image_details
        get_image_details.cache_clear()

        print(f"[Bulk Retry Tagging] Complete: {success_count} success, {still_local_count} still local, {failed_count} failed")

        return jsonify({
            "status": "success",
            "message": f"Bulk retry complete: {success_count} images updated",
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "still_local": still_local_count,
            "results": results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
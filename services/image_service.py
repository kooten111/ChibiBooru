from quart import request, jsonify, url_for
from database import models
from database import get_db_connection
from services import processing
from utils import get_thumbnail_path
from utils.file_utils import normalize_image_path, get_bucketed_thumbnail_path_on_disk
from utils.tag_extraction import (
    extract_tags_from_source,
    extract_rating_from_source,
    merge_tag_sources,
    deduplicate_categorized_tags
)
from typing import Dict, Any, List, Optional, Tuple
import os
import json
import random
import requests
import asyncio
import uuid

def get_images_for_api(search_query: str, page: int, seed: Optional[int]) -> Dict[str, Any]:
    """Service for the infinite scroll API."""
    from services import query_service  # Import here to avoid circular import
    
    per_page = 50

    # Use the same search logic as the main page for consistency
    search_results, should_shuffle = query_service.perform_search(search_query)

    if should_shuffle and seed is not None:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    total_pages = (total_results + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    from core.cache_manager import get_image_tags_as_string, remove_image_from_cache
    
    # Process images directly (already running in thread)
    images_page = _process_images_for_api(search_results[start_idx:end_idx])
    
    return {
        "images": images_page,
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results,
        "has_more": page < total_pages
    }

def _process_images_for_api(images):
    from core.cache_manager import get_image_tags_as_string
    return [
        {"path": f"images/{img['filepath']}", "thumb": get_thumbnail_path(f"images/{img['filepath']}"), "tags": get_image_tags_as_string(img)}
        for img in images
    ]


def delete_image_service(data: Dict[str, Any]) -> Dict[str, Any]:
    """Service to delete an image and its data."""
    # The filepath from the frontend is 'images/folder/image.jpg'
    # We need the path relative to the 'static/images' directory, which is 'folder/image.jpg'
    filepath = normalize_image_path(data.get('filepath', ''))

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
        
        # Construct the bucketed thumbnail path
        thumb_path = get_bucketed_thumbnail_path_on_disk(filepath)

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
            remove_image_from_cache(filepath)
            from core.cache_manager import invalidate_tag_cache
            invalidate_tag_cache()

            # Remove upscaled version if it exists
            try:
                from services.upscaler_service import delete_upscaled_image
                delete_upscaled_image(filepath)
            except Exception as e:
                print(f"Failed to delete upscaled image for {filepath}: {e}")
        else:
            print("No database entry or files were found to delete.")


        return {"status": "success", "message": "Deletion process completed."}
    except Exception as e:
        # Log the full error to the console for easier debugging in the future.
        import traceback
        traceback.print_exc()
        print(f"Error deleting image {filepath}: {e}")
        return {"error": "An unexpected error occurred during deletion."}, 500

def delete_images_bulk_service(data: Dict[str, Any]) -> Dict[str, Any]:
    """Service to delete multiple images at once."""
    from utils.validation import validate_list_of_integers, validate_string
    
    # Validate filepaths parameter
    filepaths = data.get('filepaths', [])
    if not filepaths or not isinstance(filepaths, list):
        raise ValueError("filepaths array is required")
    
    # Validate each filepath is a string
    for i, filepath in enumerate(filepaths):
        if not isinstance(filepath, str):
            raise ValueError(f"filepaths[{i}] must be a string")
        validate_string(filepath, f"filepaths[{i}]", min_length=1)

    results = {
        "total": len(filepaths),
        "deleted": 0,
        "failed": 0,
        "errors": []
    }

    for filepath in filepaths:
        # The filepath from the frontend is 'images/folder/image.jpg'
        # We need the path relative to the 'static/images' directory
        clean_filepath = normalize_image_path(filepath)

        try:
            # Remove from database
            db_success = models.delete_image(clean_filepath)

            # Construct file paths
            full_image_path = os.path.join("static/images", clean_filepath)
            thumb_path = get_bucketed_thumbnail_path_on_disk(clean_filepath)

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
                remove_image_from_cache(clean_filepath)
                # Remove upscaled version if it exists
                from services.upscaler_service import delete_upscaled_image
                delete_upscaled_image(clean_filepath)
                
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
        from core.cache_manager import invalidate_tag_cache
        invalidate_tag_cache()

    return {
        "status": "success" if results["failed"] == 0 else "partial",
        "message": f"Deleted {results['deleted']} of {results['total']} images",
        "results": results
    }

def prepare_bulk_download(data: Dict[str, Any]) -> Tuple[Any, int]:
    """Prepare a zip file of multiple images."""
    import zipfile
    import io
    from utils.validation import validate_string
    
    filepaths = data.get('filepaths', [])

    if not filepaths or not isinstance(filepaths, list):
        raise ValueError("filepaths array is required")
    
    # Validate each filepath is a string
    for i, filepath in enumerate(filepaths):
        if not isinstance(filepath, str):
            raise ValueError(f"filepaths[{i}] must be a string")
        validate_string(filepath, f"filepaths[{i}]", min_length=1)

    # Create a zip file in memory
    zip_buffer = io.BytesIO()
    
    files_added = 0
    errors = []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filepath in filepaths:
            # The filepath from the frontend is 'images/folder/image.jpg'
            # We need the path relative to the 'static/images' directory
            clean_filepath = normalize_image_path(filepath)
            full_image_path = os.path.join("static/images", clean_filepath)

            try:
                if os.path.exists(full_image_path):
                    # Add file to zip with just the basename to avoid nested folders
                    arcname = os.path.basename(clean_filepath)
                    
                    # Handle duplicate filenames by appending a counter
                    counter = 1
                    original_arcname = arcname
                    while arcname in zip_file.namelist():
                        name, ext = os.path.splitext(original_arcname)
                        arcname = f"{name}_{counter}{ext}"
                        counter += 1
                    
                    zip_file.write(full_image_path, arcname)
                    files_added += 1
                else:
                    errors.append(f"{clean_filepath}: File not found")
            except Exception as e:
                errors.append(f"{clean_filepath}: {str(e)}")

    # Check if any files were added
    if files_added == 0:
        return {
            "error": "No valid images found",
            "errors": errors
        }, 404

    # Seek to the beginning of the buffer
    zip_buffer.seek(0)
    return zip_buffer

def retry_tagging_service(data):
    """Service to retry tagging for an image that was previously tagged with local_tagger."""
    filepath = normalize_image_path(data.get('filepath', ''))
    skip_local_fallback = data.get('skip_local_fallback', False)

    if not filepath:
        return {"error": "Filepath is required"}, 400

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
                return {"error": "Image not found in database"}, 404

            image_id = result['id']
            md5 = result['md5']
            active_source = result['active_source']

            # Log the retry attempt
            mode = "online-only" if skip_local_fallback else "with fallback"
            print(f"[Retry Tagging] Processing: {filepath} (current source: {active_source}, mode: {mode})")

        # Construct full filepath
        full_path = os.path.join("static/images", filepath)
        if not os.path.exists(full_path):
            return {"error": "Image file not found on disk"}, 404

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

        # If SauceNAO failed, try extracting Pixiv ID from filename
        if not all_results:
            filename = os.path.basename(filepath)
            pixiv_id = processing.extract_pixiv_id_from_filename(filename)
            if pixiv_id:
                print(f"[Retry Tagging] Detected Pixiv ID {pixiv_id} from filename, fetching metadata...")
                pixiv_result = processing.fetch_pixiv_metadata(pixiv_id)
                if pixiv_result:
                    all_results[pixiv_result['source']] = pixiv_result['data']
                    print(f"[Retry Tagging] Tagged from Pixiv: {len([t for v in pixiv_result['data']['tags'].values() for t in v])} tags found.")

                    # Complement Pixiv with local tagger
                    print(f"[Retry Tagging] Pixiv source found, complementing with local AI tagger...")
                    local_tagger_result = processing.tag_with_local_tagger(full_path)
                    used_local_tagger = True
                    if local_tagger_result:
                        all_results[local_tagger_result['source']] = local_tagger_result['data']
                        print(f"[Retry Tagging] Tagged with Local Tagger (complementing Pixiv): {len([t for v in local_tagger_result['data']['tags'].values() for t in v])} tags found.")

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
                return {
                    "error": "No online sources found. Current tags preserved.",
                    "status": "no_online_results"
                }, 200
            else:
                return {
                    "error": "No metadata found from any source",
                    "status": "no_results"
                }, 200

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

        # Extract tags from primary source using centralized utility
        categorized_tags = extract_tags_from_source(primary_source_data, source_name)

        # Special case: If Pixiv is the source, merge with local tagger tags
        if source_name == 'pixiv' and 'local_tagger' in all_results:
            print("[Retry Tagging] Merging local tagger tags into Pixiv tags...")
            local_tagger_tags = extract_tags_from_source(all_results['local_tagger'], 'local_tagger')
            # Merge all categories except artist (Pixiv artist is usually accurate)
            categorized_tags = merge_tag_sources(
                categorized_tags,
                local_tagger_tags,
                merge_categories=['character', 'copyright', 'species', 'meta', 'general']
            )

        # Deduplicate tags across categories
        categorized_tags = deduplicate_categorized_tags(categorized_tags)

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
        from core.cache_manager import invalidate_image_cache
        invalidate_image_cache(filepath)

        print(f"[Retry Tagging] Successfully updated tags for {filepath} (new source: {source_name})")

        return {
            "status": "success",
            "message": f"Successfully retagged from {source_name}",
            "new_source": source_name,
            "old_source": active_source,
            "tag_count": sum(len(tags_str.split()) for tags_str in categorized_tags.values() if tags_str)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500

async def _process_bulk_retry_tagging_task(task_id: str, task_manager, skip_local_fallback: bool, pixiv_only: bool = False, complement_pixiv: bool = False, reprocess_all: bool = False):
    """Background task to process bulk retry tagging.
    
    Modes:
    - Default: Process locally-tagged images, try online sources, fallback to local if allowed
    - skip_local_fallback: Only try online sources for locally-tagged images
    - pixiv_only: Add local AI tags to Pixiv images (deprecated, use complement_pixiv)
    - complement_pixiv: Try online sources for Pixiv images, fallback to local AI
    - reprocess_all: Full pipeline on ALL images
    """
    
    # Get images based on mode
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if reprocess_all:
            # Process all images
            cursor.execute("""
                SELECT id, filepath, md5, active_source
                FROM images
                ORDER BY id
            """)
        elif pixiv_only or complement_pixiv:
            # Pixiv mode: only process images with Pixiv as active source
            cursor.execute("""
                SELECT id, filepath, md5, active_source
                FROM images
                WHERE active_source = 'pixiv'
                ORDER BY id
            """)
        else:
            # Normal mode: process images with local tagger
            cursor.execute("""
                SELECT id, filepath, md5, active_source
                FROM images
                WHERE active_source IN ('local_tagger', 'camie_tagger')
                ORDER BY id
            """)
        local_tagged_images = cursor.fetchall()

    if not local_tagged_images:
        if reprocess_all:
            mode_name = "any"
        elif pixiv_only or complement_pixiv:
            mode_name = "Pixiv"
        else:
            mode_name = "locally tagged"
        return {
            "status": "success",
            "message": f"No {mode_name} images found",
            "total": 0,
            "success": 0,
            "failed": 0,
            "still_local": 0
        }

    total = len(local_tagged_images)
    success_count = 0
    failed_count = 0
    still_local_count = 0
    results = []

    # Determine processing mode for logging
    if reprocess_all:
        mode = "full-reprocess-all"
    elif complement_pixiv:
        mode = "complement-pixiv"
    elif pixiv_only:
        mode = "pixiv-complement"
    elif skip_local_fallback:
        mode = "online-only"
    else:
        mode = "with fallback"
    
    print(f"[Bulk Retry Tagging] Starting bulk retry for {total} images (mode: {mode})...")

    await task_manager.update_progress(task_id, 0, total, f"Starting bulk retry for {total} images ({mode})")

    for idx, image in enumerate(local_tagged_images, 1):
        filepath = image['filepath']
        md5 = image['md5']
        image_id = image['id']

        # Update progress every 10 images or on first/last
        if idx == 1 or idx == total or idx % 10 == 0:
            await task_manager.update_progress(
                task_id, idx, total,
                f"Processing image {idx}/{total}: {filepath}",
                current_item=filepath
            )
            # Allow other async tasks to run
            await asyncio.sleep(0)

        try:
            print(f"[Bulk Retry Tagging] Processing {idx}/{total}: {filepath}")

            # Construct full filepath
            full_path = os.path.join("static/images", filepath)
            if not os.path.exists(full_path):
                print(f"[Bulk Retry Tagging] File not found: {filepath}")
                failed_count += 1
                results.append({"filepath": filepath, "status": "file_not_found"})
                continue

            all_results = {}
            used_saucenao = False
            saucenao_response = None
            used_local_tagger = False

            if pixiv_only:
                # Old mode: Get existing Pixiv data and complement with local tagger only
                print(f"[Bulk Retry Tagging] Pixiv-only mode: Fetching existing Pixiv metadata...")
                
                # Get existing Pixiv data from raw_metadata
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT data FROM raw_metadata WHERE image_id = ?", (image_id,))
                    raw_meta = cursor.fetchone()
                    if raw_meta:
                        try:
                            raw_data = json.loads(raw_meta['data'])
                            if 'sources' in raw_data and 'pixiv' in raw_data['sources']:
                                all_results['pixiv'] = raw_data['sources']['pixiv']
                                print(f"[Bulk Retry Tagging] Found existing Pixiv data")
                        except (json.JSONDecodeError, KeyError, TypeError):
                            pass
                
                # Run local tagger to complement
                print(f"[Bulk Retry Tagging] Complementing with local AI tagger...")
                local_tagger_result = processing.tag_with_local_tagger(full_path)
                used_local_tagger = True
                if local_tagger_result:
                    all_results[local_tagger_result['source']] = local_tagger_result['data']
                    print(f"[Bulk Retry Tagging] Tagged with Local Tagger (complementing Pixiv): {len([t for v in local_tagger_result['data']['tags'].values() for t in v])} tags found.")
            elif complement_pixiv:
                # New mode: Try online sources first, then fall back to local AI
                print(f"[Bulk Retry Tagging] Complement Pixiv mode: Trying online sources first...")
                
                # Try MD5 lookup first
                all_results = processing.search_all_sources(md5)
                
                # If MD5 failed, try SauceNao
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
                
                # If online sources succeeded, keep Pixiv data but merge with online
                if all_results:
                    # Get existing Pixiv data to preserve
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT data FROM raw_metadata WHERE image_id = ?", (image_id,))
                        raw_meta = cursor.fetchone()
                        if raw_meta:
                            try:
                                raw_data = json.loads(raw_meta['data'])
                                if 'sources' in raw_data and 'pixiv' in raw_data['sources']:
                                    all_results['pixiv'] = raw_data['sources']['pixiv']
                            except (json.JSONDecodeError, KeyError, TypeError):
                                pass
                else:
                    # No online sources found, use local tagger as complement
                    print(f"[Bulk Retry Tagging] No online sources, falling back to local AI...")
                    # Preserve existing Pixiv data
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT data FROM raw_metadata WHERE image_id = ?", (image_id,))
                        raw_meta = cursor.fetchone()
                        if raw_meta:
                            try:
                                raw_data = json.loads(raw_meta['data'])
                                if 'sources' in raw_data and 'pixiv' in raw_data['sources']:
                                    all_results['pixiv'] = raw_data['sources']['pixiv']
                            except (json.JSONDecodeError, KeyError, TypeError):
                                pass
                    
                    local_tagger_result = processing.tag_with_local_tagger(full_path)
                    used_local_tagger = True
                    if local_tagger_result:
                        all_results[local_tagger_result['source']] = local_tagger_result['data']
            else:
                # Normal mode: Try to fetch metadata from online sources
                all_results = processing.search_all_sources(md5)

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

                # If SauceNAO failed, try extracting Pixiv ID from filename
                if not all_results:
                    filename = os.path.basename(filepath)
                    pixiv_id = processing.extract_pixiv_id_from_filename(filename)
                    if pixiv_id:
                        print(f"[Bulk Retry Tagging] Detected Pixiv ID {pixiv_id} from filename, fetching metadata...")
                        pixiv_result = processing.fetch_pixiv_metadata(pixiv_id)
                        if pixiv_result:
                            all_results[pixiv_result['source']] = pixiv_result['data']
                            print(f"[Bulk Retry Tagging] Tagged from Pixiv: {len([t for v in pixiv_result['data']['tags'].values() for t in v])} tags found.")

                            # Complement Pixiv with local tagger
                            print(f"[Bulk Retry Tagging] Pixiv source found, complementing with local AI tagger...")
                            local_tagger_result = processing.tag_with_local_tagger(full_path)
                            used_local_tagger = True
                            if local_tagger_result:
                                all_results[local_tagger_result['source']] = local_tagger_result['data']
                                print(f"[Bulk Retry Tagging] Tagged with Local Tagger (complementing Pixiv): {len([t for v in local_tagger_result['data']['tags'].values() for t in v])} tags found.")

                # If still no results and fallback allowed, try local tagger
                if not all_results and not skip_local_fallback:
                    local_tagger_result = processing.tag_with_local_tagger(full_path)
                    used_local_tagger = True
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

            # Extract tags from primary source using centralized utility
            categorized_tags = extract_tags_from_source(primary_source_data, source_name)

            # Special case: If Pixiv is the source, merge with local tagger tags
            if source_name == 'pixiv' and 'local_tagger' in all_results:
                print("[Bulk Retry Tagging] Merging local tagger tags into Pixiv tags...")
                local_tagger_tags = extract_tags_from_source(all_results['local_tagger'], 'local_tagger')
                # Merge all categories except artist (Pixiv artist is usually accurate)
                categorized_tags = merge_tag_sources(
                    categorized_tags,
                    local_tagger_tags,
                    merge_categories=['character', 'copyright', 'species', 'meta', 'general']
                )

            # Deduplicate tags across categories
            categorized_tags = deduplicate_categorized_tags(categorized_tags)

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
                    "local_tagger_lookup": used_local_tagger,
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
    await task_manager.update_progress(task_id, total, total, "Reloading data and updating tag counts...")
    print(f"[Bulk Retry Tagging] Reloading data...")
    from core.cache_manager import invalidate_all_caches
    invalidate_all_caches()

    print(f"[Bulk Retry Tagging] Complete: {success_count} success, {still_local_count} still local, {failed_count} failed")

    return {
        "status": "success",
        "message": f"Bulk retry complete: {success_count} images updated",
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "still_local": still_local_count,
        "results": results
    }

async def bulk_retry_tagging_service():
    """Service to retry tagging for images (runs as background task).
    
    Request Body (JSON):
        skip_local_fallback: Only try online sources for locally-tagged images
        pixiv_only: Add local AI tags to Pixiv images (deprecated)
        complement_pixiv: Try online sources for Pixiv images, fallback to local AI
        reprocess_all: Full pipeline on ALL images
    """
    from services.background_tasks import task_manager

    data = await request.json or {}
    skip_local_fallback = data.get('skip_local_fallback', False)
    pixiv_only = data.get('pixiv_only', False)
    complement_pixiv = data.get('complement_pixiv', False)
    reprocess_all = data.get('reprocess_all', False)

    # Generate a unique task ID
    task_id = f"bulk_retry_{uuid.uuid4().hex[:8]}"

    try:
        # Start the background task
        await task_manager.start_task(
            task_id,
            _process_bulk_retry_tagging_task,
            skip_local_fallback=skip_local_fallback,
            pixiv_only=pixiv_only,
            complement_pixiv=complement_pixiv,
            reprocess_all=reprocess_all
        )

        return jsonify({
            "status": "started",
            "message": "Bulk retry tagging started in background",
            "task_id": task_id
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

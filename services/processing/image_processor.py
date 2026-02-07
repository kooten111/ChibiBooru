"""
Core image processing logic including tagging, video processing, and main processing pipeline.
"""

import os
import shutil
import subprocess
import config
from database import models
from database import get_db_connection
from utils.file_utils import get_file_md5, sanitize_filename_for_fs
from utils.tag_extraction import (
    extract_tags_from_source,
    extract_rating_from_source,
    merge_tag_sources,
    deduplicate_categorized_tags
)
from utils.logging_config import get_logger
from PIL import Image
from .locks import acquire_processing_lock, release_processing_lock
from .metadata_fetchers import (
    search_all_sources,
    search_saucenao,
    fetch_by_post_id,
    extract_pixiv_id_from_filename,
    fetch_pixiv_metadata
)
from .thumbnail_generator import ensure_thumbnail
from .constants import (
    CHARACTER_THRESHOLD,
    DEFAULT_TAGGER_THRESHOLD,
    DEFAULT_STORAGE_THRESHOLD,
    DEFAULT_VIDEO_FRAMES,
    MAX_COLLISION_ATTEMPTS,
    BUCKET_CHARS,
    MAX_TAGS_FOR_PAIRS,
    SAUCENAO_SIMILARITY_THRESHOLD,
)

logger = get_logger('ProcessingService')

# ML Worker client - always import (no fallback to local loading)
try:
    from ml_worker.client import get_ml_worker_client
    ML_WORKER_AVAILABLE = True
except ImportError:
    ML_WORKER_AVAILABLE = False
    logger.error("ML Worker client not available. ML operations will fail.")
    logger.error("Ensure ml_worker module is installed and accessible.")

# Local tagger configuration
tagger_config = config.get_local_tagger_config()


def tag_with_local_tagger(filepath):
    """
    Tag an image using the local tagger via ML Worker.

    Returns dict with:
      - source: 'local_tagger'
      - data: {tags, tagger_name, all_predictions}
        - tags: categorized tags above display threshold (for active_source use)
        - all_predictions: list of {tag_name, category, confidence} above storage threshold
    """
    if not ML_WORKER_AVAILABLE:
        print(f"[Local Tagger] ERROR: ML Worker not available. Cannot process {os.path.basename(filepath)}")
        return None
    
    print(f"[Local Tagger] Analyzing (via ML Worker): {os.path.basename(filepath)}")
    try:
        client = get_ml_worker_client()
        result = client.tag_image(
            image_path=filepath,
            model_path=tagger_config['model_path'],
            threshold=tagger_config.get('threshold', DEFAULT_TAGGER_THRESHOLD),
            storage_threshold=tagger_config.get('storage_threshold', DEFAULT_STORAGE_THRESHOLD),
            character_threshold=CHARACTER_THRESHOLD,
            metadata_path=tagger_config.get('metadata_path')
        )

        return {
            "source": "local_tagger",
            "data": {
                "tags": result['tags'],
                # Use config's LOCAL_TAGGER_NAME so it's preserved with the image
                "tagger_name": config.LOCAL_TAGGER_NAME,
                "all_predictions": result['all_predictions']
            }
        }
    except Exception as e:
        print(f"[Local Tagger] ML Worker error for {filepath}: {e}")
        print(f"[Local Tagger] ERROR: ML Worker failed. Skipping file.")
        return None  # ML Worker is required - no fallback available


def check_ffmpeg_available():
    """
    Check if ffmpeg and ffprobe are available in PATH.

    Returns:
        Tuple of (ffmpeg_path, ffprobe_path) if both found, or (None, None) with error message printed
    """
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')

    if not ffmpeg_path or not ffprobe_path:
        missing = []
        if not ffmpeg_path:
            missing.append('ffmpeg')
        if not ffprobe_path:
            missing.append('ffprobe')

        print(f"[Video Tagger] ERROR: {' and '.join(missing)} not found in PATH.")
        print(f"[Video Tagger] FFmpeg is required for video processing.")
        print(f"[Video Tagger] Install it using:")
        print(f"[Video Tagger]   - Arch/CachyOS: sudo pacman -S ffmpeg")
        print(f"[Video Tagger]   - Ubuntu/Debian: sudo apt install ffmpeg")
        print(f"[Video Tagger]   - macOS: brew install ffmpeg")
        return None, None

    return ffmpeg_path, ffprobe_path


def tag_video_with_frames(video_filepath, num_frames=DEFAULT_VIDEO_FRAMES):
    """
    Tag a video by extracting multiple frames and merging the tags using ML Worker.

    Args:
        video_filepath: Path to the video file
        num_frames: Number of frames to extract and analyze (default: 5)

    Returns:
        Dictionary with source and merged tag data, or None on failure
    """
    if not ML_WORKER_AVAILABLE:
        print("[Video Tagger] ERROR: ML Worker not available. Cannot process video.")
        return None

    print(f"[Video Tagger] Analyzing video via ML Worker: {os.path.basename(video_filepath)}")

    try:
        client = get_ml_worker_client()
        
        # Call ML Worker to handle extraction and tagging
        result = client.tag_video(
            video_path=os.path.abspath(video_filepath),  # Use absolute path
            num_frames=num_frames,
            model_path=tagger_config['model_path'],
            threshold=tagger_config.get('threshold', DEFAULT_TAGGER_THRESHOLD),
            storage_threshold=tagger_config.get('storage_threshold', DEFAULT_STORAGE_THRESHOLD),
            character_threshold=CHARACTER_THRESHOLD,
            metadata_path=tagger_config.get('metadata_path')
        )
        # Override tagger_name with config value
        result['tagger_name'] = f"{config.LOCAL_TAGGER_NAME} (video)"
        
        return {
            "source": "local_tagger",
            "data": result
        }

    except Exception as e:
        print(f"[Video Tagger] ERROR during video analysis via ML Worker: {e}")
        return None


def extract_tag_data(data, source):
    """Extract categorized tags and metadata from a raw API response."""
    tags_dict = {"character": "", "copyright": "", "artist": "", "meta": "", "general": ""}
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

    elif source == 'pixiv':
        tag_data = data.get("tags", {})
        tags_dict["character"] = " ".join(tag_data.get("character", []))
        tags_dict["copyright"] = " ".join(tag_data.get("copyright", []))
        tags_dict["artist"] = " ".join(tag_data.get("artist", []))
        tags_dict["meta"] = " ".join(tag_data.get("meta", []))
        tags_dict["general"] = " ".join(tag_data.get("general", []))
        tags_dict["species"] = " ".join(tag_data.get("species", []))
        image_url = data.get('image_url')
        preview_url = None  # Pixiv doesn't provide direct preview URLs
        width, height = data.get('width'), data.get('height')
        file_size = None  # Not provided by Pixiv API

    return {
        "tags": tags_dict,
        "image_url": image_url,
        "preview_url": preview_url,
        "width": width, "height": height, "file_size": file_size
    }


def process_image_file(filepath, move_from_ingest=True):
    """
    Process a single image file with unified flow.
    
    This is the main entry point for processing images. It handles:
    1. Pre-flight checks (file exists, MD5 calculation, duplicate detection)
    2. Metadata fetching (MD5 lookup, SauceNao, local tagger)
    3. Hash computation (phash, colorhash, embedding - all in one pass)
    4. File operations (move from ingest if needed)
    5. Database commit (single transaction)
    6. Post-processing (thumbnail, cache updates)
    
    Args:
        filepath: Path to the image file
        move_from_ingest: If True, move file from ingest folder to bucketed structure
        
    Returns:
        Tuple (success, message)
    """
    from utils.file_utils import ensure_bucket_dir, get_hash_bucket
    import hashlib
    
    # ========== STAGE 1: PRE-FLIGHT CHECKS ==========
    # Check if file exists (race condition check for concurrent processing)
    if not os.path.exists(filepath):
        msg = f"[Processing] File not found (likely processed by another thread): {filepath}"
        logger.error(msg)
        return False, msg
    
    filename = os.path.basename(filepath)
    logger.info(f"Starting: {filename}")
    
    # Calculate MD5 immediately
    try:
        md5 = get_file_md5(filepath)
        if md5 is None:
            msg = f"[Processing] ERROR: Failed to calculate MD5 for {filename} (File not found or unreadable)"
            logger.error(msg)
            return False, msg
    except Exception as e:
        msg = f"[Processing] ERROR: Failed to calculate MD5 for {filename}: {e}"
        logger.error(msg)
        return False, msg
    
    # Check for duplicate in database (with lock)
    lock_fd, acquired = acquire_processing_lock(md5)
    if not acquired:
        # Lock not acquired - another thread is processing this MD5
        # But we should still check if this specific file is a duplicate that can be removed
        if models.md5_exists(md5):
            # This file is a duplicate of something already in the database
            existing_filepath = None
            with get_db_connection() as conn:
                row = conn.execute('SELECT filepath FROM images WHERE md5 = ?', (md5,)).fetchone()
                if row:
                    existing_filepath = row['filepath']
            
            # Check that we're not deleting the actual canonical file
            if existing_filepath and os.path.abspath(filepath) != os.path.abspath(os.path.join("static/images", existing_filepath)):
                msg = f"[Processing] Duplicate detected (concurrent): {filename} (same as {os.path.basename(existing_filepath) if existing_filepath else 'existing file'})"
                logger.error(msg)
                
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        print(f"[Processing] Removed duplicate file: {filename}")
                    except Exception as e:
                        print(f"[Processing] WARNING: Could not remove duplicate file {filename}: {e}")
                
                return False, msg
        
        # Not a duplicate, genuinely being processed by another thread
        msg = f"[Processing] Skipped: {filename} (already being processed by another thread)"
        logger.error(msg)
        return False, msg
    
    try:
        # Re-check duplicate inside lock
        if models.md5_exists(md5):
            existing_filepath = None
            with get_db_connection() as conn:
                row = conn.execute('SELECT filepath FROM images WHERE md5 = ?', (md5,)).fetchone()
                if row:
                    existing_filepath = row['filepath']
            
            msg = f"[Processing] Duplicate detected: {filename} (same as {os.path.basename(existing_filepath) if existing_filepath else 'existing file'})"
            logger.error(msg)

            # If this is the canonical file already stored in the DB, do not delete it.
            if existing_filepath:
                canonical_path = os.path.abspath(os.path.join("static/images", existing_filepath))
                if os.path.abspath(filepath) == canonical_path:
                    msg = f"[Processing] Duplicate check hit canonical file, skipping deletion: {filename}"
                    logger.error(msg)
                    return False, msg
            
            # Remove duplicate file if it exists (e.g., ingest copy or stray file)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    print(f"[Processing] Removed duplicate file: {filename}")
                except Exception as e:
                    print(f"[Processing] WARNING: Could not remove duplicate file {filename}: {e}")
            
            return False, msg
        
        # ========== STAGE 2: METADATA FETCHING ==========
        is_video = filepath.lower().endswith(('.mp4', '.webm'))
        is_zip_animation = filepath.lower().endswith('.zip')
        
        # Parallel metadata fetching
        all_results = search_all_sources(md5)
        saucenao_used = False
        local_tagger_used = False
        
        if is_zip_animation:
            # Minimal processing for zip files
            pass
        elif is_video:
            # Video tagging via local tagger
            local_tagger_result = tag_video_with_frames(filepath)
            if local_tagger_result:
                all_results[local_tagger_result['source']] = local_tagger_result['data']
                local_tagger_used = True
            else:
                # FAIL-FAST: Video tagging failed
                msg = f"[Processing] ERROR: Video tagging failed for {filename}. File NOT ingested."
                logger.error(msg)
                return False, msg
        else:
            # Standard image processing
            if not all_results:
                # Try SauceNao if no MD5 match
                saucenao_resp = search_saucenao(filepath)
                if saucenao_resp:
                    saucenao_used = True
                    if 'results' in saucenao_resp:
                        for r in saucenao_resp.get('results', []):
                            if float(r['header']['similarity']) > SAUCENAO_SIMILARITY_THRESHOLD:
                                for url in r['data'].get('ext_urls', []):
                                    post_id, source = None, None
                                    # Parse URL to extract source and post ID
                                    # Use startswith for more secure URL matching
                                    if url.startswith('https://danbooru.donmai.us/'):
                                        post_id = url.split('/posts/')[-1].split('?')[0]
                                        source = 'danbooru'
                                    elif url.startswith('https://e621.net/'):
                                        post_id = url.split('/posts/')[-1].split('?')[0]
                                        source = 'e621'
                                    
                                    if post_id and source:
                                        fetched = fetch_by_post_id(source, post_id)
                                        if fetched:
                                            all_results[fetched['source']] = fetched['data']
                                            break
                                if all_results:
                                    break
                
                # Try Pixiv ID extraction
                if not all_results:
                    pixiv_id = extract_pixiv_id_from_filename(filename)
                    if pixiv_id:
                        pixiv_result = fetch_pixiv_metadata(pixiv_id)
                        if pixiv_result:
                            all_results[pixiv_result['source']] = pixiv_result['data']
            
            # Local tagger logic: Only run if no online sources found or if always-on
            should_run_tagger = False
            if config.LOCAL_TAGGER_ALWAYS_RUN:
                should_run_tagger = True
            elif not all_results:
                should_run_tagger = True
            
            if should_run_tagger:
                lt_res = tag_with_local_tagger(filepath)
                if lt_res:
                    all_results[lt_res['source']] = lt_res['data']
                    local_tagger_used = True
                else:
                    # FAIL-FAST: Local tagger was required but failed
                    msg = f"[Processing] ERROR: Local tagger failed for {filename}. File NOT ingested."
                    logger.error(msg)
                    return False, msg
        
        # Extract zip animation before hash computation (phash/colorhash/dimensions need frames)
        if is_zip_animation:
            from services import zip_animation_service
            extract_result = zip_animation_service.extract_zip_animation(filepath, md5)
            if not extract_result:
                msg = f"[Processing] ERROR: Failed to extract zip animation for {filename}. File NOT ingested."
                logger.error(msg)
                return False, msg
        
        # ========== STAGE 3: HASH COMPUTATION (ALL IN ONE PASS) ==========
        hashes = {}
        from services import similarity_service
        
        # Compute perceptual hash
        phash = similarity_service.compute_phash_for_file(filepath, md5)
        if phash:
            hashes['phash'] = phash
        else:
            # FAIL-FAST: Hash computation is required
            msg = f"[Processing] ERROR: Failed to compute perceptual hash for {filename}. File NOT ingested."
            logger.error(msg)
            return False, msg
        
        # Compute color hash
        colorhash = similarity_service.compute_colorhash_for_file(filepath)
        if colorhash:
            hashes['colorhash'] = colorhash
        # Note: colorhash failure is not fatal, phash is sufficient
        
        # Compute semantic embedding if available
        if similarity_service.SEMANTIC_AVAILABLE:
            engine = similarity_service.get_semantic_engine()
            if not engine.load_model():
                # FAIL-FAST: Similarity is enabled but model failed to load
                print(f"[Processing] ERROR: Failed to load similarity model for {filename}. File NOT ingested.")
                return False, "Failed to load similarity model"
            # For zip animations use first frame path (ML Worker expects an image file)
            embedding_path = filepath
            if is_zip_animation:
                first_frame = zip_animation_service.get_frame_path(md5, 0)
                if first_frame and os.path.exists(first_frame):
                    embedding_path = first_frame
            embedding = engine.get_embedding(embedding_path)
            if embedding is not None:
                hashes['embedding'] = embedding
            else:
                # FAIL-FAST: Similarity is enabled but embedding failed
                msg = f"[Processing] ERROR: Failed to compute similarity embedding for {filename}. File NOT ingested."
                logger.error(msg)
                return False, msg
        
        # ========== STAGE 4: FILE OPERATIONS ==========
        # Determine strict filename (renaming if necessary)
        # Strategy:
        # 1. If in subdirectory of ingest: ParentFolder_-_Filename.ext
        # 2. If in root of ingest: Filename_MD5.ext
        # 3. If not from ingest (e.g. upload): keep original name
        
        final_filename = filename
        if move_from_ingest:
            try:
                abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
                abs_filepath = os.path.abspath(filepath)
                
                # Check if file is inside ingest directory
                if abs_filepath.startswith(abs_ingest):
                    rel_path = os.path.relpath(abs_filepath, abs_ingest)
                    parent_dir = os.path.dirname(rel_path)
                    
                    name_base, name_ext = os.path.splitext(filename)
                    
                    if parent_dir and parent_dir != '.':
                        # Case 1: Subdirectory -> Use immediate parent folder
                        immediate_parent = os.path.basename(parent_dir)
                        final_filename = f"{immediate_parent}_-_{filename}"
                    else:
                        # Case 2: Root of ingest -> Append MD5
                        final_filename = f"{name_base}_{md5}{name_ext}"
                        
                    print(f"[Processing] Renaming {filename} -> {final_filename}")
                    
            except Exception as e:
                print(f"[Processing] WARNING: Error calculating new filename: {e}")
                # Fallback to original filename
                pass

        # Ensure filename fits filesystem limit (e.g. 255 bytes); truncate + hash if too long
        final_filename = sanitize_filename_for_fs(final_filename)

        file_dest = filepath
        if move_from_ingest:
            # Canonical bucket attempt with NEW filename
            canonical_bucket = get_hash_bucket(final_filename, BUCKET_CHARS)
            
            # Find a free filename/bucket
            attempt = 0
            target_filename = final_filename
            final_bucket = canonical_bucket
            
            while True:
                bucket_dir = os.path.join(config.IMAGE_DIRECTORY, final_bucket)
                os.makedirs(bucket_dir, exist_ok=True)
                new_path = os.path.join(bucket_dir, target_filename)
                
                if os.path.exists(new_path):
                    # File exists at this path
                    if get_file_md5(new_path) == md5:
                        # Same file, remove ingest copy
                        try:
                            os.remove(filepath)
                        except Exception as e:
                            print(f"[Processing] WARNING: Failed to remove source file {filepath}: {e}")
                             
                        file_dest = new_path
                        print(f"[Processing] File already at destination: {new_path}")
                        break
                    else:
                        # Different file! Collision!
                        print(f"[Processing] Collision for {target_filename} at bucket {final_bucket}.", 'warning')
                        
                        # Strategy: Append MD5 to filename if not already there
                        name_base, name_ext = os.path.splitext(target_filename)
                        
                        # check if md5 is already in the name to avoid infinite appending
                        if md5 in name_base:
                             # Fallback to bucket iteration if MD5 is already there
                             print(f"[Processing] MD5 already in filename, trying alternate bucket...")
                             attempt += 1
                             salt = f"_collision_{attempt}"
                             alt_hash = hashlib.md5((target_filename + salt).encode()).hexdigest()
                             final_bucket = alt_hash[:BUCKET_CHARS]
                        else:
                             # Append MD5 to filename and try again (this changes the canonical bucket)
                             print(f"[Processing] Appending MD5 to resolve collision...")
                             target_filename = sanitize_filename_for_fs(
                                 f"{name_base}_{md5}{name_ext}"
                             )
                             # Recalculate bucket for the new filename
                             final_bucket = get_hash_bucket(target_filename, BUCKET_CHARS)
                        
                        if attempt > MAX_COLLISION_ATTEMPTS:
                            msg = f"[Processing] ERROR: Too many filename collisions for {filename} (gave up after {MAX_COLLISION_ATTEMPTS} attempts)"
                            logger.error(msg)
                            return False, msg
                else:
                    # Found a free slot!
                    try:
                        shutil.move(filepath, new_path)
                        file_dest = new_path
                        print(f"[Processing] Moved to: {new_path}")
                        break
                    except Exception as e:
                        msg = f"[Processing] ERROR: Failed to move file to {new_path}: {e}"
                        logger.error(msg)
                        return False, msg
        
        db_path = os.path.relpath(file_dest, "static/images").replace('\\', '/')
        
        # ========== STAGE 5: DATABASE COMMIT ==========
        # Prepare metadata
        primary_source_data = None
        source_name = None
        priority = config.BOORU_PRIORITY
        for src in priority:
            if src in all_results:
                primary_source_data = all_results[src]
                source_name = src
                break
        
        # Check if we should merge multiple booru sources
        # Count how many "real" booru sources we have (excluding local_tagger which is AI-generated)
        booru_sources = [s for s in all_results.keys() if s not in ('local_tagger', 'camie_tagger')]
        should_merge_sources = (
            config.USE_MERGED_SOURCES_BY_DEFAULT and
            len(booru_sources) > 1
        )
        
        if should_merge_sources:
            # Merge tags from all booru sources
            from utils.tag_extraction import merge_multiple_tag_sources
            # Build a dict of only booru sources for merging
            booru_results = {k: v for k, v in all_results.items() if k in booru_sources}
            extracted_tags = merge_multiple_tag_sources(booru_results)
            extracted_tags = deduplicate_categorized_tags(extracted_tags)
            source_name = 'merged'
            logger.info(f"Merged tags from sources: {list(booru_results.keys())}")
        elif source_name == 'pixiv' and 'local_tagger' in all_results:
            # Merge Pixiv + Local Tagger if needed
            extracted_tags = extract_tags_from_source(primary_source_data, source_name)
            local_tagger_tags = extract_tags_from_source(all_results['local_tagger'], 'local_tagger')
            extracted_tags = merge_tag_sources(
                extracted_tags,
                local_tagger_tags,
                merge_categories=['character', 'copyright', 'species', 'meta', 'general']
            )
            extracted_tags = deduplicate_categorized_tags(extracted_tags)
        else:
            extracted_tags = extract_tags_from_source(primary_source_data, source_name)
            extracted_tags = deduplicate_categorized_tags(extracted_tags)
        
        categorized_tags = {
            'character': extracted_tags['tags_character'].split(),
            'copyright': extracted_tags['tags_copyright'].split(),
            'artist': extracted_tags['tags_artist'].split(),
            'species': extracted_tags['tags_species'].split(),
            'meta': extracted_tags['tags_meta'].split(),
            'general': extracted_tags['tags_general'].split()
        }
        
        rating, rating_source = extract_rating_from_source(primary_source_data, source_name)
        
        parent_id = primary_source_data.get('parent_id') if primary_source_data else None
        if source_name == 'e621' and primary_source_data:
            parent_id = primary_source_data.get('relationships', {}).get('parent_id')
        
        image_info = {
            'filepath': db_path,
            'md5': md5,
            'post_id': primary_source_data.get('id') if primary_source_data else None,
            'parent_id': parent_id,
            'has_children': primary_source_data.get('has_children', False) if primary_source_data else False,
            'saucenao_lookup': saucenao_used,
            'rating': rating,
            'rating_source': rating_source,
            'image_width': None,
            'image_height': None,
        }
        
        # Get image dimensions using PIL
        try:
            if is_zip_animation:
                # For zip animations, get dimensions from first frame
                from services import zip_animation_service
                first_frame = zip_animation_service.get_frame_path(md5, 0)
                if first_frame and os.path.exists(first_frame):
                    with Image.open(first_frame) as img:
                        image_info['image_width'] = img.width
                        image_info['image_height'] = img.height
            elif is_video:
                # For videos, try to get dimensions using ffprobe
                ffprobe_path = shutil.which('ffprobe')
                if ffprobe_path:
                    result = subprocess.run([
                        ffprobe_path, '-v', 'error', '-select_streams', 'v:0',
                        '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
                        file_dest
                    ], capture_output=True, text=True)
                    if result.returncode == 0 and result.stdout.strip():
                        parts = result.stdout.strip().split(',')
                        if len(parts) == 2:
                            image_info['image_width'] = int(parts[0])
                            image_info['image_height'] = int(parts[1])
            else:
                # Regular image - read dimensions with PIL
                with Image.open(file_dest) as img:
                    image_info['image_width'] = img.width
                    image_info['image_height'] = img.height
        except Exception as e:
            print(f"[Processing] WARNING: Could not read dimensions for {filename}: {e}")
        
        # Add computed hashes to image_info
        if 'phash' in hashes:
            image_info['phash'] = hashes['phash']
        if 'colorhash' in hashes:
            image_info['colorhash'] = hashes['colorhash']
        
        raw_metadata_to_save = {
            "md5": md5,
            "relative_path": db_path,
            "saucenao_lookup": saucenao_used,
            "saucenao_response": None,  # Don't save full response to save space
            "local_tagger_lookup": local_tagger_used,
            "sources": all_results
        }
        
        # Insert into database
        success = models.add_image_with_metadata(
            image_info,
            list(all_results.keys()),
            categorized_tags,
            raw_metadata_to_save
        )
        
        if not success:
            msg = f"[Processing] ERROR: Database insert failed for {filename}"
            logger.error(msg)
            return False, msg

        
        # ========== STAGE 6: POST-PROCESSING ==========
        # Save semantic embedding if computed
        if 'embedding' in hashes:
            try:
                from services import similarity_db
                # Get image ID
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                    row = cursor.fetchone()
                    if row:
                        similarity_db.save_embedding(row['id'], hashes['embedding'])
                        
                        # Compute and cache similarities if cache is enabled
                        if config.SIMILARITY_CACHE_ENABLED:
                            try:
                                from services import similarity_cache
                                # Queue for background processing to not block ingestion
                                # For now, do it inline since we're already in a background thread
                                similarity_cache.compute_and_cache_for_image(
                                    row['id'],
                                    similarity_type='blended',
                                    force=True
                                )
                                print(f"[Processing] Cached similarities for {filename}")
                            except Exception as e:
                                # Don't fail ingestion if caching fails
                                print(f"[Processing] WARNING: Failed to cache similarities for {filename}: {e}")
            except Exception as e:
                print(f"[Processing] WARNING: Failed to save embedding for {filename}: {e}")
        
        # Store tagger predictions if available
        if 'local_tagger' in all_results:
            local_data = all_results['local_tagger']
            all_predictions = local_data.get('all_predictions', [])
            if all_predictions:
                try:
                    from repositories import tagger_predictions_repository
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                        row = cursor.fetchone()
                        if row:
                            tagger_predictions_repository.store_predictions(
                                row['id'], 
                                all_predictions, 
                                local_data.get('tagger_name')
                            )
                except Exception as e:
                    print(f"[Processing] WARNING: Failed to save predictions for {filename}: {e}")
        
        # Generate thumbnail
        # Ensure thumbnail respects the final destination bucket
        ensure_thumbnail(file_dest, md5=md5)
        
        # Apply tag implications if enabled
        if config.APPLY_IMPLICATIONS_ON_INGEST:
            try:
                from repositories.tag_repository import apply_implications_for_image
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM images WHERE filepath = ?", (db_path,))
                    row = cursor.fetchone()
                    if row:
                        if apply_implications_for_image(row['id']):
                            logger.debug(f"Applied tag implications for: {filename}")
            except Exception as e:
                logger.warning(f"Failed to apply implications for {filename}: {e}")
        
        logger.info(f"Successfully processed: {filename}")
        return True, "Successfully processed"
        
    except Exception as e:
        msg = f"[Processing] ERROR processing {filename}: {e}"
        logger.error(msg)
        import traceback
        traceback.print_exc()
        return False, msg
    finally:
        release_processing_lock(lock_fd)

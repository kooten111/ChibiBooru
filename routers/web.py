from quart import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
import random
import asyncio
from functools import wraps
import os
from werkzeug.utils import secure_filename

import config
from database import models
from services import processing_service as processing
from services import query_service, system_service, monitor_service
from utils import get_thumbnail_path
from utils.file_utils import normalize_image_path

main_blueprint = Blueprint('main', __name__)


def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('main.login'))
        return await f(*args, **kwargs)
    return decorated_function

@main_blueprint.route('/login', methods=['GET', 'POST'])
async def login():
    if request.method == 'POST':
        form = await request.form
        if form.get('password') == config.APP_PASSWORD:
            session['logged_in'] = True
            session.permanent = True # Session timeout configured in app.py (4 hours)
            return redirect(url_for('main.home'))
        else:
            await flash('Incorrect password.', 'error')
    return await render_template('login.html', app_name=config.APP_NAME)

@main_blueprint.route('/logout')
async def logout():
    session.pop('logged_in', None)
    await flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))


@main_blueprint.route('/startup')
async def startup():
    """Display startup/loading screen while app initializes."""
    # No authentication required - this is shown during startup
    return await render_template('startup.html', app_name=config.APP_NAME)


# ============================================================================
# Rating Inference UI Routes
# ============================================================================

@main_blueprint.route('/rate/review')
@login_required
async def rate_review():
    """Interactive rating review interface (modern UI)."""
    return await render_template('rate_review_v2.html', app_name=config.APP_NAME)


@main_blueprint.route('/rate/manage')
@login_required
async def rate_manage():
    """Rating management dashboard (modern UI)."""
    return await render_template('rate_manage_v2.html', app_name=config.APP_NAME)


@main_blueprint.route('/rate/review/legacy')
@login_required
async def rate_review_legacy():
    """Legacy interactive rating review interface."""
    return await render_template('rate_review.html', app_name=config.APP_NAME)


@main_blueprint.route('/rate/manage/legacy')
@login_required
async def rate_manage_legacy():
    """Legacy rating management dashboard."""
    return await render_template('rate_manage.html', app_name=config.APP_NAME)


# ============================================================================
# Character Inference UI Routes
# ============================================================================

@main_blueprint.route('/character/manage')
@login_required
async def character_manage():
    """Character management dashboard."""
    return await render_template('character_manage.html', app_name=config.APP_NAME)


# ============================================================================
# Tag Categorization UI Routes
# ============================================================================

@main_blueprint.route('/tag_categorize')
@login_required
async def tag_categorize():
    """Interactive tag categorization interface."""
    return await render_template('tag_categorize.html', app_name=config.APP_NAME)


@main_blueprint.route('/tag_manager')
@login_required
async def tag_manager():
    """Comprehensive tag and image management interface."""
    return await render_template('tag_manager.html', app_name=config.APP_NAME)


@main_blueprint.route('/')
@login_required
async def home():
    search_query = request.args.get('query', '').strip().lower()
    seed = random.randint(1, 1_000_000)

    # Run the heavy sync operations in a thread pool to avoid blocking the event loop
    def prepare_home_data():
        stats = query_service.get_enhanced_stats()
        search_results, should_shuffle = query_service.perform_search(search_query)

        if should_shuffle:
            random.Random(seed).shuffle(search_results)

        from core.cache_manager import get_image_tags_as_string

        total_results = len(search_results)
        images_to_show = [
            {"path": f"images/{img['filepath']}", "thumb": get_thumbnail_path(f"images/{img['filepath']}"), "tags": get_image_tags_as_string(img)}
            for img in search_results[:50]
        ]

        random_tags = []
        if not search_query:
            from core.tag_id_cache import get_tag_counts_as_dict
            tag_counts_dict = get_tag_counts_as_dict()
            if tag_counts_dict:
                available_tags = list(tag_counts_dict.items())
                random_tags = random.sample(available_tags, min(len(available_tags), 30))

        return stats, images_to_show, random_tags, total_results

    stats, images_to_show, random_tags, total_results = await asyncio.to_thread(prepare_home_data)

    return await render_template(
        'index.html',
        images=images_to_show,
        query=search_query,
        random_tags=random_tags,
        stats=stats,
        total_results=total_results,
        seed=seed,
        app_name=config.APP_NAME
    )

@main_blueprint.route('/tags')
@login_required
async def tags_browser():
    # Don't load all tags - they're loaded via JavaScript API
    # Just provide stats for the page
    stats = query_service.get_enhanced_stats()

    # Get random tags for explore section
    from core.tag_id_cache import get_tag_counts_as_dict
    random_tags = []
    tag_counts_dict = get_tag_counts_as_dict()
    if tag_counts_dict:
        available_tags = list(tag_counts_dict.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))

    return await render_template(
        'tags.html',
        all_tags=[],  # Empty - tags loaded via API
        stats=stats,
        query='',
        random_tags=random_tags,
        app_name=config.APP_NAME
    )

@main_blueprint.route('/pools')
@login_required
async def pools_list():
    search_query = request.args.get('query', '').strip()
    stats = query_service.get_enhanced_stats()

    if search_query:
        pools = models.search_pools(search_query)
    else:
        pools = models.get_all_pools()
        # Add image counts to pools
        for pool in pools:
            pool_details = models.get_pool_details(pool['id'])
            pool['image_count'] = len(pool_details['images']) if pool_details else 0

    return await render_template(
        'pools.html',
        pools=pools,
        stats=stats,
        query=search_query,
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/implications')
@login_required
async def implications_manager():
    stats = query_service.get_enhanced_stats()
    return await render_template(
        'implications.html',
        stats=stats,
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/pool/<int:pool_id>')
@login_required
async def view_pool(pool_id):
    pool_details = models.get_pool_details(pool_id)
    if not pool_details:
        await flash('Pool not found.', 'error')
        return redirect(url_for('main.pools_list'))

    stats = query_service.get_enhanced_stats()

    # Transform images for display
    images_to_show = [
        {
            "path": f"images/{img['filepath']}",
            "thumb": get_thumbnail_path(f"images/{img['filepath']}"),
            "sort_order": img['sort_order']
        }
        for img in pool_details['images']
    ]

    return await render_template(
        'pool.html',
        pool=pool_details['pool'],
        images=images_to_show,
        stats=stats,
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/view/<path:filepath>')
@login_required
async def show_image(filepath):
    lookup_path = normalize_image_path(filepath)
    
    # Use the merged tags function to include high-confidence local tagger predictions
    from repositories.data_access import get_image_details_with_merged_tags
    from services import upscaler_service
    
    data = get_image_details_with_merged_tags(lookup_path)
    if not data:
        return "Image not found", 404

    # Check for upscaled version
    upscaled_image_url = upscaler_service.get_upscale_url(lookup_path)

    from core.tag_id_cache import get_tag_count_by_name

    stats = query_service.get_enhanced_stats()

    # Get general tags grouped by their extended categories
    general_tags = sorted((data.get("tags_general") or "").split())

    # Include merged local tagger predictions if available
    merged_general = data.get('merged_general_tags', [])
    if merged_general:
        general_tags = sorted(set(general_tags) | set(merged_general))

    tags_with_extended_categories = models.get_tags_with_extended_categories(general_tags)

    # Group tags by extended category for display
    extended_grouped_tags = {}
    for tag, count, extended_cat in tags_with_extended_categories:
        if extended_cat not in extended_grouped_tags:
            extended_grouped_tags[extended_cat] = []
        extended_grouped_tags[extended_cat].append((tag, count))

    # Keep the old format for backward compatibility (all general tags together)
    tags_with_counts = [(tag, get_tag_count_by_name(tag)) for tag in general_tags if tag]

    # Get rating tags from image_tags table and merge them into meta category
    rating_tags = []
    if data.get('id'):
        from database import get_db_connection
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT t.name
                FROM image_tags it
                JOIN tags t ON it.tag_id = t.id
                WHERE it.image_id = ? AND t.category = 'rating'
            """, (data['id'],))
            rating_tags = [row['name'] for row in cur.fetchall()]

    # Merge rating tags with meta tags
    meta_tags = (data.get("tags_meta") or "").split()
    meta_with_rating = sorted(set(meta_tags) | set(rating_tags))

    categorized_tags = {
        "character": [(t, get_tag_count_by_name(t)) for t in sorted((data.get("tags_character") or "").split()) if t],
        "copyright": [(t, get_tag_count_by_name(t)) for t in sorted((data.get("tags_copyright") or "").split()) if t],
        "artist": [(t, get_tag_count_by_name(t)) for t in sorted((data.get("tags_artist") or "").split()) if t],
        "species": [(t, get_tag_count_by_name(t)) for t in sorted((data.get("tags_species") or "").split()) if t],
        "meta": [(t, get_tag_count_by_name(t)) for t in meta_with_rating if t],
    }

    # Get tags that were added via implication rules (source='implication')
    # Get tags that were added via implication rules (source='implication')
    from repositories.data_access import get_implied_tags_for_image
    implied_tags_map = get_implied_tags_for_image(data.get('id'))
    implied_tag_names = set(implied_tags_map.keys())
    
    # Merge implied tags into display lists ensuring they appear
    for tag_name, info in implied_tags_map.items():
        category = info.get('category')
        extended_cat = info.get('extended_category')
        
        # 1. Update categorized_tags / tags_with_counts (Legacy/Sidebar)
        if category == 'general' or category not in categorized_tags:
            if not any(t[0] == tag_name for t in tags_with_counts):
                tags_with_counts.append((tag_name, get_tag_count_by_name(tag_name)))
                tags_with_counts.sort(key=lambda x: x[0])
        else:
            # Handle standard categories
            current_list = categorized_tags[category]
            if not any(t[0] == tag_name for t in current_list):
                current_list.append((tag_name, get_tag_count_by_name(tag_name)))
                current_list.sort(key=lambda x: x[0])

        # 2. Update extended_grouped_tags (Main Display)
        # Only relevant for general tags, as extended categorization usually applies to them
        if category == 'general':
            if extended_cat not in extended_grouped_tags:
                extended_grouped_tags[extended_cat] = []

            target_list = extended_grouped_tags[extended_cat]
            if not any(t[0] == tag_name for t in target_list):
                 target_list.append((tag_name, get_tag_count_by_name(tag_name)))
                 target_list.sort(key=lambda x: x[0])

    # Fetch family images first to exclude them from similarity results
    parent_child_images = models.get_related_images(data.get('post_id'), data.get('parent_id'))
    parent_child_paths = set()
    for img in parent_child_images:
        img['match_type'] = img['type'] # 'parent' or 'child'
        img['thumb'] = get_thumbnail_path(img['path'])
        
        # Normalize path to include 'images/' prefix for consistency with similarity results
        # DB usually stores bare filename, but similarity/query services return 'images/filename'
        p = img['path']
        if not p.startswith('images/'):
            p = f"images/{p}"
        parent_child_paths.add(p)

    # Get similar images - use mix of visual and tag-based if enabled
    if config.VISUAL_SIMILARITY_ENABLED:
        from services import similarity_service
        
        # Calculate split based on configured weights (total 40)
        total_slots = 40
        total_weight = config.VISUAL_SIMILARITY_WEIGHT + config.TAG_SIMILARITY_WEIGHT
        
        # Avoid division by zero
        if total_weight <= 0:
            v_weight_norm = 0.5
            t_weight_norm = 0.5
        else:
            v_weight_norm = config.VISUAL_SIMILARITY_WEIGHT / total_weight
            t_weight_norm = config.TAG_SIMILARITY_WEIGHT / total_weight
            
        visual_limit = int(total_slots * v_weight_norm)
        tag_limit = total_slots - visual_limit # Assign remainder to tags
        
        # 1. Fetch Visual/Semantic matches (Fetch extra to account for filtering)
        visual_candidates = []
        
        # Try semantic first if enabled and available
        if config.ENABLE_SEMANTIC_SIMILARITY and similarity_service.SEMANTIC_AVAILABLE and visual_limit > 0:
            visual_candidates = similarity_service.find_semantic_similar(lookup_path, limit=visual_limit * 2) 
        
        # Filter out self-match and family from semantic results
        visual_candidates = [
            c for c in visual_candidates 
            if normalize_image_path(c['path']) != lookup_path and c['path'] not in parent_child_paths
        ]

        # Fallback or supplement with visual hash if semantic didn't return enough (or was disabled)
        if len(visual_candidates) < visual_limit and visual_limit > 0:
            remaining = visual_limit - len(visual_candidates)
            hash_candidates = similarity_service.find_similar_images(
                lookup_path, 
                threshold=config.VISUAL_SIMILARITY_THRESHOLD, 
                limit=remaining + 20, # Fetch extra for filtering
                exclude_family=True
            )
            # Add non-duplicate hash candidates
            existing_paths = {c['path'] for c in visual_candidates}
            for hc in hash_candidates:
                # Robust filtering
                hc_path_norm = normalize_image_path(hc['path'])
                if (hc['path'] not in existing_paths 
                    and hc_path_norm != lookup_path
                    and hc['path'] not in parent_child_paths):
                    
                    visual_candidates.append(hc)
            
        # Trim to target limit
        visual_candidates = visual_candidates[:visual_limit]

        # 2. Fetch Tag matches (Fetch extra to account for filtering)
        if tag_limit > 0:
            tag_candidates = query_service.find_related_by_tags(filepath, limit=tag_limit * 2)
            # Filter out self-match and family
            tag_candidates = [
                c for c in tag_candidates 
                if normalize_image_path(c['path']) != lookup_path and c['path'] not in parent_child_paths
            ]
            tag_candidates = tag_candidates[:tag_limit]
        else:
            tag_candidates = []
        
        # 3. Interleave them (Visual, Tag, Visual, Tag...)
        mixed_related = []
        max_len = max(len(visual_candidates), len(tag_candidates))
        
        param_seen_paths = set()
        
        for i in range(max_len):
            # Add visual match
            if i < len(visual_candidates):
                item = visual_candidates[i]
                if item['path'] not in param_seen_paths:
                    mixed_related.append(item)
                    param_seen_paths.add(item['path'])
            
            # Add tag match
            if i < len(tag_candidates):
                item = tag_candidates[i]
                if item['path'] not in param_seen_paths:
                    # ensure consistent structure
                    if 'similarity' not in item:
                        item['similarity'] = item.get('score', 0) # Fallback for tag results
                    mixed_related.append(item)
                    param_seen_paths.add(item['path'])
                    
        similar_images = mixed_related
    else:
        similar_images = query_service.find_related_by_tags(filepath, limit=40)
    
    # Filter similar images to remove any that are already in the parent/child list
    # (Note: we already filtered them from 'mixed' lists above, but 'filtered_similar' variable is used for combination)
    filtered_similar = [img for img in similar_images if img['path'] not in parent_child_paths]

    # Combine the lists, parents/children first
    combined_related = parent_child_images + filtered_similar

    # Get tag deltas for this image
    tag_deltas = models.get_image_deltas(lookup_path)

    # Get thumbnail path for progressive loading
    thumbnail_path = get_thumbnail_path(filepath)

    return await render_template(
        'image.html',
        filepath=filepath,
        thumbnail_path=thumbnail_path,
        tags=tags_with_counts,
        categorized_tags=categorized_tags,
        extended_grouped_tags=extended_grouped_tags,
        metadata=data.get('raw_metadata'),
        family_images=parent_child_images,  # Parent/child for floating badge
        related_images=filtered_similar,     # Only similar images in sidebar
        stats=stats,
        random_tags=[],
        data=data,
        app_name=config.APP_NAME,
        tag_deltas=tag_deltas,

        merged_general_tags=merged_general,  # Pass to template for potential styling
        upscaled_image_url=upscaled_image_url,
        image_pools=models.get_pools_for_image(data['id']) if data and data.get('id') else [],
        implied_tag_names=implied_tag_names  # Tags implied by implication rules
    )

@main_blueprint.route('/similar/<path:filepath>')
@login_required
async def similar(filepath):
    similar_images = query_service.find_related_by_tags(filepath, limit=50)
    stats = query_service.get_enhanced_stats()
    return await render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=stats, show_similarity=True)

@main_blueprint.route('/similar-visual/<path:filepath>')
@login_required
async def similar_visual(filepath):
    """Visual similarity page with adjustable threshold."""
    from services import similarity_service
    from utils import get_thumbnail_path
    
    lookup_path = normalize_image_path(filepath)
    threshold = config.VISUAL_SIMILARITY_THRESHOLD
    exclude_family = True  # Default to excluding family
    
    # Get visually similar images
    similar_images = similarity_service.find_similar_images(
        lookup_path,
        threshold=threshold,
        limit=100,
        exclude_family=exclude_family
    )
    
    stats = query_service.get_enhanced_stats()
    thumbnail_path = get_thumbnail_path(filepath)
    
    return await render_template(
        'similar_visual.html',
        filepath=filepath,
        thumbnail_path=thumbnail_path,
        images=similar_images,
        threshold=threshold,
        exclude_family=exclude_family,
        stats=stats,
        app_name=config.APP_NAME
    )

@main_blueprint.route('/raw/<path:filepath>')
@login_required
async def show_raw_data(filepath):
    lookup_path = normalize_image_path(filepath)
    data = models.get_image_details(lookup_path)
    if not data or not data.get('raw_metadata'):
        return "Raw metadata not found", 404

    raw_metadata = data.get('raw_metadata')
    stats = query_service.get_enhanced_stats()

    return await render_template(
        'raw_data.html',
        filepath=filepath,
        raw_data=raw_metadata,
        stats=stats,
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/upload', methods=['GET', 'POST'])
@login_required
async def upload_image():
    if request.method == 'POST':
        from utils.file_utils import ensure_bucket_dir, get_bucketed_path

        if 'file' not in await request.files:
            return jsonify({"error": "No file part"}), 400

        files = (await request.files).getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "No selected file"}), 400

        processed_count = 0
        last_processed_path = None
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)

                # Save to bucketed directory
                bucket_dir = ensure_bucket_dir(filename, config.IMAGE_DIRECTORY)
                filepath = os.path.join(bucket_dir, filename)
                await file.save(filepath)

                # Process the file (already in bucketed location, so don't move)
                success, msg = processing.process_image_file(filepath, move_from_ingest=False)
                if success:
                    processed_count += 1
                    # Keep track of the last successfully processed image's path
                    # Use bucketed path for URL
                    bucketed_path = get_bucketed_path(filename, "images")
                    last_processed_path = bucketed_path
                else:
                    print(f"Failed to process {filename}: {msg}")

        if processed_count > 0:
            models.load_data_from_db()

        redirect_url = None
        # If any image was processed, generate a URL for the last one
        if last_processed_path:
            redirect_url = url_for('main.show_image', filepath=last_processed_path)

        return jsonify({
            "status": "success",
            "message": f"Successfully processed {processed_count} image(s).",
            "redirect_url": redirect_url
        })

    # GET request renders the upload page
    return await render_template(
        'upload.html',
        stats=query_service.get_enhanced_stats(),
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

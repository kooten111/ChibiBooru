from quart import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from services.switch_source_db import switch_metadata_source_db, merge_all_sources
import random
from functools import wraps
import os
from werkzeug.utils import secure_filename

import config
from database import models
from services import processing_service as processing
from services import query_service, system_service, monitor_service
from utils import get_thumbnail_path

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


# ============================================================================
# Rating Inference UI Routes
# ============================================================================

@main_blueprint.route('/rate/review')
@login_required
async def rate_review():
    """Interactive rating review interface."""
    return await render_template('rate_review.html', app_name=config.APP_NAME)


@main_blueprint.route('/rate/manage')
@login_required
async def rate_manage():
    """Rating management dashboard."""
    return await render_template('rate_manage.html', app_name=config.APP_NAME)


@main_blueprint.route('/')
@login_required
async def home():
    search_query = request.args.get('query', '').strip().lower()
    stats = query_service.get_enhanced_stats()
    seed = random.randint(1, 1_000_000)

    search_results, should_shuffle = query_service.perform_search(search_query)

    if should_shuffle:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    images_to_show = [
        {"path": f"images/{img['filepath']}", "thumb": get_thumbnail_path(f"images/{img['filepath']}"), "tags": img.get('tags', '')}
        for img in search_results[:50]
    ]

    random_tags = []
    tag_counts = models.get_tag_counts()
    if not search_query and tag_counts:
        available_tags = list(tag_counts.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))

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
    all_tags = models.get_all_tags_sorted()
    stats = query_service.get_enhanced_stats()

    # Get random tags for explore section
    random_tags = []
    tag_counts = models.get_tag_counts()
    if tag_counts:
        available_tags = list(tag_counts.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))

    return await render_template(
        'tags.html',
        all_tags=all_tags,
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
    lookup_path = filepath.replace("images/", "", 1)
    data = models.get_image_details(lookup_path)
    if not data:
        return "Image not found", 404

    tag_counts = models.get_tag_counts()
    stats = query_service.get_enhanced_stats()

    general_tags = sorted((data.get("tags_general") or "").split())
    tags_with_counts = [(tag, tag_counts.get(tag, 0)) for tag in general_tags if tag]

    categorized_tags = {
        "character": [(t, tag_counts.get(t, 0)) for t in sorted((data.get("tags_character") or "").split()) if t],
        "copyright": [(t, tag_counts.get(t, 0)) for t in sorted((data.get("tags_copyright") or "").split()) if t],
        "artist": [(t, tag_counts.get(t, 0)) for t in sorted((data.get("tags_artist") or "").split()) if t],
        "species": [(t, tag_counts.get(t, 0)) for t in sorted((data.get("tags_species") or "").split()) if t],
        "meta": [(t, tag_counts.get(t, 0)) for t in sorted((data.get("tags_meta") or "").split()) if t],
    }

    similar_images = query_service.find_related_by_tags(filepath)
    parent_child_images = models.get_related_images(data.get('post_id'), data.get('parent_id'))

    # Add a 'match_type' to parent/child images and get their paths for deduplication
    parent_child_paths = set()
    for img in parent_child_images:
        img['match_type'] = img['type'] # 'parent' or 'child'
        img['thumb'] = get_thumbnail_path(img['path'])
        parent_child_paths.add(img['path'])

    # Filter similar images to remove any that are already in the parent/child list
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
        metadata=data.get('raw_metadata'),
        related_images=combined_related,
        stats=stats,
        random_tags=[],
        data=data,
        app_name=config.APP_NAME,
        tag_deltas=tag_deltas
    )

@main_blueprint.route('/similar/<path:filepath>')
@login_required
async def similar(filepath):
    similar_images = query_service.find_related_by_tags(filepath, limit=50)
    stats = query_service.get_enhanced_stats()
    return await render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=stats, show_similarity=True)

@main_blueprint.route('/raw/<path:filepath>')
@login_required
async def show_raw_data(filepath):
    lookup_path = filepath.replace("images/", "", 1)
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

        files = await request.files.getlist('file')
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
                file.save(filepath)

                # Process the file (already in bucketed location, so don't move)
                if processing.process_image_file(filepath, move_from_ingest=False):
                    processed_count += 1
                    # Keep track of the last successfully processed image's path
                    # Use bucketed path for URL
                    bucketed_path = get_bucketed_path(filename, "images")
                    last_processed_path = bucketed_path

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

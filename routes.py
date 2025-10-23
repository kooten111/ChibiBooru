# routes.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
import random
from functools import wraps
import os
from werkzeug.utils import secure_filename

import config
import models
import processing
from services import query_service, system_service, api_service, monitor_service
from utils import get_thumbnail_path

main_blueprint = Blueprint('main', __name__)
api_blueprint = Blueprint('api', __name__)


# --- Login and Protection ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

@main_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == config.APP_PASSWORD:
            session['logged_in'] = True
            session.permanent = True # Make session last for a long time
            return redirect(url_for('main.home'))
        else:
            flash('Incorrect password.', 'error')
    return render_template('login.html', app_name=config.APP_NAME)

@main_blueprint.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))


# --- Main Page Routes ---

@main_blueprint.route('/')
@login_required
def home():
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

    return render_template(
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
def tags_browser():
    all_tags = models.get_all_tags_sorted()
    stats = query_service.get_enhanced_stats()
    return render_template(
        'tags.html',
        all_tags=all_tags,
        stats=stats,
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/pools')
@login_required
def pools_list():
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

    return render_template(
        'pools.html',
        pools=pools,
        stats=stats,
        query=search_query,
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/pool/<int:pool_id>')
@login_required
def view_pool(pool_id):
    pool_details = models.get_pool_details(pool_id)
    if not pool_details:
        flash('Pool not found.', 'error')
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

    return render_template(
        'pool.html',
        pool=pool_details['pool'],
        images=images_to_show,
        stats=stats,
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )

@main_blueprint.route('/image/<path:filepath>')
@login_required
def show_image(filepath):
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

    return render_template(
        'image.html',
        filepath=filepath,
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
def similar(filepath):
    similar_images = query_service.find_related_by_tags(filepath, limit=50)
    stats = query_service.get_enhanced_stats()
    return render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=stats, show_similarity=True)

@main_blueprint.route('/raw/<path:filepath>')
@login_required
def show_raw_data(filepath):
    lookup_path = filepath.replace("images/", "", 1)
    data = models.get_image_details(lookup_path)
    if not data or not data.get('raw_metadata'):
        return "Raw metadata not found", 404

    raw_metadata = data.get('raw_metadata')
    stats = query_service.get_enhanced_stats()

    return render_template(
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
def upload_image():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        files = request.files.getlist('file')
        if not files or files[0].filename == '':
            return jsonify({"error": "No selected file"}), 400

        processed_count = 0
        last_processed_path = None
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                filepath = os.path.join(config.IMAGE_DIRECTORY, filename)
                file.save(filepath)

                if processing.process_image_file(filepath):
                    processed_count += 1
                    # Keep track of the last successfully processed image's path
                    last_processed_path = f'images/{filename}'

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
    return render_template(
        'upload.html',
        stats=query_service.get_enhanced_stats(),
        query='',
        random_tags=[],
        app_name=config.APP_NAME
    )
# --- API Routes ---

@api_blueprint.route('/images')
def get_images():
    return api_service.get_images_for_api()

@api_blueprint.route('/reload', methods=['POST'])
def reload_data():
    return system_service.reload_data()

@api_blueprint.route('/system/status')
def system_status():
    return system_service.get_system_status()

@api_blueprint.route('/system/logs')
def system_logs():
    return jsonify(monitor_service.get_status().get('logs', []))

@api_blueprint.route('/system/scan', methods=['POST'])
def trigger_scan():
    return system_service.scan_and_process_service()

@api_blueprint.route('/system/rebuild', methods=['POST'])
def trigger_rebuild():
    return system_service.rebuild_service()

@api_blueprint.route('/system/rebuild_categorized', methods=['POST'])
def trigger_rebuild_categorized():
    return system_service.rebuild_categorized_service()
    
@api_blueprint.route('/system/recategorize', methods=['POST'])
def trigger_recategorize():
    return system_service.recategorize_service()

@api_blueprint.route('/system/thumbnails', methods=['POST'])
def trigger_thumbnails():
    return system_service.trigger_thumbnails()

@api_blueprint.route('/system/deduplicate', methods=['POST'])
def deduplicate():
    return system_service.deduplicate_service()
    
@api_blueprint.route('/system/clean_orphans', methods=['POST'])
def clean_orphans():
    return system_service.clean_orphans_service()

@api_blueprint.route('/system/monitor/start', methods=['POST'])
def start_monitor():
    if monitor_service.start_monitor():
        return jsonify({"status": "success", "message": "Monitor started."})
    return jsonify({"error": "Monitor was already running."}), 400

@api_blueprint.route('/system/monitor/stop', methods=['POST'])
def stop_monitor():
    if monitor_service.stop_monitor():
        return jsonify({"status": "success", "message": "Monitor stopped."})
    return jsonify({"error": "Monitor was not running."}), 400

@api_blueprint.route('/edit_tags', methods=['POST'])
def edit_tags():
    return api_service.edit_tags_service()

@api_blueprint.route('/delete_image', methods=['POST'])
def delete_image():
    return api_service.delete_image_service()

@api_blueprint.route('/autocomplete')
def autocomplete():
    return api_service.autocomplete()

@api_blueprint.route('/saucenao/search', methods=['POST'])
def saucenao_search():
    return api_service.saucenao_search_service()

@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
def saucenao_fetch_metadata():
    return api_service.saucenao_fetch_metadata_service()

@api_blueprint.route('/saucenao/apply', methods=['POST'])
def saucenao_apply():
    return api_service.saucenao_apply_service()

@api_blueprint.route('/switch_source', methods=['POST'])
def switch_source():
    from switch_source_db import switch_metadata_source_db

    try:
        data = request.json
        filepath = data.get('filepath')
        source = data.get('source')

        if not filepath or not source:
            return jsonify({"error": "Missing filepath or source"}), 400

        result = switch_metadata_source_db(filepath, source)

        if "error" in result:
            return jsonify(result), 400

        # Selective reload: only update this image
        models.reload_single_image(filepath.replace('images/', '', 1))

        return jsonify(result), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# --- Pool API Routes ---

@api_blueprint.route('/pools/create', methods=['POST'])
def create_pool():
    try:
        data = request.json
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()

        if not name:
            return jsonify({"error": "Pool name is required"}), 400

        pool_id = models.create_pool(name, description)
        return jsonify({"status": "success", "pool_id": pool_id, "message": f"Pool '{name}' created successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/update', methods=['POST'])
def update_pool(pool_id):
    try:
        data = request.json
        name = data.get('name')
        description = data.get('description')

        if not name and not description:
            return jsonify({"error": "At least one field (name or description) is required"}), 400

        models.update_pool(pool_id, name, description)
        return jsonify({"status": "success", "message": "Pool updated successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/delete', methods=['POST'])
def delete_pool(pool_id):
    try:
        models.delete_pool(pool_id)
        return jsonify({"status": "success", "message": "Pool deleted successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/add_image', methods=['POST'])
def add_image_to_pool(pool_id):
    try:
        data = request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.add_image_to_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image added to pool."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/remove_image', methods=['POST'])
def remove_image_from_pool(pool_id):
    try:
        data = request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.remove_image_from_pool(pool_id, image_id)
        return jsonify({"status": "success", "message": "Image removed from pool."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/<int:pool_id>/reorder', methods=['POST'])
def reorder_pool(pool_id):
    try:
        data = request.json
        filepath = data.get('filepath', '').replace('images/', '', 1)
        new_position = data.get('position')

        if new_position is None:
            return jsonify({"error": "Position is required"}), 400

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        models.reorder_pool_images(pool_id, image_id, new_position)
        return jsonify({"status": "success", "message": "Pool reordered successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/pools/for_image', methods=['GET'])
def get_pools_for_image():
    try:
        filepath = request.args.get('filepath', '').replace('images/', '', 1)

        # Get image ID from filepath
        image_data = models.get_image_details(filepath)
        if not image_data:
            return jsonify({"error": "Image not found"}), 404

        image_id = image_data['id']
        pools = models.get_pools_for_image(image_id)
        return jsonify({"pools": pools})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
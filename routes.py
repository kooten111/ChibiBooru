# routes.py
from flask import Blueprint, render_template, request, jsonify
import random

from services import query_service, system_service, api_service, monitor_service
import models
from utils import get_thumbnail_path

main_blueprint = Blueprint('main', __name__)
api_blueprint = Blueprint('api', __name__)

# --- Main Page Routes ---

@main_blueprint.route('/')
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
    )

@main_blueprint.route('/tags')
def tags_browser():
    all_tags = models.get_all_tags_sorted()
    stats = query_service.get_enhanced_stats()
    return render_template(
        'tags.html',
        all_tags=all_tags,
        stats=stats,
        query='',
        random_tags=[] # Not needed for this page
    )

@main_blueprint.route('/image/<path:filepath>')
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

    carousel_images = query_service.find_related_by_tags(filepath)
    related_images = models.get_related_images(data.get('post_id'), data.get('parent_id'))


    return render_template(
        'image.html',
        filepath=filepath,
        tags=tags_with_counts,
        categorized_tags=categorized_tags,
        metadata=data.get('raw_metadata'),
        related_images=related_images,
        carousel_images=carousel_images,
        stats=stats,
        random_tags=[],
        data=data
    )

@main_blueprint.route('/similar/<path:filepath>')
def similar(filepath):
    similar_images = query_service.find_related_by_tags(filepath, limit=50)
    stats = query_service.get_enhanced_stats()
    return render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=stats, show_similarity=True)

@main_blueprint.route('/raw/<path:filepath>')
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
        random_tags=[]
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
        
        # Reload in-memory cache after switching
        models.load_data_from_db()
        
        return jsonify(result), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
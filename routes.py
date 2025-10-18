from flask import Blueprint, render_template, request, jsonify
from services import (
    get_enhanced_stats,
    perform_search,
    get_image_data,
    get_tag_counts,
    get_raw_data,
    get_id_to_path,
    load_metadata,
    get_related_images,
    find_related_by_tags,
    reload_data as reload_data_service,
    trigger_scan as trigger_scan_service,
    trigger_rebuild as trigger_rebuild_service,
    trigger_thumbnails as trigger_thumbnails_service,
    deduplicate as deduplicate_service,
    clean_orphans as clean_orphans_service,
    start_monitor as start_monitor_service,
    stop_monitor as stop_monitor_service,
    saucenao_search as saucenao_search_service,
    saucenao_fetch_metadata as saucenao_fetch_metadata_service,
    saucenao_apply as saucenao_apply_service,
    edit_tags as edit_tags_service,
    delete_image as delete_image_service,
    autocomplete as autocomplete_service,
    find_similar as find_similar_service,
    get_system_status,
)
import random
from utils import get_thumbnail_path

main_blueprint = Blueprint('main', __name__)
api_blueprint = Blueprint('api', __name__)

@main_blueprint.route('/')
def home():
    search_query = request.args.get('query', '').strip().lower()
    per_page = 50
    stats = get_enhanced_stats()
    seed = random.randint(1, 1_000_000)

    search_results, should_shuffle = perform_search(search_query)

    if should_shuffle:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    images_to_show = [
        {"path": img['path'], "thumb": get_thumbnail_path(img['path']), "tags": img.get('tags', '')}
        for img in search_results[:per_page]
    ]

    random_tags = []
    tag_counts = get_tag_counts()
    if not search_query and tag_counts:
        available_tags = list(tag_counts.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))

    return render_template(
        'index.html',
        images=images_to_show,
        query=search_query,
        per_page=per_page,
        random_tags=random_tags,
        stats=stats,
        total_results=total_results,
        seed=seed,
    )

@main_blueprint.route('/image/<path:filepath>')
def show_image(filepath):
    lookup_path = filepath.replace("images/", "", 1)
    raw_data = get_raw_data()
    tag_counts = get_tag_counts()
    id_to_path = get_id_to_path()
    data = raw_data.get(lookup_path, "")
    stats = get_enhanced_stats()

    if isinstance(data, str):
        tag_list = sorted(data.split())
        tags_with_counts = [(tag, tag_counts.get(tag, 0)) for tag in tag_list]
        categorized_tags = None
        post_id = None
        parent_id = None
    else:
        general_tags = sorted(data.get("tags_general", "").split())
        if not general_tags or all(not t for t in general_tags):
            general_tags = sorted(data.get("tags", "").split())
        tags_with_counts = [(tag, tag_counts.get(tag, 0)) for tag in general_tags if tag]
        categorized_tags = {
            "character": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_character", "").split()) if t],
            "copyright": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_copyright", "").split()) if t],
            "artist": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_artist", "").split()) if t],
            "meta": [(t, tag_counts.get(t, 0)) for t in sorted(data.get("tags_meta", "").split()) if t],
        }
        post_id = data.get("id")
        parent_id = data.get("parent_id")

    metadata = load_metadata(filepath)
    related_images = get_related_images(post_id, parent_id, raw_data, id_to_path)
    similar_by_tags = find_related_by_tags(filepath, limit=20)
    carousel_images = [
        {"path": img['path'], "thumb": get_thumbnail_path(img['path']), "match_type": img['match_type']}
        for img in similar_by_tags
    ]

    random_tags = []
    if tag_counts:
        available_tags = list(tag_counts.items())
        random_tags = random.sample(available_tags, min(len(available_tags), 30))

    return render_template(
        'image.html',
        filepath=filepath,
        tags=tags_with_counts,
        categorized_tags=categorized_tags,
        metadata=metadata,
        related_images=related_images,
        carousel_images=carousel_images,
        stats=stats,
        random_tags=random_tags,
    )

@main_blueprint.route('/similar/<path:filepath>')
def similar(filepath):
    return find_similar_service(filepath)


@api_blueprint.route('/images')
def get_images():
    search_query = request.args.get('query', '').strip().lower()
    page = request.args.get('page', 1, type=int)
    per_page = 50
    seed = request.args.get('seed', default=None, type=int)

    search_results, should_shuffle = perform_search(search_query)

    if should_shuffle and seed is not None:
        random.Random(seed).shuffle(search_results)

    total_results = len(search_results)
    total_pages = (total_results + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    images_page = [
        {"path": img['path'], "thumb": get_thumbnail_path(img['path']), "tags": img.get('tags', '')}
        for img in search_results[start_idx:end_idx]
    ]

    return jsonify(
        {"images": images_page, "page": page, "total_pages": total_pages, "total_results": total_results, "has_more": page < total_pages}
    )

@api_blueprint.route('/reload', methods=['POST'])
def reload_data():
    return reload_data_service()

@api_blueprint.route('/system/status')
def system_status():
    return get_system_status()

@api_blueprint.route('/system/scan', methods=['POST'])
def trigger_scan():
    return trigger_scan_service()

@api_blueprint.route('/system/rebuild', methods=['POST'])
def trigger_rebuild():
    return trigger_rebuild_service()

@api_blueprint.route('/system/thumbnails', methods=['POST'])
def trigger_thumbnails():
    return trigger_thumbnails_service()

@api_blueprint.route('/system/deduplicate', methods=['POST'])
def deduplicate():
    return deduplicate_service()

@api_blueprint.route('/system/clean_orphans', methods=['POST'])
def clean_orphans():
    return clean_orphans_service()

@api_blueprint.route('/system/monitor/start', methods=['POST'])
def start_monitor():
    return start_monitor_service()

@api_blueprint.route('/system/monitor/stop', methods=['POST'])
def stop_monitor():
    return stop_monitor_service()

@api_blueprint.route('/edit_tags', methods=['POST'])
def edit_tags():
    return edit_tags_service()

@api_blueprint.route('/delete_image', methods=['POST'])
def delete_image():
    return delete_image_service()

@api_blueprint.route('/autocomplete')
def autocomplete():
    return autocomplete_service()

@api_blueprint.route('/saucenao/search', methods=['POST'])
def saucenao_search():
    return saucenao_search_service()

@api_blueprint.route('/saucenao/fetch_metadata', methods=['POST'])
def saucenao_fetch_metadata():
    return saucenao_fetch_metadata_service()

@api_blueprint.route('/saucenao/apply', methods=['POST'])
def saucenao_apply():
    return saucenao_apply_service()
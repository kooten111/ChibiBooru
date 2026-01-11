"""
Gallery and tag browsing routes.
"""

from quart import render_template, request
import random
import asyncio
import config
from services import query_service
from utils import get_thumbnail_path
from utils.decorators import login_required


def register_routes(blueprint):
    """Register gallery routes on the given blueprint."""
    
    @blueprint.route('/')
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

    @blueprint.route('/tags')
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

    @blueprint.route('/similar/<path:filepath>')
    @login_required
    async def similar(filepath):
        similar_images = query_service.find_related_by_tags(filepath, limit=50)
        stats = query_service.get_enhanced_stats()
        return await render_template('index.html', images=similar_images, query=f"similar:{filepath}", stats=stats, show_similarity=True)

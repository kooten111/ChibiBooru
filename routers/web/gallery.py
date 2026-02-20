"""
Gallery and tag browsing routes.
"""

from quart import render_template, request
import random
import asyncio
import config
from services import query_service, image_service
from utils.decorators import login_required


def register_routes(blueprint):
    """Register gallery routes on the given blueprint."""
    
    @blueprint.route('/')
    @login_required
    async def home():
        search_query = request.args.get('query', '').strip().lower()
        first_page_data = await asyncio.to_thread(
            image_service.get_images_for_api,
            search_query,
            1,
            config.IMAGES_PER_PAGE,
        )

        images_to_show = first_page_data["images"]
        total_results = first_page_data["total_results"]

        return await render_template(
            'index.html',
            images=images_to_show,
            query=search_query,
            total_results=total_results,
            images_per_page=config.IMAGES_PER_PAGE,
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
        cached_images = query_service.find_related_by_tags(filepath, limit=50)
        
        # Create copies to avoid mutating the LRU cache, and rename 'score' to 'similarity'
        similar_images = []
        for img in cached_images:
            new_img = dict(img)
            if 'score' in new_img:
                new_img['similarity'] = new_img.pop('score')
            similar_images.append(new_img)
        
        
        return await render_template(
            'index.html',
            images=similar_images,
            query=f"similar:{filepath}",
            total_results=len(similar_images),
            show_similarity=True,
            images_per_page=config.IMAGES_PER_PAGE,
            app_name=config.APP_NAME
        )


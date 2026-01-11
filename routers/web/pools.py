"""
Pool management routes.
"""

from quart import render_template, request, redirect, url_for, flash
import config
from database import models
from services import query_service
from utils import get_thumbnail_path
from utils.decorators import login_required


def register_routes(blueprint):
    """Register pool management routes on the given blueprint."""
    
    @blueprint.route('/pools')
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

    @blueprint.route('/pool/<int:pool_id>')
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

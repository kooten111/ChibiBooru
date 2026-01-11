"""
Rating inference UI routes.
"""

from quart import render_template
import config
from utils.decorators import login_required


def register_routes(blueprint):
    """Register rating inference UI routes on the given blueprint."""
    
    @blueprint.route('/rate/review')
    @login_required
    async def rate_review():
        """Interactive rating review interface (modern UI)."""
        return await render_template('rate_review.html', app_name=config.APP_NAME)

    @blueprint.route('/rate/manage')
    @login_required
    async def rate_manage():
        """Rating management dashboard (modern UI)."""
        return await render_template('rate_manage.html', app_name=config.APP_NAME)

"""
Web routes package.

This package contains all web UI routes organized by functionality:
- auth: Authentication (login/logout)
- gallery: Gallery and tag browsing
- image_detail: Image viewing and detail pages
- pools: Pool management
- rating: Rating inference UI
- misc: Miscellaneous routes (startup, system, upload, etc.)
"""

from quart import Blueprint
from . import auth, gallery, image_detail, pools, rating, misc

# Create main blueprint
main_blueprint = Blueprint('main', __name__)

# Register all routes directly on the main blueprint
auth.register_routes(main_blueprint)
gallery.register_routes(main_blueprint)
image_detail.register_routes(main_blueprint)
pools.register_routes(main_blueprint)
rating.register_routes(main_blueprint)
misc.register_routes(main_blueprint)

__all__ = ['main_blueprint']

from quart import Blueprint

api_blueprint = Blueprint('api', __name__)

# Import sub-modules to register routes
from . import (
    images,
    tags,
    pools,
    implications,
    system,
    saucenao,
    rating,
    tag_categorization,
    animation,
    favourites,
    similarity,
    tag_manager,
    upscaler
)

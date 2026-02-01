"""
ML Worker Request Handlers
"""
from ml_worker.handlers.animation import handle_extract_animation
from ml_worker.handlers.thumbnail import handle_generate_thumbnail
from ml_worker.handlers.tagging import handle_tag_image, handle_tag_video
from ml_worker.handlers.upscaling import handle_upscale_image
from ml_worker.handlers.similarity import handle_compute_similarity
from ml_worker.handlers.ratings import handle_train_rating_model, handle_infer_ratings
from ml_worker.handlers.system import handle_health_check, handle_rebuild_cache

"""
Rating service package.

This package contains rating inference functionality split into focused modules:
- config: Configuration management
- data: Data retrieval functions
- training: Model training logic
- inference: Rating prediction and inference
- stats: Statistics and analysis
"""

from .config import (
    RATINGS,
    get_model_connection,
    get_config,
    update_config,
    reset_config_to_defaults
)
from .data import (
    get_rated_images,
    get_unrated_images,
    get_unrated_images_count,
    get_unrated_images_batched
)
from .training import (
    calculate_tag_weights,
    find_frequent_tag_pairs,
    calculate_tag_pair_weights,
    train_model
)
from .inference import (
    load_weights,
    calculate_rating_scores,
    scores_to_probabilities,
    predict_rating,
    infer_rating_for_image,
    infer_all_unrated_images,
    precompute_ratings_for_unrated_images,
    set_image_rating
)
from .stats import (
    get_model_stats,
    get_rating_distribution,
    get_top_weighted_tags,
    update_model_metadata,
    get_pending_corrections_count,
    is_model_stale,
    clear_ai_inferred_ratings,
    retrain_and_reapply_all
)

__all__ = [
    'RATINGS',
    'get_model_connection',
    'get_config',
    'update_config',
    'reset_config_to_defaults',
    'get_rated_images',
    'get_unrated_images',
    'get_unrated_images_count',
    'get_unrated_images_batched',
    'calculate_tag_weights',
    'find_frequent_tag_pairs',
    'calculate_tag_pair_weights',
    'train_model',
    'load_weights',
    'calculate_rating_scores',
    'scores_to_probabilities',
    'predict_rating',
    'infer_rating_for_image',
    'infer_all_unrated_images',
    'precompute_ratings_for_unrated_images',
    'set_image_rating',
    'get_model_stats',
    'get_rating_distribution',
    'get_top_weighted_tags',
    'update_model_metadata',
    'get_pending_corrections_count',
    'is_model_stale',
    'clear_ai_inferred_ratings',
    'retrain_and_reapply_all',
]

"""
Repository modules for data access layer.

This package contains focused repository modules extracted from the monolithic
models.py to improve maintainability and testability.
"""

from .pool_repository import (
    create_pool,
    get_all_pools,
    get_pool_details,
    add_image_to_pool,
    remove_image_from_pool,
    delete_pool,
    update_pool,
    reorder_pool_images,
    search_pools,
    get_pools_for_image,
    search_images_by_pool,
)

from .delta_tracker import (
    record_tag_delta,
    compute_tag_deltas,
    apply_tag_deltas,
    get_image_deltas,
)

from .tag_repository import (
    get_tag_counts,
    reload_tag_counts,
    get_all_tags_sorted,
    recategorize_misplaced_tags,
    rebuild_categorized_tags_from_relations,
    add_implication,
    get_implications_for_tag,
    apply_implications_for_image,
    update_image_tags,
    update_image_tags_categorized,
)

__all__ = [
    # Pool repository
    'create_pool',
    'get_all_pools',
    'get_pool_details',
    'add_image_to_pool',
    'remove_image_from_pool',
    'delete_pool',
    'update_pool',
    'reorder_pool_images',
    'search_pools',
    'get_pools_for_image',
    'search_images_by_pool',
    # Delta tracker
    'record_tag_delta',
    'compute_tag_deltas',
    'apply_tag_deltas',
    'get_image_deltas',
    # Tag repository
    'get_tag_counts',
    'reload_tag_counts',
    'get_all_tags_sorted',
    'recategorize_misplaced_tags',
    'rebuild_categorized_tags_from_relations',
    'add_implication',
    'get_implications_for_tag',
    'apply_implications_for_image',
    'update_image_tags',
    'update_image_tags_categorized',
]

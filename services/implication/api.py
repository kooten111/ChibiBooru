"""Public API for implication service."""

from .management import (
    approve_suggestion,
    create_manual_implication,
    delete_implication,
    get_all_implications,
    get_implication_chain,
    get_implications_for_tag,
    get_tags_implying,
    preview_implication_impact,
)
from .suggestions import (
    get_all_suggestions,
    get_paginated_suggestions,
    invalidate_suggestion_cache,
)
from .application import (
    batch_apply_implications_to_all_images,
    apply_single_implication_to_images,
    clear_and_reapply_all_implications,
    clear_implied_tags,
)
from .approval import (
    auto_approve_naming_pattern_suggestions,
    auto_approve_high_confidence_suggestions,
    bulk_approve_implications,
)
from .models import ImplicationSuggestion

__all__ = [
    "approve_suggestion",
    "auto_approve_high_confidence_suggestions",
    "auto_approve_naming_pattern_suggestions",
    "batch_apply_implications_to_all_images",
    "bulk_approve_implications",
    "clear_and_reapply_all_implications",
    "clear_implied_tags",
    "create_manual_implication",
    "delete_implication",
    "get_all_implications",
    "get_all_suggestions",
    "get_implication_chain",
    "get_implications_for_tag",
    "get_paginated_suggestions",
    "get_tags_implying",
    "ImplicationSuggestion",
    "invalidate_suggestion_cache",
    "preview_implication_impact",
    "apply_single_implication_to_images",
]

# Events module for ChibiBooru
# This module provides event-based communication between modules
# to break circular dependencies.

from .cache_events import (
    register_cache_invalidation_callback,
    trigger_cache_invalidation
)

__all__ = [
    'register_cache_invalidation_callback',
    'trigger_cache_invalidation'
]

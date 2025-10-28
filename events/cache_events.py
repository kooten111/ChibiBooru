"""
Cache Events Module

This module provides a publish-subscribe pattern for cache invalidation events,
breaking the circular dependency between models.py and services/query_service.py.

Instead of models.py directly importing and calling query_service.invalidate_similarity_cache(),
it triggers a cache invalidation event that query_service.py can subscribe to.

Usage:
    # In service modules (e.g., query_service.py):
    from events.cache_events import register_cache_invalidation_callback
    register_cache_invalidation_callback(my_invalidation_function)

    # In models.py:
    from events.cache_events import trigger_cache_invalidation
    trigger_cache_invalidation()  # All registered callbacks will be called
"""

# Global list of cache invalidation callbacks
_cache_invalidation_callbacks = []


def register_cache_invalidation_callback(callback):
    """
    Register a callback function to be called when cache invalidation is triggered.

    Args:
        callback: A callable that takes no arguments. Will be called when
                  trigger_cache_invalidation() is invoked.

    Example:
        def my_cache_invalidator():
            print("Cache invalidated!")

        register_cache_invalidation_callback(my_cache_invalidator)
    """
    if callback not in _cache_invalidation_callbacks:
        _cache_invalidation_callbacks.append(callback)


def trigger_cache_invalidation():
    """
    Trigger all registered cache invalidation callbacks.

    This should be called whenever data changes that would affect cached results,
    such as when:
    - Database is reloaded
    - Tags are modified
    - Images are added or removed
    """
    for callback in _cache_invalidation_callbacks:
        try:
            callback()
        except Exception as e:
            # Log the error but don't let one callback failure prevent others from running
            print(f"Warning: Cache invalidation callback failed: {e}")


def clear_all_callbacks():
    """
    Clear all registered callbacks. Primarily for testing purposes.
    """
    global _cache_invalidation_callbacks
    _cache_invalidation_callbacks = []

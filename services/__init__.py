"""
Services package for ChibiBooru.

This module provides centralized business logic services for:
- Image processing and management
- Tag management and categorization
- Query and search operations
- Health checks and monitoring
- Rating inference
- Background tasks
- SauceNAO integration
- System operations
- Tag implications

Note: Some imports are lazy (inside functions) to avoid circular dependencies.
See docs/ARCHITECTURE.md for details on the services layer architecture.
"""

# Note: We intentionally keep imports minimal at the package level to avoid
# circular dependency issues. Service modules should be imported directly
# where needed, e.g., `from services import image_service`

__all__ = [
    'background_tasks',
    'config_service',
    'health_service',
    'image_service',
    'implication_service',
    'monitor_service',
    'priority_service',
    'query_service',
    'rating_service',
    'saucenao_service',
    'switch_source_db',
    'system',
    'tag_categorization_service',
    'tag_service',
]

"""
Request parsing helpers for API routes.

Provides utilities for consistently parsing query parameters and JSON bodies
across routers.
"""

from typing import List, Any, Dict


def get_query_list(request: Any, name: str) -> List[str]:
    """
    Robustly parse a list from query parameters.

    Tries, in order:
    - getlist(name + '[]')  (e.g. source_categories[])
    - getlist(name)         (e.g. source_categories)
    - split on comma if a single string value is present

    Filters out empty strings.

    Args:
        request: Quart/Flask request object (must have request.args).
        name: Parameter name (without brackets).

    Returns:
        List of non-empty strings.
    """
    args = request.args
    values = args.getlist(f"{name}[]")
    if not values:
        values = args.getlist(name)
    if not values and args.get(name) is not None:
        val = args.get(name)
        values = val.split(",") if isinstance(val, str) and val else []
    return [v.strip() for v in values if v and v.strip()]


async def require_json_body(request: Any, message: str = "Request body is required") -> Dict[str, Any]:
    """
    Await request JSON body and return it, or raise ValueError if missing/invalid.

    Use for endpoints that require a JSON body.

    Args:
        request: Quart/Flask request (must support await request.get_json()).
        message: Error message when body is missing.

    Returns:
        Parsed JSON dict.

    Raises:
        ValueError: If body is missing or not a dict.
    """
    data = await request.get_json()
    if not data or not isinstance(data, dict):
        raise ValueError(message)
    return data

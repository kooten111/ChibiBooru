"""
Standardized API response utilities.
All API endpoints should use these functions for consistent response format.
"""

import traceback
from quart import jsonify, Response
from typing import Any, Dict, Optional, Tuple


def success_response(data: Dict[str, Any] = None, message: str = None) -> Response:
    """
    Create a standardized success response.
    
    Args:
        data: Additional data to include in response
        message: Optional success message
    
    Returns:
        Quart jsonify response with 200 status
    
    Example:
        return success_response({"count": 10}, "Operation completed")
        # Returns: {"success": True, "message": "Operation completed", "count": 10}
    """
    response = {"success": True}
    if message:
        response["message"] = message
    if data:
        response.update(data)
    return jsonify(response)


def error_response(error: str, status_code: int = 400, data: Dict[str, Any] = None) -> Tuple[Response, int]:
    """
    Create a standardized error response.
    
    Args:
        error: Error message
        status_code: HTTP status code (default 400)
        data: Additional data to include
    
    Returns:
        Quart jsonify response with specified status code
    
    Example:
        return error_response("Invalid input", 400)
        # Returns: {"success": False, "error": "Invalid input"}, 400
    """
    response = {"success": False, "error": str(error)}
    if data:
        response.update(data)
    return jsonify(response), status_code


def not_found_response(message: str = "Resource not found") -> Tuple[Response, int]:
    """Create a 404 response."""
    return error_response(message, 404)


def unauthorized_response(message: str = "Unauthorized") -> Tuple[Response, int]:
    """Create a 401 response."""
    return error_response(message, 401)


def validation_error_response(message: str, field: str = None) -> Tuple[Response, int]:
    """Create a validation error response."""
    data = {"field": field} if field else None
    return error_response(message, 400, data)


def server_error_response(error: Exception, include_traceback: bool = False) -> Tuple[Response, int]:
    """
    Create a 500 server error response.
    
    Args:
        error: The exception that occurred
        include_traceback: Whether to include traceback (only in debug mode)
    """
    traceback.print_exc()  # Always log to console
    
    data = None
    if include_traceback:
        data = {"traceback": traceback.format_exc()}
    
    return error_response(str(error), 500, data)

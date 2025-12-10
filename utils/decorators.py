"""
Decorators for API endpoints and service functions.

This module provides decorators for consistent error handling,
authentication, and async/sync function wrapping.
"""

from functools import wraps
import traceback
from quart import jsonify, request
from typing import Callable, Any
import asyncio


def api_handler(require_auth: bool = False, log_errors: bool = True):
    """
    Decorator for API endpoints that handles:
    - Exception catching with proper logging
    - Consistent response format
    - Optional authentication check

    Args:
        require_auth: If True, checks for system secret in request
        log_errors: If True, prints traceback on errors

    Usage:
        @api_blueprint.route('/endpoint', methods=['POST'])
        @api_handler(require_auth=True)
        async def my_endpoint():
            # Just the logic, no try/except needed
            return {"data": "value"}  # Auto-wrapped with success=True
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                # Optional auth check
                if require_auth:
                    from config import RELOAD_SECRET
                    secret = request.args.get('secret', '') or request.form.get('secret', '')
                    if secret != RELOAD_SECRET:
                        return jsonify({"success": False, "error": "Unauthorized"}), 401

                # Call the actual function
                result = await func(*args, **kwargs)

                # Auto-wrap dict responses
                if isinstance(result, dict):
                    if 'success' not in result:
                        result = {"success": True, **result}
                    return jsonify(result)

                return result

            except ValueError as e:
                if log_errors:
                    traceback.print_exc()
                return jsonify({"success": False, "error": str(e)}), 400
            except PermissionError as e:
                return jsonify({"success": False, "error": str(e)}), 403
            except FileNotFoundError as e:
                return jsonify({"success": False, "error": str(e)}), 404
            except Exception as e:
                if log_errors:
                    traceback.print_exc()
                return jsonify({"success": False, "error": str(e)}), 500

        return wrapper
    return decorator


def sync_to_async(func: Callable) -> Callable:
    """
    Decorator to run synchronous functions in a thread pool.
    Useful for wrapping sync service functions for async routes.

    Usage:
        @sync_to_async
        def my_sync_function():
            # sync code
            return result
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


def require_secret(func: Callable) -> Callable:
    """
    Decorator that requires system secret for the endpoint.
    Can be used standalone or with api_handler.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from config import RELOAD_SECRET
        secret = request.args.get('secret', '') or request.form.get('secret', '')
        if secret != RELOAD_SECRET:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return await func(*args, **kwargs)
    return wrapper

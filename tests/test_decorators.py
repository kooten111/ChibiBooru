"""
Tests for API decorators
"""
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from quart import Quart, request
from utils.decorators import api_handler, sync_to_async, require_secret


@pytest.fixture
def app():
    """Create a test Quart app."""
    app = Quart(__name__)
    app.config['TESTING'] = True
    return app


class TestApiHandlerDecorator:
    """Test @api_handler decorator."""

    @pytest.mark.asyncio
    async def test_successful_response_wrapping(self, app):
        """Test that dict responses are auto-wrapped with success=True."""
        @api_handler()
        async def test_endpoint():
            return {"data": "value", "count": 10}
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result.get_json()
            
            assert data["success"] is True
            assert data["data"] == "value"
            assert data["count"] == 10

    @pytest.mark.asyncio
    async def test_successful_response_with_existing_success(self, app):
        """Test that existing success key is preserved."""
        @api_handler()
        async def test_endpoint():
            return {"success": False, "data": "value"}
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result.get_json()
            
            # Should preserve existing success value
            assert data["success"] is False

    @pytest.mark.asyncio
    async def test_value_error_returns_400(self, app):
        """Test that ValueError returns 400 response."""
        @api_handler()
        async def test_endpoint():
            raise ValueError("Invalid input")
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result[0].get_json()
            status_code = result[1]
            
            assert status_code == 400
            assert data["success"] is False
            assert data["error"] == "Invalid input"

    @pytest.mark.asyncio
    async def test_permission_error_returns_403(self, app):
        """Test that PermissionError returns 403 response."""
        @api_handler()
        async def test_endpoint():
            raise PermissionError("Access denied")
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result[0].get_json()
            status_code = result[1]
            
            assert status_code == 403
            assert data["success"] is False
            assert data["error"] == "Access denied"

    @pytest.mark.asyncio
    async def test_file_not_found_error_returns_404(self, app):
        """Test that FileNotFoundError returns 404 response."""
        @api_handler()
        async def test_endpoint():
            raise FileNotFoundError("Image not found")
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result[0].get_json()
            status_code = result[1]
            
            assert status_code == 404
            assert data["success"] is False
            assert data["error"] == "Image not found"

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(self, app):
        """Test that generic Exception returns 500 response."""
        @api_handler()
        async def test_endpoint():
            raise Exception("Unexpected error")
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result[0].get_json()
            status_code = result[1]
            
            assert status_code == 500
            assert data["success"] is False
            assert data["error"] == "Unexpected error"

    @pytest.mark.asyncio
    async def test_require_auth_with_valid_secret(self, app):
        """Test require_auth=True with valid secret."""
        @api_handler(require_auth=True)
        async def test_endpoint():
            return {"data": "protected"}
        
        async with app.test_request_context('/?secret=test_secret'):
            with patch('config.RELOAD_SECRET', 'test_secret'):
                result = await test_endpoint()
                data = await result.get_json()
                
                assert data["success"] is True
                assert data["data"] == "protected"

    @pytest.mark.asyncio
    async def test_require_auth_with_invalid_secret(self, app):
        """Test require_auth=True with invalid secret."""
        @api_handler(require_auth=True)
        async def test_endpoint():
            return {"data": "protected"}
        
        async with app.test_request_context('/?secret=wrong_secret'):
            with patch('config.RELOAD_SECRET', 'correct_secret'):
                result = await test_endpoint()
                data = await result[0].get_json()
                status_code = result[1]
                
                assert status_code == 401
                assert data["success"] is False
                assert data["error"] == "Unauthorized"

    @pytest.mark.asyncio
    async def test_non_dict_response_passed_through(self, app):
        """Test that non-dict responses are passed through unchanged."""
        @api_handler()
        async def test_endpoint():
            from quart import jsonify
            return jsonify({"custom": "response"}), 201
        
        async with app.app_context():
            result = await test_endpoint()
            # Result should be a tuple (response, status_code)
            assert isinstance(result, tuple)
            assert result[1] == 201

    @pytest.mark.asyncio
    async def test_log_errors_disabled(self, app):
        """Test that log_errors=False suppresses error logging."""
        @api_handler(log_errors=False)
        async def test_endpoint():
            raise ValueError("Error without logging")
        
        async with app.app_context():
            with patch('traceback.print_exc') as mock_print_exc:
                result = await test_endpoint()
                
                # Should not call print_exc
                mock_print_exc.assert_not_called()


class TestSyncToAsyncDecorator:
    """Test @sync_to_async decorator."""

    @pytest.mark.asyncio
    async def test_sync_function_wrapped(self):
        """Test that sync function is properly wrapped."""
        @sync_to_async
        def sync_function(a, b):
            return a + b
        
        result = await sync_function(5, 3)
        assert result == 8

    @pytest.mark.asyncio
    async def test_sync_function_with_no_args(self):
        """Test sync function with no arguments."""
        @sync_to_async
        def sync_function():
            return "result"
        
        result = await sync_function()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_sync_function_with_kwargs(self):
        """Test sync function with keyword arguments."""
        @sync_to_async
        def sync_function(x, y=10):
            return x * y
        
        result = await sync_function(5, y=3)
        assert result == 15

    @pytest.mark.asyncio
    async def test_sync_function_preserves_return_value(self):
        """Test that return values are preserved."""
        @sync_to_async
        def sync_function():
            return {"data": [1, 2, 3], "count": 3}
        
        result = await sync_function()
        assert result == {"data": [1, 2, 3], "count": 3}

    @pytest.mark.asyncio
    async def test_sync_function_with_exception(self):
        """Test that exceptions are properly raised."""
        @sync_to_async
        def sync_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            await sync_function()

    @pytest.mark.asyncio
    async def test_multiple_sync_calls_concurrent(self):
        """Test multiple concurrent calls to sync function."""
        import time
        
        @sync_to_async
        def slow_function(n):
            time.sleep(0.01)
            return n * 2
        
        # Run multiple calls concurrently
        results = await asyncio.gather(
            slow_function(1),
            slow_function(2),
            slow_function(3)
        )
        
        assert results == [2, 4, 6]


class TestRequireSecretDecorator:
    """Test @require_secret decorator."""

    @pytest.mark.asyncio
    async def test_require_secret_with_valid_secret(self, app):
        """Test with valid secret in query string."""
        @require_secret
        async def test_endpoint():
            return {"data": "protected"}
        
        async with app.test_request_context('/?secret=test_secret'):
            with patch('config.RELOAD_SECRET', 'test_secret'):
                result = await test_endpoint()
                assert result == {"data": "protected"}

    @pytest.mark.asyncio
    async def test_require_secret_with_invalid_secret(self, app):
        """Test with invalid secret."""
        @require_secret
        async def test_endpoint():
            return {"data": "protected"}
        
        async with app.test_request_context('/?secret=wrong_secret'):
            with patch('config.RELOAD_SECRET', 'correct_secret'):
                result = await test_endpoint()
                data = await result[0].get_json()
                status_code = result[1]
                
                assert status_code == 401
                assert data["success"] is False
                assert data["error"] == "Unauthorized"

class TestDecoratorCombinations:
    """Test combining decorators."""

    @pytest.mark.asyncio
    async def test_api_handler_with_sync_to_async(self, app):
        """Test combining @api_handler with @sync_to_async."""
        @api_handler()
        @sync_to_async
        def test_endpoint():
            return {"data": "value"}
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result.get_json()
            
            assert data["success"] is True
            assert data["data"] == "value"

    @pytest.mark.asyncio
    async def test_api_handler_error_in_sync_function(self, app):
        """Test error handling with combined decorators."""
        @api_handler()
        @sync_to_async
        def test_endpoint():
            raise ValueError("Sync error")
        
        async with app.app_context():
            result = await test_endpoint()
            data = await result[0].get_json()
            status_code = result[1]
            
            assert status_code == 400
            assert data["success"] is False
            assert data["error"] == "Sync error"

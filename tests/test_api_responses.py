"""
Tests for API response utilities
"""
import pytest
import json
from quart import Quart
from utils.api_responses import (
    success_response,
    error_response,
    not_found_response,
    unauthorized_response,
    validation_error_response,
    server_error_response
)


@pytest.fixture
def app():
    """Create a minimal Quart app for testing."""
    app = Quart(__name__)
    return app


@pytest.mark.asyncio
async def test_success_response_basic(app):
    """Test basic success response without data or message."""
    async with app.app_context():
        response = success_response()
        data = await response.get_json()
        
        assert data["success"] is True
        assert "error" not in data


@pytest.mark.asyncio
async def test_success_response_with_message(app):
    """Test success response with message."""
    async with app.app_context():
        response = success_response(message="Operation completed")
        data = await response.get_json()
        
        assert data["success"] is True
        assert data["message"] == "Operation completed"


@pytest.mark.asyncio
async def test_success_response_with_data(app):
    """Test success response with additional data."""
    async with app.app_context():
        response = success_response(data={"count": 10, "items": []})
        data = await response.get_json()
        
        assert data["success"] is True
        assert data["count"] == 10
        assert data["items"] == []


@pytest.mark.asyncio
async def test_success_response_with_data_and_message(app):
    """Test success response with both data and message."""
    async with app.app_context():
        response = success_response(
            data={"pool_id": 5},
            message="Pool created successfully"
        )
        data = await response.get_json()
        
        assert data["success"] is True
        assert data["message"] == "Pool created successfully"
        assert data["pool_id"] == 5


@pytest.mark.asyncio
async def test_error_response_basic(app):
    """Test basic error response."""
    async with app.app_context():
        response, status_code = error_response("Something went wrong")
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Something went wrong"
        assert status_code == 400


@pytest.mark.asyncio
async def test_error_response_with_custom_status(app):
    """Test error response with custom status code."""
    async with app.app_context():
        response, status_code = error_response("Server error", 500)
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Server error"
        assert status_code == 500


@pytest.mark.asyncio
async def test_error_response_with_data(app):
    """Test error response with additional data."""
    async with app.app_context():
        response, status_code = error_response(
            "Validation failed",
            400,
            data={"field": "email"}
        )
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Validation failed"
        assert data["field"] == "email"
        assert status_code == 400


@pytest.mark.asyncio
async def test_not_found_response(app):
    """Test not found response."""
    async with app.app_context():
        response, status_code = not_found_response("Image not found")
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Image not found"
        assert status_code == 404


@pytest.mark.asyncio
async def test_not_found_response_default(app):
    """Test not found response with default message."""
    async with app.app_context():
        response, status_code = not_found_response()
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Resource not found"
        assert status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_response(app):
    """Test unauthorized response."""
    async with app.app_context():
        response, status_code = unauthorized_response("Login required")
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Login required"
        assert status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_response_default(app):
    """Test unauthorized response with default message."""
    async with app.app_context():
        response, status_code = unauthorized_response()
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Unauthorized"
        assert status_code == 401


@pytest.mark.asyncio
async def test_validation_error_response(app):
    """Test validation error response with field."""
    async with app.app_context():
        response, status_code = validation_error_response(
            "Invalid email format",
            field="email"
        )
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Invalid email format"
        assert data["field"] == "email"
        assert status_code == 400


@pytest.mark.asyncio
async def test_validation_error_response_no_field(app):
    """Test validation error response without field."""
    async with app.app_context():
        response, status_code = validation_error_response("Invalid input")
        data = await response.get_json()
        
        assert data["success"] is False
        assert data["error"] == "Invalid input"
        assert "field" not in data
        assert status_code == 400


@pytest.mark.asyncio
async def test_server_error_response(app):
    """Test server error response."""
    async with app.app_context():
        try:
            raise ValueError("Database connection failed")
        except ValueError as e:
            response, status_code = server_error_response(e)
            data = await response.get_json()
            
            assert data["success"] is False
            assert data["error"] == "Database connection failed"
            assert status_code == 500
            assert "traceback" not in data


@pytest.mark.asyncio
async def test_server_error_response_with_traceback(app):
    """Test server error response with traceback."""
    async with app.app_context():
        try:
            raise ValueError("Database connection failed")
        except ValueError as e:
            response, status_code = server_error_response(e, include_traceback=True)
            data = await response.get_json()
            
            assert data["success"] is False
            assert data["error"] == "Database connection failed"
            assert status_code == 500
            assert "traceback" in data
            assert "ValueError" in data["traceback"]

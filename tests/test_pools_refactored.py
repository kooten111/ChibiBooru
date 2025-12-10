"""
Integration tests for refactored pool endpoints using standardized API responses
"""
import pytest
import json
from tests.conftest import create_test_pool


@pytest.mark.asyncio
async def test_create_pool_success(app, db_connection):
    """Test successful pool creation with new response format."""
    async with app.test_client() as client:
        response = await client.post(
            '/api/pools/create',
            json={'name': 'Test Pool', 'description': 'Test Description'}
        )
        
        assert response.status_code == 200
        data = await response.get_json()
        
        # Verify standardized response format
        assert data['success'] is True
        assert 'pool_id' in data
        assert data['message'] == "Pool 'Test Pool' created successfully."
        assert 'error' not in data
        
        # Verify pool was actually created
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM pools WHERE id = ?", (data['pool_id'],))
        pool = cursor.fetchone()
        assert pool is not None
        assert pool['name'] == 'Test Pool'


@pytest.mark.asyncio
async def test_create_pool_missing_name(app, db_connection):
    """Test pool creation fails with missing name - standardized error format."""
    async with app.test_client() as client:
        response = await client.post(
            '/api/pools/create',
            json={'description': 'Test Description'}
        )
        
        assert response.status_code == 400
        data = await response.get_json()
        
        # Verify standardized error response format
        assert data['success'] is False
        assert data['error'] == "Pool name is required"
        assert 'pool_id' not in data


@pytest.mark.asyncio
async def test_update_pool_success(app, db_connection):
    """Test successful pool update with new response format."""
    # Create a pool first
    pool_id = create_test_pool(db_connection, 'Original Name', 'Original Description')
    
    async with app.test_client() as client:
        response = await client.post(
            f'/api/pools/{pool_id}/update',
            json={'name': 'Updated Name', 'description': 'Updated Description'}
        )
        
        assert response.status_code == 200
        data = await response.get_json()
        
        # Verify standardized response format
        assert data['success'] is True
        assert data['message'] == "Pool updated successfully."
        assert 'error' not in data
        
        # Verify pool was actually updated
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM pools WHERE id = ?", (pool_id,))
        pool = cursor.fetchone()
        assert pool['name'] == 'Updated Name'
        assert pool['description'] == 'Updated Description'


@pytest.mark.asyncio
async def test_update_pool_missing_fields(app, db_connection):
    """Test pool update fails with no fields - standardized error format."""
    pool_id = create_test_pool(db_connection, 'Test Pool', 'Test Description')
    
    async with app.test_client() as client:
        response = await client.post(
            f'/api/pools/{pool_id}/update',
            json={}
        )
        
        assert response.status_code == 400
        data = await response.get_json()
        
        # Verify standardized error response format
        assert data['success'] is False
        assert data['error'] == "At least one field (name or description) is required"


@pytest.mark.asyncio
async def test_add_image_to_pool_not_found(app, db_connection):
    """Test adding non-existent image returns standardized 404."""
    pool_id = create_test_pool(db_connection, 'Test Pool', 'Test Description')
    
    async with app.test_client() as client:
        response = await client.post(
            f'/api/pools/{pool_id}/add_image',
            json={'filepath': 'nonexistent.jpg'}
        )
        
        assert response.status_code == 404
        data = await response.get_json()
        
        # Verify standardized not found response format
        assert data['success'] is False
        assert data['error'] == "Image not found"

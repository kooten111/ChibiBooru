"""
Tests for cache invalidation helpers
"""
import pytest
from unittest.mock import patch, MagicMock, call
from core import cache_manager


class TestCacheInvalidationHelpers:
    """Test cache invalidation helper functions."""

    @patch('core.cache_manager.reload_single_image')
    @patch('core.cache_manager.reload_tag_counts')
    @patch('repositories.data_access.get_image_details')
    def test_invalidate_image_cache_with_filepath(self, mock_get_image_details, 
                                                   mock_reload_tag_counts, 
                                                   mock_reload_single_image):
        """Test invalidate_image_cache with a specific filepath."""
        filepath = 'test/image.jpg'
        
        cache_manager.invalidate_image_cache(filepath)
        
        # Should reload single image, tag counts, and clear image details cache
        mock_reload_single_image.assert_called_once_with(filepath)
        mock_reload_tag_counts.assert_called_once()
        mock_get_image_details.cache_clear.assert_called_once()

    @patch('core.cache_manager.reload_single_image')
    @patch('core.cache_manager.reload_tag_counts')
    @patch('repositories.data_access.get_image_details')
    def test_invalidate_image_cache_without_filepath(self, mock_get_image_details,
                                                      mock_reload_tag_counts,
                                                      mock_reload_single_image):
        """Test invalidate_image_cache without filepath (invalidate all)."""
        cache_manager.invalidate_image_cache(None)
        
        # Should NOT reload single image, but should reload tag counts and clear cache
        mock_reload_single_image.assert_not_called()
        mock_reload_tag_counts.assert_called_once()
        mock_get_image_details.cache_clear.assert_called_once()

    @patch('core.cache_manager.reload_single_image')
    @patch('core.cache_manager.reload_tag_counts')
    @patch('repositories.data_access.get_image_details')
    def test_invalidate_image_cache_empty_filepath(self, mock_get_image_details,
                                                     mock_reload_tag_counts,
                                                     mock_reload_single_image):
        """Test invalidate_image_cache with empty string filepath."""
        cache_manager.invalidate_image_cache('')
        
        # Empty string is falsy, so should NOT reload single image
        mock_reload_single_image.assert_not_called()
        mock_reload_tag_counts.assert_called_once()
        mock_get_image_details.cache_clear.assert_called_once()

    @patch('core.cache_manager.reload_tag_counts')
    def test_invalidate_tag_cache(self, mock_reload_tag_counts):
        """Test invalidate_tag_cache."""
        cache_manager.invalidate_tag_cache()
        
        # Should only reload tag counts
        mock_reload_tag_counts.assert_called_once()

    @patch('core.cache_manager.load_data_from_db')
    @patch('repositories.data_access.get_image_details')
    def test_invalidate_all_caches(self, mock_get_image_details, mock_load_data_from_db):
        """Test invalidate_all_caches."""
        cache_manager.invalidate_all_caches()
        
        # Should reload all data and clear image details cache
        mock_load_data_from_db.assert_called_once()
        mock_get_image_details.cache_clear.assert_called_once()


class TestCacheInvalidationIntegration:
    """Integration tests for cache invalidation in realistic scenarios."""

    @patch('core.cache_manager.reload_single_image')
    @patch('core.cache_manager.reload_tag_counts')
    @patch('repositories.data_access.get_image_details')
    def test_cache_invalidation_after_tag_edit(self, mock_get_image_details,
                                                 mock_reload_tag_counts,
                                                 mock_reload_single_image):
        """Simulate cache invalidation after editing tags."""
        filepath = 'folder/image.png'
        
        # Simulate tag edit workflow
        cache_manager.invalidate_image_cache(filepath)
        
        # Verify all necessary caches are invalidated
        assert mock_reload_single_image.call_count == 1
        assert mock_reload_tag_counts.call_count == 1
        assert mock_get_image_details.cache_clear.call_count == 1

    @patch('core.cache_manager.reload_tag_counts')
    def test_cache_invalidation_after_image_deletion(self, mock_reload_tag_counts):
        """Simulate cache invalidation after deleting an image."""
        # After deleting an image, only tag counts need to be reloaded
        # (image is removed from cache separately)
        cache_manager.invalidate_tag_cache()
        
        assert mock_reload_tag_counts.call_count == 1

    @patch('core.cache_manager.load_data_from_db')
    @patch('repositories.data_access.get_image_details')
    def test_cache_invalidation_after_bulk_operation(self, mock_get_image_details,
                                                       mock_load_data_from_db):
        """Simulate cache invalidation after a bulk operation."""
        # After bulk operations, invalidate all caches
        cache_manager.invalidate_all_caches()
        
        assert mock_load_data_from_db.call_count == 1
        assert mock_get_image_details.cache_clear.call_count == 1

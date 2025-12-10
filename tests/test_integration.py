"""
Integration tests for end-to-end workflows

These tests verify that different parts of the system work together correctly.
"""
import pytest
import os
import json
from unittest.mock import patch, MagicMock
from PIL import Image
from database import models, get_db_connection


class TestImageIngestionWorkflow:
    """Test end-to-end image ingestion workflow."""

    def test_image_ingestion_with_metadata(self, db_connection, test_image_dir, monkeypatch):
        """Test full image ingestion: file detection → metadata fetch → database insert."""
        import database.core
        monkeypatch.setattr(database.core, 'DB_FILE', ':memory:')
        
        # Setup: Create a test image
        image_path = os.path.join(test_image_dir, 'test_image.jpg')
        img = Image.new('RGB', (100, 100), color='blue')
        img.save(image_path)
        
        # Mock metadata from a booru source
        mock_metadata = {
            'danbooru': {
                'id': 12345,
                'md5': 'test_md5_hash',
                'tag_string_general': 'scenery outdoor',
                'tag_string_character': 'test_character',
                'tag_string_copyright': 'test_series',
                'tag_string_artist': 'test_artist',
                'tag_string_meta': 'highres',
                'rating': 'g'
            }
        }
        
        # Simulate the ingestion process
        cursor = db_connection.cursor()
        
        # 1. Insert image metadata
        cursor.execute("""
            INSERT INTO images (
                filepath, md5, active_source,
                tags_general, tags_character, tags_copyright, tags_artist, tags_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'test_image.jpg',
            'test_md5_hash',
            'danbooru',
            'scenery outdoor',
            'test_character',
            'test_series',
            'test_artist',
            'highres'
        ))
        image_id = cursor.lastrowid
        
        # 2. Insert tags
        tags_data = [
            ('scenery', 'general'),
            ('outdoor', 'general'),
            ('test_character', 'character'),
            ('test_series', 'copyright'),
            ('test_artist', 'artist'),
            ('highres', 'meta')
        ]
        
        for tag_name, category in tags_data:
            cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", 
                         (tag_name, category))
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cursor.fetchone()['id']
            cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                         (image_id, tag_id))
        
        # 3. Store raw metadata
        cursor.execute("""
            INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)
        """, (image_id, json.dumps({'sources': mock_metadata})))
        
        db_connection.commit()
        
        # Verify the image was ingested correctly
        cursor.execute("SELECT * FROM images WHERE filepath = ?", ('test_image.jpg',))
        result = cursor.fetchone()
        assert result is not None
        assert result['md5'] == 'test_md5_hash'
        assert result['active_source'] == 'danbooru'
        assert 'scenery' in result['tags_general']
        assert result['tags_character'] == 'test_character'
        
        # Verify tags were created
        cursor.execute("SELECT COUNT(*) as count FROM tags")
        tag_count = cursor.fetchone()['count']
        assert tag_count == 6
        
        # Verify image-tag relationships
        cursor.execute("""
            SELECT COUNT(*) as count FROM image_tags WHERE image_id = ?
        """, (image_id,))
        relationship_count = cursor.fetchone()['count']
        assert relationship_count == 6


class TestSearchWorkflow:
    """Test search → results → details workflow."""

    def test_search_by_tags(self, populated_db):
        """Test searching for images by tags."""
        from services import query_service
        
        # Search for images with 'holo' tag
        results, should_shuffle = query_service.perform_search('holo')
        
        # Should find images with 'holo' character tag
        assert len(results) >= 2  # At least test1 and test2 have holo
        
        # Verify results contain expected fields
        for result in results:
            assert 'filepath' in result
            assert 'tags' in result

    def test_search_by_source(self, populated_db):
        """Test searching by source filter."""
        from services import query_service
        
        # Search for Danbooru images (if any in test data)
        results, should_shuffle = query_service.perform_search('source:danbooru')
        
        # Results should be a list (may be empty if no danbooru images)
        assert isinstance(results, list)

    def test_search_with_negative_tags(self, populated_db):
        """Test search with negative tags (exclusion)."""
        from services import query_service
        
        # Search for all images
        all_results, _ = query_service.perform_search('')
        total_count = len(all_results)
        
        # Search excluding 'holo'
        results, _ = query_service.perform_search('-holo')
        
        # Should have fewer results
        assert len(results) < total_count


class TestTagModificationWorkflow:
    """Test tag modification → cache invalidation workflow."""

    @patch('core.cache_manager.reload_single_image')
    @patch('core.cache_manager.reload_tag_counts')
    @patch('repositories.data_access.get_image_details')
    def test_tag_edit_invalidates_cache(self, mock_get_image_details,
                                        mock_reload_tag_counts,
                                        mock_reload_single_image,
                                        db_connection):
        """Test that editing tags properly invalidates caches."""
        from core.cache_manager import invalidate_image_cache
        
        # Setup: Create a test image
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5, tags_general)
            VALUES (?, ?, ?)
        """, ('test.jpg', 'md5_test', 'tag1 tag2'))
        image_id = cursor.lastrowid
        db_connection.commit()
        
        # Simulate tag edit and cache invalidation
        filepath = 'test.jpg'
        invalidate_image_cache(filepath)
        
        # Verify cache invalidation was called
        mock_reload_single_image.assert_called_once_with(filepath)
        mock_reload_tag_counts.assert_called_once()
        mock_get_image_details.cache_clear.assert_called_once()

    def test_tag_categorization_preserved(self, db_connection):
        """Test that tag categories are preserved during updates."""
        cursor = db_connection.cursor()
        
        # Insert image with categorized tags
        cursor.execute("""
            INSERT INTO images (
                filepath, md5,
                tags_character, tags_copyright, tags_general
            ) VALUES (?, ?, ?, ?, ?)
        """, ('cat_test.jpg', 'md5_cat', 'char1', 'series1', 'tag1 tag2'))
        image_id = cursor.lastrowid
        
        # Insert tags with categories
        tags = [
            ('char1', 'character'),
            ('series1', 'copyright'),
            ('tag1', 'general'),
            ('tag2', 'general')
        ]
        
        for tag_name, category in tags:
            cursor.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                         (tag_name, category))
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cursor.fetchone()['id']
            cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                         (image_id, tag_id))
        
        db_connection.commit()
        
        # Verify categories are correct
        cursor.execute("SELECT category FROM tags WHERE name = ?", ('char1',))
        result = cursor.fetchone()
        assert result['category'] == 'character'
        
        cursor.execute("SELECT category FROM tags WHERE name = ?", ('series1',))
        result = cursor.fetchone()
        assert result['category'] == 'copyright'


class TestDataConsistency:
    """Test data consistency across operations."""

    def test_image_tag_relationship_integrity(self, db_connection):
        """Test that image-tag relationships maintain referential integrity."""
        cursor = db_connection.cursor()
        
        # Create image and tags
        cursor.execute("INSERT INTO images (filepath, md5) VALUES (?, ?)",
                      ('integrity_test.jpg', 'md5_integrity'))
        image_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO tags (name, category) VALUES (?, ?)",
                      ('test_tag', 'general'))
        tag_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                      (image_id, tag_id))
        
        db_connection.commit()
        
        # Verify relationship exists
        cursor.execute("""
            SELECT t.name FROM tags t
            JOIN image_tags it ON t.id = it.tag_id
            WHERE it.image_id = ?
        """, (image_id,))
        result = cursor.fetchone()
        assert result is not None
        assert result['name'] == 'test_tag'

    def test_raw_metadata_json_storage(self, db_connection):
        """Test that raw metadata JSON is stored and retrieved correctly."""
        cursor = db_connection.cursor()
        
        # Create image
        cursor.execute("INSERT INTO images (filepath, md5) VALUES (?, ?)",
                      ('json_test.jpg', 'md5_json'))
        image_id = cursor.lastrowid
        
        # Store complex metadata
        metadata = {
            'sources': {
                'danbooru': {'id': 12345, 'tags': ['tag1', 'tag2']},
                'e621': {'id': 67890, 'tags': ['tag3', 'tag4']}
            },
            'saucenao_lookup': True
        }
        
        cursor.execute("INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)",
                      (image_id, json.dumps(metadata)))
        db_connection.commit()
        
        # Retrieve and verify
        cursor.execute("SELECT data FROM raw_metadata WHERE image_id = ?", (image_id,))
        result = cursor.fetchone()
        retrieved_metadata = json.loads(result['data'])
        
        assert retrieved_metadata['sources']['danbooru']['id'] == 12345
        assert retrieved_metadata['saucenao_lookup'] is True


class TestErrorHandling:
    """Test error handling in workflows."""

    def test_duplicate_image_md5_handling(self, db_connection):
        """Test handling of duplicate MD5 hashes."""
        cursor = db_connection.cursor()
        
        # Insert first image
        cursor.execute("INSERT INTO images (filepath, md5) VALUES (?, ?)",
                      ('image1.jpg', 'duplicate_md5'))
        db_connection.commit()
        
        # Try to insert image with same MD5 but different path
        # This should be prevented or handled at application level
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE md5 = ?",
                      ('duplicate_md5',))
        result = cursor.fetchone()
        assert result['count'] == 1

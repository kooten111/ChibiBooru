"""
Tests for tag database utilities (utils/tag_db.py)
"""
import pytest
from utils.tag_db import (
    insert_tag,
    bulk_insert_tags,
    update_tag_category,
    get_or_create_tag
)


class TestInsertTag:
    """Test insert_tag function"""
    
    def test_insert_new_tag(self, db_connection):
        """Test inserting a new tag"""
        tag_id = insert_tag("test_tag")
        assert tag_id > 0
        
        # Verify tag exists in database
        cursor = db_connection.cursor()
        cursor.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
        result = cursor.fetchone()
        assert result is not None
        assert result['name'] == "test_tag"
    
    def test_insert_tag_with_category(self, db_connection):
        """Test inserting a tag with a category"""
        tag_id = insert_tag("character_tag", category="character")
        assert tag_id > 0
        
        cursor = db_connection.cursor()
        cursor.execute("SELECT name, category FROM tags WHERE id = ?", (tag_id,))
        result = cursor.fetchone()
        assert result['name'] == "character_tag"
        assert result['category'] == "character"
    
    def test_insert_existing_tag(self, db_connection):
        """Test inserting an existing tag returns same ID"""
        tag_id_1 = insert_tag("existing_tag")
        tag_id_2 = insert_tag("existing_tag")
        assert tag_id_1 == tag_id_2
    
    def test_insert_tag_updates_category(self, db_connection):
        """Test that inserting existing tag with new category updates it"""
        tag_id_1 = insert_tag("update_tag", category="general")
        tag_id_2 = insert_tag("update_tag", category="character")
        
        assert tag_id_1 == tag_id_2
        
        cursor = db_connection.cursor()
        cursor.execute("SELECT category FROM tags WHERE id = ?", (tag_id_2,))
        result = cursor.fetchone()
        assert result['category'] == "character"
    
    def test_insert_empty_tag_raises_error(self, db_connection):
        """Test that empty tag name raises ValueError"""
        with pytest.raises(ValueError, match="Tag name cannot be empty"):
            insert_tag("")
        
        with pytest.raises(ValueError, match="Tag name cannot be empty"):
            insert_tag("   ")
    
    def test_insert_tag_strips_whitespace(self, db_connection):
        """Test that tag names are stripped of whitespace"""
        tag_id = insert_tag("  spaced_tag  ")
        
        cursor = db_connection.cursor()
        cursor.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
        result = cursor.fetchone()
        assert result['name'] == "spaced_tag"


class TestBulkInsertTags:
    """Test bulk_insert_tags function"""
    
    def test_bulk_insert_multiple_tags(self, db_connection):
        """Test bulk inserting multiple tags"""
        tags = [
            {'name': 'tag1', 'category': 'general'},
            {'name': 'tag2', 'category': 'character'},
            {'name': 'tag3'}
        ]
        
        tag_map = bulk_insert_tags(tags)
        
        assert len(tag_map) == 3
        assert 'tag1' in tag_map
        assert 'tag2' in tag_map
        assert 'tag3' in tag_map
        assert all(tag_id > 0 for tag_id in tag_map.values())
    
    def test_bulk_insert_empty_list_raises_error(self, db_connection):
        """Test that empty list raises ValueError"""
        with pytest.raises(ValueError, match="Tags list cannot be empty"):
            bulk_insert_tags([])
    
    def test_bulk_insert_with_duplicates(self, db_connection):
        """Test bulk insert handles duplicate tag names"""
        tags = [
            {'name': 'duplicate_tag', 'category': 'general'},
            {'name': 'duplicate_tag', 'category': 'character'}  # Same name, different category
        ]
        
        tag_map = bulk_insert_tags(tags)
        
        # Should return only one entry for duplicate_tag
        assert 'duplicate_tag' in tag_map
        
        # Verify the category was updated to the last one
        cursor = db_connection.cursor()
        cursor.execute("SELECT category FROM tags WHERE name = ?", ('duplicate_tag',))
        result = cursor.fetchone()
        assert result['category'] == 'character'
    
    def test_bulk_insert_skips_invalid_entries(self, db_connection):
        """Test that bulk insert skips invalid entries"""
        tags = [
            {'name': 'valid_tag'},
            {'invalid': 'no_name'},  # Missing 'name' key
            {'name': ''},  # Empty name
            {'name': 'another_valid_tag'}
        ]
        
        tag_map = bulk_insert_tags(tags)
        
        # Should only insert the valid tags
        assert len(tag_map) == 2
        assert 'valid_tag' in tag_map
        assert 'another_valid_tag' in tag_map


class TestUpdateTagCategory:
    """Test update_tag_category function"""
    
    def test_update_existing_tag_category(self, db_connection):
        """Test updating category of existing tag"""
        # Create a tag first
        tag_id = insert_tag("update_me", category="general")
        
        # Update its category
        success = update_tag_category("update_me", "character")
        assert success is True
        
        # Verify the update
        cursor = db_connection.cursor()
        cursor.execute("SELECT category FROM tags WHERE id = ?", (tag_id,))
        result = cursor.fetchone()
        assert result['category'] == "character"
    
    def test_update_nonexistent_tag(self, db_connection):
        """Test updating a non-existent tag returns False"""
        success = update_tag_category("nonexistent_tag", "general")
        assert success is False
    
    def test_update_empty_tag_name_raises_error(self, db_connection):
        """Test that empty tag name raises ValueError"""
        with pytest.raises(ValueError, match="Tag name cannot be empty"):
            update_tag_category("", "general")
    
    def test_update_empty_category_raises_error(self, db_connection):
        """Test that empty category raises ValueError"""
        with pytest.raises(ValueError, match="Category cannot be empty"):
            update_tag_category("some_tag", "")


class TestGetOrCreateTag:
    """Test get_or_create_tag function"""
    
    def test_get_or_create_new_tag(self, db_connection):
        """Test creating a new tag"""
        tag_id = get_or_create_tag("new_tag")
        assert tag_id > 0
        
        cursor = db_connection.cursor()
        cursor.execute("SELECT name FROM tags WHERE id = ?", (tag_id,))
        result = cursor.fetchone()
        assert result['name'] == "new_tag"
    
    def test_get_or_create_existing_tag(self, db_connection):
        """Test getting an existing tag"""
        # Create tag first
        tag_id_1 = get_or_create_tag("existing_tag")
        
        # Get it again
        tag_id_2 = get_or_create_tag("existing_tag")
        
        assert tag_id_1 == tag_id_2

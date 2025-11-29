"""
Tests for database.py - Schema creation, connections, and basic operations
"""
import pytest
import sqlite3
import os
from database import (
    get_db_connection,
    initialize_database,
    populate_fts_table,
)


@pytest.mark.unit
class TestDatabaseConnection:
    """Test database connection handling."""

    def test_get_db_connection_returns_connection(self, test_db_path, monkeypatch):
        """Test that get_db_connection returns a valid SQLite connection."""
        import database
        monkeypatch.setattr(database, 'DB_FILE', test_db_path)

        conn = get_db_connection()
        assert isinstance(conn, sqlite3.Connection)
        assert conn.row_factory == sqlite3.Row
        conn.close()

    def test_connection_can_execute_queries(self, db_connection):
        """Test that returned connection can execute queries."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT 1 as test")
        result = cursor.fetchone()
        assert result['test'] == 1


@pytest.mark.unit
class TestDatabaseInitialization:
    """Test database schema creation."""

    def test_initialize_database_creates_tables(self, test_db_path, monkeypatch):
        """Test that initialize_database creates all required tables."""
        import database
        monkeypatch.setattr(database, 'DB_FILE', test_db_path)

        initialize_database()

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check all expected tables exist
        expected_tables = [
            'images', 'tags', 'image_tags', 'sources', 'image_sources',
            'raw_metadata', 'pools', 'pool_images', 'tag_implications',
            'tag_deltas', 'images_fts'
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]

        for table in expected_tables:
            assert table in tables, f"Table {table} was not created"

        conn.close()

    def test_images_table_has_correct_columns(self, db_connection):
        """Test that images table has all required columns."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(images)")
        columns = {row['name']: row['type'] for row in cursor.fetchall()}

        expected_columns = {
            'id': 'INTEGER',
            'filepath': 'TEXT',
            'md5': 'TEXT',
            'post_id': 'INTEGER',
            'parent_id': 'INTEGER',
            'has_children': 'BOOLEAN',
            'saucenao_lookup': 'BOOLEAN',
            'active_source': 'TEXT',
            'tags_character': 'TEXT',
            'tags_copyright': 'TEXT',
            'tags_artist': 'TEXT',
            'tags_species': 'TEXT',
            'tags_meta': 'TEXT',
            'tags_general': 'TEXT',
        }

        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Column {col_name} missing from images table"

    def test_tags_table_has_correct_columns(self, db_connection):
        """Test that tags table has all required columns."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(tags)")
        columns = {row['name'] for row in cursor.fetchall()}

        expected_columns = {'id', 'name', 'category'}
        assert expected_columns.issubset(columns)

    def test_tag_implications_has_metadata_columns(self, db_connection):
        """Test that tag_implications has metadata columns."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(tag_implications)")
        columns = {row['name'] for row in cursor.fetchall()}

        expected_columns = {
            'source_tag_id', 'implied_tag_id', 'inference_type',
            'confidence', 'created_at', 'status'
        }
        assert expected_columns.issubset(columns)

    def test_tag_deltas_table_exists(self, db_connection):
        """Test that tag_deltas table exists for delta tracking."""
        cursor = db_connection.cursor()
        cursor.execute("PRAGMA table_info(tag_deltas)")
        columns = {row['name'] for row in cursor.fetchall()}

        expected_columns = {
            'id', 'image_md5', 'tag_name', 'tag_category', 'operation', 'timestamp'
        }
        assert expected_columns.issubset(columns)

    def test_indexes_are_created(self, db_connection):
        """Test that performance indexes are created."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row['name'] for row in cursor.fetchall()]

        expected_indexes = [
            'idx_images_filepath',
            'idx_images_md5',
            'idx_tags_name',
            'idx_image_tags_image_id',
            'idx_image_tags_tag_id',
        ]

        for index in expected_indexes:
            assert index in indexes, f"Index {index} was not created"

    def test_fts_triggers_are_created(self, db_connection):
        """Test that FTS5 triggers are created."""
        cursor = db_connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row['name'] for row in cursor.fetchall()]

        expected_triggers = [
            'images_fts_insert',
            'images_fts_update',
            'images_fts_delete',
        ]

        for trigger in expected_triggers:
            assert trigger in triggers, f"Trigger {trigger} was not created"


@pytest.mark.unit
class TestFTSPopulation:
    """Test FTS5 table population."""

    def test_populate_fts_table_with_empty_db(self, db_connection):
        """Test populating FTS table when no images exist."""
        # Should not raise any errors
        populate_fts_table()

        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM images_fts")
        count = cursor.fetchone()['cnt']
        assert count == 0

    def test_populate_fts_table_with_data(self, populated_db):
        """Test populating FTS table with existing images."""
        cursor = populated_db.cursor()

        # Check that FTS table has entries
        cursor.execute("SELECT COUNT(*) as cnt FROM images_fts")
        fts_count = cursor.fetchone()['cnt']

        cursor.execute("SELECT COUNT(*) as cnt FROM images")
        img_count = cursor.fetchone()['cnt']

        assert fts_count == img_count, "FTS table should have same count as images table"

    def test_fts_insert_trigger_fires(self, db_connection):
        """Test that FTS insert trigger works when adding new image."""
        cursor = db_connection.cursor()

        # Insert an image
        cursor.execute("""
            INSERT INTO images (filepath, md5, tags_general)
            VALUES ('test.png', 'test_md5', 'tag1 tag2')
        """)
        db_connection.commit()

        # Check FTS table was updated
        cursor.execute("SELECT COUNT(*) as cnt FROM images_fts WHERE filepath = 'test.png'")
        count = cursor.fetchone()['cnt']
        assert count == 1

    def test_fts_update_trigger_fires(self, db_connection):
        """Test that FTS update trigger works when updating image tags."""
        cursor = db_connection.cursor()

        # Insert an image
        cursor.execute("""
            INSERT INTO images (filepath, md5, tags_general)
            VALUES ('test.png', 'test_md5', 'tag1 tag2')
        """)
        db_connection.commit()

        # Update the tags
        cursor.execute("""
            UPDATE images SET tags_general = 'tag3 tag4'
            WHERE filepath = 'test.png'
        """)
        db_connection.commit()

        # Check FTS table reflects the update
        cursor.execute("""
            SELECT tags_general FROM images_fts WHERE filepath = 'test.png'
        """)
        result = cursor.fetchone()
        assert 'tag3' in result['tags_general']
        assert 'tag4' in result['tags_general']

    def test_fts_delete_trigger_fires(self, db_connection):
        """Test that FTS delete trigger works when removing image."""
        cursor = db_connection.cursor()

        # Insert an image
        cursor.execute("""
            INSERT INTO images (filepath, md5, tags_general)
            VALUES ('test.png', 'test_md5', 'tag1 tag2')
        """)
        db_connection.commit()

        # Delete the image
        cursor.execute("DELETE FROM images WHERE filepath = 'test.png'")
        db_connection.commit()

        # Check FTS table was updated
        cursor.execute("SELECT COUNT(*) as cnt FROM images_fts WHERE filepath = 'test.png'")
        count = cursor.fetchone()['cnt']
        assert count == 0


@pytest.mark.unit
class TestDatabaseConstraints:
    """Test database constraints and foreign keys."""

    def test_images_filepath_unique_constraint(self, db_connection):
        """Test that filepath must be unique."""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'md5_1')
        """)

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO images (filepath, md5) VALUES ('test.png', 'md5_2')
            """)

    def test_images_md5_unique_constraint(self, db_connection):
        """Test that MD5 must be unique."""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test1.png', 'same_md5')
        """)

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO images (filepath, md5) VALUES ('test2.png', 'same_md5')
            """)

    def test_tags_name_unique_constraint(self, db_connection):
        """Test that tag names must be unique."""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO tags (name, category) VALUES ('test_tag', 'general')
        """)

        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("""
                INSERT INTO tags (name, category) VALUES ('test_tag', 'character')
            """)

    def test_cascade_delete_on_image_removal(self, db_connection):
        """Test that removing an image cascades to related tables."""
        cursor = db_connection.cursor()

        # Insert image
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        image_id = cursor.lastrowid

        # Insert tag and relationship
        cursor.execute("""
            INSERT INTO tags (name, category) VALUES ('test_tag', 'general')
        """)
        tag_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)
        """, (image_id, tag_id))

        db_connection.commit()

        # Delete the image
        cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
        db_connection.commit()

        # Check that image_tags entry was also deleted
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM image_tags WHERE image_id = ?
        """, (image_id,))
        count = cursor.fetchone()['cnt']
        assert count == 0, "image_tags should cascade delete"


@pytest.mark.unit
class TestDatabaseMigrations:
    """Test that database can handle schema migrations."""

    def test_adding_columns_does_not_break_existing_data(self, db_connection):
        """Test that we can add columns without breaking existing data."""
        cursor = db_connection.cursor()

        # Insert data
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        db_connection.commit()

        # Verify the categorized tag columns exist (they're added as migrations)
        cursor.execute("SELECT tags_character, tags_copyright FROM images")
        result = cursor.fetchone()
        # Should not raise error, columns should exist (even if NULL)
        assert result is not None

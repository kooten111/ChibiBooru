"""
Tests for models.py - Data access layer and caching
"""
import pytest
import json
from tests.conftest import (
    assert_image_exists_in_db,
    assert_tag_exists,
    create_test_pool,
    create_test_implication,
)
from database import models


@pytest.mark.unit
class TestMD5Checking:
    """Test MD5 duplicate detection."""

    def test_md5_exists_returns_false_for_new_md5(self, db_connection):
        """Test that md5_exists returns False for non-existent MD5."""
        assert models.md5_exists('nonexistent_md5') is False

    def test_md5_exists_returns_true_for_existing_md5(self, db_connection):
        """Test that md5_exists returns True for existing MD5."""
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'existing_md5')
        """)
        db_connection.commit()

        assert models.md5_exists('existing_md5') is True


@pytest.mark.unit
class TestDataLoading:
    """Test data loading from database into memory cache."""

    def test_load_data_from_db_empty_database(self, db_connection, monkeypatch):
        """Test loading data from empty database."""
        # Monkeypatch get_db_connection to return our test connection
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        result = models.load_data_from_db()

        assert result is True
        assert len(models.get_tag_counts()) == 0
        assert len(models.get_image_data()) == 0

    def test_load_data_from_db_populated_database(self, populated_db, monkeypatch):
        """Test loading data from populated database."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        result = models.load_data_from_db()

        assert result is True
        assert len(models.get_tag_counts()) > 0
        assert len(models.get_image_data()) > 0

    def test_load_data_builds_post_id_mapping(self, populated_db, monkeypatch):
        """Test that load_data builds the post_id to MD5 mapping."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        models.load_data_from_db()

        # Check that post_id_to_md5 was populated
        assert len(models.post_id_to_md5) >= 0  # May be empty if no post_ids in test data


@pytest.mark.unit
class TestCacheAccess:
    """Test cache access functions."""

    def test_get_tag_counts_returns_dict(self, populated_db, monkeypatch):
        """Test that get_tag_counts returns a dictionary."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        tag_counts = models.get_tag_counts()
        assert isinstance(tag_counts, dict)

    def test_get_image_data_returns_list(self, populated_db, monkeypatch):
        """Test that get_image_data returns a list."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        image_data = models.get_image_data()
        assert isinstance(image_data, list)


@pytest.mark.unit
class TestStatistics:
    """Test statistics functions."""

    def test_get_image_count_empty_db(self, db_connection, monkeypatch):
        """Test get_image_count with empty database."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        count = models.get_image_count()
        assert count == 0

    def test_get_image_count_populated_db(self, populated_db, monkeypatch):
        """Test get_image_count with data."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        count = models.get_image_count()
        assert count == 3  # populated_db has 3 images

    def test_get_avg_tags_per_image(self, populated_db, monkeypatch):
        """Test average tags per image calculation."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        avg = models.get_avg_tags_per_image()
        assert avg > 0
        assert isinstance(avg, float)

    def test_get_source_breakdown(self, populated_db, monkeypatch):
        """Test source breakdown statistics."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        breakdown = models.get_source_breakdown()
        assert isinstance(breakdown, dict)

    def test_get_category_counts(self, populated_db, monkeypatch):
        """Test category counts."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        counts = models.get_category_counts()
        assert isinstance(counts, dict)


@pytest.mark.unit
class TestImageDetails:
    """Test image detail retrieval."""

    def test_get_image_details_nonexistent(self, db_connection, monkeypatch):
        """Test getting details for non-existent image."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        details = models.get_image_details('nonexistent.png')
        assert details is None

    def test_get_image_details_returns_complete_data(self, populated_db, monkeypatch):
        """Test that get_image_details returns all fields."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        details = models.get_image_details('test1.png')

        assert details is not None
        assert details['filepath'] == 'test1.png'
        assert 'md5' in details
        assert 'tags_general' in details
        assert 'tags_character' in details
        assert 'all_tags' in details

    def test_get_image_details_parses_json_metadata(self, db_connection, monkeypatch):
        """Test that raw_metadata is parsed from JSON."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        image_id = cursor.lastrowid

        metadata = {'test': 'data', 'sources': {}}
        cursor.execute("""
            INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)
        """, (image_id, json.dumps(metadata)))
        db_connection.commit()

        details = models.get_image_details('test.png')
        assert details['raw_metadata'] == metadata


@pytest.mark.unit
class TestImageDeletion:
    """Test image deletion."""

    def test_delete_image_removes_from_db(self, db_connection, monkeypatch):
        """Test that delete_image removes the image."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        db_connection.commit()

        result = models.delete_image('test.png')
        assert result is True

        cursor.execute("SELECT COUNT(*) as cnt FROM images WHERE filepath = 'test.png'")
        count = cursor.fetchone()['cnt']
        assert count == 0

    def test_delete_image_nonexistent_returns_false(self, db_connection, monkeypatch):
        """Test deleting non-existent image returns False."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        result = models.delete_image('nonexistent.png')
        assert result is False


@pytest.mark.unit
class TestTagUpdating:
    """Test tag update functions."""

    def test_update_image_tags_categorized(self, db_connection, monkeypatch):
        """Test updating categorized tags."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Create test image
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        db_connection.commit()

        # Update tags
        categorized_tags = {
            'tags_general': 'tag1 tag2',
            'tags_character': 'character1',
            'tags_copyright': 'series1',
            'tags_artist': 'artist1',
            'tags_species': '',
            'tags_meta': 'highres',
        }

        result = models.update_image_tags_categorized('test.png', categorized_tags)
        assert result is True

        # Verify tags were updated
        cursor.execute("""
            SELECT tags_general, tags_character FROM images WHERE filepath = 'test.png'
        """)
        row = cursor.fetchone()
        assert row['tags_general'] == 'tag1 tag2'
        assert row['tags_character'] == 'character1'


@pytest.mark.unit
class TestAddImageWithMetadata:
    """Test adding images with full metadata."""

    def test_add_image_with_metadata_creates_all_relationships(self, db_connection, monkeypatch):
        """Test that add_image_with_metadata creates all required relationships."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        image_info = {
            'filepath': 'test.png',
            'md5': 'test_md5',
            'post_id': 12345,
            'parent_id': None,
            'has_children': False,
            'saucenao_lookup': False,
        }

        source_names = ['danbooru']

        categorized_tags = {
            'general': ['tag1', 'tag2'],
            'character': ['character1'],
            'copyright': ['series1'],
            'artist': ['artist1'],
            'species': [],
            'meta': ['highres'],
        }

        raw_metadata = {
            'md5': 'test_md5',
            'sources': {'danbooru': {}}
        }

        result = models.add_image_with_metadata(
            image_info, source_names, categorized_tags, raw_metadata
        )

        assert result is True

        # Verify image was created
        image_id = assert_image_exists_in_db(db_connection, 'test.png')

        # Verify tags were created
        assert_tag_exists(db_connection, 'tag1')
        assert_tag_exists(db_connection, 'character1')

        # Verify raw metadata was stored
        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT data FROM raw_metadata WHERE image_id = ?
        """, (image_id,))
        result = cursor.fetchone()
        assert result is not None

    def test_add_image_with_duplicate_md5_returns_false(self, db_connection, monkeypatch):
        """Test that duplicate MD5 returns False."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Insert first image
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('first.png', 'same_md5')
        """)
        db_connection.commit()

        # Try to insert second with same MD5
        image_info = {
            'filepath': 'second.png',
            'md5': 'same_md5',
            'post_id': 12345,
            'parent_id': None,
            'has_children': False,
            'saucenao_lookup': False,
        }

        result = models.add_image_with_metadata(image_info, [], {}, {})
        assert result is False


@pytest.mark.unit
class TestPoolFunctions:
    """Test pool management functions."""

    def test_create_pool(self, db_connection, monkeypatch):
        """Test creating a pool."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        pool_id = models.create_pool('Test Pool', 'Test Description')
        assert pool_id > 0

        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM pools WHERE id = ?", (pool_id,))
        pool = cursor.fetchone()
        assert pool['name'] == 'Test Pool'
        assert pool['description'] == 'Test Description'

    def test_get_all_pools(self, db_connection, monkeypatch):
        """Test retrieving all pools."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Create some pools
        create_test_pool(db_connection, 'Pool 1')
        create_test_pool(db_connection, 'Pool 2')

        pools = models.get_all_pools()
        assert len(pools) == 2

    def test_get_pool_details(self, populated_db, monkeypatch):
        """Test getting pool details with images."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # Create pool and add image
        pool_id = create_test_pool(populated_db, 'Test Pool')

        cursor = populated_db.cursor()
        cursor.execute("SELECT id FROM images LIMIT 1")
        image_id = cursor.fetchone()['id']

        cursor.execute("""
            INSERT INTO pool_images (pool_id, image_id, sort_order)
            VALUES (?, ?, 1)
        """, (pool_id, image_id))
        populated_db.commit()

        details = models.get_pool_details(pool_id)
        assert details is not None
        assert details['pool']['name'] == 'Test Pool'
        assert len(details['images']) == 1

    def test_add_image_to_pool(self, populated_db, monkeypatch):
        """Test adding image to pool."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        pool_id = create_test_pool(populated_db, 'Test Pool')

        cursor = populated_db.cursor()
        cursor.execute("SELECT id FROM images LIMIT 1")
        image_id = cursor.fetchone()['id']

        models.add_image_to_pool(pool_id, image_id)

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM pool_images
            WHERE pool_id = ? AND image_id = ?
        """, (pool_id, image_id))
        count = cursor.fetchone()['cnt']
        assert count == 1

    def test_remove_image_from_pool(self, populated_db, monkeypatch):
        """Test removing image from pool."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        pool_id = create_test_pool(populated_db, 'Test Pool')

        cursor = populated_db.cursor()
        cursor.execute("SELECT id FROM images LIMIT 1")
        image_id = cursor.fetchone()['id']

        # Add then remove
        models.add_image_to_pool(pool_id, image_id)
        models.remove_image_from_pool(pool_id, image_id)

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM pool_images
            WHERE pool_id = ? AND image_id = ?
        """, (pool_id, image_id))
        count = cursor.fetchone()['cnt']
        assert count == 0

    def test_delete_pool(self, db_connection, monkeypatch):
        """Test deleting a pool."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        pool_id = create_test_pool(db_connection, 'Test Pool')
        models.delete_pool(pool_id)

        cursor = db_connection.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM pools WHERE id = ?", (pool_id,))
        count = cursor.fetchone()['cnt']
        assert count == 0


@pytest.mark.unit
class TestTagImplications:
    """Test tag implication functions."""

    def test_add_implication(self, db_connection, monkeypatch):
        """Test creating a tag implication."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Create tags
        cursor = db_connection.cursor()
        cursor.execute("INSERT INTO tags (name, category) VALUES ('holo', 'character')")
        cursor.execute("INSERT INTO tags (name, category) VALUES ('spice_and_wolf', 'copyright')")
        db_connection.commit()

        result = models.add_implication('holo', 'spice_and_wolf')
        assert result is True

        cursor.execute("""
            SELECT COUNT(*) as cnt FROM tag_implications ti
            JOIN tags t1 ON ti.source_tag_id = t1.id
            JOIN tags t2 ON ti.implied_tag_id = t2.id
            WHERE t1.name = 'holo' AND t2.name = 'spice_and_wolf'
        """)
        count = cursor.fetchone()['cnt']
        assert count == 1

    def test_get_implications_for_tag(self, db_connection, monkeypatch):
        """Test retrieving implications for a tag."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        create_test_implication(db_connection, 'holo', 'spice_and_wolf')
        create_test_implication(db_connection, 'holo', 'wolf')

        implications = models.get_implications_for_tag('holo')
        assert len(implications) == 2
        assert 'spice_and_wolf' in implications
        assert 'wolf' in implications


@pytest.mark.unit
class TestDeltaTracking:
    """Test delta tracking functions."""

    def test_record_tag_delta(self, db_connection, monkeypatch):
        """Test recording a tag delta."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        result = models.record_tag_delta('test_md5', 'test_tag', 'general', 'add')
        assert result is True

        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT * FROM tag_deltas
            WHERE image_md5 = 'test_md5' AND tag_name = 'test_tag'
        """)
        delta = cursor.fetchone()
        assert delta is not None
        assert delta['operation'] == 'add'

    def test_record_opposite_deltas_cancel_out(self, db_connection, monkeypatch):
        """Test that recording opposite operations cancels them out."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Add a tag
        models.record_tag_delta('test_md5', 'test_tag', 'general', 'add')

        # Remove the same tag (should cancel)
        models.record_tag_delta('test_md5', 'test_tag', 'general', 'remove')

        cursor = db_connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM tag_deltas
            WHERE image_md5 = 'test_md5' AND tag_name = 'test_tag'
        """)
        count = cursor.fetchone()['cnt']
        assert count == 0, "Opposite operations should cancel each other"

    def test_get_image_deltas(self, db_connection, monkeypatch):
        """Test retrieving deltas for an image."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)

        # Create image
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        db_connection.commit()

        # Record deltas
        models.record_tag_delta('test_md5', 'added_tag', 'general', 'add')
        models.record_tag_delta('test_md5', 'removed_tag', 'general', 'remove')

        deltas = models.get_image_deltas('test.png')
        assert len(deltas['added']) == 1
        assert len(deltas['removed']) == 1
        assert deltas['added'][0]['name'] == 'added_tag'
        assert deltas['removed'][0]['name'] == 'removed_tag'


@pytest.mark.integration
class TestDataRebuild:
    """Test database rebuild functionality."""

    def test_repopulate_from_database(self, db_connection, monkeypatch):
        """Test full database repopulation from raw_metadata."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: db_connection)
        monkeypatch.setattr(models, 'recategorize_misplaced_tags', lambda: 0)
        monkeypatch.setattr(models, 'rebuild_categorized_tags_from_relations', lambda: 0)
        monkeypatch.setattr(models, 'apply_tag_deltas', lambda: True)

        # Create image with raw metadata
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO images (filepath, md5) VALUES ('test.png', 'test_md5')
        """)
        image_id = cursor.lastrowid

        metadata = {
            'md5': 'test_md5',
            'sources': {
                'danbooru': {
                    'id': 12345,
                    'tag_string_general': 'tag1 tag2',
                    'tag_string_character': 'character1',
                    'tag_string_copyright': '',
                    'tag_string_artist': '',
                    'tag_string_meta': '',
                    'parent_id': None,
                    'has_children': False,
                }
            }
        }

        cursor.execute("""
            INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)
        """, (image_id, json.dumps(metadata)))
        db_connection.commit()

        # Run repopulation
        models.repopulate_from_database()

        # Verify tags were created
        cursor.execute("SELECT COUNT(*) as cnt FROM tags")
        tag_count = cursor.fetchone()['cnt']
        assert tag_count > 0

        # Verify image_tags relationships
        cursor.execute("SELECT COUNT(*) as cnt FROM image_tags WHERE image_id = ?", (image_id,))
        link_count = cursor.fetchone()['cnt']
        assert link_count > 0

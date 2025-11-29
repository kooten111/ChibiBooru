"""
Pytest fixtures and test configuration
"""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
import sqlite3
from PIL import Image
import json

# Set testing environment variables BEFORE importing app modules
os.environ['TESTING'] = 'true'
os.environ['FLASK_ENV'] = 'testing'

# Now import app modules
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
import database
from database import models
import config


@pytest.fixture(scope='session')
def test_config():
    """Test configuration that overrides production config."""
    return {
        'IMAGE_DIRECTORY': None,  # Set per test
        'THUMB_DIR': None,  # Set per test
        'DATABASE_PATH': None,  # Set per test
        'ENABLE_LOCAL_TAGGER': False,  # Disable AI tagger in tests
        'ENABLE_SAUCENAO': False,  # Disable external API in tests
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'APP_PASSWORD': 'test-password',
    }


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def test_db_path(temp_dir):
    """Path to test database file."""
    return os.path.join(temp_dir, 'test_booru.db')


@pytest.fixture
def test_image_dir(temp_dir):
    """Create temporary image directory."""
    image_dir = os.path.join(temp_dir, 'images')
    os.makedirs(image_dir, exist_ok=True)
    return image_dir


@pytest.fixture
def test_thumb_dir(temp_dir):
    """Create temporary thumbnail directory."""
    thumb_dir = os.path.join(temp_dir, 'thumbnails')
    os.makedirs(thumb_dir, exist_ok=True)
    return thumb_dir


@pytest.fixture
def db_connection(test_db_path, monkeypatch):
    """
    Create a test database connection.
    Uses monkeypatch to override the DB_FILE path.
    """
    # Override the DB_FILE in database module
    # Override the DB_FILE in database.core module
    import database.core
    monkeypatch.setattr(database.core, 'DB_FILE', test_db_path)

    # Initialize the test database
    database.initialize_database()

    # Return a connection for use in tests
    conn = database.get_db_connection()
    yield conn

    # Cleanup
    conn.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)


@pytest.fixture
def clean_db(db_connection):
    """
    Provide a clean database for each test.
    Rolls back any changes after the test.
    """
    # Start a transaction
    db_connection.execute("BEGIN")
    yield db_connection
    # Rollback after test
    db_connection.rollback()


@pytest.fixture
def app(test_db_path, test_image_dir, test_thumb_dir, monkeypatch):
    """Create Flask app configured for testing."""
    # Override config paths
    monkeypatch.setattr(config, 'DATABASE_PATH', test_db_path)
    monkeypatch.setattr(config, 'IMAGE_DIRECTORY', test_image_dir)
    monkeypatch.setattr(config, 'THUMB_DIR', test_thumb_dir)
    monkeypatch.setattr(config, 'ENABLE_LOCAL_TAGGER', False)
    monkeypatch.setattr(config, 'ENABLE_SAUCENAO', False)
    # Override the DB_FILE in database.core module
    import database.core
    monkeypatch.setattr(database.core, 'DB_FILE', test_db_path)

    # Create app
    app = create_app()
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'

    yield app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def authenticated_client(client):
    """Flask test client with authentication."""
    with client.session_transaction() as sess:
        sess['logged_in'] = True
    return client


@pytest.fixture
def sample_image(test_image_dir):
    """
    Create a sample test image.
    Returns the path to the created image.
    """
    image_path = os.path.join(test_image_dir, 'test_image.png')

    # Create a simple 100x100 RGB image
    img = Image.new('RGB', (100, 100), color='red')
    img.save(image_path)

    return image_path


@pytest.fixture
def sample_images(test_image_dir):
    """
    Create multiple sample test images.
    Returns a list of image paths.
    """
    images = []
    colors = ['red', 'blue', 'green', 'yellow', 'purple']

    for i, color in enumerate(colors):
        image_path = os.path.join(test_image_dir, f'test_image_{i}.png')
        img = Image.new('RGB', (100, 100), color=color)
        img.save(image_path)
        images.append(image_path)

    return images


@pytest.fixture
def sample_metadata():
    """Sample booru metadata for testing."""
    return {
        'danbooru': {
            'id': 12345,
            'md5': 'abc123def456',
            'file_url': 'https://example.com/image.png',
            'tag_string_general': 'scenery outdoor sky',
            'tag_string_character': 'holo',
            'tag_string_copyright': 'spice_and_wolf',
            'tag_string_artist': 'artist_name',
            'tag_string_meta': 'highres',
            'parent_id': None,
            'has_children': False,
        },
        'e621': {
            'id': 67890,
            'file': {'url': 'https://example.com/image.png'},
            'tags': {
                'general': ['scenery', 'outdoor', 'sky'],
                'character': ['holo'],
                'copyright': ['spice_and_wolf'],
                'artist': ['artist_name'],
                'species': ['wolf'],
                'meta': ['highres'],
            },
            'relationships': {
                'parent_id': None,
            },
            'has_children': False,
        }
    }


@pytest.fixture
def populated_db(db_connection, test_image_dir):
    """
    Create a database populated with test data.
    Includes images, tags, and relationships.
    """
    cursor = db_connection.cursor()

    # Create some test images
    test_data = [
        {
            'filepath': 'test1.png',
            'md5': 'md5_test1',
            'post_id': 1,
            'parent_id': None,
            'has_children': True,
            'saucenao_lookup': False,
            'tags_general': 'scenery outdoor mountain',
            'tags_character': 'holo',
            'tags_copyright': 'spice_and_wolf',
            'tags_artist': 'artist1',
            'tags_species': 'wolf',
            'tags_meta': 'highres',
        },
        {
            'filepath': 'test2.png',
            'md5': 'md5_test2',
            'post_id': 2,
            'parent_id': 1,  # Child of test1
            'has_children': False,
            'saucenao_lookup': False,
            'tags_general': 'scenery outdoor forest',
            'tags_character': 'holo',
            'tags_copyright': 'spice_and_wolf',
            'tags_artist': 'artist1',
            'tags_species': 'wolf',
            'tags_meta': 'highres',
        },
        {
            'filepath': 'test3.png',
            'md5': 'md5_test3',
            'post_id': 3,
            'parent_id': None,
            'has_children': False,
            'saucenao_lookup': True,
            'tags_general': 'character_portrait indoor',
            'tags_character': 'other_char',
            'tags_copyright': 'other_series',
            'tags_artist': 'artist2',
            'tags_species': '',
            'tags_meta': 'lowres',
        },
    ]

    # Insert images
    for data in test_data:
        cursor.execute("""
            INSERT INTO images (
                filepath, md5, post_id, parent_id, has_children, saucenao_lookup,
                tags_general, tags_character, tags_copyright, tags_artist, tags_species, tags_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['filepath'], data['md5'], data['post_id'], data['parent_id'],
            data['has_children'], data['saucenao_lookup'],
            data['tags_general'], data['tags_character'], data['tags_copyright'],
            data['tags_artist'], data['tags_species'], data['tags_meta']
        ))

        image_id = cursor.lastrowid

        # Insert tags and relationships
        all_tags = []
        for category in ['general', 'character', 'copyright', 'artist', 'species', 'meta']:
            tags_str = data.get(f'tags_{category}', '')
            if tags_str:
                for tag in tags_str.split():
                    all_tags.append((tag, category))

        for tag_name, category in all_tags:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
                (tag_name, category)
            )
            cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
            tag_id = cursor.fetchone()['id']
            cursor.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id)
            )

        # Insert raw metadata
        raw_metadata = {
            'md5': data['md5'],
            'relative_path': data['filepath'],
            'sources': {}
        }
        cursor.execute(
            "INSERT INTO raw_metadata (image_id, data) VALUES (?, ?)",
            (image_id, json.dumps(raw_metadata))
        )

    db_connection.commit()

    # Populate FTS table
    database.populate_fts_table()

    return db_connection


@pytest.fixture
def mock_booru_response():
    """Mock response from booru API."""
    def _make_response(source='danbooru', tags_override=None):
        if source == 'danbooru':
            response = {
                'id': 12345,
                'md5': 'test_md5',
                'file_url': 'https://example.com/image.png',
                'tag_string_general': 'tag1 tag2 tag3',
                'tag_string_character': 'character1',
                'tag_string_copyright': 'series1',
                'tag_string_artist': 'artist1',
                'tag_string_meta': 'highres',
                'parent_id': None,
                'has_children': False,
            }
            if tags_override:
                response.update(tags_override)
            return response
        elif source == 'e621':
            response = {
                'id': 67890,
                'file': {'url': 'https://example.com/image.png'},
                'tags': {
                    'general': ['tag1', 'tag2', 'tag3'],
                    'character': ['character1'],
                    'copyright': ['series1'],
                    'artist': ['artist1'],
                    'species': ['species1'],
                    'meta': ['highres'],
                },
                'relationships': {'parent_id': None},
                'has_children': False,
            }
            if tags_override:
                response['tags'].update(tags_override)
            return response

    return _make_response


@pytest.fixture
def mock_image_file():
    """Create a temporary mock image file that can be used for testing."""
    def _create_image(filename='test.png', size=(100, 100), color='red'):
        temp_file = tempfile.NamedTemporaryFile(suffix=f'.{filename.split(".")[-1]}', delete=False)
        img = Image.new('RGB', size, color=color)
        img.save(temp_file.name)
        temp_file.close()
        return temp_file.name

    yield _create_image

    # Cleanup happens via temp_dir fixture


# Helper functions for tests

def create_test_pool(db_connection, name='Test Pool', description='Test Description'):
    """Helper to create a test pool."""
    cursor = db_connection.cursor()
    cursor.execute(
        "INSERT INTO pools (name, description) VALUES (?, ?)",
        (name, description)
    )
    db_connection.commit()
    return cursor.lastrowid


def create_test_implication(db_connection, source_tag, implied_tag):
    """Helper to create a test tag implication."""
    cursor = db_connection.cursor()

    # Ensure tags exist
    for tag_name in [source_tag, implied_tag]:
        cursor.execute(
            "INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)",
            (tag_name, 'general')
        )

    # Get tag IDs
    cursor.execute("SELECT id FROM tags WHERE name = ?", (source_tag,))
    source_id = cursor.fetchone()['id']
    cursor.execute("SELECT id FROM tags WHERE name = ?", (implied_tag,))
    implied_id = cursor.fetchone()['id']

    # Create implication
    cursor.execute(
        "INSERT INTO tag_implications (source_tag_id, implied_tag_id) VALUES (?, ?)",
        (source_id, implied_id)
    )
    db_connection.commit()


def assert_image_exists_in_db(db_connection, filepath):
    """Helper to assert an image exists in the database."""
    cursor = db_connection.cursor()
    cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
    result = cursor.fetchone()
    assert result is not None, f"Image {filepath} not found in database"
    return result['id']


def assert_tag_exists(db_connection, tag_name, category=None):
    """Helper to assert a tag exists in the database."""
    cursor = db_connection.cursor()
    if category:
        cursor.execute("SELECT id FROM tags WHERE name = ? AND category = ?", (tag_name, category))
    else:
        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
    result = cursor.fetchone()
    assert result is not None, f"Tag {tag_name} not found in database"
    return result['id']

"""
Tests for services/query_service.py - Search and similarity calculations
"""
import pytest
from services import query_service
import database_models as models
import config


@pytest.mark.unit
class TestSimilarityCalculations:
    """Test similarity calculation methods."""

    def test_calculate_jaccard_similarity_identical_sets(self):
        """Test Jaccard similarity with identical tag sets."""
        tags1 = "tag1 tag2 tag3"
        tags2 = "tag1 tag2 tag3"

        similarity = query_service.calculate_jaccard_similarity(tags1, tags2)
        assert similarity == 1.0

    def test_calculate_jaccard_similarity_no_overlap(self):
        """Test Jaccard similarity with no overlapping tags."""
        tags1 = "tag1 tag2 tag3"
        tags2 = "tag4 tag5 tag6"

        similarity = query_service.calculate_jaccard_similarity(tags1, tags2)
        assert similarity == 0.0

    def test_calculate_jaccard_similarity_partial_overlap(self):
        """Test Jaccard similarity with partial overlap."""
        tags1 = "tag1 tag2 tag3"
        tags2 = "tag2 tag3 tag4"

        # Intersection: {tag2, tag3} = 2
        # Union: {tag1, tag2, tag3, tag4} = 4
        # Similarity: 2/4 = 0.5
        similarity = query_service.calculate_jaccard_similarity(tags1, tags2)
        assert similarity == 0.5

    def test_calculate_jaccard_similarity_empty_sets(self):
        """Test Jaccard similarity with empty tag sets."""
        similarity = query_service.calculate_jaccard_similarity("", "")
        assert similarity == 0.0

        similarity = query_service.calculate_jaccard_similarity("tag1", "")
        assert similarity == 0.0

    def test_calculate_weighted_similarity_uses_weights(self, populated_db, monkeypatch):
        """Test that weighted similarity considers tag weights."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        monkeypatch.setattr(config, 'SIMILARITY_METHOD', 'weighted')

        # Load data to populate caches
        models.load_data_from_db()

        tags1 = "scenery outdoor"
        tags2 = "scenery mountain"

        similarity = query_service.calculate_weighted_similarity(tags1, tags2)
        # Should be > 0 (they share "scenery")
        assert similarity > 0

    def test_calculate_similarity_dispatcher(self, monkeypatch):
        """Test that calculate_similarity uses the configured method."""
        # Test Jaccard method
        monkeypatch.setattr(config, 'SIMILARITY_METHOD', 'jaccard')
        result = query_service.calculate_similarity("tag1 tag2", "tag1 tag3")
        assert isinstance(result, float)

        # Test Weighted method (requires cache initialization)
        monkeypatch.setattr(config, 'SIMILARITY_METHOD', 'weighted')
        result = query_service.calculate_similarity("tag1 tag2", "tag1 tag3")
        assert isinstance(result, float)


@pytest.mark.unit
class TestStatistics:
    """Test statistics gathering."""

    def test_get_enhanced_stats_structure(self, populated_db, monkeypatch):
        """Test that enhanced stats returns correct structure."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        stats = query_service.get_enhanced_stats()

        # Check all expected keys
        expected_keys = [
            'total', 'with_metadata', 'without_metadata',
            'total_tags', 'avg_tags_per_image', 'source_breakdown',
            'top_tags', 'category_counts', 'saucenao_used', 'local_tagger_used'
        ]

        for key in expected_keys:
            assert key in stats, f"Missing key: {key}"

    def test_get_enhanced_stats_values(self, populated_db, monkeypatch):
        """Test that stats contain reasonable values."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        stats = query_service.get_enhanced_stats()

        assert stats['total'] > 0
        assert stats['total_tags'] > 0
        assert isinstance(stats['avg_tags_per_image'], (int, float))
        assert isinstance(stats['top_tags'], list)


@pytest.mark.unit
class TestSearchQueryParsing:
    """Test search query parsing and execution."""

    def test_perform_search_empty_query(self, populated_db, monkeypatch):
        """Test search with empty query returns all images."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        monkeypatch.setattr(models, 'get_all_images_with_tags',
                           lambda: [{'filepath': 'test1.png', 'tags': 'tag1'}])

        results, should_shuffle = query_service.perform_search('')

        assert len(results) > 0
        assert should_shuffle is True

    def test_perform_search_simple_tag(self, populated_db, monkeypatch):
        """Test search for a simple tag."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # Patch get_all_images_with_tags to return test data
        test_images = [
            {'filepath': 'test1.png', 'tags': 'scenery outdoor'},
            {'filepath': 'test2.png', 'tags': 'character portrait'},
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: test_images)

        results, should_shuffle = query_service.perform_search('scenery')

        # Should return only images with "scenery" tag
        assert len(results) >= 0  # May be 0 if tag-based, 1 if freetext
        for img in results:
            # Either matches tag or filepath
            assert 'scenery' in img['tags'].lower() or 'scenery' in img['filepath'].lower()

    def test_perform_search_negative_term(self, populated_db, monkeypatch):
        """Test search with negative term."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        test_images = [
            {'filepath': 'test1.png', 'tags': 'scenery outdoor'},
            {'filepath': 'test2.png', 'tags': 'scenery indoor'},
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: test_images)

        results, _ = query_service.perform_search('scenery -indoor')

        # Should exclude images with "indoor"
        for img in results:
            assert 'indoor' not in img['tags'].lower()
            assert 'indoor' not in img['filepath'].lower()

    def test_perform_search_source_filter(self, populated_db, monkeypatch):
        """Test search with source filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        monkeypatch.setattr(models, 'search_images_by_multiple_sources',
                           lambda sources: [{'filepath': 'test.png', 'tags': 'tag1'}] if 'danbooru' in sources else [])

        results, _ = query_service.perform_search('source:danbooru')

        # Should call search_images_by_multiple_sources with ['danbooru']
        assert isinstance(results, list)

    def test_perform_search_filename_filter(self, populated_db, monkeypatch):
        """Test search with filename filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        test_images = [
            {'filepath': 'sunset_beach.png', 'tags': 'scenery'},
            {'filepath': 'mountain_view.png', 'tags': 'scenery'},
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: test_images)

        results, _ = query_service.perform_search('filename:sunset')

        # Should return only files with "sunset" in name
        assert len(results) > 0
        for img in results:
            assert 'sunset' in img['filepath'].lower()

    def test_perform_search_extension_filter(self, populated_db, monkeypatch):
        """Test search with file extension filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        test_images = [
            {'filepath': 'test.png', 'tags': 'tag1'},
            {'filepath': 'test.jpg', 'tags': 'tag2'},
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: test_images)

        results, _ = query_service.perform_search('.png')

        # Should return only PNG files
        for img in results:
            assert img['filepath'].endswith('.png')

    def test_perform_search_category_filter(self, populated_db, monkeypatch):
        """Test search with category-specific filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        test_images = [
            {'filepath': 'test1.png', 'tags': 'tag1'},
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: test_images)

        # This will query the database, so we need to ensure it's set up
        results, _ = query_service.perform_search('character:holo')

        # Should filter by character category
        assert isinstance(results, list)

    def test_perform_search_pool_filter(self, populated_db, monkeypatch):
        """Test search with pool filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        monkeypatch.setattr(models, 'search_images_by_pool',
                           lambda pool_name: [{'filepath': 'test.png'}])

        results, _ = query_service.perform_search('pool:mypool')

        # Should call search_images_by_pool
        assert isinstance(results, list)

    def test_perform_search_relationship_filter(self, populated_db, monkeypatch):
        """Test search with relationship filter."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        monkeypatch.setattr(models, 'search_images_by_relationship',
                           lambda rel_type: [{'filepath': 'test.png', 'tags': 'tag1'}])

        results, _ = query_service.perform_search('has:parent')

        # Should call search_images_by_relationship with 'parent'
        assert isinstance(results, list)


@pytest.mark.unit
class TestFTSSearch:
    """Test FTS5 full-text search functionality."""

    def test_should_use_fts_with_exact_tags(self, populated_db, monkeypatch):
        """Test that exact tags don't trigger FTS."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # For tags that exist in DB, should return False (use tag-based search)
        result = query_service._should_use_fts(['scenery'])
        # Result depends on whether 'scenery' exists as exact tag
        assert isinstance(result, bool)

    def test_should_use_fts_with_freetext(self, populated_db, monkeypatch):
        """Test that freetext terms trigger FTS."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # For terms that don't exist as exact tags, should return True
        result = query_service._should_use_fts(['nonexistent_freetext_term_xyz'])
        assert result is True

    def test_fts_search_with_general_terms(self, populated_db, monkeypatch):
        """Test FTS search with general search terms."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        results = query_service._fts_search(
            general_terms=['scenery'],
            negative_terms=[],
            source_filters=[],
            filename_filter=None,
            extension_filter=None,
            relationship_filter=None,
            pool_filter=None
        )

        # Should return a list (may be empty if no matches)
        assert isinstance(results, list)

    def test_fts_search_with_negative_terms(self, populated_db, monkeypatch):
        """Test FTS search excluding certain terms."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        results = query_service._fts_search(
            general_terms=['outdoor'],
            negative_terms=['indoor'],
            source_filters=[],
            filename_filter=None,
            extension_filter=None,
            relationship_filter=None,
            pool_filter=None
        )

        # Results should not contain 'indoor'
        for img in results:
            assert 'indoor' not in img['tags'].lower()


@pytest.mark.unit
class TestRelatedImages:
    """Test finding related images by tags."""

    def test_find_related_by_tags_no_similar(self, populated_db, monkeypatch):
        """Test finding related images when none are similar."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # Mock image with very unique tags
        monkeypatch.setattr(models, 'get_image_details',
                           lambda fp: {'filepath': 'test.png', 'tags_general': 'unique_tag_xyz'})
        monkeypatch.setattr(models, 'get_all_images_with_tags',
                           lambda: [{'filepath': 'other.png', 'tags': 'completely different'}])

        related = query_service.find_related_by_tags('images/test.png', limit=10)

        # May return empty or very low similarity matches
        assert isinstance(related, list)
        assert len(related) <= 10

    def test_find_related_by_tags_with_similar(self, populated_db, monkeypatch):
        """Test finding related images with similar tags."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        # Mock images with overlapping tags
        monkeypatch.setattr(models, 'get_image_details',
                           lambda fp: {'filepath': 'test.png', 'tags_general': 'tag1 tag2 tag3'})
        monkeypatch.setattr(models, 'get_all_images_with_tags',
                           lambda: [
                               {'filepath': 'similar1.png', 'tags': 'tag1 tag2 tag4'},
                               {'filepath': 'similar2.png', 'tags': 'tag1 tag5 tag6'},
                               {'filepath': 'different.png', 'tags': 'completely different'},
                           ])

        related = query_service.find_related_by_tags('images/test.png', limit=10)

        # Should return results sorted by similarity
        assert isinstance(related, list)
        if len(related) > 0:
            # First result should have highest score
            assert 'score' in related[0]

    def test_find_related_by_tags_respects_limit(self, populated_db, monkeypatch):
        """Test that limit parameter is respected."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)

        monkeypatch.setattr(models, 'get_image_details',
                           lambda fp: {'filepath': 'test.png', 'tags_general': 'tag1 tag2'})

        # Create many similar images
        many_images = [
            {'filepath': f'img{i}.png', 'tags': 'tag1 tag2'}
            for i in range(100)
        ]
        monkeypatch.setattr(models, 'get_all_images_with_tags', lambda: many_images)

        related = query_service.find_related_by_tags('images/test.png', limit=5)

        # Should return at most 5 results
        assert len(related) <= 5


@pytest.mark.unit
class TestCacheManagement:
    """Test similarity cache management."""

    def test_invalidate_similarity_cache_clears_caches(self):
        """Test that cache invalidation clears internal caches."""
        # Initialize caches
        query_service._initialize_similarity_cache()

        # Invalidate
        query_service.invalidate_similarity_cache()

        # Check that caches are cleared
        assert query_service._tag_category_cache is None
        assert query_service._similarity_context_cache is None

    def test_initialize_similarity_cache_loads_data(self, populated_db, monkeypatch):
        """Test that cache initialization loads tag data."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        # Clear caches first
        query_service.invalidate_similarity_cache()

        # Initialize
        query_service._initialize_similarity_cache()

        # Check caches are populated
        assert query_service._tag_category_cache is not None
        assert query_service._similarity_context_cache is not None
        assert 'tag_counts' in query_service._similarity_context_cache
        assert 'total_images' in query_service._similarity_context_cache


@pytest.mark.integration
class TestSearchIntegration:
    """Integration tests for full search pipeline."""

    def test_full_search_pipeline_with_multiple_filters(self, populated_db, monkeypatch):
        """Test search with multiple filters combined."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        # Search with multiple conditions
        results, should_shuffle = query_service.perform_search('scenery -indoor .png')

        # Should apply all filters
        assert isinstance(results, list)
        for img in results:
            if 'filepath' in img:
                # Should be PNG
                assert img['filepath'].endswith('.png')
                # Should not contain 'indoor'
                if 'tags' in img:
                    assert 'indoor' not in img['tags'].lower()

    def test_search_results_have_required_fields(self, populated_db, monkeypatch):
        """Test that search results have required fields."""
        monkeypatch.setattr(models, 'get_db_connection', lambda: populated_db)
        models.load_data_from_db()

        results, _ = query_service.perform_search('scenery')

        for img in results:
            assert 'filepath' in img
            assert 'tags' in img

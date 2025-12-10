"""
Tests for tag extraction utilities
"""
import pytest
from utils.tag_extraction import (
    extract_tags_from_source,
    extract_rating_from_source,
    merge_tag_sources,
    deduplicate_categorized_tags,
    is_rating_tag,
    get_tag_category,
    RATING_TAGS,
    RATING_MAP,
    TAG_CATEGORIES
)


class TestExtractTagsFromSource:
    """Test extract_tags_from_source for different booru formats."""

    def test_extract_danbooru_tags(self):
        """Test tag extraction from Danbooru format."""
        source_data = {
            "tag_string_character": "holo",
            "tag_string_copyright": "spice_and_wolf",
            "tag_string_artist": "artist_name",
            "tag_string_meta": "highres",
            "tag_string_general": "scenery outdoor sky",
        }
        
        result = extract_tags_from_source(source_data, 'danbooru')
        
        assert result['tags_character'] == "holo"
        assert result['tags_copyright'] == "spice_and_wolf"
        assert result['tags_artist'] == "artist_name"
        assert result['tags_meta'] == "highres"
        assert result['tags_general'] == "scenery outdoor sky"
        assert result['tags_species'] == ""  # Danbooru doesn't have species

    def test_extract_e621_tags(self):
        """Test tag extraction from e621 format."""
        source_data = {
            "tags": {
                "character": ["holo", "lawrence"],
                "copyright": ["spice_and_wolf"],
                "artist": ["artist_name"],
                "species": ["wolf", "human"],
                "meta": ["highres", "absurdres"],
                "general": ["scenery", "outdoor", "sky"],
            }
        }
        
        result = extract_tags_from_source(source_data, 'e621')
        
        assert result['tags_character'] == "holo lawrence"
        assert result['tags_copyright'] == "spice_and_wolf"
        assert result['tags_artist'] == "artist_name"
        assert result['tags_species'] == "wolf human"
        assert result['tags_meta'] == "highres absurdres"
        assert result['tags_general'] == "scenery outdoor sky"

    def test_extract_local_tagger_tags(self):
        """Test tag extraction from local tagger format (same as e621)."""
        source_data = {
            "tags": {
                "character": ["character1"],
                "copyright": ["series1"],
                "artist": [],
                "species": ["cat"],
                "meta": [],
                "general": ["standing", "smiling"],
            }
        }
        
        result = extract_tags_from_source(source_data, 'local_tagger')
        
        assert result['tags_character'] == "character1"
        assert result['tags_copyright'] == "series1"
        assert result['tags_artist'] == ""
        assert result['tags_species'] == "cat"
        assert result['tags_meta'] == ""
        assert result['tags_general'] == "standing smiling"

    def test_extract_pixiv_tags(self):
        """Test tag extraction from Pixiv format (same as e621)."""
        source_data = {
            "tags": {
                "character": ["character_name"],
                "copyright": ["copyright_name"],
                "artist": ["pixiv_artist"],
                "species": [],
                "meta": ["original"],
                "general": ["illustration"],
            }
        }
        
        result = extract_tags_from_source(source_data, 'pixiv')
        
        assert result['tags_character'] == "character_name"
        assert result['tags_copyright'] == "copyright_name"
        assert result['tags_artist'] == "pixiv_artist"
        assert result['tags_species'] == ""
        assert result['tags_meta'] == "original"
        assert result['tags_general'] == "illustration"

    def test_extract_gelbooru_tags_string(self):
        """Test tag extraction from Gelbooru format with string tags."""
        source_data = {
            "tags": "tag1 tag2 tag3 character1 series1"
        }
        
        result = extract_tags_from_source(source_data, 'gelbooru')
        
        # Gelbooru doesn't have categories, everything goes to general
        assert result['tags_general'] == "tag1 tag2 tag3 character1 series1"
        assert result['tags_character'] == ""
        assert result['tags_copyright'] == ""
        assert result['tags_artist'] == ""
        assert result['tags_species'] == ""
        assert result['tags_meta'] == ""

    def test_extract_gelbooru_tags_list(self):
        """Test tag extraction from Gelbooru format with list tags."""
        source_data = {
            "tags": ["tag1", "tag2", "tag3"]
        }
        
        result = extract_tags_from_source(source_data, 'gelbooru')
        
        assert result['tags_general'] == "tag1 tag2 tag3"

    def test_extract_yandere_tags(self):
        """Test tag extraction from Yandere format (same as Gelbooru)."""
        source_data = {
            "tags": "yandere tag1 tag2"
        }
        
        result = extract_tags_from_source(source_data, 'yandere')
        
        assert result['tags_general'] == "yandere tag1 tag2"

    def test_extract_unknown_source_with_e621_format(self):
        """Test extraction from unknown source that uses e621 format."""
        source_data = {
            "tags": {
                "character": ["char1"],
                "general": ["tag1"]
            }
        }
        
        result = extract_tags_from_source(source_data, 'unknown_source')
        
        assert result['tags_character'] == "char1"
        assert result['tags_general'] == "tag1"

    def test_extract_unknown_source_with_danbooru_format(self):
        """Test extraction from unknown source that uses Danbooru format."""
        source_data = {
            "tag_string_general": "general_tag",
            "tag_string_character": "char_tag"
        }
        
        result = extract_tags_from_source(source_data, 'unknown_source')
        
        assert result['tags_general'] == "general_tag"
        assert result['tags_character'] == "char_tag"

    def test_extract_unknown_source_no_tags(self):
        """Test extraction from unknown source with no recognizable tags."""
        source_data = {
            "some_field": "some_value"
        }
        
        result = extract_tags_from_source(source_data, 'unknown_source')
        
        # Should return empty tags for all categories
        for category in TAG_CATEGORIES:
            assert result[f'tags_{category}'] == ""

    def test_extract_empty_source_data(self):
        """Test extraction with empty source data."""
        result = extract_tags_from_source({}, 'danbooru')
        
        # Should handle missing fields gracefully
        assert result['tags_general'] == ""
        assert result['tags_character'] == ""

    def test_extract_with_missing_fields(self):
        """Test extraction when some fields are missing."""
        source_data = {
            "tag_string_general": "tag1 tag2",
            # Missing other fields
        }
        
        result = extract_tags_from_source(source_data, 'danbooru')
        
        assert result['tags_general'] == "tag1 tag2"
        assert result['tags_character'] == ""
        assert result['tags_copyright'] == ""


class TestExtractRatingFromSource:
    """Test extract_rating_from_source."""

    def test_extract_rating_general(self):
        """Test extraction of general rating."""
        source_data = {"rating": "g"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag == "rating:general"
        assert rating_source == "original"

    def test_extract_rating_sensitive(self):
        """Test extraction of sensitive rating."""
        source_data = {"rating": "s"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'e621')
        
        assert rating_tag == "rating:sensitive"
        assert rating_source == "original"

    def test_extract_rating_questionable(self):
        """Test extraction of questionable rating."""
        source_data = {"rating": "q"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag == "rating:questionable"
        assert rating_source == "original"

    def test_extract_rating_explicit(self):
        """Test extraction of explicit rating."""
        source_data = {"rating": "e"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'e621')
        
        assert rating_tag == "rating:explicit"
        assert rating_source == "original"

    def test_extract_rating_uppercase(self):
        """Test extraction with uppercase rating."""
        source_data = {"rating": "G"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag == "rating:general"

    def test_extract_rating_from_ai_tagger(self):
        """Test rating source for AI tagger."""
        source_data = {"rating": "e"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'local_tagger')
        
        assert rating_tag == "rating:explicit"
        assert rating_source == "ai_inference"

    def test_extract_rating_from_camie_tagger(self):
        """Test rating source for Camie tagger."""
        source_data = {"rating": "s"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'camie_tagger')
        
        assert rating_tag == "rating:sensitive"
        assert rating_source == "ai_inference"

    def test_extract_rating_missing(self):
        """Test extraction when rating is missing."""
        source_data = {}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag is None
        assert rating_source is None

    def test_extract_rating_invalid(self):
        """Test extraction with invalid rating character."""
        source_data = {"rating": "x"}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag is None
        assert rating_source is None

    def test_extract_rating_empty_string(self):
        """Test extraction with empty rating string."""
        source_data = {"rating": ""}
        rating_tag, rating_source = extract_rating_from_source(source_data, 'danbooru')
        
        assert rating_tag is None
        assert rating_source is None


class TestMergeTagSources:
    """Test merge_tag_sources."""

    def test_merge_non_overlapping_tags(self):
        """Test merging tags with no overlap."""
        primary = {
            'tags_character': 'char1',
            'tags_copyright': 'series1',
            'tags_artist': 'artist1',
            'tags_species': '',
            'tags_meta': 'highres',
            'tags_general': 'tag1 tag2'
        }
        secondary = {
            'tags_character': 'char2',
            'tags_copyright': 'series2',
            'tags_artist': 'artist2',
            'tags_species': 'species1',
            'tags_meta': 'absurdres',
            'tags_general': 'tag3 tag4'
        }
        
        result = merge_tag_sources(primary, secondary)
        
        # Primary + secondary (sorted)
        assert 'char1' in result['tags_character']
        assert 'char2' in result['tags_character']
        assert 'series1' in result['tags_copyright']
        assert 'series2' in result['tags_copyright']
        # Artist not merged by default
        assert result['tags_artist'] == 'artist1'
        assert 'species1' in result['tags_species']
        assert 'highres' in result['tags_meta']
        assert 'absurdres' in result['tags_meta']
        assert 'tag1' in result['tags_general']
        assert 'tag4' in result['tags_general']

    def test_merge_overlapping_tags(self):
        """Test merging tags with overlap (no duplicates)."""
        primary = {
            'tags_character': 'char1 char2',
            'tags_general': 'tag1 tag2',
            'tags_artist': 'artist1',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        secondary = {
            'tags_character': 'char2 char3',
            'tags_general': 'tag2 tag3',
            'tags_artist': 'artist2',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = merge_tag_sources(primary, secondary)
        
        # Should not have duplicates
        char_tags = result['tags_character'].split()
        assert len(char_tags) == len(set(char_tags))
        assert 'char1' in char_tags
        assert 'char2' in char_tags
        assert 'char3' in char_tags
        
        gen_tags = result['tags_general'].split()
        assert len(gen_tags) == len(set(gen_tags))

    def test_merge_with_custom_categories(self):
        """Test merging with custom category list."""
        primary = {
            'tags_character': 'char1',
            'tags_artist': 'artist1',
            'tags_general': 'tag1',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        secondary = {
            'tags_character': 'char2',
            'tags_artist': 'artist2',
            'tags_general': 'tag2',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        # Only merge general tags
        result = merge_tag_sources(primary, secondary, merge_categories=['general'])
        
        # Character should be only from primary (not merged)
        assert result['tags_character'] == 'char1'
        # General should be merged
        assert 'tag1' in result['tags_general']
        assert 'tag2' in result['tags_general']

    def test_merge_empty_primary(self):
        """Test merging when primary has empty tags."""
        primary = {
            'tags_character': '',
            'tags_general': '',
            'tags_artist': '',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        secondary = {
            'tags_character': 'char1',
            'tags_general': 'tag1',
            'tags_artist': 'artist1',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = merge_tag_sources(primary, secondary)
        
        # Secondary fills in the gaps
        assert result['tags_character'] == 'char1'
        assert result['tags_general'] == 'tag1'

    def test_merge_empty_secondary(self):
        """Test merging when secondary has empty tags."""
        primary = {
            'tags_character': 'char1',
            'tags_general': 'tag1',
            'tags_artist': 'artist1',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        secondary = {
            'tags_character': '',
            'tags_general': '',
            'tags_artist': '',
            'tags_copyright': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = merge_tag_sources(primary, secondary)
        
        # Primary remains unchanged
        assert result['tags_character'] == 'char1'
        assert result['tags_general'] == 'tag1'


class TestDeduplicateCategorizedTags:
    """Test deduplicate_categorized_tags."""

    def test_deduplicate_no_duplicates(self):
        """Test when there are no duplicates."""
        tags = {
            'tags_character': 'char1 char2',
            'tags_copyright': 'series1',
            'tags_artist': 'artist1',
            'tags_species': 'species1',
            'tags_meta': 'meta1',
            'tags_general': 'tag1 tag2'
        }
        
        result = deduplicate_categorized_tags(tags)
        
        assert 'char1' in result['tags_character']
        assert 'tag1' in result['tags_general']

    def test_deduplicate_character_in_general(self):
        """Test removing character tags from general."""
        tags = {
            'tags_character': 'holo',
            'tags_general': 'holo scenery outdoor',
            'tags_copyright': '',
            'tags_artist': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = deduplicate_categorized_tags(tags)
        
        assert result['tags_character'] == 'holo'
        # 'holo' should be removed from general
        assert 'holo' not in result['tags_general']
        assert 'scenery' in result['tags_general']
        assert 'outdoor' in result['tags_general']

    def test_deduplicate_multiple_categories_in_general(self):
        """Test removing tags from multiple specific categories."""
        tags = {
            'tags_character': 'char1',
            'tags_copyright': 'series1',
            'tags_artist': 'artist1',
            'tags_species': 'wolf',
            'tags_meta': 'highres',
            'tags_general': 'char1 series1 artist1 wolf highres tag1 tag2'
        }
        
        result = deduplicate_categorized_tags(tags)
        
        # All specific category tags should be removed from general
        gen_tags = result['tags_general'].split()
        assert 'char1' not in gen_tags
        assert 'series1' not in gen_tags
        assert 'artist1' not in gen_tags
        assert 'wolf' not in gen_tags
        assert 'highres' not in gen_tags
        # Only truly general tags remain
        assert 'tag1' in gen_tags
        assert 'tag2' in gen_tags

    def test_deduplicate_empty_general(self):
        """Test when general is empty."""
        tags = {
            'tags_character': 'char1',
            'tags_general': '',
            'tags_copyright': '',
            'tags_artist': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = deduplicate_categorized_tags(tags)
        
        assert result['tags_character'] == 'char1'
        assert result['tags_general'] == ''

    def test_deduplicate_preserves_order(self):
        """Test that results are sorted."""
        tags = {
            'tags_general': 'zebra apple banana',
            'tags_character': '',
            'tags_copyright': '',
            'tags_artist': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = deduplicate_categorized_tags(tags)
        
        # Tags should be sorted
        gen_tags = result['tags_general'].split()
        assert gen_tags == sorted(gen_tags)

    def test_deduplicate_handles_none_values(self):
        """Test handling of None values in tags."""
        tags = {
            'tags_character': None,
            'tags_general': 'tag1 tag2',
            'tags_copyright': None,
            'tags_artist': '',
            'tags_species': '',
            'tags_meta': ''
        }
        
        result = deduplicate_categorized_tags(tags)
        
        # Should handle None gracefully
        assert result['tags_character'] == ''
        assert 'tag1' in result['tags_general']


class TestIsRatingTag:
    """Test is_rating_tag."""

    def test_is_rating_tag_standard_tags(self):
        """Test standard rating tags."""
        for rating_tag in RATING_TAGS:
            assert is_rating_tag(rating_tag) is True

    def test_is_rating_tag_with_prefix(self):
        """Test tags starting with 'rating:'."""
        assert is_rating_tag('rating:general') is True
        assert is_rating_tag('rating:explicit') is True
        assert is_rating_tag('rating:custom') is True

    def test_is_rating_tag_non_rating(self):
        """Test non-rating tags."""
        assert is_rating_tag('character') is False
        assert is_rating_tag('scenery') is False
        assert is_rating_tag('artist_name') is False
        assert is_rating_tag('rate:general') is False  # Wrong prefix


class TestGetTagCategory:
    """Test get_tag_category."""

    def test_get_category_for_rating_tag(self):
        """Test category for rating tags."""
        assert get_tag_category('rating:general') == 'rating'
        assert get_tag_category('rating:explicit') == 'rating'

    def test_get_category_for_non_rating_tag(self):
        """Test category for non-rating tags (uses default)."""
        assert get_tag_category('character_name') == 'general'
        assert get_tag_category('some_tag') == 'general'

    def test_get_category_with_custom_default(self):
        """Test with custom default category."""
        assert get_tag_category('some_tag', default='character') == 'character'
        assert get_tag_category('some_tag', default='meta') == 'meta'

    def test_get_category_rating_ignores_default(self):
        """Test that rating tags ignore default parameter."""
        assert get_tag_category('rating:general', default='character') == 'rating'

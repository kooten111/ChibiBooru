#!/usr/bin/env python3
"""
Test script to verify multi-source tag merging logic.

This script tests the merge_multiple_tag_sources function to ensure
tags from multiple booru sources are correctly merged with proper
category priority handling.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.tag_extraction import merge_multiple_tag_sources, TAG_CATEGORIES


def test_basic_merge():
    """Test that tags from multiple sources are combined."""
    source_results = {
        'danbooru': {
            'tag_string_general': 'solo standing smile',
            'tag_string_character': 'hatsune_miku',
            'tag_string_copyright': 'vocaloid',
            'tag_string_artist': 'artist_name',
            'tag_string_meta': 'highres',
        },
        'e621': {
            'tags': {
                'general': ['solo', 'blue_hair', 'twintails'],
                'character': ['hatsune_miku'],
                'copyright': ['vocaloid'],
                'artist': ['artist_name'],
                'species': ['humanoid'],
                'meta': ['hi_res'],
            }
        }
    }
    
    result = merge_multiple_tag_sources(source_results)
    
    # Check that tags from both sources are included
    general_tags = set(result['tags_general'].split())
    assert 'solo' in general_tags, "Common tag 'solo' should be in general"
    assert 'standing' in general_tags, "Danbooru-only tag 'standing' should be in general"
    assert 'smile' in general_tags, "Danbooru-only tag 'smile' should be in general"
    assert 'blue_hair' in general_tags, "e621-only tag 'blue_hair' should be in general"
    assert 'twintails' in general_tags, "e621-only tag 'twintails' should be in general"
    
    # Check species (only from e621)
    species_tags = set(result['tags_species'].split())
    assert 'humanoid' in species_tags, "e621 species tag should be present"
    
    # Check character
    char_tags = set(result['tags_character'].split())
    assert 'hatsune_miku' in char_tags, "Character tag should be present"
    
    print("✓ test_basic_merge passed")


def test_category_priority():
    """Test that higher priority categories win when tag appears in multiple categories."""
    # This simulates a case where e621 might categorize a tag as 'species'
    # while Danbooru puts it in 'general'. Species should win (higher priority).
    source_results = {
        'danbooru': {
            'tag_string_general': 'solo fox',  # 'fox' is in general
            'tag_string_character': '',
            'tag_string_copyright': '',
            'tag_string_artist': '',
            'tag_string_meta': '',
        },
        'e621': {
            'tags': {
                'general': ['solo'],
                'character': [],
                'copyright': [],
                'artist': [],
                'species': ['fox'],  # 'fox' is in species (higher priority)
                'meta': [],
            }
        }
    }
    
    result = merge_multiple_tag_sources(source_results)
    
    # 'fox' should be in species (priority 5) not general (priority 1)
    species_tags = set(result['tags_species'].split())
    general_tags = set(result['tags_general'].split())
    
    assert 'fox' in species_tags, "'fox' should be in species (higher priority)"
    assert 'fox' not in general_tags, "'fox' should NOT be in general"
    assert 'solo' in general_tags, "'solo' should remain in general"
    
    print("✓ test_category_priority passed")


def test_empty_sources():
    """Test handling of empty or None source data."""
    source_results = {
        'danbooru': {
            'tag_string_general': 'solo',
            'tag_string_character': '',
            'tag_string_copyright': '',
            'tag_string_artist': '',
            'tag_string_meta': '',
        },
        'e621': None,  # None source
        'gelbooru': {},  # Empty dict
    }
    
    result = merge_multiple_tag_sources(source_results)
    
    general_tags = set(result['tags_general'].split())
    assert 'solo' in general_tags, "Should still get tags from valid source"
    
    print("✓ test_empty_sources passed")


def test_all_categories_present():
    """Test that result contains all expected category keys."""
    source_results = {
        'danbooru': {
            'tag_string_general': 'solo',
            'tag_string_character': 'test_char',
            'tag_string_copyright': 'test_copy',
            'tag_string_artist': 'test_artist',
            'tag_string_meta': 'test_meta',
        }
    }
    
    result = merge_multiple_tag_sources(source_results)
    
    expected_keys = [f'tags_{cat}' for cat in TAG_CATEGORIES]
    for key in expected_keys:
        assert key in result, f"Result should contain key '{key}'"
    
    print("✓ test_all_categories_present passed")


if __name__ == '__main__':
    print("Running tag merging tests...\n")
    
    test_basic_merge()
    test_category_priority()
    test_empty_sources()
    test_all_categories_present()
    
    print("\n✅ All tests passed!")

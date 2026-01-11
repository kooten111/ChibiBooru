"""
Processing service facade.

This module provides backward compatibility by re-exporting all functions
from the new processing package structure.

The processing functionality has been split into focused modules:
- processing/rate_limiter.py: SauceNAO API rate limiting
- processing/locks.py: File-based locking
- processing/metadata_fetchers.py: Metadata fetching from various sources
- processing/image_processor.py: Core image processing logic
- processing/thumbnail_generator.py: Thumbnail generation
"""

# Re-export everything from the processing package for backward compatibility
from .processing import (
    AdaptiveSauceNAORateLimiter,
    saucenao_rate_limiter,
    acquire_processing_lock,
    release_processing_lock,
    search_danbooru,
    search_e621,
    search_all_sources,
    search_saucenao,
    fetch_by_post_id,
    fetch_pixiv_metadata,
    download_pixiv_image,
    extract_pixiv_id_from_filename,
    tag_with_local_tagger,
    tag_video_with_frames,
    check_ffmpeg_available,
    extract_tag_data,
    process_image_file,
    ensure_thumbnail,
)

__all__ = [
    'AdaptiveSauceNAORateLimiter',
    'saucenao_rate_limiter',
    'acquire_processing_lock',
    'release_processing_lock',
    'search_danbooru',
    'search_e621',
    'search_all_sources',
    'search_saucenao',
    'fetch_by_post_id',
    'fetch_pixiv_metadata',
    'download_pixiv_image',
    'extract_pixiv_id_from_filename',
    'tag_with_local_tagger',
    'tag_video_with_frames',
    'check_ffmpeg_available',
    'extract_tag_data',
    'process_image_file',
    'ensure_thumbnail',
]

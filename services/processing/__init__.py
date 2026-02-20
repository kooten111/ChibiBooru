"""
Processing service package.

This package contains image processing functionality split into focused modules:
- rate_limiter: SauceNAO API rate limiting
- locks: File-based locking for concurrent processing
- metadata_fetchers: Fetching metadata from various sources
- image_processor: Core image processing logic
- thumbnail_generator: Thumbnail generation
"""

from .rate_limiter import AdaptiveSauceNAORateLimiter, saucenao_rate_limiter
from .locks import acquire_processing_lock, release_processing_lock
from .metadata_fetchers import (
    search_danbooru,
    search_e621,
    search_all_sources,
    search_saucenao,
    fetch_by_post_id,
    fetch_pixiv_metadata,
    download_pixiv_image,
    extract_pixiv_id_from_filename
)
from .image_processor import (
    tag_with_local_tagger,
    tag_video_with_frames,
    check_ffmpeg_available,
    extract_tag_data,
    process_image_file,
    is_pixiv_complemented
)
from .thumbnail_generator import ensure_thumbnail
from . import constants

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
    'is_pixiv_complemented',
    'ensure_thumbnail',
]

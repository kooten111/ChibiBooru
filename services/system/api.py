from .broken_images import run_cleanup_broken_images, run_find_broken_images
from .bulk_retag import bulk_retag_local_task, run_bulk_retag_local
from .dedup import deduplicate_task, run_deduplicate
from .health import run_database_health_check
from .maintenance import reindex_database_task, run_reindex_database
from .orphans import clean_orphans_task, run_clean_orphans
from .rebuild import (
    apply_merged_sources_task,
    recategorize_task,
    rebuild_categorized_task,
    rebuild_task,
    recount_tags_task,
    run_apply_merged_sources,
    run_rebuild,
    run_rebuild_categorized,
    run_recategorize,
    run_recount_tags,
)
from .scan import run_scan_and_process, scan_and_process_task
from .status import get_system_status, get_task_status_by_id, run_reload_data, validate_secret_string
from .thumbnails import run_thumbnail_generation_task, start_thumbnail_generation

__all__ = [
    "apply_merged_sources_task",
    "bulk_retag_local_task",
    "clean_orphans_task",
    "deduplicate_task",
    "get_system_status",
    "get_task_status_by_id",
    "rebuild_categorized_task",
    "rebuild_task",
    "recategorize_task",
    "recount_tags_task",
    "reindex_database_task",
    "run_apply_merged_sources",
    "run_bulk_retag_local",
    "run_cleanup_broken_images",
    "run_database_health_check",
    "run_deduplicate",
    "run_find_broken_images",
    "run_rebuild",
    "run_rebuild_categorized",
    "run_recategorize",
    "run_recount_tags",
    "run_reindex_database",
    "run_reload_data",
    "run_scan_and_process",
    "run_thumbnail_generation_task",
    "scan_and_process_task",
    "start_thumbnail_generation",
    "validate_secret_string",
]

import os
from typing import Any, Dict, List, Optional

import config
from database import get_db_connection
from services import monitor_service
from services import upscaler_service


def _normalize_settings(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = settings or {}

    use_filesize = _to_bool(settings.get('use_filesize_kb'), config.UPSCALE_MAINTENANCE_USE_FILESIZE_KB)
    max_filesize_kb = _to_int(settings.get('max_filesize_kb'), config.UPSCALE_MAINTENANCE_MAX_FILESIZE_KB)

    use_megapixels = _to_bool(settings.get('use_megapixels'), config.UPSCALE_MAINTENANCE_USE_MEGAPIXELS)
    max_megapixels = _to_float(settings.get('max_megapixels'), config.UPSCALE_MAINTENANCE_MAX_MEGAPIXELS)

    use_dimensions = _to_bool(settings.get('use_dimensions'), config.UPSCALE_MAINTENANCE_USE_DIMENSIONS)
    max_width = _to_int(settings.get('max_width'), config.UPSCALE_MAINTENANCE_MAX_WIDTH)
    max_height = _to_int(settings.get('max_height'), config.UPSCALE_MAINTENANCE_MAX_HEIGHT)

    exclude_upscaled = _to_bool(settings.get('exclude_upscaled'), config.UPSCALE_MAINTENANCE_EXCLUDE_UPSCALED)

    return {
        'use_filesize_kb': use_filesize,
        'max_filesize_kb': max_filesize_kb,
        'use_megapixels': use_megapixels,
        'max_megapixels': max_megapixels,
        'use_dimensions': use_dimensions,
        'max_width': max_width,
        'max_height': max_height,
        'exclude_upscaled': exclude_upscaled,
    }


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('true', '1', 'yes', 'on')


def _to_int(value: Any, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _to_float(value: Any, default: float, minimum: float = 0.01) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _resolve_image_path(filepath: str) -> Optional[str]:
    candidates = [
        filepath,
        os.path.join(config.IMAGE_DIRECTORY, filepath),
        os.path.join('./static', filepath),
        os.path.join('./static/images', filepath),
    ]

    if filepath.startswith('images/'):
        relative = filepath[len('images/'):]
        candidates.append(os.path.join(config.IMAGE_DIRECTORY, relative))
    else:
        candidates.append(f"images/{filepath}")

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def _load_candidates(exclude_upscaled: bool) -> List[Dict[str, Any]]:
    where_parts = [
        "image_width IS NOT NULL",
        "image_height IS NOT NULL",
        "image_width > 0",
        "image_height > 0",
    ]
    if exclude_upscaled:
        where_parts.append("(upscaled_width IS NULL OR upscaled_height IS NULL)")

    query = f"""
        SELECT filepath, image_width, image_height, upscaled_width, upscaled_height
        FROM images
        WHERE {' AND '.join(where_parts)}
        ORDER BY id
    """

    with get_db_connection() as conn:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]


def _collect_matching_filepaths(normalized_settings: Dict[str, Any]) -> Dict[str, Any]:
    use_filesize = normalized_settings['use_filesize_kb']
    max_filesize_kb = normalized_settings['max_filesize_kb']
    use_megapixels = normalized_settings['use_megapixels']
    max_megapixels = normalized_settings['max_megapixels']
    use_dimensions = normalized_settings['use_dimensions']
    max_width = normalized_settings['max_width']
    max_height = normalized_settings['max_height']
    exclude_upscaled = normalized_settings['exclude_upscaled']

    rows = _load_candidates(exclude_upscaled)

    selected_filepaths: List[str] = []
    missing_files = 0
    scanned = 0

    for row in rows:
        filepath = row['filepath']
        if not config.is_supported_image(filepath):
            continue
        if not config.is_upscalable(filepath):
            continue

        scanned += 1
        width = int(row['image_width'])
        height = int(row['image_height'])

        checks: List[bool] = []

        if use_dimensions:
            checks.append(width <= max_width or height <= max_height)

        if use_megapixels:
            megapixels = (width * height) / 1_000_000
            checks.append(megapixels <= max_megapixels)

        if use_filesize:
            disk_path = _resolve_image_path(filepath)
            if not disk_path:
                missing_files += 1
                continue

            filesize_kb = os.path.getsize(disk_path) / 1024
            checks.append(filesize_kb <= max_filesize_kb)

        if checks and any(checks):
            selected_filepaths.append(filepath)

    return {
        'selected_filepaths': selected_filepaths,
        'missing_files': missing_files,
        'scanned': scanned,
    }


def preview_bulk_upscale_small_images(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not config.UPSCALER_ENABLED:
        return {
            'status': 'error',
            'error': 'Upscaler is disabled in configuration',
        }

    normalized_settings = _normalize_settings(settings)
    if not any([
        normalized_settings['use_filesize_kb'],
        normalized_settings['use_megapixels'],
        normalized_settings['use_dimensions'],
    ]):
        return {
            'status': 'error',
            'error': 'At least one threshold filter must be enabled',
        }

    selection = _collect_matching_filepaths(normalized_settings)
    queued_count = len(selection['selected_filepaths'])

    return {
        'status': 'success',
        'queued': queued_count,
        'scanned': selection['scanned'],
        'missing_files': selection['missing_files'],
        'settings': normalized_settings,
        'message': f'{queued_count} images will be queued',
    }


async def bulk_upscale_small_images_task(task_id, task_manager_instance, settings: Optional[Dict[str, Any]] = None, *args, **kwargs):
    normalized_settings = _normalize_settings(settings)
    use_filesize = normalized_settings['use_filesize_kb']

    if not any([
        normalized_settings['use_filesize_kb'],
        normalized_settings['use_megapixels'],
        normalized_settings['use_dimensions'],
    ]):
        raise ValueError('At least one threshold filter must be enabled')

    if not config.UPSCALER_ENABLED:
        raise ValueError('Upscaler is disabled in configuration')

    monitor_service.add_log('Bulk upscale maintenance started', 'info')

    await task_manager_instance.update_progress(task_id, 0, 1, 'Scanning images...')
    selection = _collect_matching_filepaths(normalized_settings)
    selected_filepaths = selection['selected_filepaths']
    missing_files = selection['missing_files']

    total = len(selected_filepaths)

    if total == 0:
        message = 'No images matched the bulk upscale maintenance thresholds.'
        if missing_files > 0:
            message += f' ({missing_files} files missing on disk were skipped)'
        monitor_service.add_log(message, 'info')
        await task_manager_instance.update_progress(task_id, 1, 1, message)
        return {
            'status': 'success',
            'message': message,
            'queued': 0,
            'completed': 0,
            'failed': 0,
            'already_upscaled': 0,
            'missing_files': missing_files,
        }

    monitor_service.add_log(f'Found {total} images to upscale', 'info')

    completed = 0
    failed = 0
    already_upscaled = 0
    error_samples: List[str] = []

    for index, filepath in enumerate(selected_filepaths, 1):
        await task_manager_instance.update_progress(
            task_id,
            index - 1,
            total,
            f'Upscaling {index}/{total}',
            current_item=filepath,
        )

        result = await upscaler_service.upscale_image(filepath, force=False)

        if result.get('success'):
            if result.get('error') == 'Already upscaled':
                already_upscaled += 1
            else:
                completed += 1
        else:
            failed += 1
            if len(error_samples) < 5:
                error_samples.append(f"{filepath}: {result.get('error', 'Unknown error')}")

    await task_manager_instance.update_progress(task_id, total, total, 'Bulk upscale maintenance complete')

    message = (
        f'Bulk upscale maintenance complete: {completed} completed, '
        f'{already_upscaled} already upscaled, {failed} failed '
        f'(matched {total} images).'
    )
    if missing_files > 0:
        message += f' Skipped {missing_files} missing files.'

    if failed > 0:
        monitor_service.add_log(f'{message} Sample errors: {"; ".join(error_samples)}', 'warning')
    else:
        monitor_service.add_log(message, 'success')

    return {
        'status': 'success',
        'message': message,
        'queued': total,
        'completed': completed,
        'already_upscaled': already_upscaled,
        'failed': failed,
        'missing_files': missing_files,
        'errors': error_samples,
    }

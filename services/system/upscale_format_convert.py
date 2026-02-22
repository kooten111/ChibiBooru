"""
Convert existing upscaled images to the configured output format.
"""
import os
import logging
from typing import Any, Dict, List, Optional

import config
from services import monitor_service

logger = logging.getLogger(__name__)

# Image extensions we recognise as upscaler output
_IMAGE_EXTENSIONS = {'.png', '.webp', '.jpg', '.jpeg'}


def _scan_convertible_files() -> List[Dict[str, Any]]:
    """
    Walk the upscaled images directory and return files whose extension
    differs from the currently configured output format.
    """
    target_ext = f".{config.UPSCALER_OUTPUT_FORMAT}"
    upscaled_dir = config.UPSCALED_IMAGES_DIR
    convertible: List[Dict[str, Any]] = []

    if not os.path.isdir(upscaled_dir):
        return convertible

    for dirpath, _dirnames, filenames in os.walk(upscaled_dir):
        for filename in filenames:
            stem, ext = os.path.splitext(filename)
            if ext.lower() not in _IMAGE_EXTENSIONS:
                continue
            if ext.lower() == target_ext:
                continue

            full_path = os.path.join(dirpath, filename)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0

            convertible.append({
                'path': full_path,
                'old_ext': ext.lower(),
                'size': size,
            })

    return convertible


def preview_upscale_format_conversion() -> Dict[str, Any]:
    """Preview how many upscaled files would be converted."""
    target_format = config.UPSCALER_OUTPUT_FORMAT
    files = _scan_convertible_files()
    total_size = sum(f['size'] for f in files)

    return {
        'status': 'success',
        'count': len(files),
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'target_format': target_format,
        'quality': config.UPSCALER_OUTPUT_QUALITY if target_format == 'webp' else None,
        'message': f'{len(files)} files to convert to {target_format}',
    }


async def convert_upscaled_format_task(
    task_id,
    task_manager_instance,
    *args,
    **kwargs,
):
    """
    Background task: convert all upscaled images to the configured format.
    """
    from PIL import Image

    target_format = config.UPSCALER_OUTPUT_FORMAT
    target_quality = config.UPSCALER_OUTPUT_QUALITY

    monitor_service.add_log(
        f'Upscale format conversion started (target: {target_format})',
        'info',
    )

    await task_manager_instance.update_progress(task_id, 0, 1, 'Scanning files...')
    files = _scan_convertible_files()
    total = len(files)

    if total == 0:
        message = 'No upscaled files need conversion.'
        monitor_service.add_log(message, 'info')
        await task_manager_instance.update_progress(task_id, 1, 1, message)
        return {
            'status': 'success',
            'message': message,
            'converted': 0,
            'failed': 0,
            'space_saved_mb': 0,
        }

    monitor_service.add_log(f'Found {total} upscaled files to convert to {target_format}', 'info')

    converted = 0
    failed = 0
    bytes_before = 0
    bytes_after = 0
    error_samples: List[str] = []

    for index, entry in enumerate(files, 1):
        src_path = entry['path']
        stem = os.path.splitext(src_path)[0]
        dst_path = f"{stem}.{target_format}"

        await task_manager_instance.update_progress(
            task_id,
            index - 1,
            total,
            f'Converting {index}/{total}',
            current_item=os.path.basename(src_path),
        )

        try:
            with Image.open(src_path) as img:
                if img.mode == 'RGBA' and target_format == 'webp':
                    # WebP supports RGBA natively
                    pass
                elif img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGB')

                if target_format == 'webp':
                    img.save(dst_path, format='WEBP', quality=target_quality, method=4)
                else:
                    img.save(dst_path, format='PNG')

            new_size = os.path.getsize(dst_path)
            bytes_before += entry['size']
            bytes_after += new_size

            # Remove old file (only if dst differs from src)
            if os.path.abspath(dst_path) != os.path.abspath(src_path):
                os.remove(src_path)

            converted += 1
        except Exception as e:
            failed += 1
            if len(error_samples) < 5:
                error_samples.append(f"{os.path.basename(src_path)}: {e}")
            logger.warning(f"Failed to convert {src_path}: {e}")

    space_saved_mb = round((bytes_before - bytes_after) / (1024 * 1024), 2)

    await task_manager_instance.update_progress(task_id, total, total, 'Conversion complete')

    message = (
        f'Format conversion complete: {converted} converted, {failed} failed. '
        f'Space saved: {space_saved_mb} MB'
    )
    if failed > 0:
        monitor_service.add_log(f'{message} Errors: {"; ".join(error_samples)}', 'warning')
    else:
        monitor_service.add_log(message, 'success')

    return {
        'status': 'success',
        'message': message,
        'converted': converted,
        'failed': failed,
        'space_saved_mb': space_saved_mb,
        'errors': error_samples,
    }

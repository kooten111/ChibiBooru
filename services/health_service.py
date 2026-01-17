"""
Database health check and auto-repair system.
Ensures database integrity and fixes common issues automatically.
"""
import logging
import config
from database import get_db_connection

logger = logging.getLogger('chibibooru.HealthService')


class HealthCheckResult:
    """Result of a health check operation."""
    def __init__(self, check_name):
        self.check_name = check_name
        self.passed = True
        self.issues_found = 0
        self.issues_fixed = 0
        self.errors = []
        self.messages = []

    def add_message(self, msg):
        self.messages.append(msg)

    def add_error(self, error):
        self.errors.append(error)
        self.passed = False

    def to_dict(self):
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "issues_found": self.issues_found,
            "issues_fixed": self.issues_fixed,
            "errors": self.errors,
            "messages": self.messages
        }


def check_and_fix_null_active_source(auto_fix=True):
    """
    Check for images with NULL active_source that have sources available.
    If auto_fix=True, automatically sets active_source based on BOORU_PRIORITY.
    """
    result = HealthCheckResult("NULL active_source")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Find images with NULL active_source that have sources
            cursor.execute("""
                SELECT i.id, i.filepath, GROUP_CONCAT(s.name) as sources
                FROM images i
                JOIN image_sources isr ON i.id = isr.image_id
                JOIN sources s ON isr.source_id = s.id
                WHERE i.active_source IS NULL
                GROUP BY i.id
            """)

            null_images = cursor.fetchall()
            result.issues_found = len(null_images)

            if result.issues_found == 0:
                result.add_message("All images have valid active_source")
                return result

            result.add_message(f"Found {result.issues_found} images with NULL active_source")

            if not auto_fix:
                return result

            # Fix each image
            for image in null_images:
                image_id = image['id']
                sources = image['sources'].split(',')

                # Determine active_source based on BOORU_PRIORITY
                active_source = None
                for priority_source in config.BOORU_PRIORITY:
                    if priority_source in sources:
                        active_source = priority_source
                        break

                # If no priority match, use first available source
                if not active_source and sources:
                    active_source = sources[0]

                if active_source:
                    cursor.execute("""
                        UPDATE images
                        SET active_source = ?
                        WHERE id = ?
                    """, (active_source, image_id))
                    result.issues_fixed += 1

            conn.commit()
            result.add_message(f"Fixed {result.issues_fixed} images")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def check_orphaned_image_sources(auto_fix=True):
    """
    Check for orphaned records in image_sources table.
    If auto_fix=True, removes orphaned entries.
    """
    result = HealthCheckResult("Orphaned image_sources")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Find orphaned image_sources (images that don't exist)
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM image_sources isr
                LEFT JOIN images i ON isr.image_id = i.id
                WHERE i.id IS NULL
            """)

            orphaned_count = cursor.fetchone()['count']
            result.issues_found = orphaned_count

            if result.issues_found == 0:
                result.add_message("No orphaned image_sources found")
                return result

            result.add_message(f"Found {result.issues_found} orphaned image_sources entries")

            if auto_fix:
                cursor.execute("""
                    DELETE FROM image_sources
                    WHERE image_id NOT IN (SELECT id FROM images)
                """)
                conn.commit()
                result.issues_fixed = cursor.rowcount
                result.add_message(f"Removed {result.issues_fixed} orphaned entries")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def check_missing_thumbnails(auto_fix=False):
    """
    Check for images that don't have thumbnails generated.
    If auto_fix=True, generates missing thumbnails (can be slow).
    """
    import os
    from utils.file_utils import get_hash_bucket

    result = HealthCheckResult("Missing thumbnails")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Include md5 for zip animation thumbnail generation
            cursor.execute("SELECT filepath, md5 FROM images")
            all_images = cursor.fetchall()

        missing = []
        for image in all_images:
            filepath = image['filepath']
            filename = os.path.basename(filepath)
            base_name = os.path.splitext(filename)[0]
            bucket = get_hash_bucket(filename)
            thumb_path = os.path.join(config.THUMB_DIR, bucket, base_name + '.webp')

            if not os.path.exists(thumb_path):
                # Store both filepath and md5 for zip animations
                missing.append({'filepath': filepath, 'md5': image['md5']})

        result.issues_found = len(missing)

        if result.issues_found == 0:
            result.add_message("All images have thumbnails")
            return result

        result.add_message(f"Found {result.issues_found} images without thumbnails")

        if auto_fix:
            from services.processing.thumbnail_generator import ensure_thumbnail
            for item in missing:
                filepath = item['filepath']
                md5 = item['md5']
                full_path = os.path.join("static/images", filepath)
                if os.path.exists(full_path):
                    # Pass md5 for zip animation thumbnails
                    ensure_thumbnail(full_path, md5=md5)
                    result.issues_fixed += 1

            result.add_message(f"Generated {result.issues_fixed} thumbnails")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def check_active_source_priority(auto_fix=True):
    """
    Check if active_source matches current BOORU_PRIORITY for images with multiple sources.
    If auto_fix=True, updates active_source to match current priority.
    """
    result = HealthCheckResult("Active source priority")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all images with their sources
            cursor.execute("""
                SELECT i.id, i.filepath, i.active_source, GROUP_CONCAT(s.name) as sources
                FROM images i
                JOIN image_sources isr ON i.id = isr.image_id
                JOIN sources s ON isr.source_id = s.id
                GROUP BY i.id
                HAVING COUNT(*) > 1
            """)

            multi_source_images = cursor.fetchall()
            mismatched = []

            for image in multi_source_images:
                sources = image['sources'].split(',')
                current_active = image['active_source']

                # Determine what active_source SHOULD be based on priority
                correct_active = None
                for priority_source in config.BOORU_PRIORITY:
                    if priority_source in sources:
                        correct_active = priority_source
                        break

                if not correct_active:
                    correct_active = sources[0]

                if current_active != correct_active:
                    mismatched.append({
                        'id': image['id'],
                        'filepath': image['filepath'],
                        'current': current_active,
                        'correct': correct_active
                    })

            result.issues_found = len(mismatched)

            if result.issues_found == 0:
                result.add_message("All active_source values match current BOORU_PRIORITY")
                return result

            result.add_message(f"Found {result.issues_found} images with outdated active_source")

            if auto_fix:
                for img in mismatched:
                    cursor.execute("""
                        UPDATE images
                        SET active_source = ?
                        WHERE id = ?
                    """, (img['correct'], img['id']))
                    result.issues_fixed += 1

                conn.commit()
                result.add_message(f"Updated {result.issues_fixed} images to match current priority")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def cleanup_tag_deltas(auto_fix=True):
    """
    Clean up tag deltas by removing operations that cancel each other out.
    For example, if a tag was added then removed, both operations are removed.
    If auto_fix=True, performs the cleanup.
    """
    result = HealthCheckResult("Tag delta cleanup")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get all unique image/tag combinations that have deltas
            cursor.execute("""
                SELECT DISTINCT image_md5, tag_name
                FROM tag_deltas
            """)

            combinations = cursor.fetchall()
            result.issues_found = 0
            cancelled_count = 0

            for combo in combinations:
                image_md5 = combo['image_md5']
                tag_name = combo['tag_name']

                # Get all operations for this image/tag in chronological order
                cursor.execute("""
                    SELECT operation, tag_category
                    FROM tag_deltas
                    WHERE image_md5 = ? AND tag_name = ?
                    ORDER BY timestamp
                """, (image_md5, tag_name))

                operations = cursor.fetchall()

                if len(operations) <= 1:
                    continue

                # Calculate net state
                net_state = None  # None, 'add', or 'remove'
                last_category = None

                for op in operations:
                    if op['operation'] == 'add':
                        if net_state == 'remove':
                            net_state = None  # Cancel out
                        else:
                            net_state = 'add'
                        last_category = op['tag_category']
                    elif op['operation'] == 'remove':
                        if net_state == 'add':
                            net_state = None  # Cancel out
                        else:
                            net_state = 'remove'
                        last_category = op['tag_category']

                # If operations cancel out, this is a cleanable entry
                if net_state is None or len(operations) > 1:
                    result.issues_found += 1

                    if auto_fix:
                        # Delete all entries for this combination
                        cursor.execute("""
                            DELETE FROM tag_deltas
                            WHERE image_md5 = ? AND tag_name = ?
                        """, (image_md5, tag_name))

                        # If there's a net change, insert it
                        if net_state:
                            cursor.execute("""
                                INSERT INTO tag_deltas
                                (image_md5, tag_name, tag_category, operation, timestamp)
                                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                            """, (image_md5, tag_name, last_category, net_state))
                        else:
                            cancelled_count += 1

                        result.issues_fixed += 1

            if auto_fix:
                conn.commit()

            if result.issues_found == 0:
                result.add_message("No redundant tag deltas found")
            else:
                result.add_message(f"Found {result.issues_found} tag delta entries to clean")
                if auto_fix:
                    result.add_message(f"Cleaned {result.issues_fixed} entries ({cancelled_count} fully cancelled)")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def check_merged_images_missing_tags(auto_fix=True):
    """
    Check for images with active_source='merged' that have no tags in image_tags table.
    This can happen if merge_all_sources was called with an old version that didn't
    properly populate the image_tags table.
    If auto_fix=True, re-runs merge_all_sources on affected images.
    """
    result = HealthCheckResult("Merged images missing tags")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Find images with merged source but no tags
            cursor.execute("""
                SELECT i.id, i.filepath
                FROM images i
                WHERE i.active_source = 'merged'
                AND i.id NOT IN (SELECT DISTINCT image_id FROM image_tags)
            """)

            affected_images = cursor.fetchall()
            result.issues_found = len(affected_images)

            if result.issues_found == 0:
                result.add_message("All merged images have tags")
                return result

            result.add_message(f"Found {result.issues_found} merged images without tags")

            if not auto_fix:
                return result

            # Fix each image by re-running merge_all_sources
            from services.switch_source_db import merge_all_sources

            for image in affected_images:
                filepath = image['filepath']
                merge_result = merge_all_sources(filepath)

                if merge_result.get("status") == "success":
                    result.issues_fixed += 1
                else:
                    error_msg = merge_result.get("error", "Unknown error")
                    result.add_error(f"Failed to fix {filepath}: {error_msg}")

            result.add_message(f"Re-merged {result.issues_fixed} images")

    except Exception as e:
        result.add_error(f"Error during check: {str(e)}")

    return result


def run_all_health_checks(auto_fix=True, include_thumbnails=False, include_tag_deltas=True):
    """
    Run all database health checks.

    Args:
        auto_fix: If True, automatically fix issues found
        include_thumbnails: If True, check for missing thumbnails (can be slow)
        include_tag_deltas: If True, cleanup redundant tag deltas (default: True)

    Returns:
        dict: Summary of all health check results
    """
    logger.debug("Running health checks...")

    checks = [
        check_and_fix_null_active_source(auto_fix),
        check_active_source_priority(auto_fix),
        check_orphaned_image_sources(auto_fix),
        check_merged_images_missing_tags(auto_fix),
    ]

    if include_tag_deltas:
        checks.append(cleanup_tag_deltas(auto_fix))

    if include_thumbnails:
        checks.append(check_missing_thumbnails(auto_fix))

    results = {
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c.passed),
        "failed": sum(1 for c in checks if not c.passed),
        "total_issues_found": sum(c.issues_found for c in checks),
        "total_issues_fixed": sum(c.issues_fixed for c in checks),
        "checks": [c.to_dict() for c in checks]
    }

    # Print summary
    logger.debug(f"Completed {results['total_checks']} checks")
    logger.debug(f"Found {results['total_issues_found']} issues, fixed {results['total_issues_fixed']}")

    for check in checks:
        if check.issues_found > 0:
            logger.debug(f"- {check.check_name}: {check.issues_found} issues, {check.issues_fixed} fixed")

    return results


def startup_health_check():
    """
    Run critical health checks on application startup.
    Only runs checks that are fast and safe to auto-fix.
    """
    logger.debug("Running startup health checks...")

    # Only run critical, fast checks on startup
    checks = [
        check_and_fix_null_active_source(auto_fix=True),
        check_orphaned_image_sources(auto_fix=True),
        check_merged_images_missing_tags(auto_fix=True),
    ]

    total_issues = sum(c.issues_found for c in checks)
    total_fixed = sum(c.issues_fixed for c in checks)

    if total_issues > 0:
        logger.info(f"Startup: Found {total_issues} issues, fixed {total_fixed}")
    else:
        logger.info("Startup: Database is healthy")

    return {
        "issues_found": total_issues,
        "issues_fixed": total_fixed,
        "checks": [c.to_dict() for c in checks]
    }

import os
import shutil
from typing import Any, Dict, List

import config
import numpy as np

from database import models
from services import monitor_service, similarity_service


def run_find_broken_images() -> Dict[str, Any]:
    """
    Service to find images with missing tags, hashes, or embeddings.

    Returns:
        Dict containing:
        - total_broken: Total number of broken images found
        - images: List of broken images (limited to first 100) with their issues
        - has_more: Whether there are more than 100 broken images
    """
    try:
        from database import get_db_connection

        broken_images = []

        with get_db_connection() as conn:
            cursor = conn.cursor()

            video_excl = " AND ".join(
                "LOWER(filepath) NOT LIKE '%{ext}'".format(ext=ext)
                for ext in config.SUPPORTED_VIDEO_EXTENSIONS
            )
            cursor.execute(
                """
                SELECT id, filepath, phash, colorhash, md5
                FROM images
                WHERE (phash IS NULL OR phash = '') AND {video_excl}
            """.format(
                    video_excl=video_excl
                )
            )
            missing_phash = cursor.fetchall()

            for row in missing_phash:
                broken_images.append(
                    {
                        "id": row["id"],
                        "filepath": row["filepath"],
                        "md5": row["md5"],
                        "issues": ["missing_phash"],
                    }
                )

            cursor.execute(
                """
                SELECT i.id, i.filepath, i.md5, COUNT(it.tag_id) as tag_count
                FROM images i
                LEFT JOIN image_tags it ON i.id = it.image_id
                GROUP BY i.id
                HAVING tag_count = 0
            """
            )
            no_tags = cursor.fetchall()

            for row in no_tags:
                existing = next((b for b in broken_images if b["id"] == row["id"]), None)
                if existing:
                    existing["issues"].append("no_tags")
                else:
                    broken_images.append(
                        {
                            "id": row["id"],
                            "filepath": row["filepath"],
                            "md5": row["md5"],
                            "issues": ["no_tags"],
                        }
                    )

            if similarity_service.SEMANTIC_AVAILABLE:
                from services import similarity_db

                embedding_ids = set(similarity_db.get_all_embedding_ids())

                cursor.execute("SELECT id, filepath, md5 FROM images")
                all_images = cursor.fetchall()

                for row in all_images:
                    if row["id"] not in embedding_ids:
                        existing = next(
                            (b for b in broken_images if b["id"] == row["id"]), None
                        )
                        if existing:
                            existing["issues"].append("missing_embedding")
                        else:
                            broken_images.append(
                                {
                                    "id": row["id"],
                                    "filepath": row["filepath"],
                                    "md5": row["md5"],
                                    "issues": ["missing_embedding"],
                                }
                            )

            if similarity_service.SEMANTIC_AVAILABLE:
                from services import similarity_db

                with similarity_db.get_db_connection() as emb_conn:
                    emb_cursor = emb_conn.execute(
                        "SELECT image_id, embedding FROM embeddings"
                    )
                    for emb_row in emb_cursor:
                        vec = np.frombuffer(emb_row["embedding"], dtype=np.float32)
                        if len(vec) != 1024:
                            cursor.execute(
                                "SELECT id, filepath, md5 FROM images WHERE id = ?",
                                (emb_row["image_id"],),
                            )
                            img_row = cursor.fetchone()
                            if img_row:
                                existing = next(
                                    (b for b in broken_images if b["id"] == img_row["id"]),
                                    None,
                                )
                                if existing:
                                    existing["issues"].append("invalid_embedding_dim")
                                else:
                                    broken_images.append(
                                        {
                                            "id": img_row["id"],
                                            "filepath": img_row["filepath"],
                                            "md5": img_row["md5"],
                                            "issues": ["invalid_embedding_dim"],
                                        }
                                    )

        broken_images.sort(key=lambda x: len(x["issues"]), reverse=True)

        return {
            "status": "success",
            "total_broken": len(broken_images),
            "images": broken_images[:100],
            "has_more": len(broken_images) > 100,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise e


async def run_cleanup_broken_images(action: str, image_ids: List[int]) -> Dict[str, Any]:
    """
    Service to cleanup or retry broken images.
    Actions:
    - 'scan': Just find and return count of broken images
    - 'delete': Remove broken images from database and move files back to ingest
    - 'retry': Re-process broken images (regenerate hashes/embeddings)
    - 'delete_permanent': Remove from database and delete files permanently
    """
    try:
        from database import get_db_connection

        if not image_ids:
            from services import similarity_db

            embedding_ids = (
                set(similarity_db.get_all_embedding_ids())
                if similarity_service.SEMANTIC_AVAILABLE
                else set()
            )

            with get_db_connection() as conn:
                cursor = conn.cursor()

                video_excl = " AND ".join(
                    "LOWER(i.filepath) NOT LIKE '%{ext}'".format(ext=ext)
                    for ext in config.SUPPORTED_VIDEO_EXTENSIONS
                )
                cursor.execute(
                    """
                    SELECT DISTINCT i.id
                    FROM images i
                    LEFT JOIN image_tags it ON i.id = it.image_id
                    WHERE ( (i.phash IS NULL OR i.phash = '') AND {video_excl} )
                       OR it.tag_id IS NULL
                    GROUP BY i.id
                """.format(
                        video_excl=video_excl
                    )
                )

                broken_ids = set(row["id"] for row in cursor.fetchall())

                if similarity_service.SEMANTIC_AVAILABLE:
                    cursor.execute("SELECT id FROM images")
                    all_ids = set(row["id"] for row in cursor.fetchall())
                    missing_embeddings = all_ids - embedding_ids
                    broken_ids.update(missing_embeddings)

                    with similarity_db.get_db_connection() as emb_conn:
                        emb_cursor = emb_conn.execute(
                            "SELECT image_id, embedding FROM embeddings"
                        )
                        for emb_row in emb_cursor:
                            try:
                                vec = np.frombuffer(emb_row["embedding"], dtype=np.float32)
                                if len(vec) != 1024:
                                    broken_ids.add(emb_row["image_id"])
                            except Exception:
                                broken_ids.add(emb_row["image_id"])

                image_ids = list(broken_ids)

        if action == "scan":
            return {
                "status": "success",
                "message": f"Found {len(image_ids)} broken images",
                "count": len(image_ids),
            }

        if not image_ids:
            return {
                "status": "success",
                "message": "No broken images found",
                "processed": 0,
            }

        processed = 0
        errors = 0

        if action == "delete":
            monitor_service.add_log(
                f"Moving {len(image_ids)} broken images back to ingest...", "info"
            )

            with get_db_connection() as conn:
                cursor = conn.cursor()

                for image_id in image_ids:
                    cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
                    row = cursor.fetchone()
                    if row:
                        filepath = row["filepath"]
                        full_path = f"static/images/{filepath}"

                        if os.path.exists(full_path):
                            filename = os.path.basename(filepath)
                            ingest_path = os.path.join(config.INGEST_DIRECTORY, filename)

                            try:
                                shutil.move(full_path, ingest_path)
                                models.delete_image(filepath)
                                processed += 1
                            except Exception as e:
                                errors += 1
                                monitor_service.add_log(
                                    f"Error moving {filename}: {e}", "error"
                                )
                        else:
                            models.delete_image(filepath)
                            processed += 1

            models.load_data_from_db()
            message = f"Moved {processed} broken images back to ingest folder"

        elif action == "delete_permanent":
            monitor_service.add_log(
                f"Permanently deleting {len(image_ids)} broken images...", "info"
            )

            with get_db_connection() as conn:
                cursor = conn.cursor()

                for image_id in image_ids:
                    cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
                    row = cursor.fetchone()
                    if row:
                        filepath = row["filepath"]
                        full_path = f"static/images/{filepath}"

                        if os.path.exists(full_path):
                            try:
                                os.remove(full_path)
                            except Exception as e:
                                monitor_service.add_log(
                                    f"Error deleting {filepath}: {e}", "error"
                                )

                        thumb_path = f"static/thumbnails/{filepath.rsplit('.', 1)[0]}.webp"
                        if os.path.exists(thumb_path):
                            try:
                                os.remove(thumb_path)
                            except Exception:
                                pass

                        models.delete_image(filepath)
                        processed += 1

            models.load_data_from_db()
            message = f"Permanently deleted {processed} broken images"

        elif action == "retry":
            monitor_service.add_log(
                f"Retrying {len(image_ids)} broken images...", "info"
            )

            with get_db_connection() as conn:
                cursor = conn.cursor()

                for idx, image_id in enumerate(image_ids, 1):
                    if idx % 10 == 0:
                        monitor_service.add_log(
                            f"Progress: {idx}/{len(image_ids)}", "info"
                        )

                    cursor.execute(
                        "SELECT filepath, md5 FROM images WHERE id = ?", (image_id,)
                    )
                    row = cursor.fetchone()
                    if row:
                        filepath = row["filepath"]
                        md5 = row["md5"]
                        full_path = f"static/images/{filepath}"

                        if not os.path.exists(full_path):
                            continue

                        try:
                            cursor.execute(
                                "SELECT phash FROM images WHERE id = ?", (image_id,)
                            )
                            if not cursor.fetchone()["phash"]:
                                phash = similarity_service.compute_phash_for_file(
                                    full_path, md5
                                )
                                if phash:
                                    cursor.execute(
                                        "UPDATE images SET phash = ? WHERE id = ?",
                                        (phash, image_id),
                                    )

                            cursor.execute(
                                "SELECT colorhash FROM images WHERE id = ?", (image_id,)
                            )
                            if not cursor.fetchone()["colorhash"]:
                                colorhash = similarity_service.compute_colorhash_for_file(
                                    full_path
                                )
                                if colorhash:
                                    cursor.execute(
                                        "UPDATE images SET colorhash = ? WHERE id = ?",
                                        (colorhash, image_id),
                                    )

                            if similarity_service.SEMANTIC_AVAILABLE:
                                from services import similarity_db

                                existing_embedding = similarity_db.get_embedding(image_id)
                                if existing_embedding is None:
                                    engine = similarity_service.get_semantic_engine()
                                    if engine.load_model():
                                        embedding = engine.get_embedding(full_path)
                                        if embedding is not None:
                                            similarity_service.store_embedding(
                                                image_id, embedding
                                            )

                            conn.commit()
                            processed += 1
                        except Exception as e:
                            errors += 1
                            if errors <= 5:
                                monitor_service.add_log(
                                    f"Error retrying {filepath}: {e}", "error"
                                )

            message = f"Retried {processed} images"
            if errors > 0:
                message += f", {errors} errors"
        else:
            raise ValueError(f"Unknown action: {action}")

        monitor_service.add_log(f"✓ {message}", "success")

        return {
            "status": "success",
            "message": message,
            "processed": processed,
            "errors": errors,
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise e

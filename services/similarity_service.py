"""
Perceptual Hash Similarity Service

Provides visual similarity detection using perceptual hashing algorithms.
Similar to Czkawka's duplicate detection approach.
"""
import os
from typing import Optional, List, Dict, Tuple
from PIL import Image, UnidentifiedImageError
import imagehash
import config
from database import get_db_connection
from utils.file_utils import get_thumbnail_path


# ============================================================================
# Hash Computation
# ============================================================================

def compute_phash(image_path: str, hash_size: int = 8) -> Optional[str]:
    """
    Compute perceptual hash for an image.
    
    Args:
        image_path: Path to the image file
        hash_size: Size of the hash (8 = 64-bit hash, 16 = 256-bit)
    
    Returns:
        Hex string representation of the hash, or None on error
    """
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (handles RGBA, P mode, etc.)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                if 'A' in img.mode:
                    background.paste(img, mask=img.split()[-1])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Compute perceptual hash
            phash = imagehash.phash(img, hash_size=hash_size)
            return str(phash)
    except UnidentifiedImageError:
        print(f"[Similarity] Cannot identify image: {image_path}")
        return None
    except Exception as e:
        print(f"[Similarity] Error computing hash for {image_path}: {e}")
        return None


def compute_phash_for_video(video_path: str) -> Optional[str]:
    """
    Compute perceptual hash from the first frame of a video.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Hex string representation of the hash, or None on error
    """
    import subprocess
    import tempfile
    
    # Check for ffmpeg
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        if result.returncode != 0:
            print("[Similarity] ffmpeg not found, cannot hash video")
            return None
    except Exception:
        return None
    
    # Extract first frame to temp file
    try:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        
        cmd = [
            'ffmpeg', '-y', '-i', video_path,
            '-vframes', '1', '-f', 'image2',
            tmp_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            result = compute_phash(tmp_path)
            os.unlink(tmp_path)
            return result
        
        return None
    except Exception as e:
        print(f"[Similarity] Error extracting video frame: {e}")
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return None


def compute_phash_for_zip_animation(md5: str) -> Optional[str]:
    """
    Compute perceptual hash from the first frame of a zip animation.
    
    Args:
        md5: MD5 hash of the zip file
        
    Returns:
        Hex string representation of the hash, or None on error
    """
    try:
        from services.zip_animation_service import get_frame_path
        first_frame = get_frame_path(md5, 0)
        if first_frame and os.path.exists(first_frame):
            return compute_phash(first_frame)
        return None
    except Exception as e:
        print(f"[Similarity] Error hashing zip animation: {e}")
        return None


def compute_phash_for_file(filepath: str, md5: str = None) -> Optional[str]:
    """
    Compute perceptual hash for any supported file type.
    
    Args:
        filepath: Path to the file
        md5: MD5 hash (required for zip animations)
        
    Returns:
        Hex string representation of the hash, or None on error
    """
    if filepath.lower().endswith(config.SUPPORTED_VIDEO_EXTENSIONS):
        return compute_phash_for_video(filepath)
    elif filepath.lower().endswith(config.SUPPORTED_ZIP_EXTENSIONS):
        if md5:
            return compute_phash_for_zip_animation(md5)
        return None
    else:
        return compute_phash(filepath)


# ============================================================================
# Hash Comparison
# ============================================================================

def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two hex hash strings.
    
    Lower distance = more similar:
    - 0-5: Near identical (same image, different compression)
    - 6-10: Very similar (minor edits, cropping)
    - 11-15: Somewhat similar
    - 16+: Different images
    
    Args:
        hash1: First hash as hex string
        hash2: Second hash as hex string
        
    Returns:
        Hamming distance (number of differing bits)
    """
    try:
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        # Cast to int because imagehash returns numpy type which isn't JSON serializable
        return int(h1 - h2)
    except Exception:
        return 64  # Maximum distance for 64-bit hash


def hash_similarity_score(hash1: str, hash2: str, max_distance: int = 64) -> float:
    """
    Convert Hamming distance to a similarity score (0.0 to 1.0).
    
    Args:
        hash1: First hash as hex string
        hash2: Second hash as hex string
        max_distance: Maximum possible distance (64 for 64-bit hash)
        
    Returns:
        Similarity score (1.0 = identical, 0.0 = completely different)
    """
    distance = hamming_distance(hash1, hash2)
    return float(max(0.0, 1.0 - (distance / max_distance)))


# ============================================================================
# Database Operations
# ============================================================================

def get_image_phash(filepath: str) -> Optional[str]:
    """Get the stored phash for an image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT phash FROM images WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        return row['phash'] if row else None


def update_image_phash(filepath: str, phash: str) -> bool:
    """Update the phash for an image in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE images SET phash = ? WHERE filepath = ?",
                (phash, filepath)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        print(f"[Similarity] Error updating phash: {e}")
        return False


def find_similar_images(
    filepath: str,
    threshold: int = 10,
    limit: int = 50,
    exclude_family: bool = False
) -> List[Dict]:
    """
    Find images visually similar to the given image.
    
    Args:
        filepath: Path to the reference image (relative, without 'images/' prefix)
        threshold: Maximum Hamming distance (lower = stricter, 0-64)
        limit: Maximum number of results
        exclude_family: If True, exclude images in the same parent/child chain
        
    Returns:
        List of similar images with distance and similarity score
    """
    try:
        # Get reference hash and family info
        ref_hash = get_image_phash(filepath)
        family_filepaths = set()
        
        if exclude_family:
            try:
                family_filepaths = _get_family_filepaths(filepath)
            except Exception as e:
                print(f"[Similarity] Error getting family for {filepath}: {e}")
                # Continue without exclude_family if it fails
        
        # If no hash stored, try to compute it
        if not ref_hash:
            full_path = os.path.join("static/images", filepath)
            if os.path.exists(full_path):
                ref_hash = compute_phash(full_path)
                if ref_hash:
                    update_image_phash(filepath, ref_hash)
        
        if not ref_hash:
            return []
        
        # Get all images with hashes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filepath, phash
                FROM images
                WHERE phash IS NOT NULL AND filepath != ?
            """, (filepath,))
            candidates = cursor.fetchall()
        
        # Calculate distances
        similar = []
        for row in candidates:
            try:
                # Skip family members if requested
                if exclude_family and row['filepath'] in family_filepaths:
                    continue
                    
                distance = hamming_distance(ref_hash, row['phash'])
                if distance <= threshold:
                    similar.append({
                        'path': f"images/{row['filepath']}",
                        'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
                        'distance': distance,
                        'similarity': hash_similarity_score(ref_hash, row['phash']),
                        'match_type': 'visual'
                    })
            except Exception as e:
                # Log error but continue processing other images
                from services import monitor_service
                monitor_service.add_log(f"Error processing candidate {row['filepath']}: {e}", "warning")
                continue
        
        # Sort by distance (closest first)
        similar.sort(key=lambda x: x['distance'])
        return similar[:limit]

    except Exception as e:
        import traceback
        traceback.print_exc()
        from services import monitor_service
        monitor_service.add_log(f"Critical error in visual search: {e}", "error")
        return []


def find_all_duplicate_groups(threshold: int = 5) -> List[List[Dict]]:
    """
    Find all groups of visually similar/duplicate images.
    
    Args:
        threshold: Maximum Hamming distance to consider duplicates
        
    Returns:
        List of groups, where each group is a list of similar images
    """
    # Get all images with hashes
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, filepath, phash, md5
            FROM images
            WHERE phash IS NOT NULL
            ORDER BY id
        """)
        all_images = cursor.fetchall()
    
    if not all_images:
        return []
    
    # Build groups using union-find approach
    visited = set()
    groups = []
    
    for i, img1 in enumerate(all_images):
        if img1['id'] in visited:
            continue
        
        group = [{
            'id': img1['id'],
            'path': f"images/{img1['filepath']}",
            'thumb': get_thumbnail_path(f"images/{img1['filepath']}"),
            'md5': img1['md5'],
            'distance': 0
        }]
        visited.add(img1['id'])
        
        for img2 in all_images[i+1:]:
            if img2['id'] in visited:
                continue
            
            distance = hamming_distance(img1['phash'], img2['phash'])
            if distance <= threshold:
                group.append({
                    'id': img2['id'],
                    'path': f"images/{img2['filepath']}",
                    'thumb': get_thumbnail_path(f"images/{img2['filepath']}"),
                    'md5': img2['md5'],
                    'distance': distance
                })
                visited.add(img2['id'])
        
        if len(group) > 1:
            groups.append(group)
    
    return groups


# ============================================================================
# Batch Operations
# ============================================================================

def generate_missing_hashes(batch_size: int = 100, progress_callback=None) -> Dict:
    """
    Generate perceptual hashes for images that don't have one.
    
    Args:
        batch_size: Number of images to process at a time
        progress_callback: Optional callback(current, total) for progress updates
        
    Returns:
        Dictionary with counts of processed, successful, failed
    """
    stats = {'processed': 0, 'success': 0, 'failed': 0, 'total': 0}
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT filepath, md5
            FROM images
            WHERE phash IS NULL
        """)
        missing = cursor.fetchall()
    
    stats['total'] = len(missing)
    
    for i, row in enumerate(missing):
        filepath = row['filepath']
        md5 = row['md5']
        full_path = os.path.join("static/images", filepath)
        
        phash = compute_phash_for_file(full_path, md5)
        
        if phash:
            update_image_phash(filepath, phash)
            stats['success'] += 1
        else:
            stats['failed'] += 1
        
        stats['processed'] += 1
        
        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(stats['processed'], stats['total'])
    
    return stats


def get_hash_coverage_stats() -> Dict:
    """Get statistics about hash coverage in the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM images")
        total = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as hashed FROM images WHERE phash IS NOT NULL")
        hashed = cursor.fetchone()['hashed']
        
        cursor.execute("SELECT COUNT(*) as missing FROM images WHERE phash IS NULL")
        missing = cursor.fetchone()['missing']
    
    return {
        'total': total,
        'hashed': hashed,
        'missing': missing,
        'coverage_percent': round(hashed / total * 100, 1) if total > 0 else 0
    }


# ============================================================================
# Blended Similarity (Visual + Tags)
# ============================================================================

def _get_family_filepaths(filepath: str) -> set:
    """
    Get filepaths of all images in the same parent/child family chain.
    
    Args:
        filepath: Path to the reference image (relative, without 'images/' prefix)
        
    Returns:
        Set of filepaths in the same family
    """
    family = set()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get the reference image's post_id and parent_id
        cursor.execute("""
            SELECT post_id, parent_id
            FROM images
            WHERE filepath = ?
        """, (filepath,))
        ref_row = cursor.fetchone()
        
        if not ref_row:
            return family
        
        post_id = ref_row['post_id']
        parent_id = ref_row['parent_id']
        
        # Get children (images where parent_id matches our post_id)
        if post_id:
            cursor.execute("""
                SELECT filepath FROM images WHERE parent_id = ?
            """, (post_id,))
            for row in cursor.fetchall():
                family.add(row['filepath'])
        
        # Get parent (image whose post_id matches our parent_id)
        if parent_id:
            cursor.execute("""
                SELECT filepath FROM images WHERE post_id = ?
            """, (parent_id,))
            for row in cursor.fetchall():
                family.add(row['filepath'])
            
            # Also get siblings (other children of same parent)
            cursor.execute("""
                SELECT filepath FROM images WHERE parent_id = ? AND filepath != ?
            """, (parent_id, filepath))
            for row in cursor.fetchall():
                family.add(row['filepath'])
    
    return family


def find_blended_similar(
    filepath: str,
    visual_weight: float = 0.5,
    tag_weight: float = 0.5,
    threshold: int = 15,
    limit: int = 20,
    exclude_family: bool = False
) -> List[Dict]:
    """
    Find similar images using both visual hash and tag similarity.
    
    Args:
        filepath: Path to reference image (relative, without 'images/' prefix)
        visual_weight: Weight for visual similarity (0.0 to 1.0)
        tag_weight: Weight for tag similarity (0.0 to 1.0)
        threshold: Maximum Hamming distance for visual candidates
        limit: Maximum results to return
        exclude_family: If True, exclude images in the same parent/child chain
        
    Returns:
        List of similar images with blended scores
    """
    from services import query_service
    
    # Get family filepaths to exclude if requested
    family_paths = set()
    if exclude_family:
        family_filepaths = _get_family_filepaths(filepath)
        family_paths = {f"images/{fp}" for fp in family_filepaths}
    
    # Normalize weights
    total_weight = visual_weight + tag_weight
    if total_weight > 0:
        visual_weight = visual_weight / total_weight
        tag_weight = tag_weight / total_weight
    else:
        visual_weight = tag_weight = 0.5
    
    # Get visual similar images (use higher threshold to get more candidates)
    visual_results = find_similar_images(filepath, threshold=threshold, limit=limit * 2, exclude_family=exclude_family)
    visual_scores = {r['path']: r['similarity'] for r in visual_results}
    
    # Get tag-based similar images
    tag_results = query_service.find_related_by_tags(f"images/{filepath}", limit=limit * 2)
    tag_scores = {r['path']: r.get('score', 0) for r in tag_results}
    
    # Combine all candidates, filtering out family if requested
    all_paths = set(visual_scores.keys()) | set(tag_scores.keys())
    if exclude_family:
        all_paths = all_paths - family_paths
    
    blended = []
    for path in all_paths:
        v_score = visual_scores.get(path, 0)
        t_score = tag_scores.get(path, 0)
        combined_score = (v_score * visual_weight) + (t_score * tag_weight)
        
        blended.append({
            'path': path,
            'thumb': get_thumbnail_path(path),
            'score': combined_score,
            'visual_score': v_score,
            'tag_score': t_score,
            'match_type': 'blended'
        })
    
    # Sort by combined score
    blended.sort(key=lambda x: x['score'], reverse=True)
    return blended[:limit]

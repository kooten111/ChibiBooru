"""
Similarity Cache Service

Pre-computes and caches top-N similar images for fast sidebar lookups.
Reduces memory usage by eliminating need to keep FAISS index loaded 24/7.
"""

import time
from typing import List, Dict, Optional, Tuple
from database import get_db_connection
import config


def get_similar_from_cache(
    image_id: int,
    limit: int = 12,
    similarity_type: str = 'blended'
) -> List[Dict]:
    """
    Fast SQLite lookup for cached similarity results.
    
    Args:
        image_id: Source image ID
        limit: Number of results to return (default 12 for sidebar)
        similarity_type: Type of similarity ('visual', 'semantic', 'tag', 'blended')
    
    Returns:
        List of similar images with scores, or empty list if cache miss
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Fetch from cache, ordered by rank (pre-computed during cache build)
            cursor.execute("""
                SELECT 
                    i.filepath,
                    c.similarity_score,
                    c.rank
                FROM similar_images_cache c
                JOIN images i ON c.similar_image_id = i.id
                WHERE c.source_image_id = ?
                  AND c.similarity_type = ?
                ORDER BY c.rank
                LIMIT ?
            """, (image_id, similarity_type, limit))
            
            results = []
            for row in cursor.fetchall():
                from utils.file_utils import get_thumbnail_path
                path = f"images/{row['filepath']}"
                results.append({
                    'path': path,
                    'thumb': get_thumbnail_path(path),
                    'score': row['similarity_score'],
                    'similarity': row['similarity_score'],
                    'match_type': similarity_type
                })
            
            return results
            
    except Exception as e:
        print(f"[SimilarityCache] Error fetching from cache: {e}")
        return []


def store_in_cache(
    source_id: int,
    results: List[Tuple[int, float]],
    similarity_type: str = 'blended'
) -> bool:
    """
    Store computed similarities in cache.
    
    Args:
        source_id: Source image ID
        results: List of (similar_image_id, score) tuples, ordered by relevance
        similarity_type: Type of similarity being cached
    
    Returns:
        True if successful
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Delete existing entries for this source + type
            cursor.execute("""
                DELETE FROM similar_images_cache
                WHERE source_image_id = ? AND similarity_type = ?
            """, (source_id, similarity_type))
            
            # Insert new entries with rank
            cache_size = min(len(results), config.SIMILARITY_CACHE_SIZE)
            for rank, (similar_id, score) in enumerate(results[:cache_size], start=1):
                cursor.execute("""
                    INSERT INTO similar_images_cache
                    (source_image_id, similar_image_id, similarity_score, similarity_type, rank)
                    VALUES (?, ?, ?, ?, ?)
                """, (source_id, similar_id, score, similarity_type, rank))
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"[SimilarityCache] Error storing in cache: {e}")
        return False


def compute_and_cache_for_image(
    image_id: int,
    similarity_type: str = 'blended',
    force: bool = False
) -> bool:
    """
    Compute and cache similarities for a single image.
    
    Args:
        image_id: Image ID to compute similarities for
        similarity_type: Type of similarity to compute
        force: If True, recompute even if cache exists
    
    Returns:
        True if successful
    """
    # Check if already cached (unless force)
    if not force:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as cnt
                FROM similar_images_cache
                WHERE source_image_id = ? AND similarity_type = ?
            """, (image_id, similarity_type))
            if cursor.fetchone()['cnt'] > 0:
                # Already cached
                return True
    
    # Get filepath for this image
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT filepath FROM images WHERE id = ?", (image_id,))
        row = cursor.fetchone()
        if not row:
            return False
        filepath = row['filepath']
    
    # Compute similarities based on type
    if similarity_type == 'blended':
        from services.similarity_service import find_blended_similar
        # Use live computation (bypassing cache) to get fresh results
        results = find_blended_similar(
            filepath,
            limit=config.SIMILARITY_CACHE_SIZE,
            exclude_family=False  # Cache everything, filter at retrieval
        )
    elif similarity_type == 'semantic':
        from services.similarity_service import find_semantic_similar
        results = find_semantic_similar(filepath, limit=config.SIMILARITY_CACHE_SIZE)
    elif similarity_type == 'visual':
        from services.similarity_service import find_similar_images
        results = find_similar_images(
            filepath,
            threshold=config.VISUAL_SIMILARITY_THRESHOLD,
            limit=config.SIMILARITY_CACHE_SIZE,
            exclude_family=False
        )
    elif similarity_type == 'tag':
        from services import query_service
        results = query_service.find_related_by_tags(
            f"images/{filepath}",
            limit=config.SIMILARITY_CACHE_SIZE
        )
    else:
        print(f"[SimilarityCache] Unknown similarity type: {similarity_type}")
        return False
    
    # Convert results to (id, score) tuples
    cache_entries = []
    for result in results:
        # Get image ID from filepath
        result_path = result['path'].replace('images/', '')
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (result_path,))
            row = cursor.fetchone()
            if row:
                score = result.get('score', result.get('similarity', 0))
                cache_entries.append((row['id'], score))
    
    # Store in cache
    return store_in_cache(image_id, cache_entries, similarity_type)


def rebuild_cache_full(
    similarity_type: str = 'blended',
    progress_callback=None
) -> Dict:
    """
    Full rebuild of similarity cache for all images.
    
    Args:
        similarity_type: Type of similarity to rebuild
        progress_callback: Optional callback(current, total) for progress
    
    Returns:
        Dictionary with statistics
    """
    stats = {
        'total': 0,
        'processed': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0
    }
    
    try:
        # Get all image IDs
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM images ORDER BY id")
            image_ids = [row['id'] for row in cursor.fetchall()]
        
        stats['total'] = len(image_ids)
        print(f"[SimilarityCache] Rebuilding {similarity_type} cache for {stats['total']} images...")
        
        # Process each image
        for i, image_id in enumerate(image_ids):
            try:
                if compute_and_cache_for_image(image_id, similarity_type, force=True):
                    stats['success'] += 1
                else:
                    stats['failed'] += 1
                    
                stats['processed'] += 1
                
                # Progress callback
                if progress_callback and i % 10 == 0:
                    progress_callback(stats['processed'], stats['total'])
                
                # Print progress every 100 images
                if (i + 1) % 100 == 0:
                    print(f"[SimilarityCache] Progress: {i + 1}/{stats['total']}")
                    
            except Exception as e:
                print(f"[SimilarityCache] Error processing image {image_id}: {e}")
                stats['failed'] += 1
                stats['processed'] += 1
        
        print(f"[SimilarityCache] Rebuild complete: {stats['success']} success, {stats['failed']} failed")
        return stats
        
    except Exception as e:
        print(f"[SimilarityCache] Error in rebuild_cache_full: {e}")
        import traceback
        traceback.print_exc()
        return stats


def get_cache_stats() -> Dict:
    """
    Get statistics about cache coverage.
    
    Returns:
        Dictionary with cache statistics
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Total images
            cursor.execute("SELECT COUNT(*) as cnt FROM images")
            total_images = cursor.fetchone()['cnt']
            
            # Images with blended cache
            cursor.execute("""
                SELECT COUNT(DISTINCT source_image_id) as cnt
                FROM similar_images_cache
                WHERE similarity_type = 'blended'
            """)
            blended_cached = cursor.fetchone()['cnt']
            
            # Images with semantic cache
            cursor.execute("""
                SELECT COUNT(DISTINCT source_image_id) as cnt
                FROM similar_images_cache
                WHERE similarity_type = 'semantic'
            """)
            semantic_cached = cursor.fetchone()['cnt']
            
            # Images with visual cache
            cursor.execute("""
                SELECT COUNT(DISTINCT source_image_id) as cnt
                FROM similar_images_cache
                WHERE similarity_type = 'visual'
            """)
            visual_cached = cursor.fetchone()['cnt']
            
            # Total cache entries
            cursor.execute("SELECT COUNT(*) as cnt FROM similar_images_cache")
            total_entries = cursor.fetchone()['cnt']
            
            return {
                'total_images': total_images,
                'blended_cached': blended_cached,
                'blended_coverage': round(blended_cached / total_images * 100, 1) if total_images > 0 else 0,
                'semantic_cached': semantic_cached,
                'semantic_coverage': round(semantic_cached / total_images * 100, 1) if total_images > 0 else 0,
                'visual_cached': visual_cached,
                'visual_coverage': round(visual_cached / total_images * 100, 1) if total_images > 0 else 0,
                'total_entries': total_entries,
                'cache_enabled': config.SIMILARITY_CACHE_ENABLED,
                'cache_size': config.SIMILARITY_CACHE_SIZE
            }
            
    except Exception as e:
        print(f"[SimilarityCache] Error getting cache stats: {e}")
        return {
            'total_images': 0,
            'blended_cached': 0,
            'blended_coverage': 0,
            'cache_enabled': config.SIMILARITY_CACHE_ENABLED,
            'cache_size': config.SIMILARITY_CACHE_SIZE
        }


def clear_cache(similarity_type: Optional[str] = None) -> bool:
    """
    Clear similarity cache.
    
    Args:
        similarity_type: If specified, only clear this type. If None, clear all.
    
    Returns:
        True if successful
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if similarity_type:
                cursor.execute(
                    "DELETE FROM similar_images_cache WHERE similarity_type = ?",
                    (similarity_type,)
                )
            else:
                cursor.execute("DELETE FROM similar_images_cache")
            
            conn.commit()
            print(f"[SimilarityCache] Cleared cache for type: {similarity_type or 'all'}")
            return True
            
    except Exception as e:
        print(f"[SimilarityCache] Error clearing cache: {e}")
        return False

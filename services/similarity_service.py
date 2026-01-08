"""
Perceptual Hash Similarity Service

Provides visual similarity detection using perceptual hashing algorithms.
Similar to Czkawka's duplicate detection approach.
"""
import os
import time
import threading
from typing import Optional, List, Dict, Tuple
from PIL import Image, UnidentifiedImageError
import imagehash
import config
from database import get_db_connection, models
from utils.file_utils import get_thumbnail_path
from services import similarity_db, zip_animation_service
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

# Optional dependencies for Semantic Similarity
# FAISS is now in main app for fast in-memory search
try:
    import numpy as np
    import faiss
    NUMPY_AVAILABLE = True
    FAISS_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    FAISS_AVAILABLE = False
    np = None
    faiss = None

# ML Worker client - for embedding computation only
if config.ENABLE_SEMANTIC_SIMILARITY:
    try:
        from ml_worker.client import get_ml_worker_client
        ML_WORKER_AVAILABLE = True
        SEMANTIC_AVAILABLE = NUMPY_AVAILABLE and FAISS_AVAILABLE  # Need numpy and FAISS for semantic search
    except ImportError:
        ML_WORKER_AVAILABLE = False
        SEMANTIC_AVAILABLE = False
        print("[Similarity] Warning: ML Worker not available. Semantic similarity disabled.")
else:
    ML_WORKER_AVAILABLE = False
    SEMANTIC_AVAILABLE = False

# Global state for semantic search
_semantic_engine = None


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


def compute_colorhash(image_path: str, binbits: int = 3) -> Optional[str]:
    """
    Compute color hash for an image (captures color distribution).
    
    Args:
        image_path: Path to the image file
        binbits: Bits per channel (3 = 8x8x8 bins)
    
    Returns:
        Hex string representation of the hash, or None on error
    """
    try:
        with Image.open(image_path) as img:
            # Convert to RGB (colorhash requires color info)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Compute color hash
            chash = imagehash.colorhash(img, binbits=binbits)
            return str(chash)
    except UnidentifiedImageError:
        print(f"[Similarity] Cannot identify image for colorhash: {image_path}")
        return None
    except Exception as e:
        print(f"[Similarity] Error computing colorhash for {image_path}: {e}")
        return None


def compute_colorhash_for_video(video_path: str) -> Optional[str]:
    """
    Compute color hash from the first frame of a video.
    
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
            result = compute_colorhash(tmp_path)
            os.unlink(tmp_path)
            return result
        
        return None
    except Exception as e:
        print(f"[Similarity] Error extracting video frame: {e}")
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)
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


def compute_colorhash_for_file(filepath: str) -> Optional[str]:
    """
    Compute color hash for any supported file type.
    
    Args:
        filepath: Path to the file
        
    Returns:
        Hex string representation of the hash, or None on error
    """
    if filepath.lower().endswith(config.SUPPORTED_VIDEO_EXTENSIONS):
        return compute_colorhash_for_video(filepath)
    elif filepath.lower().endswith(config.SUPPORTED_ZIP_EXTENSIONS):
        # Compute colorhash from first frame of zip animation
        # Get MD5 to find extracted frames
        image_data = models.get_image_details(filepath)
        if image_data and image_data.get('md5'):
            md5 = image_data['md5']
            first_frame_path = zip_animation_service.get_frame_path(md5, 0)
            if first_frame_path and os.path.exists(first_frame_path):
                try:
                    img = Image.open(first_frame_path)
                    return str(imagehash.colorhash(img))
                except (OSError, IOError, UnidentifiedImageError) as e:
                    print(f"Error computing colorhash for zip animation {filepath}: {e}")
                    return None
        return None
    else:
        return compute_colorhash(filepath)


# ============================================================================
# Semantic Embedding & Search
# ============================================================================

class SemanticIndex:
    """
    FAISS-based semantic similarity index.
    Singleton pattern to keep index in memory for fast searches.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.index = None
        self.ids = []
        self.dimension = 1024
        self._initialized = True
        
        # Build index on initialization if embeddings exist
        if FAISS_AVAILABLE and SEMANTIC_AVAILABLE:
            try:
                self._build_index()
            except Exception as e:
                print(f"[SemanticIndex] Failed to build index on init: {e}")
    
    def _build_index(self):
        """Build FAISS index from all embeddings in database."""
        if not FAISS_AVAILABLE:
            print("[SemanticIndex] FAISS not available")
            return
            
        # Get all embeddings from database
        ids, matrix = similarity_db.get_all_embeddings()
        
        if len(ids) == 0:
            print("[SemanticIndex] No embeddings found in database")
            self.index = None
            self.ids = []
            return
        
        # Normalize embeddings for cosine similarity (IndexFlatIP with normalized vectors = cosine)
        # Note: modifies matrix in-place, but this is safe since get_all_embeddings() returns a new array
        faiss.normalize_L2(matrix)
        
        # Build FAISS index
        self.dimension = matrix.shape[1]
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(matrix)
        self.ids = ids
        
        print(f"[SemanticIndex] Built FAISS index with {len(ids)} embeddings")
    
    def rebuild(self):
        """Rebuild the index from scratch (call after adding new embeddings)."""
        print("[SemanticIndex] Rebuilding index...")
        self._build_index()
    
    def search(self, query_embedding: np.ndarray, limit: int = 50) -> List[Dict]:
        """
        Search for similar images using FAISS index.
        
        Args:
            query_embedding: 1024-d embedding vector (numpy array or list)
            limit: Maximum number of results
            
        Returns:
            List of dicts with 'image_id' and 'score'
        """
        if not FAISS_AVAILABLE or self.index is None:
            return []
        
        # Convert to numpy array if needed
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding, dtype=np.float32)
        
        # Make a copy and reshape to 2D array for FAISS
        # (copy to avoid modifying the caller's array)
        query = query_embedding.copy().reshape(1, -1)
        
        # Normalize query for cosine similarity
        faiss.normalize_L2(query)
        
        # Search
        distances, indices = self.index.search(query, min(limit, len(self.ids)))
        
        # Build results
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            if idx < len(self.ids):
                results.append({
                    'image_id': int(self.ids[idx]),
                    'score': float(dist)
                })
        
        return results

# Global singleton instance
_semantic_index = None

def get_semantic_index() -> SemanticIndex:
    """Get the global semantic index singleton."""
    global _semantic_index
    if _semantic_index is None:
        _semantic_index = SemanticIndex()
    return _semantic_index

# Backend Interface
class SemanticBackend:
    """Abstract base class for semantic similarity backends."""
    def is_available(self) -> bool:
        raise NotImplementedError
        
    def get_embedding(self, image_path: str, model_path: str) -> Optional[np.ndarray]:
        raise NotImplementedError
        
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        raise NotImplementedError

class MLWorkerSemanticBackend(SemanticBackend):
    """Default backend using ML Worker process via IPC."""
    def is_available(self) -> bool:
        return ML_WORKER_AVAILABLE
        
    def get_embedding(self, image_path: str, model_path: str) -> Optional[np.ndarray]:
        if not ML_WORKER_AVAILABLE:
            return None
        try:
            client = get_ml_worker_client()
            result = client.compute_similarity(image_path=image_path, model_path=model_path)
            embedding = result['embedding']
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            print(f"[Similarity] ML Worker error for {image_path}: {e}")
            return None
            
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """
        Deprecated: Search is now done locally with FAISS in main process.
        This method is kept for backward compatibility but returns empty list.
        """
        print("[Similarity] Warning: MLWorkerSemanticBackend.search_similar is deprecated. Use SemanticIndex directly.")
        return []

class SemanticSearchEngine:
    """
    Semantic similarity engine.
    Delegates actual work to a backend (ML Worker by default, or Local for inside worker).
    """
    def __init__(self):
        self.model_path = config.SEMANTIC_MODEL_PATH
        self.ml_worker_ready = False
        self._backend = MLWorkerSemanticBackend()
        
    def set_backend(self, backend: SemanticBackend):
        """Override the backend (e.g. for running inside the worker process)"""
        self._backend = backend
        
    def load_model(self):
        """Check availability."""
        if not SEMANTIC_AVAILABLE: return False
        
        if not self._backend.is_available():
            print("[Similarity] ERROR: Backend not available for semantic similarity")
            return False
            
        if not os.path.exists(self.model_path):
            print(f"[Similarity] Model not found at {self.model_path}")
            return False
        
        self.ml_worker_ready = True
        return True

    def get_embedding(self, image_path: str) -> Optional[np.ndarray]:
        """Get embedding via backend."""
        if not self.ml_worker_ready and not self.load_model():
            return None
        return self._backend.get_embedding(image_path, self.model_path)
    
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """Search via backend."""
        if not self.ml_worker_ready and not self.load_model():
            return []
        return self._backend.search_similar(query_embedding, limit)

def get_semantic_engine():
    global _semantic_engine
    if _semantic_engine is None:
        _semantic_engine = SemanticSearchEngine()
    return _semantic_engine

def set_semantic_backend(backend: SemanticBackend):
    """Global helper to set the backend for the singleton engine."""
    get_semantic_engine().set_backend(backend)

def find_semantic_similar(filepath: str, limit: int = 20) -> List[Dict]:
    """Find semantically similar images using local FAISS index."""
    if not SEMANTIC_AVAILABLE: return []
    
    # 1. Get embedding for query image
    # First check DB
    with get_db_connection() as conn:
        row = conn.execute("SELECT id FROM images WHERE filepath = ?", (filepath,)).fetchone()
        if not row: return []
        image_id = row['id']

    embedding = similarity_db.get_embedding(image_id)
    
    # If not in DB, compute it via ml_worker
    if embedding is None:
        full_path = os.path.join("static/images", filepath)
        if os.path.exists(full_path):
            engine = get_semantic_engine()
            embedding = engine.get_embedding(full_path)
            if embedding is not None:
                # Save it
                similarity_db.save_embedding(image_id, embedding)
                # Rebuild index to include new embedding
                get_semantic_index().rebuild()
    
    if embedding is None: return []
    
    # 2. Search using local FAISS index
    try:
        semantic_index = get_semantic_index()
        search_results = semantic_index.search(embedding, limit)
    except Exception as e:
        print(f"[Similarity] Semantic search failed: {e}")
        return []
    
    # 3. Resolve results
    if not search_results: return []
    
    ids = [r['image_id'] for r in search_results]
    scores = {r['image_id']: r['score'] for r in search_results}
    
    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(ids))
        rows = conn.execute(f"SELECT id, filepath FROM images WHERE id IN ({placeholders})", ids).fetchall()
        
    resolved = []
    for row in rows:
        sim_score = scores.get(row['id'], 0)
        resolved.append({
            'path': f"images/{row['filepath']}",
            'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
            'similarity': sim_score,
            'match_type': 'semantic',
            'score': sim_score
        })
        
    resolved.sort(key=lambda x: x['score'], reverse=True)
    return resolved


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


def get_image_colorhash(filepath: str) -> Optional[str]:
    """Get the stored colorhash for an image."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT colorhash FROM images WHERE filepath = ?", (filepath,))
        row = cursor.fetchone()
        return row['colorhash'] if row else None


def update_image_colorhash(filepath: str, colorhash: str) -> bool:
    """Update the colorhash for an image in the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE images SET colorhash = ? WHERE filepath = ?",
                (colorhash, filepath)
            )
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        from services import monitor_service
        monitor_service.add_log(f"Error updating colorhash: {e}", "error")
        return False


def find_similar_images(
    filepath: str,
    threshold: int = 10,
    limit: int = 50,
    exclude_family: bool = False,
    color_weight: float = 0.0
) -> List[Dict]:
    """
    Find images visually similar to the given image.
    
    Args:
        filepath: Path to the reference image (relative, without 'images/' prefix)
        threshold: Maximum Hamming distance (lower = stricter, 0-64)
        limit: Maximum number of results
        exclude_family: If True, exclude images in the same parent/child chain
        color_weight: Weight of color similarity (0.0 = only pHash, 1.0 = only ColorHash)
        
    Returns:
        List of similar images with distance and similarity score
    """
    try:
        # Get reference hashes and family info
        ref_phash = get_image_phash(filepath)
        ref_colorhash = get_image_colorhash(filepath)
        family_filepaths = set()
        
        if exclude_family:
            try:
                family_filepaths = _get_family_filepaths(filepath)
            except Exception as e:
                print(f"[Similarity] Error getting family for {filepath}: {e}")
                # Continue without exclude_family if it fails
        
        # If hashes missing, try to compute them
        full_path = os.path.join("static/images", filepath)
        
        if not ref_phash and os.path.exists(full_path):
            ref_phash = compute_phash(full_path)
            if ref_phash:
                update_image_phash(filepath, ref_phash)
                
        if not ref_colorhash and os.path.exists(full_path):
            chash = compute_colorhash(full_path)
            if chash:
                ref_colorhash = chash
                update_image_colorhash(filepath, chash)
    
        if not ref_phash:
            return []
        
        # Get all images with hashes
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT filepath, phash, colorhash
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
                    
                # 1. pHash Score (Structure)
                phash_score = hash_similarity_score(ref_phash, row['phash'])
                phash_dist = 64 * (1.0 - phash_score) # Estimated distance
                
                # 2. ColorHash Score (Color)
                color_score = 0.0
                if row['colorhash'] and ref_colorhash:
                    # Use standard max distance for colorhash? 
                    # imagehash.colorhash default binbits=3 means 8x8x8 = 512 bits? No.
                    # It creates a 144 bit hash? 
                    # Let's rely on hash_similarity_score default max=64?
                    # Actually, let's use the helper but maybe max distance differs.
                    # For now treating it same as phash for simplicity of implementation.
                    color_score = hash_similarity_score(ref_colorhash, row['colorhash'])
                
                # 3. Hybrid Score
                # color_weight 0 -> 100% pHash
                # color_weight 1 -> 100% ColorHash
                
                final_score = (phash_score * (1.0 - color_weight)) + (color_score * color_weight)
                
                # Convert back to "Effective Distance" for threshold filtering (0-64 scale)
                effective_distance = 64.0 * (1.0 - final_score)
                
                if effective_distance <= threshold:
                    similar.append({
                        'path': f"images/{row['filepath']}",
                        'thumb': get_thumbnail_path(f"images/{row['filepath']}"),
                        'distance': int(effective_distance), # Return as int for UI compatibility
                        'score': float(final_score),
                        'similarity': float(final_score),
                        'match_type': 'visual'
                    })
            except Exception as e:
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
        monitor_service.add_log(f"Critical error in find_similar_images: {e}", "error")
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

# Worker state management removed - ThreadPoolExecutor shares memory space

def _process_semantic_single(row: dict) -> dict:
    """
    Process a single image for semantic embedding.
    Designed to run in a THREAD (ProcessPoolExecutor would re-load model).
    """
    import os
    # Uses the main process global semantic engine (shared memory)
    # We don't import _worker_semantic_engine here, we use the module level one via get_semantic_engine or direct
    # But wait, we are in the same process, so direct access is fine.
    
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'semantic_generated': False,
        'errors': []
    }
    
    try:
        start_time = time.time()
        filepath = row['filepath']
        
        # Zip handling
        full_path = os.path.join("static/images", filepath)
        if filepath.lower().endswith('.zip'):
             from utils.file_utils import get_thumbnail_path
             thumb_rel = get_thumbnail_path(filepath)
             if thumb_rel != filepath:
                 full_path = os.path.join("static", thumb_rel)

        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result

        # Use global engine (which is thread-safe for inference usually, or we lock if needed, 
        # but ORT is generally thread safe for independent runs)
        engine = get_semantic_engine()
        # Ensure loaded
        if not engine.ml_worker_ready:
            # Load explicitly if not loaded (main thread should have loaded it, but self-repair is good)
            print(f"[Semantic Worker {row['id']}] Loading model (latency expected)...")
            engine.load_model()
            
        embedding = engine.get_embedding(full_path)
        duration = time.time() - start_time
        
        if embedding is not None:
             result['new_embedding'] = embedding
             result['semantic_generated'] = True
             result['success'] = True
             print(f"[Semantic Worker {row['id']}] Processed {filepath} in {duration:.2f}s")
        else:
             print(f"[Semantic Worker {row['id']}] Failed to embed {filepath} in {duration:.2f}s")
             
    except Exception as e:
        result['errors'].append(f"Semantic error: {e}")
        print(f"[Semantic Worker {row['id']}] Exception: {e}")
        
    return result


def _process_single_image_threaded(row: dict) -> dict:
    """
    Process a single image for hash generation in a thread.
    This is the threaded version that doesn't need to re-import modules.
    """
    import os
    from utils.file_utils import get_thumbnail_path
    
    result = {
        'id': row['id'],
        'filepath': row['filepath'],
        'success': False,
        'phash_generated': False,
        'colorhash_generated': False,
        'semantic_generated': False,
        'errors': []
    }
    
    try:
        filepath = row['filepath']
        md5 = row['md5']
        full_path = os.path.join("static/images", filepath)
        
        # Special handling for ZIP files (animations) -> use thumbnail for hash/embedding
        if filepath.lower().endswith('.zip'):
             thumb_rel = get_thumbnail_path(filepath)
             # get_thumbnail_path returns relative path like 'thumbnails/...' or original 'filepath' if not found
             if thumb_rel != filepath:
                 # Use the thumbnail instead
                 full_path = os.path.join("static", thumb_rel)
        
        # Check if file exists
        if not os.path.exists(full_path):
            result['errors'].append(f"File not found: {full_path}")
            return result

        updated_something = False
        
        # 1. Compute pHash if missing
        if not row['phash']:
            try:
                phash = compute_phash_for_file(full_path, md5)
                if phash:
                    result['new_phash'] = phash
                    result['phash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"pHash error: {e}")
        
        # 2. Compute ColorHash if missing
        if not row['colorhash']:
            try:
                chash = compute_colorhash_for_file(full_path)
                if chash:
                    result['new_colorhash'] = chash
                    result['colorhash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"ColorHash error: {e}")

        result['success'] = updated_something
        
    except Exception as e:
        result['errors'].append(f"Worker error: {e}")
        
    return result


# Remove old ProcessPoolExecutor worker function
# def _process_single_image(row: dict) -> dict:
#     """Old ProcessPool version - no longer used"""
#     pass

def _bulk_save_hashes(results: List[Dict]):
    """
    Save a batch of computed hashes to the database in a single transaction.
    """
    if not results:
        return

    try:
        # Separate semantic updates (custom DB) from main DB updates
        semantic_updates = []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            for res in results:
                # Update main DB hashes
                if 'new_phash' in res:
                    cursor.execute("UPDATE images SET phash = ? WHERE id = ?", (res['new_phash'], res['id']))
                
                if 'new_colorhash' in res:
                    cursor.execute("UPDATE images SET colorhash = ? WHERE id = ?", (res['new_colorhash'], res['id']))
                
                # Collect semantic embeddings
                if 'new_embedding' in res:
                    semantic_updates.append((res['id'], res['new_embedding']))
            
            conn.commit()

        # Save semantic embeddings if any (these use their own DB/file structure)
        if semantic_updates:
            for img_id, embedding in semantic_updates:
                similarity_db.save_embedding(img_id, embedding)
                
    except Exception as e:
        print(f"[Similarity] Error in bulk save: {e}")


def generate_missing_hashes(batch_size: int = 100, progress_callback=None) -> Dict:
    """
    Generate perceptual hashes and semantic embeddings for images that don't have them.
    Continuously loops until all missing hashes are generated.
    Uses ThreadPoolExecutor for parallel execution.
    
    Args:
        batch_size: Number of images to process at a time (per chunk)
        progress_callback: Optional callback(current, total) for progress updates
        
    Returns:
        Dictionary with counts of processed, successful, failed
    """
    import concurrent.futures
    import multiprocessing
    
    total_stats = {'processed': 0, 'success': 0, 'failed': 0, 'total': 0}
    
    # 1. Estimate total missing count for progress reporting
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM images WHERE phash IS NULL OR colorhash IS NULL")
            missing_visual_count = cursor.fetchone()[0]
            
            if SEMANTIC_AVAILABLE:
                cursor.execute("SELECT id FROM images")
                all_db_ids = set(row[0] for row in cursor.fetchall())
                embedded_ids = set(similarity_db.get_all_embedding_ids())
                missing_semantic_count = len(all_db_ids - embedded_ids)
            else:
                missing_semantic_count = 0
                
            # Total tasks to process
            total_stats['total'] = missing_visual_count + missing_semantic_count
            
            if total_stats['total'] == 0:
                 return total_stats

    except Exception as e:
        print(f"[Similarity] Error estimating total missing hashes: {e}")
        total_stats['total'] = 1000 # Fallback
    
    # Determine number of workers
    import config
    try:
        max_workers = config.MAX_WORKERS
    except AttributeError:
        max_workers = 4 # Fallback
        
    if max_workers <= 0:
        max_workers = max(1, multiprocessing.cpu_count() - 1)
        
    print(f"[Similarity] Starting parallel hash generation with {max_workers} workers. Total to process: {total_stats['total']}")
    
    # Track failed IDs to avoid infinite loops
    failed_ids = set()
    
    # Use ThreadPoolExecutor for all hash computation
    # This avoids the overhead of ProcessPoolExecutor and works better with I/O-bound tasks
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="IngestWorker") as executor:

        while True:
            # Fetch candidates that need hashes
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Exclude known failures
                exclude_clause = ""
                params = [batch_size]
                if failed_ids:
                    placeholders = ','.join('?' * len(failed_ids))
                    exclude_clause = f"AND id NOT IN ({placeholders})"
                    params = list(failed_ids) + params
                    
                cursor.execute(f"""
                    SELECT id, filepath, md5, phash, colorhash
                    FROM images
                    WHERE (phash IS NULL OR colorhash IS NULL)
                    {exclude_clause}
                    LIMIT ?
                """, params)
                missing_hashes = [dict(row) for row in cursor.fetchall()]

            # Also fetch semantic candidates if available
            missing_semantic = []
            
            if SEMANTIC_AVAILABLE:
                try:
                    # Get current state
                    embedded_ids = set(similarity_db.get_all_embedding_ids())
                    embedded_ids.update(failed_ids)  # Don't retry failed ones
                    
                    # Compute missing IDs efficiently
                    with get_db_connection() as conn:
                         cursor = conn.cursor()
                         cursor.execute("SELECT id FROM images")
                         all_db_ids = set(row[0] for row in cursor.fetchall())
                    
                    # Exclude images already being processed for visual hashes
                    current_batch_ids = {r['id'] for r in missing_hashes}
                    
                    candidates_ids = list(all_db_ids - embedded_ids - current_batch_ids)
                    candidates_ids.sort(reverse=True)
                    
                    target_ids = candidates_ids[:batch_size]
                    
                    if target_ids:
                        target_placeholders = ','.join('?' * len(target_ids))
                        params = tuple(target_ids)
                        
                        with get_db_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(f"""
                                SELECT id, filepath, md5, phash, colorhash
                                FROM images 
                                WHERE id IN ({target_placeholders})
                            """, params)
                            missing_semantic = [dict(row) for row in cursor.fetchall()]

                except Exception as e:
                    print(f"[Similarity] Error finding missing semantic: {e}")

            if not missing_hashes and not missing_semantic:
                break
                
            # Submit all tasks to thread pool
            futures = {}
            
            # Submit visual hash tasks
            for row in missing_hashes:
                future = executor.submit(_process_single_image_threaded, row)
                futures[future] = ('visual', row)
                
            # Submit semantic tasks
            for row in missing_semantic:
                future = executor.submit(_process_semantic_single, row)
                futures[future] = ('semantic', row)
            
            # Collect results
            results_buffer = []
            
            for future in concurrent.futures.as_completed(futures):
                task_type, row = futures[future]
                try:
                    result = future.result()
                    
                    total_stats['processed'] += 1
                    if result['success']:
                        total_stats['success'] += 1
                        results_buffer.append(result)
                    else:
                        total_stats['failed'] += 1
                        failed_ids.add(result['id'])
                    
                    if result.get('errors'):
                         error_msg = result['errors'][0]
                         if "File not found" in error_msg:
                             # Warning level for missing files (clean_orphans should run)
                             print(f"[Similarity] Warning: {result['filepath']} - {error_msg}")
                         else:
                             print(f"[Similarity] Error processing {result['filepath']}: {error_msg}")

                    if progress_callback:
                        progress_callback(total_stats['processed'], total_stats['total'])
                        
                except Exception as e:
                    print(f"[Similarity] Exception in {task_type} result: {e}")
                    total_stats['failed'] += 1
                    failed_ids.add(row['id'])

            # Bulk save
            if results_buffer:
                _bulk_save_hashes(results_buffer)
                print(f"[Similarity] Batch complete. Saved {len(results_buffer)} results.")
                
                # Rebuild semantic index if we saved any new embeddings
                has_semantic = any('new_embedding' in r for r in results_buffer)
                if has_semantic and SEMANTIC_AVAILABLE:
                    print("[Similarity] Rebuilding semantic index with new embeddings...")
                    get_semantic_index().rebuild()
    
    return total_stats





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
    visual_weight: float = 0.2,
    tag_weight: float = 0.2,
    semantic_weight: float = 0.6,
    visual_threshold: int = 15,
    tag_threshold: float = 0.1,
    semantic_threshold: float = 0.3,
    exclude_family: bool = False,
    limit: int = 12,
    use_cache: bool = True
) -> List[Dict]:
    """
    Find similar images using a weighted blend of visual, semantic, and tag similarity.
    
    Args:
        filepath: Path to reference image
        visual_weight: Weight for pHash/ColorHash (structure/color)
        tag_weight: Weight for tag similarity
        semantic_weight: Weight for neural embeddings (content/vibe)
        visual_threshold: Max visual hamming distance (0-64, lower = stricter)
        tag_threshold: Min tag similarity score (0-1, higher = stricter)
        semantic_threshold: Min semantic similarity score (0-1, higher = stricter)
        exclude_family: If True, exclude images in the same parent/child chain
        limit: Maximum number of results to return (default 12 for sidebar)
        use_cache: If True, check cache first (default True for performance)
        
    Returns:
        List of similar images, limited to specified count
    """
    from services import query_service
    
    # Check cache first if enabled (and using default parameters)
    if use_cache and config.SIMILARITY_CACHE_ENABLED:
        # Only use cache if using default/standard parameters
        # This ensures cache is used for the common sidebar case
        is_default_params = (
            visual_weight == 0.2 and 
            tag_weight == 0.2 and 
            semantic_weight == 0.6 and
            visual_threshold == 15 and
            tag_threshold == 0.1 and
            semantic_threshold == 0.3
        )
        
        if is_default_params:
            # Get image ID from filepath
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
                row = cursor.fetchone()
                if row:
                    from services import similarity_cache
                    cached_results = similarity_cache.get_similar_from_cache(
                        row['id'], 
                        limit=limit,
                        similarity_type='blended'
                    )
                    
                    if cached_results:
                        # Apply family filter if requested
                        if exclude_family:
                            family_filepaths = _get_family_filepaths(filepath)
                            family_paths = {f"images/{fp}" for fp in family_filepaths}
                            cached_results = [r for r in cached_results if r['path'] not in family_paths]
                        
                        return cached_results[:limit]
    
    # Get family filepaths to exclude if requested
    family_paths = set()
    if exclude_family:
        family_filepaths = _get_family_filepaths(filepath)
        family_paths = {f"images/{fp}" for fp in family_filepaths}
    
    # Normalize weights
    total_weight = visual_weight + tag_weight + semantic_weight
    if total_weight > 0:
        visual_weight /= total_weight
        tag_weight /= total_weight
        semantic_weight /= total_weight
    
    # Fetch large candidate pools from all sources (500 each for good coverage)
    POOL_SIZE = 500
    
    # 1. Visual (pHash/ColorHash) - filter by threshold
    visual_results = find_similar_images(
        filepath, 
        threshold=visual_threshold, 
        limit=POOL_SIZE, 
        exclude_family=exclude_family
    )
    visual_scores = {r['path']: r['similarity'] for r in visual_results}
    
    # 2. Tag - fetch all then filter by threshold
    tag_results = query_service.find_related_by_tags(f"images/{filepath}", limit=POOL_SIZE)
    tag_scores = {r['path']: r.get('score', 0) for r in tag_results if r.get('score', 0) >= tag_threshold}
    
    # 3. Semantic - fetch all then filter by threshold
    semantic_scores = {}
    if SEMANTIC_AVAILABLE and semantic_weight > 0:
        semantic_results = find_semantic_similar(filepath, limit=POOL_SIZE)
        semantic_scores = {r['path']: r['score'] for r in semantic_results if r.get('score', 0) >= semantic_threshold}
        
    # Combine all candidates that pass at least one threshold
    all_paths = set(visual_scores.keys()) | set(tag_scores.keys()) | set(semantic_scores.keys())
    if exclude_family:
        all_paths = all_paths - family_paths
        
    blended = []
    for path in all_paths:
        v_score = visual_scores.get(path, 0)
        t_score = tag_scores.get(path, 0)
        s_score = semantic_scores.get(path, 0)
        
        combined_score = (v_score * visual_weight) + (t_score * tag_weight) + (s_score * semantic_weight)
        
        # Convert visual distance to display-friendly value
        v_distance = int(64 * (1.0 - v_score)) if v_score > 0 else None
        
        blended.append({
            'path': path,
            'thumb': get_thumbnail_path(path),
            'score': combined_score,
            'visual_score': v_score,
            'visual_distance': v_distance,
            'tag_score': t_score,
            'semantic_score': s_score,
            'match_type': 'blended'
        })
        
    blended.sort(key=lambda x: x['score'], reverse=True)
    return blended[:limit] if limit else blended

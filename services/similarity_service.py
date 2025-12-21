"""
Perceptual Hash Similarity Service

Provides visual similarity detection using perceptual hashing algorithms.
Similar to Czkawka's duplicate detection approach.
"""
import os
import time
from typing import Optional, List, Dict, Tuple
from PIL import Image, UnidentifiedImageError
import imagehash
import config
from database import get_db_connection
from utils.file_utils import get_thumbnail_path
from services import similarity_db

# Optional dependencies for Semantic Similarity
try:
    import onnxruntime as ort
    import numpy as np
    import faiss
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    print("[Similarity] Warning: semantic similarity dependencies missing (onnxruntime, numpy, faiss)")

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
    # Zip animation colorhash? We could support it but maybe overkill for now.
    # If we want consistency, we should. But let's skip for now or use thumb.
    elif filepath.lower().endswith(config.SUPPORTED_ZIP_EXTENSIONS):
        return None # TODO: Implement zip colorhash
    else:
        return compute_colorhash(filepath)


# ============================================================================
# Semantic Embedding & Search
# ============================================================================

class SemanticSearchEngine:
    def __init__(self):
        self.model_path = "/mnt/Server/ChibiBooru/models/Similarity/model.onnx"
        self.session = None
        self.index = None
        self.image_ids = [] # map index ID to image ID
        self.index_dirty = True
        
    def load_model(self):
        if not SEMANTIC_AVAILABLE: return False
        if self.session: return True
        
        if not os.path.exists(self.model_path):
            print(f"[Similarity] Model not found at {self.model_path}")
            return False
            
        try:
            # Load ONNX model
            self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
            # Verify inputs/outputs
            self.input_name = self.session.get_inputs()[0].name
            # We expect the embedding output to be available (added via modification script)
            # It's usually the second or third output now
            self.output_names = [o.name for o in self.session.get_outputs()]
            print(f"[Similarity] Loaded semantic model. Outputs: {self.output_names}")
            return True
        except Exception as e:
            print(f"[Similarity] Error loading model: {e}")
            return False

    def get_embedding(self, image_path: str) -> Optional[np.ndarray]:
        if not self.load_model(): return None
        
        try:
            # Preprocess
            img_tensor = self._preprocess(image_path)
            if img_tensor is None: return None
            
            # Run inference
            # We want the normalized embedding (usually the last added output)
            # In our modified model, it is 'StatefulPartitionedCall/ConvNextBV1/predictions_norm/add:0'
            # We can request all outputs and pick the one with shape (1, 1024)
            outputs = self.session.run(None, {self.input_name: img_tensor})
            
            for out in outputs:
                if out.shape == (1, 1024):
                    return out[0] # Return 1D array
            
            # Fallback: if we can't find exact shape, maybe it's the 3rd output
            if len(outputs) >= 3:
                 return outputs[2][0]
                 
            return None
        except Exception as e:
            print(f"[Similarity] Inference error for {image_path}: {e}")
            return None

    def _get_image_for_embedding(self, image_path: str) -> Optional[Image.Image]:
        """Load image or extract frame from video for embedding."""
        try:
            # Check extension
            if image_path.lower().endswith(config.SUPPORTED_VIDEO_EXTENSIONS):
                # Use existing helper to compute pHash which extracts a frame? 
                # No, we need the PIL Image object.
                # Reuse the logic from compute_phash_for_video but return Image not hash?
                # Actually, duplicate logic or factor it out?
                # Let's verify if a thumbnail exists first, as it's faster.
                rel_path = os.path.relpath(image_path, "static/images").replace('\\', '/')
                thumb_path = get_thumbnail_path(f"images/{rel_path}")
                # thumb_path is /thumbnails/uuid.jpg relative to static usually? 
                # get_thumbnail_path returns URL path e.g. /thumbnails/...
                # We need filesystem path.
                # standard: static/thumbnails/UUID.jpg
                
                # We can't easily guess UUID from here without DB lookup usually.
                # But wait, compute_phash_for_video extracts a temp frame. 
                
                import subprocess
                import tempfile
                
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    tmp_path = tmp.name
                
                cmd = [
                    'ffmpeg', '-y', '-i', image_path,
                    '-vframes', '1', '-f', 'image2',
                    tmp_path
                ]
                # Suppress output
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                    img = Image.open(tmp_path).convert('RGB')
                    # We have to load it into memory before deleting file, or keep file until closed
                    img.load() 
                    os.unlink(tmp_path)
                    return img
                return None
            
            # Use logic to open file
            img = Image.open(image_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            return img
        except Exception as e:
            print(f"[Similarity] Error loading image for embedding {image_path}: {e}")
            return None

    def _preprocess(self, image_path: str):
        try:
            # Get PIL Image (handles videos now)
            img = self._get_image_for_embedding(image_path)
            if img is None: return None
            
            # Setup transforms (manual to avoid torchvision dependency if possible, 
            # but we likely have torchvision from requirements if using local tagger.
            # If avoiding torchvision, we do numpy math)
            # Resize to 448x448 (standard for v2? or 384? Model input says 448 in inspect output)
            # Inspect output said: [1, 448, 448, 3] -> wait, inspect output said 448x448?
            # Let's check my inspect output: "Shape: [1, 448, 448, 3]"
            target_size = 448
            
            # Resize with aspect ratio preservation + padding
            w, h = img.size
            ratio = min(target_size/w, target_size/h)
            new_w, new_h = int(w*ratio), int(h*ratio)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Paste on gray background (128, 128, 128) or specific mean? 
            # WD14 usually uses (255, 255, 255) for padding? check processing_service
            # processing_service used (124, 116, 104)
            new_img = Image.new('RGB', (target_size, target_size), (124, 116, 104))
            new_img.paste(img, ((target_size-new_w)//2, (target_size-new_h)//2))
            
            # Convert to numpy float32, normalize
            # mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
            data = np.array(new_img).astype(np.float32) / 255.0
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            data = (data - mean) / std
            
            # Transpose to BCHW? Inspect output said [1, 448, 448, 3] which is BHWC?
            # Wait. Inspect output: "Name: input_1:0, Shape: [1, 448, 448, 3], Type: tensor(float)"
            # This suggests TF-style NHWC! WD14 models are often Keras/TF exported to ONNX.
            # processed `data` is (448, 448, 3).
            # Expand dims to (1, 448, 448, 3)
            data = np.expand_dims(data, axis=0)
            
            return data
        except Exception as e:
            print(f"[Similarity] Preprocessing error: {e}")
            return None

    def build_index(self):
        if not SEMANTIC_AVAILABLE: return
        print("[Similarity] Building Semantic Index...")
        ids, matrix = similarity_db.get_all_embeddings()
        if len(ids) == 0:
            print("[Similarity] No embeddings found in DB.")
            self.index = None
            self.image_ids = []
            return

        # Normalize metrics for Cosine Similarity (Inner Product on normalized vectors)
        faiss.normalize_L2(matrix)
        
        dimension = matrix.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(matrix)
        self.image_ids = ids
        self.index_dirty = False
        print(f"[Similarity] Index built with {len(ids)} items.")

    def search(self, embedding: np.ndarray, k: int = 20):
        if self.index is None or self.index_dirty:
            self.build_index()
        
        if self.index is None: return [] # Still empty
        
        # Normalize query
        query = embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query)
        
        distances, indices = self.index.search(query, k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1: continue
            if idx < len(self.image_ids):
                results.append((self.image_ids[idx], float(dist)))
                
        return results

def get_semantic_engine():
    global _semantic_engine
    if _semantic_engine is None:
        _semantic_engine = SemanticSearchEngine()
    return _semantic_engine

def find_semantic_similar(filepath: str, limit: int = 20) -> List[Dict]:
    """Find semantically similar images."""
    if not SEMANTIC_AVAILABLE: return []
    
    # 1. Get embedding for query image
    # First check DB
    # We need image_id for DB lookup. Map filepath -> ID
    with get_db_connection() as conn:
        row = conn.execute("SELECT id FROM images WHERE filepath = ?", (filepath,)).fetchone()
        if not row: return []
        image_id = row['id']

    embedding = similarity_db.get_embedding(image_id)
    
    # If not in DB, compute it
    if embedding is None:
        full_path = os.path.join("static/images", filepath)
        if os.path.exists(full_path):
            engine = get_semantic_engine()
            embedding = engine.get_embedding(full_path)
            if embedding is not None:
                # Save it
                similarity_db.save_embedding(image_id, embedding)
                engine.index_dirty = True # Mark index as needing update (or partial add?)
    
    if embedding is None: return []
    
    # 2. Search
    engine = get_semantic_engine()
    results = engine.search(embedding, k=limit)
    
    # 3. Resolve results
    if not results: return []
    
    ids = [r[0] for r in results]
    scores = {r[0]: r[1] for r in results}
    
    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(ids))
        rows = conn.execute(f"SELECT id, filepath FROM images WHERE id IN ({placeholders})", ids).fetchall()
        
    resolved = []
    for row in rows:
        sim_score = scores.get(row['id'], 0)
        # Convert cosine similarity (-1 to 1) to distance-like (0 to 1 where 0 is close? or just score)
        # User wants similarity score.
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

# Global worker state
_worker_semantic_engine = None

def _init_worker():
    """Initialize worker process state."""
    global _worker_semantic_engine
    # No longer load model in workers to save RAM!
    _worker_semantic_engine = None

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
        if not engine.session:
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


def _process_single_image(row: dict) -> dict:
    """
    Process a single image for hash generation.
    Designed to run in a separate process.
    """
    import os
    # Re-import dependencies inside worker
    from services import similarity_db
    from utils.file_utils import get_thumbnail_path
    
    # Avoid circular/recursive execution by importing specific functions if needed, 
    # but since this is a library, importing module is standard.
    from services.similarity_service import (
        compute_phash_for_file, 
        compute_colorhash_for_file, 
        update_image_phash, 
        update_image_colorhash,
        SEMANTIC_AVAILABLE,
        SemanticSearchEngine
    )

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
                    # Return distinct value for saving later
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
                    # Return distinct value for saving later
                    result['new_colorhash'] = chash
                    result['colorhash_generated'] = True
                    updated_something = True
            except Exception as e:
                result['errors'].append(f"ColorHash error: {e}")

        # 3. Semantic Embedding
        if SEMANTIC_AVAILABLE:
            try:
                global _worker_semantic_engine
                if _worker_semantic_engine:
                    embedding = _worker_semantic_engine.get_embedding(full_path)
                    if embedding is not None:
                        # Return distinct value for saving later
                        result['new_embedding'] = embedding
                        result['semantic_generated'] = True
                        updated_something = True
            except Exception as e:
                result['errors'].append(f"Semantic error: {e}")

        result['success'] = updated_something
        
    except Exception as e:
        result['errors'].append(f"Worker error: {e}")
        
    return result

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
    Uses ProcessPoolExecutor for parallel execution.
    
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
                
            # Sum is a better estimate for total tasks (ProcessPool + ThreadPool tasks)
            # Even if same image, they are distinct tasks in our hybrid model
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
    failed_visual_ids = set()
    failed_semantic_ids = set()
    
    # Hybrid Approach:
    # ProcessPool for Visual Hashing (CPU intensive, Python GIL blocks parallel CPU)
    # ThreadPool for Semantic (Memory intensive, ONNX releases GIL, huge RAM savings)
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers, initializer=_init_worker) as process_executor, \
         concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as thread_executor:

        while True:
            # 1. Fetch Visual Candidates
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Exclude known failures
                exclude_clause = ""
                params = [batch_size]
                if failed_visual_ids:
                    placeholders = ','.join('?' * len(failed_visual_ids))
                    exclude_clause = f"AND id NOT IN ({placeholders})"
                    params = list(failed_visual_ids) + params
                    
                cursor.execute(f"""
                    SELECT id, filepath, md5, phash, colorhash
                    FROM images
                    WHERE (phash IS NULL OR colorhash IS NULL)
                    {exclude_clause}
                    LIMIT ?
                """, params)
                missing_hashes = [dict(row) for row in cursor.fetchall()]

            # 2. Fetch Semantic Candidates
            missing_semantic = []
            
            if SEMANTIC_AVAILABLE:
                try:
                    # Get current state
                    embedded_ids = set(similarity_db.get_all_embedding_ids())
                    embedded_ids.update(failed_semantic_ids)
                    
                    # Compute missing IDs efficiently
                    with get_db_connection() as conn:
                         cursor = conn.cursor()
                         cursor.execute("SELECT id FROM images")
                         all_db_ids = set(row[0] for row in cursor.fetchall())
                    
                    # Exclude valid embeddings and already-queued visual tasks (if same ID)
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
                
            # Submit tasks
            future_to_id = {}
            
            # Submit Visual -> ProcessPool
            for row in missing_hashes:
                future = process_executor.submit(_process_single_image, row)
                future_to_id[future] = ('visual', row)
                
            # Submit Semantic -> ThreadPool
            for row in missing_semantic:
                # _process_semantic_single uses the global model
                future = thread_executor.submit(_process_semantic_single, row)
                future_to_id[future] = ('semantic', row)
            
            # Collect results
            results_buffer = []
            
            for future in concurrent.futures.as_completed(future_to_id):
                task_type, row = future_to_id[future]
                try:
                    result = future.result()
                    
                    total_stats['processed'] += 1
                    if result['success']:
                        total_stats['success'] += 1
                        results_buffer.append(result)
                    
                    # Failure handling
                    if not result['success']:
                         if task_type == 'visual':
                             failed_visual_ids.add(result['id'])
                         elif task_type == 'semantic':
                             failed_semantic_ids.add(result['id'])
                        
                    if result.get('errors'):
                         print(f"[Similarity] Error processing {result['filepath']}: {result['errors'][0]}")

                    if progress_callback:
                        progress_callback(total_stats['processed'], total_stats['total'])
                        
                except Exception as e:
                    print(f"[Similarity] Exception in {task_type} result: {e}")
                    total_stats['failed'] += 1
                    if task_type == 'visual':
                         failed_visual_ids.add(row['id'])
                    elif task_type == 'semantic':
                         failed_semantic_ids.add(row['id'])

            # Bulk save
            if results_buffer:
                _bulk_save_hashes(results_buffer)
                print(f"[Similarity] Batch complete. Saved {len(results_buffer)} results.")
    
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
    threshold: int = 15,
    limit: int = 20,
    exclude_family: bool = False
) -> List[Dict]:
    """
    Find similar images using a weighted blend of visual, semantic, and tag similarity.
    
    Args:
        filepath: Path to reference image
        visual_weight: Weight for pHash/ColorHash (structure/color)
        tag_weight: Weight for tag similarity
        semantic_weight: Weight for neural embeddings (content/vibe)
        threshold: Max visual hamming distance to consider (for visual candidates)
        limit: Results limit
        
    Returns:
        List of similar images
    """
    from services import query_service
    
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
    
    # Fetch candidates from all sources
    # 1. Visual (pHash/ColorHash)
    visual_results = find_similar_images(filepath, threshold=threshold, limit=limit * 2, exclude_family=exclude_family)
    visual_scores = {r['path']: r['similarity'] for r in visual_results}
    
    # 2. Tag
    tag_results = query_service.find_related_by_tags(f"images/{filepath}", limit=limit * 2)
    tag_scores = {r['path']: r.get('score', 0) for r in tag_results}
    
    # 3. Semantic
    semantic_scores = {}
    if SEMANTIC_AVAILABLE and semantic_weight > 0:
        semantic_results = find_semantic_similar(filepath, limit=limit * 2)
        semantic_scores = {r['path']: r['score'] for r in semantic_results}
        
    # Combine
    all_paths = set(visual_scores.keys()) | set(tag_scores.keys()) | set(semantic_scores.keys())
    if exclude_family:
        all_paths = all_paths - family_paths
        
    blended = []
    for path in all_paths:
        v_score = visual_scores.get(path, 0)
        t_score = tag_scores.get(path, 0)
        s_score = semantic_scores.get(path, 0)
        
        combined_score = (v_score * visual_weight) + (t_score * tag_weight) + (s_score * semantic_weight)
        
        blended.append({
            'path': path,
            'thumb': get_thumbnail_path(path),
            'score': combined_score,
            'visual_score': v_score,
            'tag_score': t_score,
            'semantic_score': s_score,
            'match_type': 'blended'
        })
        
    blended.sort(key=lambda x: x['score'], reverse=True)
    return blended[:limit]

"""
Semantic Similarity Module

Provides FAISS-based semantic similarity search using embedding vectors.
Uses ML Worker for embedding computation, FAISS for fast nearest-neighbor search.
"""
import os
import threading
from typing import Optional, List, Dict
import config
from database import get_db_connection
from services import similarity_db
from utils.file_utils import get_thumbnail_path

# Optional numpy and FAISS imports
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

# ML Worker client
if config.ENABLE_SEMANTIC_SIMILARITY:
    try:
        from ml_worker.client import get_ml_worker_client
        ML_WORKER_AVAILABLE = True
        SEMANTIC_AVAILABLE = NUMPY_AVAILABLE and FAISS_AVAILABLE
    except ImportError:
        ML_WORKER_AVAILABLE = False
        SEMANTIC_AVAILABLE = False
else:
    ML_WORKER_AVAILABLE = False
    SEMANTIC_AVAILABLE = False


def _log(message: str, level: str = "info"):
    """Centralized logging helper."""
    try:
        from services import monitor_service
        monitor_service.add_log(f"[Semantic] {message}", level)
    except Exception:
        print(f"[Semantic] {message}")


# ============================================================================
# FAISS Semantic Index
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
        
        if FAISS_AVAILABLE and SEMANTIC_AVAILABLE:
            try:
                self._build_index()
            except Exception as e:
                _log(f"Failed to build index on init: {e}", "error")
    
    def _build_index(self):
        """Build FAISS index from all embeddings in database."""
        if not FAISS_AVAILABLE:
            _log("FAISS not available", "warning")
            return
            
        ids, matrix = similarity_db.get_all_embeddings()
        
        if len(ids) == 0:
            _log("No embeddings found in database", "info")
            self.index = None
            self.ids = []
            return
        
        faiss.normalize_L2(matrix)
        
        self.dimension = matrix.shape[1]
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(matrix)
        self.ids = ids
        
        _log(f"Built FAISS index with {len(ids)} embeddings", "info")
    
    def rebuild(self):
        """Rebuild the index from scratch."""
        _log("Rebuilding index...", "info")
        self._build_index()
    
    def search(self, query_embedding, limit: int = 50) -> List[Dict]:
        """Search for similar images using FAISS index."""
        if not FAISS_AVAILABLE or self.index is None:
            return []
        
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding, dtype=np.float32)
        
        query = query_embedding.copy().reshape(1, -1)
        faiss.normalize_L2(query)
        
        distances, indices = self.index.search(query, min(limit, len(self.ids)))
        
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


def get_semantic_index() -> SemanticIndex:
    """Get the global semantic index singleton."""
    return SemanticIndex()


# ============================================================================
# Semantic Backend Interface
# ============================================================================

class SemanticBackend:
    """Abstract base class for semantic similarity backends."""
    def is_available(self) -> bool:
        raise NotImplementedError
        
    def get_embedding(self, image_path: str, model_path: str):
        raise NotImplementedError
        
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        raise NotImplementedError


class MLWorkerSemanticBackend(SemanticBackend):
    """Default backend using ML Worker process via IPC."""
    def is_available(self) -> bool:
        return ML_WORKER_AVAILABLE
        
    def get_embedding(self, image_path: str, model_path: str):
        if not ML_WORKER_AVAILABLE:
            return None
        try:
            client = get_ml_worker_client()
            result = client.compute_similarity(image_path=image_path, model_path=model_path)
            embedding = result['embedding']
            return np.array(embedding, dtype=np.float32)
        except Exception as e:
            _log(f"ML Worker error for {image_path}: {e}", "error")
            return None
            
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """Deprecated: Search is now done locally with FAISS."""
        _log("MLWorkerSemanticBackend.search_similar is deprecated", "warning")
        return []


class SemanticSearchEngine:
    """Semantic similarity engine with pluggable backend."""
    def __init__(self):
        self.model_path = config.SEMANTIC_MODEL_PATH
        self.ml_worker_ready = False
        self._backend = MLWorkerSemanticBackend()
        
    def set_backend(self, backend: SemanticBackend):
        """Override the backend."""
        self._backend = backend
        
    def load_model(self):
        """Check availability."""
        if not SEMANTIC_AVAILABLE:
            return False
        
        if not self._backend.is_available():
            _log("Backend not available", "error")
            return False
            
        if not os.path.exists(self.model_path):
            _log(f"Model not found at {self.model_path}", "error")
            return False
        
        self.ml_worker_ready = True
        return True

    def get_embedding(self, image_path: str):
        """Get embedding via backend."""
        if not self.ml_worker_ready and not self.load_model():
            return None
        return self._backend.get_embedding(image_path, self.model_path)
    
    def search_similar(self, query_embedding: List[float], limit: int) -> List[Dict]:
        """Search via backend."""
        if not self.ml_worker_ready and not self.load_model():
            return []
        return self._backend.search_similar(query_embedding, limit)


# Global engine instance
_semantic_engine = None

def get_semantic_engine() -> SemanticSearchEngine:
    global _semantic_engine
    if _semantic_engine is None:
        _semantic_engine = SemanticSearchEngine()
    return _semantic_engine


def set_semantic_backend(backend: SemanticBackend):
    """Set the backend for the singleton engine."""
    get_semantic_engine().set_backend(backend)


# ============================================================================
# Semantic Search Function
# ============================================================================

def find_semantic_similar(
    filepath: str,
    limit: int = 20,
    exclude_self: bool = True,
    exclude_family: bool = False,
    get_family_func=None
) -> List[Dict]:
    """
    Find semantically similar images using local FAISS index.
    
    Args:
        filepath: Path to reference image (relative, without 'images/' prefix)
        limit: Maximum number of results
        exclude_self: If True, exclude current image from results
        exclude_family: If True, exclude images in same parent/child chain
        get_family_func: Optional function to get family filepaths
    """
    if not SEMANTIC_AVAILABLE:
        return []
    
    # Get image ID
    with get_db_connection() as conn:
        row = conn.execute("SELECT id FROM images WHERE filepath = ?", (filepath,)).fetchone()
        if not row:
            return []
        image_id = row['id']

    # Get embedding
    embedding = similarity_db.get_embedding(image_id)
    
    if embedding is None:
        full_path = os.path.join("static/images", filepath)
        if os.path.exists(full_path):
            engine = get_semantic_engine()
            embedding = engine.get_embedding(full_path)
            if embedding is not None:
                similarity_db.save_embedding(image_id, embedding)
                get_semantic_index().rebuild()
    
    if embedding is None:
        return []
    
    # Search
    try:
        semantic_index = get_semantic_index()
        
        if semantic_index.index and embedding.shape[0] != semantic_index.dimension:
            _log(f"Dimension mismatch: embedding has {embedding.shape[0]}, index has {semantic_index.dimension}", "warning")
            return []
            
        search_results = semantic_index.search(embedding, limit + 10)
    except Exception as e:
        _log(f"Semantic search failed: {e}", "error")
        return []
    
    if not search_results:
        return []
    
    # Resolve results
    ids = [r['image_id'] for r in search_results]
    scores = {r['image_id']: r['score'] for r in search_results}
    
    with get_db_connection() as conn:
        placeholders = ','.join('?' * len(ids))
        rows = conn.execute(f"SELECT id, filepath FROM images WHERE id IN ({placeholders})", ids).fetchall()
    
    # Build exclusion sets
    current_path_normalized = f"images/{filepath}"
    family_paths = set()
    if exclude_family and get_family_func:
        try:
            family_filepaths = get_family_func(filepath)
            family_paths = {f"images/{fp}" for fp in family_filepaths}
        except Exception as e:
            _log(f"Error getting family: {e}", "warning")
        
    resolved = []
    for row in rows:
        result_path = f"images/{row['filepath']}"
        
        if exclude_self and result_path == current_path_normalized:
            continue
        if exclude_family and result_path in family_paths:
            continue
            
        sim_score = scores.get(row['id'], 0)
        resolved.append({
            'path': result_path,
            'thumb': get_thumbnail_path(result_path),
            'similarity': sim_score,
            'match_type': 'semantic',
            'score': sim_score,
            'primary_source': 'semantic'
        })
        
    resolved.sort(key=lambda x: x['score'], reverse=True)
    return resolved[:limit]


# Export availability flags
__all__ = [
    'SEMANTIC_AVAILABLE', 'FAISS_AVAILABLE', 'ML_WORKER_AVAILABLE', 'NUMPY_AVAILABLE',
    'SemanticIndex', 'get_semantic_index',
    'SemanticBackend', 'MLWorkerSemanticBackend', 'SemanticSearchEngine',
    'get_semantic_engine', 'set_semantic_backend',
    'find_semantic_similar',
]

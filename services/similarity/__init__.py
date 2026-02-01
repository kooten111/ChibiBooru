"""
Similarity Package

Provides visual and semantic similarity detection for images.
Re-exports commonly used functions for backward compatibility.
"""

# Hashing functions
from services.similarity.hashing import (
    compute_phash,
    compute_colorhash,
    compute_phash_for_video,
    compute_colorhash_for_video,
    compute_phash_for_zip_animation,
    compute_phash_for_file,
    compute_colorhash_for_file,
    hamming_distance,
    hash_similarity_score,
)

# Semantic search
from services.similarity.semantic import (
    SEMANTIC_AVAILABLE,
    FAISS_AVAILABLE,
    ML_WORKER_AVAILABLE,
    NUMPY_AVAILABLE,
    SemanticIndex,
    get_semantic_index,
    SemanticBackend,
    MLWorkerSemanticBackend,
    SemanticSearchEngine,
    get_semantic_engine,
    set_semantic_backend,
    find_semantic_similar,
)

__all__ = [
    # Hashing
    'compute_phash',
    'compute_colorhash',
    'compute_phash_for_video',
    'compute_colorhash_for_video',
    'compute_phash_for_zip_animation',
    'compute_phash_for_file',
    'compute_colorhash_for_file',
    'hamming_distance',
    'hash_similarity_score',
    # Semantic
    'SEMANTIC_AVAILABLE',
    'FAISS_AVAILABLE',
    'ML_WORKER_AVAILABLE',
    'NUMPY_AVAILABLE',
    'SemanticIndex',
    'get_semantic_index',
    'SemanticBackend',
    'MLWorkerSemanticBackend',
    'SemanticSearchEngine',
    'get_semantic_engine',
    'set_semantic_backend',
    'find_semantic_similar',
]

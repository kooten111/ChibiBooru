"""
System handlers (health check, cache rebuild etc)
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any

from ml_worker.jobs import start_job, get_active_jobs_count

logger = logging.getLogger(__name__)

def handle_health_check(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle health check request"""
    import torch
    
    return {
        "status": "ok",
        "cuda_available": torch.cuda.is_available(),
        "active_jobs": get_active_jobs_count()
    }


def handle_rebuild_cache(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle rebuild_cache request.
    Restarts the cache build process in a background thread.
    """
    similarity_type = request_data.get('similarity_type', 'blended')
    logger.info(f"Starting similarity cache rebuild ({similarity_type})...")
    
    # Import here to avoid circular dependencies
    # Assuming project root in path
    if 'services.similarity_cache' not in sys.modules:
         try:
             from services import similarity_cache
         except ImportError:
             sys.path.insert(0, str(Path(__file__).parent.parent.parent))
             from services import similarity_cache
    else:
         from services import similarity_cache
    
    def _run_rebuild(progress_callback=None):
        logger.info(f"Rebuilding cache ({similarity_type})...")
        
        def adapter(current, total):
            if progress_callback:
                pct = int(current / total * 100) if total > 0 else 0
                progress_callback(pct, f"Processed {current}/{total} images")
            
        stats = similarity_cache.rebuild_cache_full(
            similarity_type=similarity_type,
            progress_callback=adapter
        )
        
        logger.info(f"Rebuild complete. Stats: {stats}")
        return stats
        
    job_id = start_job(_run_rebuild)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Cache rebuild started"
    }

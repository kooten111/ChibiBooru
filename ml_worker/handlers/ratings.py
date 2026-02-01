"""
Ratings model service handlers
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any

from ml_worker.jobs import start_job

logger = logging.getLogger(__name__)

def handle_train_rating_model(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle train_rating_model request.
    
    Returns:
        Dict with job info (job_id, status)
    """
    logger.info("Starting rating model training background job...")
    
    # Import rating service from parent context
    # This assumes we are running with project root in path (which server.py ensures)
    if 'services.rating_service' not in sys.modules:
        try:
            from services import rating_service
        except ImportError:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from services import rating_service
    else:
        from services import rating_service
    
    job_id = start_job(rating_service.train_model)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Training started in background"
    }


def handle_infer_ratings(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle infer_ratings request.
    
    Args:
        request_data: {image_ids: list | None}
    
    Returns:
        Dict with job info (job_id, status)
    """
    image_ids = request_data.get('image_ids', [])
    
    logger.info(f"Starting rating inference background job (image_ids: {len(image_ids) if image_ids else 'all unrated'})")
    
    # Import rating service
    if 'services.rating_service' not in sys.modules:
        try:
             from services import rating_service
        except ImportError:
             sys.path.insert(0, str(Path(__file__).parent.parent.parent))
             from services import rating_service
    else:
         from services import rating_service
    
    if image_ids:
        # Wrapper for specific images
        def _run_specific(progress_callback=None):
            if progress_callback:
                progress_callback(0, "Processing specific images...")
                
            stats = {
                'processed': 0,
                'rated': 0,
                'skipped_low_confidence': 0,
                'by_rating': {r: 0 for r in rating_service.RATINGS}
            }
            
            total = len(image_ids)
            for i, image_id in enumerate(image_ids):
                result = rating_service.infer_rating_for_image(image_id)
                stats['processed'] += 1
                if result['rated']:
                    stats['rated'] += 1
                    stats['by_rating'][result['rating']] += 1
                else:
                    stats['skipped_low_confidence'] += 1
                
                if progress_callback and (i + 1) % 10 == 0:
                     progress_callback(int((i+1)/total * 100), f"Processed {i+1}/{total}")
                     
            return stats
            
        job_id = start_job(_run_specific)
    else:
        # Infer all unrated supports callback natively now
        job_id = start_job(rating_service.infer_all_unrated_images)
    
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Inference started in background"
    }

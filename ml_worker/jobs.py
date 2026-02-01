"""
Background job management for ML worker
"""
import uuid
import time
import threading
import traceback
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Job status tracking (simple in-memory store)
_job_store = {}


class JobRunner(threading.Thread):
    def __init__(self, job_id: str, target, args=(), kwargs=None):
        super().__init__()
        self.job_id = job_id
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = True
        
    def run(self):
        try:
            _job_store[self.job_id]['status'] = 'running'
            
            def progress_callback(percent, message):
                _job_store[self.job_id]['progress'] = percent
                _job_store[self.job_id]['message'] = message
            
            # Inject progress_callback if target accepts it
            # We assume target function signature handles this if needed
            # For simplicity, we pass it as a kwarg if supported, or wrapped
            
            # Note: In the original code, it was passed as *self.args or **kwargs
            # but let's stick to the pattern used: 
            # result = self.target(progress_callback=progress_callback, *self.args, **self.kwargs)
            
            # However some targets might NOT accept progress_callback.
            # We should probably inspect the target, or rely on the caller to wrap it if needed.
            # For now, let's keep the existing behavior which seems to assume the target knows what to simplify.
            
            # Check if we should pass progress_callback (naive check)
            try:
                result = self.target(progress_callback=progress_callback, *self.args, **self.kwargs)
            except TypeError as e:
                # Fallback if unexpected argument (e.g. target doesn't accept progress_callback)
                if "unexpected keyword argument 'progress_callback'" in str(e):
                     result = self.target(*self.args, **self.kwargs)
                else:
                    raise e
            
            _job_store[self.job_id]['status'] = 'completed'
            _job_store[self.job_id]['progress'] = 100
            _job_store[self.job_id]['result'] = result
            
        except Exception as e:
            logger.error(f"Job {self.job_id} failed: {e}")
            logger.error(traceback.format_exc())
            _job_store[self.job_id]['status'] = 'failed'
            _job_store[self.job_id]['error'] = str(e)


def start_job(target, *args, **kwargs) -> str:
    """Start a background job and return its ID"""
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {
        'status': 'pending',
        'progress': 0,
        'message': 'Starting...',
        'created_at': time.time()
    }
    
    runner = JobRunner(job_id, target, args, kwargs)
    runner.start()
    
    return job_id


def handle_get_job_status(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle get_job_status request.
    
    Args:
        request_data: {job_id: str}
    
    Returns:
        Dict with job status
    """
    job_id = request_data.get('job_id')
    
    if not job_id:
        raise ValueError("job_id is required")
    
    job = _job_store.get(job_id)
    
    if not job:
        return {
            "found": False,
            "job_id": job_id
        }
    
    return {
        "found": True,
        "job_id": job_id,
        **job
    }


def get_active_jobs_count() -> int:
    """Return number of active (running/pending) jobs"""
    return sum(1 for job in _job_store.values() if job['status'] in ('running', 'pending'))

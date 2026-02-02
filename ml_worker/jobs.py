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
            
            # Smartly inject progress_callback using inspection
            import inspect
            
            sig = inspect.signature(self.target)
            params = sig.parameters
            
            # If target accepts 'progress_callback' or **kwargs, pass it
            accepts_callback = 'progress_callback' in params or \
                               any(p.kind == p.VAR_KEYWORD for p in params.values())
            
            if accepts_callback:
                # Avoid passing it twice if it's already in kwargs
                if 'progress_callback' not in self.kwargs:
                     result = self.target(progress_callback=progress_callback, *self.args, **self.kwargs)
                else:
                     result = self.target(*self.args, **self.kwargs)
            else:
                result = self.target(*self.args, **self.kwargs)
            
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
    
    # Check if job_id was passed in kwargs (special case for handler injection)
    if 'job_id' in kwargs:
        job_id = kwargs.pop('job_id')
    else:
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

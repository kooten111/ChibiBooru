# services/background_tasks.py
import asyncio
from datetime import datetime
from typing import Dict, Optional, Callable, Any
import traceback

class BackgroundTaskManager:
    """Manages background tasks with progress tracking."""

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def start_task(self, task_id: str, task_func: Callable, *args, **kwargs):
        """Start a background task."""
        async with self._lock:
            if task_id in self.tasks and self.tasks[task_id]['status'] in ['running', 'pending']:
                raise ValueError(f"Task {task_id} is already running")

            self.tasks[task_id] = {
                'status': 'pending',
                'progress': 0,
                'total': 0,
                'current_item': None,
                'message': 'Starting task...',
                'started_at': datetime.now().isoformat(),
                'completed_at': None,
                'error': None,
                'result': None
            }

        # Create the task
        asyncio.create_task(self._run_task(task_id, task_func, *args, **kwargs))

    async def _run_task(self, task_id: str, task_func: Callable, *args, **kwargs):
        """Run a task in the background."""
        try:
            async with self._lock:
                self.tasks[task_id]['status'] = 'running'

            # Run the task function
            result = await task_func(task_id, self, *args, **kwargs)

            async with self._lock:
                self.tasks[task_id]['status'] = 'completed'
                self.tasks[task_id]['completed_at'] = datetime.now().isoformat()
                self.tasks[task_id]['result'] = result
                self.tasks[task_id]['message'] = 'Task completed successfully'

        except Exception as e:
            async with self._lock:
                self.tasks[task_id]['status'] = 'failed'
                self.tasks[task_id]['completed_at'] = datetime.now().isoformat()
                self.tasks[task_id]['error'] = str(e)
                self.tasks[task_id]['message'] = f'Task failed: {str(e)}'
                print(f"[Background Task {task_id}] Error: {e}")
                traceback.print_exc()

    async def update_progress(self, task_id: str, progress: int, total: int,
                             message: Optional[str] = None, current_item: Optional[str] = None):
        """Update task progress."""
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id]['progress'] = progress
                self.tasks[task_id]['total'] = total
                if message:
                    self.tasks[task_id]['message'] = message
                if current_item:
                    self.tasks[task_id]['current_item'] = current_item

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a task."""
        async with self._lock:
            return self.tasks.get(task_id, None)

    async def cancel_task(self, task_id: str):
        """Mark a task as cancelled (note: actual cancellation needs cooperation from task)."""
        async with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id]['status'] = 'cancelled'
                self.tasks[task_id]['completed_at'] = datetime.now().isoformat()
                self.tasks[task_id]['message'] = 'Task was cancelled'

# Global task manager instance
task_manager = BackgroundTaskManager()

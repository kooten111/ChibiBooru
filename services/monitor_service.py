# services/monitor_service.py
import threading
import time
import os
from concurrent.futures import ThreadPoolExecutor
from database import models
from services import processing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from utils.logging_config import get_logger

logger = get_logger('MonitorService')

# --- Shared Monitor State ---
monitor_thread = None
observer = None
ingest_executor = None  # Global ThreadPoolExecutor (changed from ProcessPoolExecutor)

# Thread-safe set of files currently queued/in-progress to prevent double-submission
_files_in_progress = set()
_files_lock = threading.Lock()
monitor_status = {
    "running": False,
    "last_check": None,
    "last_scan_found": 0,
    "total_processed": 0,
    "total_skipped_duplicate": 0,
    "total_skipped_race": 0,
    "total_failed": 0,
    "interval_seconds": 300, # 5 minutes (fallback, not used with watchdog)
    "logs": [],
    "mode": "watchdog",  # "watchdog" for real-time or "polling" for legacy
}

LOG_FILE = "monitor.logs"

def check_external_monitor():
    """Check if the external monitor process is running via PID file."""
    try:
        import psutil
        if os.path.exists("monitor.pid"):
            with open("monitor.pid", "r") as f:
                pid = int(f.read().strip())
            
            if psutil.pid_exists(pid):
                # Verify it's actually our python process
                try:
                    proc = psutil.Process(pid)
                    if 'python' in proc.name().lower():
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # If we get here, PID file exists but process doesn't (stale)
            # Optional: could clean it up here, but maybe safer to let runner handle it
            pass
    except Exception:
        pass
    return False

def get_status():
    """Return the current status of the monitor."""
    # Check external monitor status if not running locally
    if not monitor_status["running"]:
        if check_external_monitor():
             monitor_status["running"] = True
             monitor_status["mode"] = "external"
    
    # If we think it's running but it died, update
    elif monitor_status["mode"] == "external":
        if not check_external_monitor():
            monitor_status["running"] = False
            monitor_status["mode"] = "watchdog" # Reset to default

    # Always try to load latest logs from file
    try:
        if os.path.exists(LOG_FILE):
            import json
            with open(LOG_FILE, 'r') as f:
                monitor_status['logs'] = json.load(f)
    except Exception:
        pass
            
    return monitor_status

# Global lock for log file access
# Global lock for thread safety within this process
log_lock = threading.Lock()

def add_log(message, type='info'):
    """Adds a log entry to the monitor status and persistent file."""
    import json
    import fcntl
    
    log_entry = {'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"), 'message': message, 'type': type}
    
    # Use thread lock for intra-process safety
    with log_lock:
        try:
            # Use file lock for inter-process safety
            # Open the file in Append mode first to ensure it exists, but we need Read/Write
            if not os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'w') as f:
                    json.dump([], f)

            with open(LOG_FILE, 'r+') as f:
                # Acquire exclusive lock - blocks if another process has it
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    # Read existing
                    try:
                        f.seek(0)
                        content = f.read().strip()
                        current_logs = json.loads(content) if content else []
                    except Exception:
                        current_logs = []
                    
                    # Insert new log
                    current_logs.insert(0, log_entry)
                    if len(current_logs) > 100:
                        current_logs = current_logs[:100]
                    
                    # Write back
                    f.seek(0)
                    f.truncate()
                    json.dump(current_logs, f)
                    f.flush()
                    os.fsync(f.fileno()) # Force write to disk
                    
                    # Update memory for this process
                    monitor_status['logs'] = current_logs
                    
                finally:
                    # Release lock
                    fcntl.flock(f, fcntl.LOCK_UN)
                    
        except Exception as e:
            print(f"Error writing log file: {e}")

    # Update memory (this is thread-safe enough for assignment)
    monitor_status['logs'] = current_logs

# --- Watchdog Event Handler ---

class ImageFileHandler(FileSystemEventHandler):
    """Handles filesystem events for new image files."""

    def __init__(self, watch_ingest=False):
        super().__init__()
        # Debounce: track recently processed files to avoid duplicates
        self.recently_processed = {}
        self.debounce_seconds = 2
        self.watch_ingest = watch_ingest

    def is_image_file(self, filepath):
        """Check if file is an image, video, or zip animation."""
        return filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.zip'))

    def should_process(self, filepath):
        """Check if we should process this file (debouncing)."""
        now = time.time()
        # Clean old entries
        self.recently_processed = {
            k: v for k, v in self.recently_processed.items()
            if now - v < self.debounce_seconds
        }
        # Check if recently processed
        if filepath in self.recently_processed:
            return False
        self.recently_processed[filepath] = now
        return True
        
    def handle_file_completion(self, future, is_from_ingest, filename, abs_filepath=None):
        """Callback for when file processing completes."""
        try:
            result = future.result()
            # process_image_file returns (success, msg, failure_type) tuple
            if isinstance(result, tuple):
                if len(result) == 3:
                    success, msg, failure_type = result
                elif len(result) == 2:
                    # Backwards compatibility with 2-tuple returns
                    success, msg = result
                    failure_type = "unknown"
                else:
                    success = bool(result[0]) if result else False
                    msg = ""
                    failure_type = "unknown"
            else:
                success = bool(result)
                msg = ""
                failure_type = "unknown"
            
            if success:
                monitor_status["last_scan_found"] = 1
                monitor_status["total_processed"] += 1
                add_log(f"Successfully processed: {filename}", 'success')
            elif failure_type == 'duplicate':
                monitor_status["total_skipped_duplicate"] += 1
                add_log(f"Skipped duplicate: {filename}", 'warning')
            elif failure_type == 'race_condition':
                monitor_status["total_skipped_race"] += 1
                add_log(f"Skipped (already being processed): {filename}", 'info')
            else:
                # Only log real errors
                monitor_status["total_failed"] += 1
                add_log(f"Failed to process {filename}: {msg}", 'error')
                
        except Exception as e:
            add_log(f"Error processing {filename}: {e}", 'error')
        finally:
            # Always release from tracking set when done
            if abs_filepath:
                with _files_lock:
                    _files_in_progress.discard(abs_filepath)

    def on_created(self, event):
        """Called when a file is created."""
        try:
            if event.is_directory:
                return

            filepath = event.src_path
            if not self.is_image_file(filepath):
                return

            if not self.should_process(filepath):
                return

            # Small delay to ensure file is fully written
            time.sleep(0.5)
            
            # Check if file still exists (might have been moved/deleted)
            if not os.path.exists(filepath):
                return

            import config
            
            # Determine if this is from ingest folder
            abs_filepath = os.path.abspath(filepath)
            abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
            is_from_ingest = self.watch_ingest and abs_filepath.startswith(abs_ingest)
            filename = os.path.basename(filepath)

            if not is_from_ingest:
                # Check if already in DB for static/images files
                rel_path = os.path.relpath(filepath, "static/images").replace('\\', '/')
                if rel_path in models.get_all_filepaths():
                    return

            # Prevent double-submission: check if this file is already queued/in-progress
            with _files_lock:
                if abs_filepath in _files_in_progress:
                    logger.debug(f"Watchdog skipping {filename} - already in progress")
                    return
                _files_in_progress.add(abs_filepath)

            add_log(f"Detected {filename}, queuing for processing...", 'info')
            logger.debug(f"Watchdog queuing: {abs_filepath}")
            
            # Submit to global executor with unified processing function
            if ingest_executor:
                future = ingest_executor.submit(processing.process_image_file, filepath, is_from_ingest)
                # Use partial to pass extra args to callback
                from functools import partial
                future.add_done_callback(partial(self.handle_file_completion, is_from_ingest=is_from_ingest, filename=filename, abs_filepath=abs_filepath))
            else:
                add_log("Executor not ready, skipping processing.", 'error')
                # Release from tracking set on failure
                with _files_lock:
                    _files_in_progress.discard(abs_filepath)
                
        except Exception as e:
            # Log but don't crash the watchdog thread
            try:
                add_log(f"Error in file handler: {e}", 'error')
            except:
                print(f"[Monitor] Error in file handler: {e}")


# --- Core Monitor Logic ---

def find_ingest_files():
    """
    Finds all image files in the ingest directory (recursively).
    Returns a list of absolute file paths.
    """
    import config

    ingest_files = []
    if os.path.exists(config.INGEST_DIRECTORY):
        for root, _, files in os.walk(config.INGEST_DIRECTORY):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.zip')):
                    filepath = os.path.join(root, file)
                    ingest_files.append(filepath)
    return ingest_files

def find_unprocessed_images():
    """
    Finds image files on disk that are not in the database.
    Also checks for MD5 duplicates and removes them automatically,
    but only if the file is not currently being processed by another thread.
    """
    import hashlib
    from database import get_db_connection
    from .processing.locks import acquire_processing_lock, release_processing_lock
    
    db_filepaths = models.get_all_filepaths()
    unprocessed_files = []
    duplicates_removed = 0
    skipped_in_progress = 0

    # Check static/images directory
    for root, _, files in os.walk("static/images"):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm', '.zip')):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, "static/images").replace('\\', '/')
                
                if rel_path not in db_filepaths:
                    # Filepath not in DB - but check if MD5 already exists (duplicate file)
                    try:
                        with open(filepath, 'rb') as f:
                            md5 = hashlib.md5(f.read()).hexdigest()
                        
                        with get_db_connection() as conn:
                            row = conn.execute('SELECT filepath FROM images WHERE md5 = ?', (md5,)).fetchone()
                            if row:
                                # Before deleting, check if another thread is actively processing this MD5
                                lock_fd, acquired = acquire_processing_lock(md5)
                                if not acquired:
                                    # Another thread is actively processing this MD5 — do NOT delete
                                    logger.debug(f"Skipping duplicate removal for {file} (MD5 {md5}) - currently being processed")
                                    skipped_in_progress += 1
                                    continue
                                
                                try:
                                    # Re-verify inside lock that the DB entry still exists
                                    row = conn.execute('SELECT filepath FROM images WHERE md5 = ?', (md5,)).fetchone()
                                    if row:
                                        # This is a duplicate file - same content, different name
                                        logger.info(f"Auto-removing duplicate: {file} (MD5: {md5}, same as {row['filepath']})")
                                        add_log(f"Auto-removing duplicate: {file} (same as {os.path.basename(row['filepath'])})", 'warning')
                                        os.remove(filepath)
                                        duplicates_removed += 1
                                    else:
                                        # DB entry disappeared between checks (another thread deleted it?)
                                        logger.debug(f"MD5 {md5} no longer in DB after acquiring lock, treating {file} as unprocessed")
                                        unprocessed_files.append(filepath)
                                finally:
                                    release_processing_lock(lock_fd)
                                continue
                    except Exception as e:
                        add_log(f"Error checking MD5 for {file}: {e}", 'error')
                    
                    unprocessed_files.append(filepath)

    # Check ingest directory (use helper function)
    unprocessed_files.extend(find_ingest_files())
    
    if duplicates_removed > 0:
        add_log(f"Cleaned up {duplicates_removed} duplicate file(s)", 'info')
    if skipped_in_progress > 0:
        logger.info(f"Skipped {skipped_in_progress} file(s) that are currently being processed")

    return unprocessed_files

def run_scan():
    """
    Finds and processes all new images using parallel workers.
    Returns (processed_count, attempted_count) so callers can distinguish
    "no files found" from "files found but none processed".
    """
    import config

    unprocessed_files = find_unprocessed_images()
    if not unprocessed_files:
        add_log("No new images found.")
        return 0, 0

    add_log(f"Found {len(unprocessed_files)} new images. Starting parallel processing...", 'info')

    # Use global executor if available; otherwise create a one-off executor for this scan.
    # This allows "Run scan" from the UI to work when the monitor is external or not started.
    executor = ingest_executor
    one_off_executor = None
    if not executor:
        try:
            max_workers = getattr(config, 'MAX_WORKERS', 4)
            if max_workers <= 0:
                import multiprocessing
                max_workers = max(1, multiprocessing.cpu_count() - 1)
            one_off_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="IngestWorker")
            executor = one_off_executor
            add_log("Using temporary executor for this scan.", 'info')
        except Exception as e:
            add_log(f"Failed to create executor for scan: {e}", 'error')
            return 0, len(unprocessed_files)

    # Submit all files for processing, skipping any already in-progress
    futures = {}
    skipped = 0
    for filepath in unprocessed_files:
        abs_filepath = os.path.abspath(filepath)
        abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
        is_from_ingest = abs_filepath.startswith(abs_ingest)
        
        # Prevent double-submission: check if this file is already queued by watchdog
        with _files_lock:
            if abs_filepath in _files_in_progress:
                logger.debug(f"Scan skipping {os.path.basename(filepath)} - already in progress (submitted by watchdog)")
                skipped += 1
                continue
            _files_in_progress.add(abs_filepath)
        
        future = executor.submit(processing.process_image_file, filepath, is_from_ingest)
        futures[future] = (filepath, abs_filepath)
    
    if skipped > 0:
        logger.info(f"Scan skipped {skipped} file(s) already being processed by watchdog")
        add_log(f"Skipped {skipped} file(s) already being processed", 'info')

    processed_count = 0
    from concurrent.futures import as_completed
    for future in as_completed(futures):
        filepath, abs_filepath = futures[future]
        try:
            result = future.result()
            # Handle 3-tuple (success, msg, failure_type) or 2-tuple (success, msg)
            if isinstance(result, tuple):
                if len(result) == 3:
                    success, msg, failure_type = result
                else:
                    success, msg = result
                    failure_type = "unknown"
            else:
                success = bool(result)
                msg = ""
                failure_type = "unknown"
            
            if success:
                processed_count += 1
                add_log(f"Successfully processed: {os.path.basename(filepath)}", 'success')
            elif failure_type == 'duplicate':
                monitor_status["total_skipped_duplicate"] += 1
                add_log(f"Skipped duplicate: {os.path.basename(filepath)}", 'warning')
            elif failure_type == 'race_condition':
                monitor_status["total_skipped_race"] += 1
                add_log(f"Skipped (already being processed): {os.path.basename(filepath)}", 'info')
            else:
                # Only log real errors
                monitor_status["total_failed"] += 1
                add_log(f"Failed to process {os.path.basename(filepath)}: {msg}", 'error')
        except Exception as e:
            add_log(f"Error processing {os.path.basename(filepath)}: {e}", 'error')
        finally:
            # Release from tracking set
            with _files_lock:
                _files_in_progress.discard(abs_filepath)

    if one_off_executor:
        try:
            one_off_executor.shutdown(wait=True)
        except Exception:
            pass

    # Note: We don't reload the cache here because the monitor runs in a
    # separate process from the web server. The web server handles its own
    # cache invalidation when images are added via API.

    return processed_count, len(unprocessed_files)

def monitor_loop():
    """The main loop for the background thread."""
    while monitor_status["running"]:
        add_log("Running periodic check...")
        monitor_status["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            processed_count, _ = run_scan()
            monitor_status["last_scan_found"] = processed_count
            monitor_status["total_processed"] += processed_count
        except Exception as e:
            add_log(f"An exception occurred during scan: {e}", 'error')

        # Wait for the next interval
        for _ in range(monitor_status["interval_seconds"]):
            if not monitor_status["running"]:
                break
            time.sleep(1)
    add_log("Monitor thread has stopped.")

# --- Control Functions ---

def start_monitor():
    """Starts the background monitoring thread with watchdog and ThreadPoolExecutor."""
    global monitor_thread, observer, ingest_executor
    import config

    if monitor_status["running"]:
        return False

    monitor_status["running"] = True
    
    # Initialize ThreadPoolExecutor (changed from ProcessPoolExecutor)
    try:
        max_workers = config.MAX_WORKERS
    except AttributeError:
        max_workers = 4 # Fallback if config is missing
        
    if max_workers <= 0:
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, cpu_count - 1)
        
    add_log(f"Starting ThreadPoolExecutor with {max_workers} workers...", 'info')

    # ThreadPoolExecutor doesn't need special initializer for semantic engine
    # since all threads share the same memory space
    ingest_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="IngestWorker")

    if monitor_status["mode"] == "watchdog":
        # Use watchdog for real-time filesystem monitoring
        try:
            event_handler = ImageFileHandler(watch_ingest=True)
            observer = Observer()
            observer.schedule(event_handler, "static/images", recursive=True)

            # Also watch ingest folder
            if os.path.exists(config.INGEST_DIRECTORY):
                observer.schedule(event_handler, config.INGEST_DIRECTORY, recursive=True)
                add_log(f"Watching ingest folder: {config.INGEST_DIRECTORY}")

            observer.start()
            add_log("Background monitor started (watchdog mode).")

            # Also do an initial scan
            monitor_thread = threading.Thread(target=initial_scan_then_idle, daemon=True)
            monitor_thread.start()
        except Exception as e:
            add_log(f"Failed to start watchdog: {e}. Falling back to polling.", 'error')
            monitor_status["mode"] = "polling"
            monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            monitor_thread.start()
    else:
        # Legacy polling mode
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

    return True

def initial_scan_then_idle():
    """Do an initial scan for existing files, then idle."""
    add_log("Running initial scan...")
    try:
        processed_count, _ = run_scan()
        monitor_status["last_scan_found"] = processed_count
        monitor_status["total_processed"] += processed_count
        add_log(f"Initial scan complete. Processed {processed_count} images.")
    except Exception as e:
        add_log(f"Error during initial scan: {e}", 'error')

    # Now just idle - the monitor doesn't need to maintain a cache
    # The web server handles its own cache in a separate process
    while monitor_status["running"]:
        time.sleep(1)

def stop_monitor():
    """
    Stops the background monitoring thread and executor with proper cleanup.
    
    Note: This function blocks until all active tasks complete. If tasks are stuck,
    the application may hang. In production, consider monitoring this with a watchdog.
    """
    global observer, ingest_executor

    if not monitor_status["running"]:
        return False
        
    # Handle external monitor stop
    if monitor_status.get("mode") == "external":
        try:
            if os.path.exists("monitor.pid"):
                with open("monitor.pid", "r") as f:
                    pid = int(f.read().strip())
                
                import psutil
                if psutil.pid_exists(pid):
                    os.kill(pid, 15) # SIGTERM
                    add_log("Sent stop signal to external monitor.")
                    monitor_status["running"] = False
                    return True
        except Exception as e:
            add_log(f"Error stopping external monitor: {e}", 'error')
            return False

    monitor_status["running"] = False
    add_log("Stopping background monitor...")

    # Stop watchdog observer first
    if observer:
        try:
            observer.stop()
            observer.join(timeout=5)
            add_log("Watchdog observer stopped.")
        except Exception as e:
            add_log(f"Error stopping observer: {e}", 'error')
        observer = None
    
    # Shutdown executor with proper wait
    if ingest_executor:
        add_log("Shutting down executor (waiting for active tasks)...")
        try:
            # Shutdown with wait=True to allow current tasks to complete
            # Note: This blocks until tasks finish. Tasks should be designed to complete quickly.
            # ThreadPoolExecutor.shutdown(timeout=...) requires Python 3.9+
            # For compatibility, we use wait=True without timeout parameter
            ingest_executor.shutdown(wait=True)
            add_log("Executor shutdown complete.")
        except Exception as e:
            add_log(f"Error stopping executor: {e}", 'error')
            # Try force shutdown on error
            try:
                ingest_executor.shutdown(wait=False)
            except Exception:
                pass
        ingest_executor = None

    return True
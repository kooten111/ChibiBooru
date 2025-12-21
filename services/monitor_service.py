# services/monitor_service.py
import threading
import time
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from database import models
from services import processing_service as processing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Shared Monitor State ---
monitor_thread = None
observer = None
ingest_executor = None  # Global ProcessPoolExecutor
monitor_status = {
    "running": False,
    "last_check": None,
    "last_scan_found": 0,
    "total_processed": 0,
    "interval_seconds": 300, # 5 minutes (fallback, not used with watchdog)
    "logs": [],
    "mode": "watchdog",  # "watchdog" for real-time or "polling" for legacy
    "pending_reload": False,
    "last_activity": 0
}

def get_status():
    """Return the current status of the monitor."""
    return monitor_status

def add_log(message, type='info'):
    """Adds a log entry to the monitor status."""
    log_entry = {'timestamp': time.strftime("%Y-%m-%d %H:%M:%S"), 'message': message, 'type': type}
    monitor_status['logs'].insert(0, log_entry)
    # Keep the log size manageable
    if len(monitor_status['logs']) > 100:
        monitor_status['logs'] = monitor_status['logs'][:100]

# --- Watchdog Event Handler ---

class ImageFileHandler(FileSystemEventHandler):
    """Handles filesystem events for new image files."""

    def __init__(self, watch_ingest=False):
        super().__init__()
        # self.processing_lock = threading.Lock() # No longer needed for parallel submission
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
        
    def handle_ingest_completion(self, future, is_from_ingest, filename):
        """Callback for when ingest analysis completes."""
        try:
            result = future.result()
            
            # Commit results in this thread (callback thread)
            success = processing.commit_image_ingest(result, move_from_ingest=is_from_ingest)
            
            if success:
                monitor_status["last_scan_found"] = 1
                monitor_status["total_processed"] += 1
                monitor_status["pending_reload"] = True
                monitor_status["last_activity"] = time.time()
                add_log(f"Successfully processed: {filename}", 'success')
            else:
                add_log(f"Skipped/Failed: {filename}", 'warning')
                
        except Exception as e:
            add_log(f"Error processing {filename}: {e}", 'error')

    def on_created(self, event):
        """Called when a file is created."""
        if event.is_directory:
            return

        filepath = event.src_path
        if not self.is_image_file(filepath):
            return

        if not self.should_process(filepath):
            return

        # Small delay to ensure file is fully written
        time.sleep(0.5)

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

        add_log(f"Detected {filename}, queuing for analysis...", 'info')
        
        # Submit to global executor
        if ingest_executor:
            future = ingest_executor.submit(processing.analyze_image_for_ingest, filepath)
            # Use partial to pass extra args to callback
            from functools import partial
            future.add_done_callback(partial(self.handle_ingest_completion, is_from_ingest=is_from_ingest, filename=filename))
        else:
            add_log("Executor not ready, skipping processing.", 'error')


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
    Also checks for MD5 duplicates and removes them automatically.
    """
    import hashlib
    from database import get_db_connection
    
    db_filepaths = models.get_all_filepaths()
    unprocessed_files = []
    duplicates_removed = 0

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
                                # This is a duplicate file - same content, different name
                                add_log(f"Auto-removing duplicate: {file} (same as {os.path.basename(row['filepath'])})", 'warning')
                                os.remove(filepath)
                                duplicates_removed += 1
                                continue
                    except Exception as e:
                        add_log(f"Error checking MD5 for {file}: {e}", 'error')
                    
                    unprocessed_files.append(filepath)

    # Check ingest directory (use helper function)
    unprocessed_files.extend(find_ingest_files())
    
    if duplicates_removed > 0:
        add_log(f"Cleaned up {duplicates_removed} duplicate file(s)", 'info')

    return unprocessed_files

def run_scan():
    """
    Finds and processes all new images using parallel workers.
    Returns the number of images processed.
    """
    import config
    
    unprocessed_files = find_unprocessed_images()
    if not unprocessed_files:
        add_log("No new images found.")
        return 0

    add_log(f"Found {len(unprocessed_files)} new images. Starting parallel analysis...", 'info')
    
    # Store futures to track batch completion
    futures = {}
    
    if not ingest_executor:
        add_log("Executor died? Restarting...", 'error')
        # Should not happen if start_monitor called
        return 0

    # Submit batches
    for f in unprocessed_files:
        future = ingest_executor.submit(processing.analyze_image_for_ingest, f)
        futures[future] = f

    processed_count = 0
    from concurrent.futures import as_completed
    
    for future in as_completed(futures):
        f = futures[future]
        try:
            result = future.result()
            
            # Determine logic for commit
            abs_filepath = os.path.abspath(f)
            abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
            is_from_ingest = abs_filepath.startswith(abs_ingest)
            
            if processing.commit_image_ingest(result, move_from_ingest=is_from_ingest):
                processed_count += 1
                add_log(f"Successfully processed: {os.path.basename(f)}", 'success')
            else:
                 add_log(f"Skipped/Duplicate: {os.path.basename(f)}", 'warning')
                 
        except Exception as e:
            add_log(f"Error processing {os.path.basename(f)}: {e}", 'error')

    # For bulk operations, full reload is acceptable
    if processed_count > 0:
        from core.cache_manager import load_data_from_db_async
        load_data_from_db_async()

    return processed_count

def monitor_loop():
    """The main loop for the background thread."""
    while monitor_status["running"]:
        add_log("Running periodic check...")
        monitor_status["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            processed_count = run_scan()
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
    """Starts the background monitoring thread with watchdog and parallel executor."""
    global monitor_thread, observer, ingest_executor
    import config
    from services import similarity_service # Needed for worker init

    if monitor_status["running"]:
        return False

    monitor_status["running"] = True
    
    # Initialize Executor
    try:
        max_workers = config.MAX_WORKERS
    except AttributeError:
        max_workers = 4 # Fallback if config is missing
        
    if max_workers <= 0:
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(1, cpu_count - 1)
        
    add_log(f"Starting Ingest Executor with {max_workers} workers...", 'info')

    # Use Semantic Init if available
    init_func = None
    if getattr(similarity_service, '_init_worker', None):
        init_func = similarity_service._init_worker
        
    ingest_executor = ProcessPoolExecutor(max_workers=max_workers, initializer=init_func)

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
        processed_count = run_scan()
        monitor_status["last_scan_found"] = processed_count
        monitor_status["total_processed"] += processed_count
        add_log(f"Initial scan complete. Processed {processed_count} images.")
    except Exception as e:
        add_log(f"Error during initial scan: {e}", 'error')

    # Now just idle
    while monitor_status["running"]:
        if monitor_status["pending_reload"]:
            if time.time() - monitor_status["last_activity"] > 2.0:
                try:
                    add_log("Reloading data after batch ingest...")
                    from core.cache_manager import load_data_from_db_async
                    load_data_from_db_async()
                    monitor_status["pending_reload"] = False
                    add_log("Data reload complete.", 'success')
                except Exception as e:
                    add_log(f"Error reloading data: {e}", 'error')
        
        time.sleep(1)

def stop_monitor():
    """Stops the background monitoring thread and executor."""
    global observer, ingest_executor

    if not monitor_status["running"]:
        return False

    monitor_status["running"] = False
    add_log("Stopping background monitor...")

    if observer:
        try:
            observer.stop()
            observer.join(timeout=2)
            add_log("Watchdog observer stopped.")
        except Exception as e:
            add_log(f"Error stopping observer: {e}", 'error')
        observer = None
        
    if ingest_executor:
        add_log("Shutting down executor...")
        try:
            ingest_executor.shutdown(wait=False)
            add_log("Executor shutdown.")
        except Exception as e:
             add_log(f"Error stopping executor: {e}", 'error')
        ingest_executor = None

    return True
# services/monitor_service.py
import threading
import time
import os
from database import models
from services import processing_service as processing
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Shared Monitor State ---
monitor_thread = None
observer = None
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
        self.processing_lock = threading.Lock()
        # Debounce: track recently processed files to avoid duplicates
        self.recently_processed = {}
        self.debounce_seconds = 2
        self.watch_ingest = watch_ingest

    def is_image_file(self, filepath):
        """Check if file is an image or video."""
        return filepath.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm'))

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

        with self.processing_lock:
            import config
            from utils.file_utils import get_bucketed_path

            # Normalize paths for comparison
            abs_filepath = os.path.abspath(filepath)
            abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)

            # Determine if this is from ingest folder
            is_from_ingest = self.watch_ingest and abs_filepath.startswith(abs_ingest)

            if is_from_ingest:
                # File from ingest - will be moved to bucketed structure
                filename = os.path.basename(filepath)
                try:
                    add_log(f"New file detected in ingest: {filename}", 'info')
                    if processing.process_image_file(filepath, move_from_ingest=True):
                        monitor_status["last_scan_found"] = 1
                        monitor_status["total_processed"] += 1
                        
                        # Mark for reload, but don't reload immediately to prevent UI hang
                        monitor_status["pending_reload"] = True
                        monitor_status["last_activity"] = time.time()
                        
                        add_log(f"Successfully processed from ingest: {filename}", 'success')
                    else:
                        add_log(f"Skipped (duplicate): {filename}", 'warning')
                except Exception as e:
                    add_log(f"Error processing {filename}: {e}", 'error')
            else:
                # File directly in images directory - already in bucketed location
                # Check if already in database
                rel_path = os.path.relpath(filepath, "static/images").replace('\\', '/')
                if rel_path in models.get_all_filepaths():
                    return

                try:
                    add_log(f"New file detected: {os.path.basename(filepath)}", 'info')
                    if processing.process_image_file(filepath, move_from_ingest=False):
                        monitor_status["last_scan_found"] = 1
                        monitor_status["total_processed"] += 1
                        
                        # Mark for reload
                        monitor_status["pending_reload"] = True
                        monitor_status["last_activity"] = time.time()
                        
                        add_log(f"Successfully processed: {os.path.basename(filepath)}", 'success')
                    else:
                        add_log(f"Skipped (duplicate): {os.path.basename(filepath)}", 'warning')
                except Exception as e:
                    add_log(f"Error processing {os.path.basename(filepath)}: {e}", 'error')

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
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')):
                    filepath = os.path.join(root, file)
                    ingest_files.append(filepath)
    return ingest_files

def find_unprocessed_images():
    """Finds image files on disk that are not in the database."""
    db_filepaths = models.get_all_filepaths()
    unprocessed_files = []

    # Check static/images directory
    for root, _, files in os.walk("static/images"):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.mp4', '.webm')):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, "static/images").replace('\\', '/')
                if rel_path not in db_filepaths:
                    unprocessed_files.append(filepath)

    # Check ingest directory (use helper function)
    unprocessed_files.extend(find_ingest_files())

    return unprocessed_files

def run_scan():
    """
    Finds and processes all new images.
    Returns the number of images processed.
    """
    import config
    from utils.file_utils import get_bucketed_path

    unprocessed_files = find_unprocessed_images()
    if not unprocessed_files:
        add_log("No new images found.")
        return 0

    add_log(f"Found {len(unprocessed_files)} new images to process.")
    processed_count = 0
    for f in unprocessed_files:
        # Determine if file is in ingest folder
        abs_filepath = os.path.abspath(f)
        abs_ingest = os.path.abspath(config.INGEST_DIRECTORY)
        is_from_ingest = abs_filepath.startswith(abs_ingest)

        try:
            if processing.process_image_file(f, move_from_ingest=is_from_ingest):
                processed_count += 1
                add_log(f"Successfully processed: {os.path.basename(f)}", 'success')
            else:
                add_log(f"Skipped (duplicate): {os.path.basename(f)}", 'warning')
        except Exception as e:
            add_log(f"Error processing {os.path.basename(f)}: {e}", 'error')

    # For bulk operations, full reload is acceptable
    if processed_count > 0:
        models.load_data_from_db()

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
    """Starts the background monitoring thread with watchdog."""
    global monitor_thread, observer
    import config

    if monitor_status["running"]:
        return False

    monitor_status["running"] = True

    if monitor_status["mode"] == "watchdog":
        # Use watchdog for real-time filesystem monitoring
        try:
            event_handler = ImageFileHandler(watch_ingest=True)
            observer = Observer()
            observer.schedule(event_handler, "static/images", recursive=True)

            # Also watch ingest folder if it exists (recursively to support folder structures)
            if os.path.exists(config.INGEST_DIRECTORY):
                observer.schedule(event_handler, config.INGEST_DIRECTORY, recursive=True)
                add_log(f"Watching ingest folder (recursively): {config.INGEST_DIRECTORY}")

            observer.start()
            add_log("Background monitor started (watchdog mode - real-time detection).")

            # Also do an initial scan to catch any existing unprocessed files
            monitor_thread = threading.Thread(target=initial_scan_then_idle, daemon=True)
            monitor_thread.start()
        except Exception as e:
            add_log(f"Failed to start watchdog: {e}. Falling back to polling mode.", 'error')
            monitor_status["mode"] = "polling"
            monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
            monitor_thread.start()
            add_log("Background monitor started (polling mode).")
    else:
        # Legacy polling mode
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        add_log("Background monitor started (polling mode).")

    return True

def initial_scan_then_idle():
    """Do an initial scan for existing files, then idle."""
    add_log("Running initial scan for existing unprocessed files...")
    try:
        processed_count = run_scan()
        monitor_status["last_scan_found"] = processed_count
        monitor_status["total_processed"] += processed_count
        add_log(f"Initial scan complete. Found {processed_count} unprocessed images.")
    except Exception as e:
        add_log(f"Error during initial scan: {e}", 'error')

    # Now just idle - watchdog will handle new files
    # Check for pending reloads periodically
    while monitor_status["running"]:
        if monitor_status["pending_reload"]:
            # Check if enough time has passed since last activity (debounce)
            if time.time() - monitor_status["last_activity"] > 2.0:
                try:
                    add_log("Reloading data after batch ingest...")
                    models.load_data_from_db()
                    monitor_status["pending_reload"] = False
                    add_log("Data reload complete.", 'success')
                except Exception as e:
                    add_log(f"Error reloading data: {e}", 'error')
        
        time.sleep(1)

def stop_monitor():
    """Stops the background monitoring thread."""
    global observer

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

    return True
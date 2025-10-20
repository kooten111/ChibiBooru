# services/monitor_service.py
import threading
import time
import os
import models
import processing

# --- Shared Monitor State ---
monitor_thread = None
monitor_status = {
    "running": False,
    "last_check": None,
    "last_scan_found": 0,
    "total_processed": 0,
    "interval_seconds": 300, # 5 minutes
    "logs": []
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

# --- Core Monitor Logic ---

def find_unprocessed_images():
    """Finds image files on disk that are not in the database."""
    db_filepaths = models.get_all_filepaths()
    disk_filepaths = []
    for root, _, files in os.walk("static/images"):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                disk_filepaths.append(os.path.join(root, file))

    unprocessed_files = [
        fp for fp in disk_filepaths
        if os.path.relpath(fp, "static/images").replace('\\', '/') not in db_filepaths
    ]
    return unprocessed_files

def run_scan():
    """
    Finds and processes all new images.
    Returns the number of images processed.
    """
    unprocessed_files = find_unprocessed_images()
    if not unprocessed_files:
        add_log("No new images found.")
        return 0
    
    add_log(f"Found {len(unprocessed_files)} new images to process.")
    processed_count = 0
    for f in unprocessed_files:
        try:
            if processing.process_image_file(f):
                processed_count += 1
                add_log(f"Successfully processed: {os.path.basename(f)}", 'success')
            else:
                add_log(f"Skipped (duplicate): {os.path.basename(f)}", 'warning')
        except Exception as e:
            add_log(f"Error processing {os.path.basename(f)}: {e}", 'error')

    if processed_count > 0:
        models.load_data_from_db() # Reload cache after processing
        
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
    """Starts the background monitoring thread."""
    global monitor_thread
    if not monitor_status["running"]:
        monitor_status["running"] = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        add_log("Background monitor started.")
        return True
    return False

def stop_monitor():
    """Stops the background monitoring thread."""
    if monitor_status["running"]:
        monitor_status["running"] = False
        add_log("Stopping background monitor...")
        return True
    return False
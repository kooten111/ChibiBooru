#!/usr/bin/env python3
import os
import time
import signal
import sys
import hashlib
import logging
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tag_watcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
IMAGE_DIRECTORY = "./static/images"
METADATA_DIR = "./metadata"
CHECK_INTERVAL = 300  # seconds (5 minutes)
LOCK_FILE = "./tag_watcher.lock"

# Global flag for graceful shutdown
running = True

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    running = False

def create_lock_file():
    """Create lock file to prevent multiple instances"""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
            logger.error(f"Lock file exists (PID: {pid}). Another instance may be running.")
            logger.error(f"If not, delete {LOCK_FILE} and try again.")
            return False
        except:
            pass
    
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    return True

def remove_lock_file():
    """Remove lock file on exit"""
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def get_md5(filepath):
    """Calculate MD5 hash of a file"""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def find_new_images():
    """Find images that don't have metadata yet"""
    if not os.path.isdir(IMAGE_DIRECTORY):
        logger.warning(f"Image directory not found: {IMAGE_DIRECTORY}")
        return []
    
    new_images = []
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
    
    for root, _, files in os.walk(IMAGE_DIRECTORY):
        for file in files:
            if not file.lower().endswith(image_extensions):
                continue
            
            filepath = os.path.join(root, file)
            
            try:
                md5 = get_md5(filepath)
                metadata_file = os.path.join(METADATA_DIR, f"{md5}.json")
                
                if not os.path.exists(metadata_file):
                    new_images.append(filepath)
            except Exception as e:
                logger.error(f"Error checking {filepath}: {e}")
    
    return new_images

def run_tag_finder():
    """Run the tag finder script"""
    logger.info("Running tag_finder_simple.py...")
    try:
        import tag_finder_simple
        tag_finder_simple.main()
        logger.info("Tag finder completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running tag finder: {e}", exc_info=True)
        return False

def run_rebuild():
    """Run the rebuild script"""
    logger.info("Running rebuild_tags_from_metadata.py...")
    try:
        import rebuild_tags_from_metadata
        rebuild_tags_from_metadata.rebuild_tags()
        logger.info("Rebuild completed successfully")
        return True
    except Exception as e:
        logger.error(f"Error running rebuild: {e}", exc_info=True)
        return False

def trigger_flask_reload():
    """Trigger Flask app to reload data via HTTP"""
    import requests
    
    flask_url = os.environ.get('FLASK_URL', 'http://localhost:5000')
    reload_secret = os.environ.get('RELOAD_SECRET', 'change-this-secret')
    
    try:
        response = requests.post(
            f"{flask_url}/api/reload",
            data={'secret': reload_secret},
            timeout=10
        )
        if response.status_code == 200:
            logger.info("Flask app reloaded successfully")
            return True
        else:
            logger.warning(f"Flask reload returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        logger.warning("Could not connect to Flask app (is it running?)")
        return False
    except Exception as e:
        logger.error(f"Error triggering Flask reload: {e}")
        return False

def main():
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create lock file
    if not create_lock_file():
        sys.exit(1)
    
    logger.info("Tag Watcher Daemon started")
    logger.info(f"Monitoring: {IMAGE_DIRECTORY}")
    logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
    logger.info(f"Press Ctrl+C to stop")
    
    try:
        while running:
            logger.info("Checking for new images...")
            new_images = find_new_images()
            
            if new_images:
                logger.info(f"Found {len(new_images)} new images")
                
                # Run tag finder to process new images
                if run_tag_finder():
                    logger.info("All new images processed")
                else:
                    logger.warning("Tag finder encountered errors")
            else:
                logger.info("No new images found")
            
            # Wait for next check
            logger.info(f"Next check in {CHECK_INTERVAL} seconds...")
            for _ in range(CHECK_INTERVAL):
                if not running:
                    break
                time.sleep(1)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    
    finally:
        remove_lock_file()
        logger.info("Tag Watcher Daemon stopped")

if __name__ == "__main__":
    main()
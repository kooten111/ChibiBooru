#!/usr/bin/env python3
"""
Monitor Runner - Standalone Process

This script runs the monitor service in a separate process from the web workers.
It ensures only one monitor runs regardless of how many uvicorn workers are active.

Features:
- Initializes database and loads data
- Starts the monitor service
- Handles graceful shutdown on SIGINT/SIGTERM
- Auto-shutdown when main app process dies (process coordination)
"""

import os
import sys
import time
import signal
import psutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

from database import initialize_database, repair_orphaned_image_tags
from database import models
from services.priority_service import check_and_apply_priority_changes
from services.health_service import startup_health_check
from utils.logging_config import setup_logging, get_logger
import config

# Global flag for graceful shutdown
shutdown_requested = False

# Initialize logger at module level for use in signal handlers
logger = None

def signal_handler(signum, frame):
    """Handle shutdown signals (SIGINT, SIGTERM)."""
    global shutdown_requested
    shutdown_requested = True
    # Use module-level logger with fallback
    if logger:
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    else:
        print(f"Received signal {signum}, initiating graceful shutdown...")

def is_main_app_running():
    """
    Check if the main uvicorn application is still running.
    
    Returns:
        bool: True if uvicorn process is found, False otherwise
    """
    try:
        # Look for uvicorn processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline and any('uvicorn' in arg for arg in cmdline):
                    # Make sure it's the app:create_app or app:app process
                    if any('app:' in arg for arg in cmdline):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    except Exception as e:
        # If we can't determine, assume it's running to avoid premature shutdown
        # Use basic logging in case get_logger fails
        try:
            logger = get_logger('MonitorRunner')
            logger.warning(f"Error checking for main app process: {e}")
        except Exception:
            import logging
            logging.warning(f"Error checking for main app process: {e}")
        return True

def main():
    """Main entry point for the monitor runner."""
    global shutdown_requested, logger
    
    # Initialize logging
    log_level = getattr(config, 'LOG_LEVEL', 'INFO')
    setup_logging(level=log_level)
    logger = get_logger('MonitorRunner')
    
    logger.info("=" * 60)
    logger.info("Starting ChibiBooru Monitor Runner (Standalone Process)")
    logger.info("=" * 60)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Check if monitor is enabled in config
    if not config.MONITOR_ENABLED:
        logger.warning("⚠ MONITOR_ENABLED is False in config - monitor will not start")
        logger.warning("⚠ Set MONITOR_ENABLED=True in config.py or .env to enable monitoring")
        return 0
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        initialize_database()
        
        # Auto-repair any orphaned image tags (data integrity check)
        logger.info("Running data integrity checks...")
        repair_orphaned_image_tags()
        
        # Run database health checks and auto-fix critical issues
        startup_health_check()
        
        # Check if BOORU_PRIORITY changed and auto-apply if needed
        logger.info("Checking for priority changes...")
        check_and_apply_priority_changes()
        
        # Load data from DB
        logger.info("Loading data from database...")
        models.load_data_from_db()
        
        # Start monitor service
        logger.info("Starting monitor service...")
        from services import monitor_service
        
        if monitor_service.start_monitor():
            logger.info("✓ Monitor service started successfully")
        else:
            logger.error("✗ Failed to start monitor service (may already be running)")
            return 1
        
        write_pid_file()
        logger.info("Monitor runner is now active")
        logger.info("Press Ctrl+C to stop, or kill the main app to auto-shutdown")
        
        # Main monitoring loop
        # Check periodically if main app is still running
        check_interval = 10  # Check every 10 seconds
        last_check = time.time()
        
        while not shutdown_requested:
            time.sleep(1)
            
            # Periodically check if main app is still running
            now = time.time()
            if now - last_check >= check_interval:
                last_check = now
                if not is_main_app_running():
                    logger.info("Main application process not detected - shutting down monitor")
                    shutdown_requested = True
                    break
        
        # Shutdown monitor service
        logger.info("Stopping monitor service...")
        from services import monitor_service
        if monitor_service.stop_monitor():
            logger.info("✓ Monitor service stopped successfully")
        else:
            logger.warning("⚠ Monitor service was not running")
        
        logger.info("Monitor runner shutdown complete")
        remove_pid_file()
        return 0
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        remove_pid_file()
        return 0
    except Exception as e:
        logger.error(f"Fatal error in monitor runner: {e}", exc_info=True)
        remove_pid_file()
        return 1

def write_pid_file():
    """Write the current PID to a file."""
    try:
        pid = os.getpid()
        with open("monitor.pid", "w") as f:
            f.write(str(pid))
    except Exception as e:
        if logger:
            logger.error(f"Failed to write PID file: {e}")
        else:
            print(f"Failed to write PID file: {e}")

def remove_pid_file():
    """Remove the PID file."""
    try:
        if os.path.exists("monitor.pid"):
            os.remove("monitor.pid")
    except Exception as e:
        if logger:
            logger.error(f"Failed to remove PID file: {e}")
        else:
            print(f"Failed to remove PID file: {e}")

if __name__ == '__main__':
    sys.exit(main())

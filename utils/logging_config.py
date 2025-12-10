"""
Centralized logging configuration.
All modules should use get_logger() instead of print().
"""

import logging
import sys
from typing import Optional

# Cache for logger instances
_loggers = {}

# Default format with emoji support
DEFAULT_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
SIMPLE_FORMAT = '[%(name)s] %(levelname)s: %(message)s'


def setup_logging(level: str = None, log_file: str = None):
    """
    Configure the root logger for the application.
    Call this once at application startup.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
    """
    # Default to INFO if not specified
    if level is None:
        level = 'INFO'

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger('chibibooru')
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    root_logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Logger name (usually module name like 'SauceNAO', 'Monitor', etc.)

    Returns:
        Configured logger instance

    Usage:
        logger = get_logger('SauceNAO')
        logger.info("Processing request...")
        logger.error(f"Failed: {e}")
    """
    if name not in _loggers:
        logger = logging.getLogger(f"chibibooru.{name}")
        _loggers[name] = logger

    return _loggers[name]

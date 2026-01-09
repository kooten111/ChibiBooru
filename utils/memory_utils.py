"""
Memory monitoring and cleanup utilities for multiprocessing operations.
"""

import gc
import os
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Try to import psutil, but handle gracefully if not available
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available - memory monitoring will be limited")


def get_memory_usage() -> Dict[str, float]:
    """
    Get current memory usage statistics.
    
    Returns:
        dict: Memory usage in MB with keys: 'rss', 'vms', 'percent'
    """
    if not PSUTIL_AVAILABLE:
        return {'rss_mb': 0.0, 'vms_mb': 0.0, 'percent': 0.0}
    
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        mem_percent = process.memory_percent()
        
        return {
            'rss_mb': mem_info.rss / (1024 * 1024),  # Resident Set Size
            'vms_mb': mem_info.vms / (1024 * 1024),  # Virtual Memory Size
            'percent': mem_percent
        }
    except Exception as e:
        logger.warning(f"Failed to get memory usage: {e}")
        return {'rss_mb': 0.0, 'vms_mb': 0.0, 'percent': 0.0}


def get_available_memory_mb() -> Optional[float]:
    """
    Get available system memory in MB.
    
    Returns:
        float or None: Available memory in MB, or None if unavailable
    """
    if not PSUTIL_AVAILABLE:
        return None
    
    try:
        mem = psutil.virtual_memory()
        return mem.available / (1024 * 1024)
    except Exception as e:
        logger.warning(f"Failed to get available memory: {e}")
        return None


def cleanup_memory(force_gc: bool = True) -> Dict[str, float]:
    """
    Force garbage collection and return memory usage after cleanup.
    
    Args:
        force_gc: If True, run gc.collect() multiple times
    
    Returns:
        dict: Memory usage after cleanup
    """
    before = get_memory_usage()
    
    if force_gc:
        # Run GC multiple times to handle circular references
        collected = 0
        for _ in range(3):
            collected += gc.collect()
        
        if collected > 0:
            logger.debug(f"Garbage collection freed {collected} objects")
    
    after = get_memory_usage()
    
    freed_mb = before['rss_mb'] - after['rss_mb']
    if freed_mb > 0:
        logger.debug(f"Memory cleanup freed {freed_mb:.2f} MB")
    
    return after


def estimate_batch_size(available_memory_mb: float, 
                        memory_per_image_mb: float = 0.5,
                        safety_factor: float = 0.7) -> int:
    """
    Estimate safe batch size based on available memory.
    
    Args:
        available_memory_mb: Available memory in MB
        memory_per_image_mb: Estimated memory per image (default: 0.5 MB)
        safety_factor: Safety factor to avoid OOM (default: 0.7 = use 70% of available)
    
    Returns:
        int: Recommended batch size
    """
    if available_memory_mb <= 0 or memory_per_image_mb <= 0:
        return 100  # Default safe batch size
    
    safe_memory = available_memory_mb * safety_factor
    batch_size = int(safe_memory / memory_per_image_mb)
    
    # Clamp to reasonable bounds
    batch_size = max(10, min(batch_size, 1000))
    
    return batch_size


def log_memory_usage(context: str = "") -> None:
    """
    Log current memory usage for debugging.
    
    Args:
        context: Optional context string for the log message
    """
    mem = get_memory_usage()
    available = get_available_memory_mb()
    
    msg = f"Memory usage {context}: RSS={mem['rss_mb']:.1f}MB, VMS={mem['vms_mb']:.1f}MB, {mem['percent']:.1f}%"
    if available:
        msg += f", Available={available:.1f}MB"
    
    logger.info(msg)

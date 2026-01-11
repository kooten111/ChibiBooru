"""
File-based locking for preventing concurrent processing of the same file.
"""

import os
import fcntl

# Lock directory for preventing concurrent processing of the same file across workers
LOCK_DIR = ".processing_locks"
os.makedirs(LOCK_DIR, exist_ok=True)


def acquire_processing_lock(md5):
    """
    Try to acquire a file-based lock for processing an image with the given MD5.
    Returns (lock_fd, acquired) where lock_fd is the file descriptor (or None) and acquired is a boolean.
    """
    lock_file = os.path.join(LOCK_DIR, f"{md5}.lock")
    try:
        fd = open(lock_file, 'w')
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return (fd, True)
    except (IOError, OSError):
        # Lock is held by another process
        if 'fd' in locals():
            fd.close()
        return (None, False)


def release_processing_lock(lock_fd):
    """Release a processing lock."""
    if lock_fd:
        try:
            lock_file = lock_fd.name
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
            os.remove(lock_file)
        except Exception as e:
            pass  # Lock cleanup failure is not critical

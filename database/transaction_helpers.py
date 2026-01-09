"""
Database transaction helpers for special connection requirements.

This module provides context managers and helpers for database operations
that require special connection settings (e.g., VACUUM, REINDEX).
"""

from contextlib import contextmanager
from typing import Generator
import sqlite3
from database.core import get_db_connection_direct


@contextmanager
def get_db_connection_autocommit() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections with autocommit mode (isolation_level=None).
    
    Required for operations like VACUUM and REINDEX that cannot run inside a transaction.
    
    Uses a direct (non-pooled) connection since maintenance operations need isolation
    and should not interfere with the connection pool.
    
    Usage:
        with get_db_connection_autocommit() as conn:
            conn.execute("VACUUM")
            conn.execute("REINDEX")
    
    Yields:
        sqlite3.Connection: Database connection with autocommit enabled
    """
    conn = get_db_connection_direct()
    original_isolation = conn.isolation_level
    conn.isolation_level = None  # Enable autocommit mode
    
    try:
        yield conn
    finally:
        conn.isolation_level = original_isolation
        conn.close()


@contextmanager
def get_db_connection_for_maintenance() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections configured for maintenance operations.
    
    Sets up connection with autocommit mode and optimizes PRAGMA settings
    for operations like VACUUM, REINDEX, and ANALYZE.
    
    Uses a direct (non-pooled) connection since maintenance operations need isolation
    and should not interfere with the connection pool.
    
    Usage:
        with get_db_connection_for_maintenance() as conn:
            conn.execute("PRAGMA auto_vacuum = FULL")
            conn.execute("VACUUM")
            conn.execute("REINDEX")
            conn.execute("ANALYZE")
    
    Yields:
        sqlite3.Connection: Database connection configured for maintenance
    """
    conn = get_db_connection_direct()
    original_isolation = conn.isolation_level
    conn.isolation_level = None  # Enable autocommit mode
    
    try:
        # Enable auto-vacuum to keep DB size in check
        conn.execute("PRAGMA auto_vacuum = FULL")
        yield conn
    finally:
        conn.isolation_level = original_isolation
        conn.close()

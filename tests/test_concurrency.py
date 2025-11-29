
import unittest
import sqlite3
import threading
import time
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import DB_FILE, get_db_connection

class TestConcurrency(unittest.TestCase):
    def setUp(self):
        # Ensure we are in WAL mode
        with get_db_connection() as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.lower() != 'wal':
                print(f"Warning: Database is in {mode} mode, not WAL.")

    def test_concurrent_read_write(self):
        print("\nTesting concurrent read/write...")
        
        stop_event = threading.Event()
        
        def writer_thread():
            # Continuously write to a dummy table
            conn = get_db_connection()
            conn.execute("CREATE TABLE IF NOT EXISTS test_concurrency (id INTEGER PRIMARY KEY, data TEXT)")
            while not stop_event.is_set():
                try:
                    conn.execute("INSERT INTO test_concurrency (data) VALUES (?)", (str(time.time()),))
                    conn.commit()
                    time.sleep(0.01) # Slight delay to avoid completely hogging CPU
                except Exception as e:
                    print(f"Writer error: {e}")
            conn.close()

        # Start writer
        t = threading.Thread(target=writer_thread)
        t.start()
        
        try:
            # Perform reads and measure time
            start_time = time.time()
            read_count = 0
            
            # Try to read 100 times
            for _ in range(100):
                with get_db_connection() as conn:
                    conn.execute("SELECT COUNT(*) FROM images").fetchone()
                read_count += 1
                
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"Performed {read_count} reads in {duration:.4f} seconds during heavy writes.")
            
            # In WAL mode, this should be very fast. 
            # In DELETE mode, this would be much slower due to locking.
            # 100 reads in < 1 second is a reasonable benchmark for WAL mode on local DB
            self.assertLess(duration, 2.0, "Reads took too long, potential locking issue.")
            
        finally:
            stop_event.set()
            t.join()
            
            # Cleanup
            with get_db_connection() as conn:
                conn.execute("DROP TABLE IF EXISTS test_concurrency")
                conn.commit()

if __name__ == '__main__':
    unittest.main()

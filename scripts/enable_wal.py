
import sqlite3
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import DB_FILE

def enable_wal():
    print(f"Enabling WAL mode for {DB_FILE}...")
    try:
        conn = sqlite3.connect(DB_FILE)
        # Check current mode
        current_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        print(f"Current journal mode: {current_mode}")
        
        if current_mode.lower() != 'wal':
            # Enable WAL
            new_mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            print(f"New journal mode: {new_mode}")
            
            if new_mode.lower() == 'wal':
                print("Successfully enabled WAL mode.")
            else:
                print("Failed to enable WAL mode.")
        else:
            print("WAL mode is already enabled.")
            
        conn.close()
    except Exception as e:
        print(f"Error enabling WAL mode: {e}")

if __name__ == "__main__":
    enable_wal()


import sys
import os

# Add project root to path
sys.path.insert(0, '/mnt/Server/ChibiBooru')

from database import get_db_connection
from repositories.rating_repository import get_model_db_connection

def check_config():
    print("Checking Rating Model Config...")
    try:
        with get_model_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM rating_inference_config")
            rows = cur.fetchall()
            print("\nConfiguration:")
            for row in rows:
                print(f"  {row['key']}: {row['value']} (type: {type(row['value'])})")
                
            cur.execute("SELECT COUNT(*) FROM rating_tag_pair_weights")
            count = cur.fetchone()[0]
            print(f"\nExisting Pair Weights: {count}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    check_config()

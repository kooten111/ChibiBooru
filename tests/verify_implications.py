
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_backend():
    session = requests.Session()
    
    # 1. Test Suggestions Filtering
    print("Testing Suggestions Filtering...")
    try:
        resp = session.get(f"{BASE_URL}/api/implications/suggestions?q=test")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Suggestions search 'test': Found {len(data.get('suggestions', []))} items")
        else:
            print(f"FAILED: Suggestions search 'test' - Status {resp.status_code}")
    except Exception as e:
        print(f"FAILED: Suggestions search - {e}")

    # 2. Test Get All Implications
    print("\nTesting Get All Implications...")
    try:
        resp = session.get(f"{BASE_URL}/api/implications/all")
        if resp.status_code == 200:
            data = resp.json()
            initial_count = len(data.get('implications', []))
            print(f"Initial active implications: {initial_count}")
        else:
            print(f"FAILED: Get All Implications - Status {resp.status_code}")
            return
    except Exception as e:
        print(f"FAILED: Get All Implications - {e}")
        return

    # 3. Create a dummy implication
    print("\nCreating dummy implication...")
    dummy = {
        "source_tag": "test_source_verify",
        "implied_tag": "test_implied_verify"
    }
    try:
        resp = session.post(f"{BASE_URL}/api/implications/create", json=dummy)
        if resp.status_code == 200:
            print("Dummy implication created.")
        elif resp.status_code == 400:
            print("Dummy implication creation failed (tags might not exist). Skipping creation.")
        else:
            print(f"FAILED: Create dummy implication - Status {resp.status_code}")
    except Exception as e:
        print(f"FAILED: Create dummy implication - {e}")

    # 4. Verify count increased
    try:
        resp = session.get(f"{BASE_URL}/api/implications/all")
        data = resp.json()
        new_count = len(data.get('implications', []))
        print(f"Active implications after creation: {new_count}")
    except Exception as e:
        print(f"FAILED: Verify count - {e}")

if __name__ == "__main__":
    test_backend()

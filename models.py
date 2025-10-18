import threading
import json
import os

# Global data structures
raw_data = {}
tag_counts = {}
id_to_path = {}
image_data = []
data_lock = threading.Lock()

def load_data():
    """Load or reload tags.json data"""
    global raw_data, tag_counts, id_to_path, image_data

    with data_lock:
        raw_data = {}
        tag_counts = {}
        id_to_path = {}
        image_data = []

        try:
            with open('tags.json', 'r') as f:
                raw_data = json.load(f)

                for path, data in raw_data.items():
                    if data == "not_found":
                        continue

                    if isinstance(data, str):
                        tags = data
                        post_id = None
                        sources = []
                    else:
                        tags = data.get("tags", "")
                        post_id = data.get("id")
                        sources = data.get("sources", [])

                        if post_id:
                            id_to_path[post_id] = path

                    image_data.append({"path": f"images/{path}", "tags": tags, "sources": sources})

                    for tag in tags.split():
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1

            print(f"Loaded {len(raw_data)} images, {len(tag_counts)} unique tags")
            return True
        except FileNotFoundError:
            print("Error: tags.json not found!")
            return False
        except Exception as e:
            print(f"Error loading data: {e}")
            return False

def get_raw_data():
    with data_lock:
        return raw_data

def get_tag_counts():
    with data_lock:
        return tag_counts

def get_id_to_path():
    with data_lock:
        return id_to_path

def get_image_data():
    with data_lock:
        return image_data
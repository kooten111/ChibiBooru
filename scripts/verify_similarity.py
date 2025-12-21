
import asyncio
import os
import sys
sys.path.append('/mnt/Server/ChibiBooru')
from services import similarity_service, similarity_db
from database import get_db_connection

# Force enable semantic
similarity_service.SEMANTIC_AVAILABLE = True

def verify():
    print("Verifying Semantic Similarity...")
    
    # 1. Check DB
    with get_db_connection() as conn:
        row = conn.execute("SELECT filepath, id FROM images LIMIT 1").fetchone()
        if not row:
            print("No images in DB to test.")
            return

        filepath = row['filepath']
        image_id = row['id']
        print(f"Testing with image: {filepath} (ID: {image_id})")

    # 2. Check Embedding Generation
    full_path = os.path.join("static/images", filepath)
    if not os.path.exists(full_path):
        print(f"File not found: {full_path}")
        return

    print("Generating embedding...")
    engine = similarity_service.get_semantic_engine()
    embedding = engine.get_embedding(full_path)
    
    if embedding is None:
        print("FAIL: Embedding generation returned None")
        return
    else:
        print(f"PASS: Generated embedding with shape {embedding.shape}")

    # 3. Check Storage
    print("Saving to DB...")
    similarity_db.save_embedding(image_id, embedding)
    
    stored = similarity_db.get_embedding(image_id)
    if stored is None:
        print("FAIL: Embedding not retrieved from DB")
    else:
        print("PASS: Embedding retrieved from DB")

    # 4. Check Search
    print("Running Search...")
    results = similarity_service.find_semantic_similar(filepath)
    print(f"Found {len(results)} results.")
    for r in results[:5]:
        print(f" - {r['path']}: {r['score']:.4f}")

    if len(results) > 0:
        if results[0]['path'] == f"images/{filepath}":
            print("PASS: Top result is the image itself (expected)")
        else:
            print("WARN: Top result is NOT the image itself (might be issue or just close match)")

if __name__ == "__main__":
    verify()

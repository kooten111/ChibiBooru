#!/usr/bin/env python3
"""
Check Score Spread - Diagnose if scores are too clustered

If all images score similarly high with each other, it means:
1. The embedding space might be too uniform
2. Results feel "random" because everything is equally similar

Usage:
    cd /mnt/Server/ChibiBooru
    source venv/bin/activate
    python scripts/check_score_spread.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import random
from database import get_db_connection
from services import similarity_db, similarity_service


def check_spread():
    print("="*60)
    print("SCORE SPREAD ANALYSIS")
    print("="*60)
    
    # Get some random images
    embedded_ids = similarity_db.get_all_embedding_ids()
    sample_ids = random.sample(embedded_ids, min(20, len(embedded_ids)))
    
    print(f"\nTesting {len(sample_ids)} random images...")
    
    # Get filepaths
    images = []
    with get_db_connection() as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(sample_ids))
        cursor.execute(f"SELECT id, filepath FROM images WHERE id IN ({placeholders})", sample_ids)
        images = [dict(row) for row in cursor.fetchall()]
    
    if not images:
        print("No images found!")
        return
    
    # For each image, check the RANGE of scores it gets
    print("\nPer-image score analysis (excluding self):")
    print("-" * 60)
    
    ranges = []
    all_top1 = []
    all_bottom = []
    
    for img in images[:10]:
        results = similarity_service.find_semantic_similar(img['filepath'], limit=50)
        # Exclude self
        results = [r for r in results if r['path'] != f"images/{img['filepath']}"]
        
        if len(results) < 10:
            continue
        
        scores = [r['score'] for r in results]
        top_score = max(scores)
        bottom_score = min(scores)
        score_range = top_score - bottom_score
        
        ranges.append(score_range)
        all_top1.append(top_score)
        all_bottom.append(bottom_score)
        
        print(f"  ID {img['id']:6d}: top={top_score:.4f}, bottom={bottom_score:.4f}, range={score_range:.4f}")
    
    print("-" * 60)
    
    if ranges:
        avg_range = sum(ranges) / len(ranges)
        avg_top = sum(all_top1) / len(all_top1)
        avg_bottom = sum(all_bottom) / len(all_bottom)
        
        print(f"\nAggregates:")
        print(f"  Average score range: {avg_range:.4f}")
        print(f"  Average top-1 score: {avg_top:.4f}")
        print(f"  Average bottom (of 50): {avg_bottom:.4f}")
        
        # Check for problematic patterns
        print("\nAnalysis:")
        
        if avg_range < 0.05:
            print("  ⚠ WARNING: Score range is VERY narrow!")
            print("    All images score similarly - results may feel random.")
            print("    This could indicate:")
            print("    - Embeddings are too similar to each other")
            print("    - The model may not be discriminative enough")
        elif avg_range < 0.1:
            print("  ⚠ Moderate concern: Score range is narrow.")
            print("    Top results may not be much better than random.")
        else:
            print("  ✓ Score range looks healthy.")
            print("    Good differentiation between similar/dissimilar images.")
        
        if avg_top > 0.95:
            print(f"\n  ℹ Very high top scores ({avg_top:.4f}).")
            print("    This is normal if your dataset has many similar images")
            print("    (e.g., same character, same artist, variants).")
        
        if avg_bottom > 0.9:
            print(f"\n  ⚠ Very high bottom scores ({avg_bottom:.4f}).")
            print("    Even 'dissimilar' images score high.")
            print("    This could make results feel undifferentiated.")
    
    # Cross-image similarity test
    print("\n" + "="*60)
    print("CROSS-IMAGE SIMILARITY TEST")
    print("="*60)
    print("Comparing random pairs of images that should NOT be similar...")
    
    # Get embeddings for random pairs
    if len(sample_ids) >= 10:
        cross_scores = []
        semantic_index = similarity_service.get_semantic_index()
        
        for i in range(min(20, len(sample_ids) - 1)):
            id1 = sample_ids[i]
            id2 = sample_ids[(i + 5) % len(sample_ids)]  # Some offset
            
            if id1 == id2:
                continue
            
            emb1 = similarity_db.get_embedding(id1)
            emb2 = similarity_db.get_embedding(id2)
            
            if emb1 is not None and emb2 is not None:
                # Normalize and compute cosine similarity
                emb1_norm = emb1 / np.linalg.norm(emb1)
                emb2_norm = emb2 / np.linalg.norm(emb2)
                score = float(np.dot(emb1_norm, emb2_norm))
                cross_scores.append(score)
        
        if cross_scores:
            print(f"\n  Random pair similarity stats:")
            print(f"    Mean: {sum(cross_scores)/len(cross_scores):.4f}")
            print(f"    Min: {min(cross_scores):.4f}")
            print(f"    Max: {max(cross_scores):.4f}")
            
            if sum(cross_scores)/len(cross_scores) > 0.85:
                print("\n  ⚠ WARNING: Random pairs are scoring very high!")
                print("    This suggests the embedding space is not discriminative.")
            else:
                print("\n  ✓ Random pairs have reasonable scores.")


if __name__ == '__main__':
    check_spread()

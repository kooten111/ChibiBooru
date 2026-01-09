#!/usr/bin/env python3
"""
Test script to understand database size and structure for multiprocessing optimization.
This script will help us understand:
1. How many weights are in the database
2. Estimated memory usage
3. Database query patterns
"""

import sqlite3
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def get_db_size_mb(db_path):
    """Get database file size in MB."""
    if not os.path.exists(db_path):
        return 0
    return os.path.getsize(db_path) / (1024 * 1024)

def count_weights(conn, table_name, join_clause=""):
    """Count weights in a table."""
    cur = conn.cursor()
    query = f"SELECT COUNT(*) as cnt FROM {table_name} {join_clause}"
    cur.execute(query)
    return cur.fetchone()['cnt']

def estimate_memory_usage(tag_weights_count, pair_weights_count):
    """Estimate memory usage for weights dictionaries."""
    # Rough estimate: each dict entry is ~100-200 bytes
    # (tag, character/rating): weight = ~150 bytes average
    tag_memory_mb = (tag_weights_count * 150) / (1024 * 1024)
    pair_memory_mb = (pair_weights_count * 200) / (1024 * 1024)  # Pairs are larger
    return tag_memory_mb + pair_memory_mb

def analyze_rating_model():
    """Analyze rating model database."""
    print("\n" + "=" * 60)
    print("RATING MODEL DATABASE ANALYSIS")
    print("=" * 60)
    
    try:
        from repositories.rating_repository import get_model_db_path
        db_path = get_model_db_path()
    except:
        db_path = os.path.join(project_root, "rating_model.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    db_size = get_db_size_mb(db_path)
    print(f"\nDatabase file: {db_path}")
    print(f"File size: {db_size:.2f} MB")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Count tag weights
    tag_weights_count = count_weights(conn, "rating_tag_weights")
    print(f"\nTag weights: {tag_weights_count:,}")
    
    # Count pair weights
    pair_weights_count = count_weights(conn, "rating_tag_pair_weights")
    print(f"Pair weights: {pair_weights_count:,}")
    
    # Count unique tags
    cur.execute("SELECT COUNT(DISTINCT tag_id) as cnt FROM rating_tag_weights")
    unique_tags = cur.fetchone()['cnt']
    print(f"Unique tags: {unique_tags:,}")
    
    # Count unique ratings (should be 4)
    cur.execute("SELECT COUNT(DISTINCT rating_id) as cnt FROM rating_tag_weights")
    unique_ratings = cur.fetchone()['cnt']
    print(f"Unique ratings: {unique_ratings:,}")
    
    # Estimate memory usage
    estimated_memory = estimate_memory_usage(tag_weights_count, pair_weights_count)
    print(f"\nEstimated memory usage (all weights in dict): {estimated_memory:.2f} MB")
    
    # Sample a few weights
    cur.execute("""
        SELECT t.name as tag, r.name as rating, tw.weight
        FROM rating_tag_weights tw
        JOIN tags t ON tw.tag_id = t.id
        JOIN ratings r ON tw.rating_id = r.id
        LIMIT 5
    """)
    print("\nSample tag weights:")
    for row in cur.fetchall():
        print(f"  ({row['tag']}, {row['rating']}): {row['weight']:.3f}")
    
    conn.close()

def analyze_main_db():
    """Analyze main database for image counts."""
    print("\n" + "=" * 60)
    print("MAIN DATABASE ANALYSIS")
    print("=" * 60)
    
    try:
        from database import get_db_connection
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # Count total images
            cur.execute("SELECT COUNT(*) as cnt FROM images")
            total_images = cur.fetchone()['cnt']
            print(f"\nTotal images: {total_images:,}")
            
            # Count unrated images
            from services.rating_service import RATINGS
            placeholders = ','.join('?' * len(RATINGS))
            cur.execute(f"""
                SELECT COUNT(*) as cnt
                FROM images i
                WHERE NOT EXISTS (
                    SELECT 1 FROM image_tags it
                    JOIN tags t ON it.tag_id = t.id
                    WHERE it.image_id = i.id
                      AND t.name IN ({placeholders})
                )
            """, RATINGS)
            unrated_count = cur.fetchone()['cnt']
            print(f"Unrated images: {unrated_count:,}")
            
            # Average tags per image
            cur.execute("""
                SELECT AVG(tag_count) as avg_tags
                FROM (
                    SELECT image_id, COUNT(*) as tag_count
                    FROM image_tags
                    GROUP BY image_id
                )
            """)
            avg_tags = cur.fetchone()['avg_tags'] or 0
            print(f"Average tags per image: {avg_tags:.1f}")
            
    except Exception as e:
        print(f"Error analyzing main DB: {e}")

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("DATABASE SIZE AND STRUCTURE ANALYSIS")
    print("=" * 60)
    print("\nThis script analyzes the database to understand:")
    print("1. Model weight counts and estimated memory usage")
    print("2. Database file sizes")
    print("3. Image counts for processing")
    print("\n")
    
    analyze_rating_model()
    analyze_main_db()
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print("\nRecommendations:")
    print("1. If estimated memory > 500MB, use lazy loading/querying")
    print("2. For multiprocessing, share weights via shared memory or file-backed")
    print("3. Use batched queries instead of loading all weights")
    print("4. Consider SQLite WAL mode for better concurrent access")
    print()

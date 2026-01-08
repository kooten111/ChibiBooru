#!/usr/bin/env python3
"""
Memory profiling script to identify what's using RAM in ChibiBooru
"""
import sys
import gc
from database import get_db_connection

def get_size_mb(obj):
    """Get approximate size of object in MB"""
    return sys.getsizeof(obj) / 1024 / 1024

def profile_cache_manager():
    """Profile cache_manager memory usage"""
    print("\n=== Cache Manager Memory Profile ===")

    from core import cache_manager

    # Force garbage collection
    gc.collect()

    print(f"tag_counts entries: {len(cache_manager.tag_counts)}")
    print(f"tag_counts size: {get_size_mb(cache_manager.tag_counts):.2f} MB")

    print(f"\nimage_data entries: {len(cache_manager.image_data)}")
    print(f"image_data size: {get_size_mb(cache_manager.image_data):.2f} MB")

    # Sample an image_data entry
    if cache_manager.image_data:
        sample = cache_manager.image_data[0]
        print(f"Sample image_data entry: {list(sample.keys())}")
        if 'tag_ids' in sample:
            print(f"  tag_ids type: {type(sample['tag_ids'])}, length: {len(sample['tag_ids'])}")

    print(f"\npost_id_to_md5 entries: {len(cache_manager.post_id_to_md5)}")
    print(f"post_id_to_md5 size: {get_size_mb(cache_manager.post_id_to_md5):.2f} MB")

def profile_tag_id_cache():
    """Profile tag ID cache memory usage"""
    print("\n=== Tag ID Cache Memory Profile ===")

    from core.tag_id_cache import get_tag_id_cache
    cache = get_tag_id_cache()

    print(f"name_to_id entries: {len(cache.name_to_id)}")
    print(f"name_to_id size: {get_size_mb(cache.name_to_id):.2f} MB")

    print(f"id_to_name entries: {len(cache.id_to_name)}")
    print(f"id_to_name size: {get_size_mb(cache.id_to_name):.2f} MB")

def profile_database():
    """Profile database content"""
    print("\n=== Database Content Profile ===")

    with get_db_connection() as conn:
        # Count records
        image_count = conn.execute("SELECT COUNT(*) as count FROM images").fetchone()['count']
        tag_count = conn.execute("SELECT COUNT(*) as count FROM tags").fetchone()['count']
        tag_assoc_count = conn.execute("SELECT COUNT(*) as count FROM image_tags").fetchone()['count']

        print(f"Images: {image_count:,}")
        print(f"Tags: {tag_count:,}")
        print(f"Tag associations: {tag_assoc_count:,}")
        print(f"Avg tags per image: {tag_assoc_count / image_count:.1f}")

        # Check raw_metadata size
        metadata_count = conn.execute("SELECT COUNT(*) as count FROM raw_metadata WHERE data IS NOT NULL").fetchone()['count']
        avg_metadata_size = conn.execute("""
            SELECT AVG(LENGTH(data)) as avg_size
            FROM raw_metadata
            WHERE data IS NOT NULL
        """).fetchone()['avg_size']

        print(f"\nRaw metadata entries: {metadata_count:,}")
        if avg_metadata_size:
            print(f"Avg metadata size: {avg_metadata_size / 1024:.1f} KB")
            total_metadata_mb = (metadata_count * avg_metadata_size) / 1024 / 1024
            print(f"Total metadata in DB: {total_metadata_mb:.1f} MB")

def check_imports():
    """Check what large modules are loaded"""
    print("\n=== Loaded Modules ===")

    large_modules = ['numpy', 'torch', 'tensorflow', 'transformers', 'faiss', 'onnxruntime', 'PIL']

    for module_name in large_modules:
        if module_name in sys.modules:
            print(f"✓ {module_name} is loaded")
        else:
            print(f"✗ {module_name} not loaded")

def main():
    print("ChibiBooru Memory Profile")
    print("=" * 50)

    try:
        check_imports()
        profile_database()
        profile_cache_manager()
        profile_tag_id_cache()

        print("\n" + "=" * 50)
        print("Note: sys.getsizeof() shows shallow size only.")
        print("Actual memory usage includes:")
        print("  - Python interpreter overhead")
        print("  - Import overhead (libraries like Flask, numpy, PIL)")
        print("  - Deep object structures (nested dicts, lists)")
        print("  - String interning deduplication not reflected")

    except Exception as e:
        print(f"\nError during profiling: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Memory usage comparison: Tag IDs vs Tag Strings

Measures memory savings from using int32 arrays instead of string objects
for tag storage in the in-memory cache.
"""

import sys
import os
import gc

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def get_memory_usage():
    """Get current memory usage in MB"""
    import psutil
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024  # Convert to MB

def measure_cache_memory(use_tag_ids=True):
    """Measure memory usage with tag IDs or tag strings"""

    # Force reimport with modified config
    import importlib
    if 'config' in sys.modules:
        del sys.modules['config']
    if 'core.cache_manager' in sys.modules:
        del sys.modules['core.cache_manager']
    if 'core.tag_id_cache' in sys.modules:
        del sys.modules['core.tag_id_cache']

    # Set environment variable
    os.environ['TAG_ID_CACHE_ENABLED'] = 'true' if use_tag_ids else 'false'

    import config
    config.TAG_ID_CACHE_ENABLED = use_tag_ids

    # Force garbage collection before measurement
    gc.collect()
    gc.collect()
    gc.collect()

    memory_before = get_memory_usage()

    # Load cache
    from core.cache_manager import load_data_from_db, get_image_data, get_tag_counts
    print(f"\n{'=' * 70}")
    print(f"Testing with TAG_ID_CACHE_ENABLED = {use_tag_ids}")
    print(f"{'=' * 70}")
    print(f"Memory before loading: {memory_before:.2f} MB")

    load_data_from_db()

    # Force garbage collection after loading
    gc.collect()
    gc.collect()
    gc.collect()

    memory_after = get_memory_usage()

    # Get cache statistics
    image_data = get_image_data()
    tag_counts = get_tag_counts()

    print(f"Memory after loading: {memory_after:.2f} MB")
    print(f"Memory used by cache: {memory_after - memory_before:.2f} MB")
    print(f"\nCache statistics:")
    print(f"  Images loaded: {len(image_data)}")
    print(f"  Unique tags: {len(tag_counts)}")

    # Sample first image to show storage format
    if image_data:
        sample = image_data[0]
        print(f"\nSample image: {sample['filepath']}")

        if use_tag_ids and 'tag_ids' in sample:
            from array import array
            tag_ids = sample['tag_ids']
            print(f"  Storage format: int32 array")
            print(f"  Number of tags: {len(tag_ids)}")
            print(f"  Array size: {len(tag_ids) * 4} bytes")
            print(f"  Sample IDs: {list(tag_ids)[:10]}")
        elif 'tags' in sample:
            tags_str = sample['tags']
            print(f"  Storage format: string")
            print(f"  Number of tags: {len(tags_str.split())}")
            print(f"  String size: {len(tags_str)} chars")
            print(f"  First 100 chars: {tags_str[:100]}...")

    return memory_after - memory_before

def main():
    """Run memory comparison"""

    print("=" * 70)
    print("Memory Savings Test: Tag IDs vs Tag Strings")
    print("=" * 70)
    print("\nThis test measures memory usage with two configurations:")
    print("1. TAG_ID_CACHE_ENABLED=false (string storage)")
    print("2. TAG_ID_CACHE_ENABLED=true (int32 array storage)")

    try:
        import psutil
    except ImportError:
        print("\n⚠️  Error: psutil not installed")
        print("Install with: pip install psutil")
        return

    # Measure with strings
    print("\n" + "=" * 70)
    print("Phase 1: Measuring with TAG STRING storage")
    print("=" * 70)
    memory_strings = measure_cache_memory(use_tag_ids=False)

    # Clear memory
    print("\n\nClearing memory...")
    if 'core.cache_manager' in sys.modules:
        del sys.modules['core.cache_manager']
    if 'core.tag_id_cache' in sys.modules:
        del sys.modules['core.tag_id_cache']
    gc.collect()
    gc.collect()
    gc.collect()

    import time
    time.sleep(2)

    # Measure with IDs
    print("\n" + "=" * 70)
    print("Phase 2: Measuring with TAG ID storage")
    print("=" * 70)
    memory_ids = measure_cache_memory(use_tag_ids=True)

    # Results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nMemory used with STRINGS: {memory_strings:.2f} MB")
    print(f"Memory used with IDs:     {memory_ids:.2f} MB")
    print(f"\nSavings:                  {memory_strings - memory_ids:.2f} MB")
    print(f"Reduction:                {((memory_strings - memory_ids) / memory_strings * 100):.1f}%")

    print("\n" + "=" * 70)
    print("Note: Memory measurements include Python overhead and may vary")
    print("between runs. The savings come from:")
    print("- Using 4-byte int32 IDs instead of 50+ byte string objects")
    print("- Reduced GC pressure from fewer temporary objects")
    print("- More efficient set operations (int comparison vs string)")
    print("=" * 70)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Script to retroactively apply merged sources to all images with multiple sources.

This script will:
- Find all images with multiple booru sources (excluding AI taggers)
- Merge tags from all sources for those images
- Set their active_source to 'merged'
- Update the database with merged tags

Run this after enabling USE_MERGED_SOURCES_BY_DEFAULT in config.yml
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.system.rebuild import run_apply_merged_sources
import config

def main():
    print("=" * 70)
    print("ChibiBooru - Retroactive Merged Sources Application")
    print("=" * 70)
    
    if not config.USE_MERGED_SOURCES_BY_DEFAULT:
        print("\n⚠️  WARNING: USE_MERGED_SOURCES_BY_DEFAULT is set to False")
        print("   This script will only apply merging if it's enabled.")
        print("   Set it to True in config.yml first.\n")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return 1
    else:
        print("\n✓ USE_MERGED_SOURCES_BY_DEFAULT is True")
        print("  All images with multiple booru sources will be merged.\n")
    
    print("Starting retroactive merge application...")
    print("This may take several minutes depending on image count.\n")
    
    try:
        result = run_apply_merged_sources()
        
        print("\n" + "=" * 70)
        print(f"Status: {result.get('status', 'unknown').upper()}")
        print(f"Message: {result.get('message', '')}")
        print(f"Processed: {result.get('processed', 0)}")
        print(f"Errors: {result.get('errors', 0)}")
        print(f"Total: {result.get('total', 0)}")
        print("=" * 70)
        
        return 0 if result.get('status') == 'success' else 1
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

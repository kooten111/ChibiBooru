#!/usr/bin/env python3
"""
Process all files currently in the ingest folder.

This script is useful when:
- Files were added to ingest before the monitor was started
- You want to manually trigger processing of ingest files
- The monitor is not running but you want to process files

Usage:
    python scripts/process_ingest_folder.py
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import monitor_service
import config

def main():
    print("=" * 70)
    print("Ingest Folder Processing Script")
    print("=" * 70)
    print(f"Ingest directory: {config.INGEST_DIRECTORY}\n")

    # Check if ingest folder exists
    if not os.path.exists(config.INGEST_DIRECTORY):
        print(f"Ingest folder not found: {config.INGEST_DIRECTORY}")
        return

    # Find all files in ingest (use helper function)
    ingest_files = monitor_service.find_ingest_files()

    if not ingest_files:
        print("✓ No files in ingest folder. All clear!")
        return

    print(f"Found {len(ingest_files)} files to process:")
    for f in ingest_files[:10]:
        # Show relative path from ingest directory for better readability
        rel_path = os.path.relpath(f, config.INGEST_DIRECTORY)
        print(f"  - {rel_path}")
    if len(ingest_files) > 10:
        print(f"  ... and {len(ingest_files) - 10} more")

    print("\nStarting processing...")
    print("-" * 70)

    # Run the scan
    count = monitor_service.run_scan()

    print("-" * 70)
    print(f"\n✓ Processed {count} files")

    # Check if anything is left (use helper function)
    remaining = monitor_service.find_ingest_files()

    if remaining:
        print(f"\n⚠ {len(remaining)} files still in ingest (likely duplicates)")
    else:
        print("\n✓ Ingest folder is now empty")

    # Show recent logs
    print("\nRecent processing logs:")
    status = monitor_service.get_status()
    for log in status['logs'][:15]:
        emoji = {"info": "ℹ️", "success": "✓", "warning": "⚠", "error": "✗"}.get(log['type'], "•")
        print(f"  {emoji} {log['message']}")


if __name__ == '__main__':
    main()

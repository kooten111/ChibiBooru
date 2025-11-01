#!/usr/bin/env python3
"""Test script to run a manual scan"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import monitor_service

print("Running manual scan...")
count = monitor_service.run_scan()
print(f"\nProcessed {count} files")

# Show recent logs
status = monitor_service.get_status()
print("\nRecent logs:")
for log in status['logs'][:10]:
    print(f"  [{log['timestamp']}] {log['type']}: {log['message']}")

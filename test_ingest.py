#!/usr/bin/env python3
"""Test script to verify ingest folder functionality"""
import os
import sys
import shutil

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import processing

# Test file
test_file = "/tmp/test_ingest.jpg"
test_filename = "test_ingest.jpg"

if not os.path.exists(test_file):
    print(f"Test file not found: {test_file}")
    sys.exit(1)

# Copy to ingest folder
ingest_path = os.path.join(config.INGEST_DIRECTORY, test_filename)
print(f"Copying test file to: {ingest_path}")
shutil.copy(test_file, ingest_path)

# Process it
print(f"\nProcessing file from ingest...")
print(f"File exists before processing: {os.path.exists(ingest_path)}")

result = processing.process_image_file(ingest_path, move_from_ingest=True)

print(f"\nProcessing result: {result}")
print(f"File still in ingest: {os.path.exists(ingest_path)}")

# Check where it ended up
from utils.file_utils import get_bucketed_path
expected_path = get_bucketed_path(test_filename, config.IMAGE_DIRECTORY)
expected_full = os.path.join(expected_path)
print(f"Expected location: {expected_full}")
print(f"File at expected location: {os.path.exists(expected_full)}")

# Cleanup
if os.path.exists(ingest_path):
    os.remove(ingest_path)
    print(f"\nCleaned up test file from ingest")

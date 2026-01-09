#!/usr/bin/env python3
"""
Standalone character inference worker.

Runs as a separate process to infer characters for all untagged images.
When complete, the process exits and all memory is freed.

Usage:
    python character_infer_worker.py [--image-id ID]

The worker will:
1. Load model weights from character_model.db
2. Infer characters for untagged images (or specific image)
3. Save results to main database
4. Exit (freeing all memory)
"""

import os
import sys
import json
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def infer_all():
    """Infer characters for all untagged images."""
    from services import character_service
    
    print("Starting character inference for all untagged images...")
    
    try:
        stats = character_service.infer_all_untagged_images()
        print(f"Inference complete!")
        print(f"  Images processed: {stats.get('processed', 0)}")
        print(f"  Characters applied: {stats.get('characters_applied', 0)}")
        
        # Output stats as JSON for parent process to read
        print(f"STATS_JSON:{json.dumps(stats)}")
        return stats
    except Exception as e:
        print(f"Inference failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def infer_single(image_id):
    """Infer characters for a single image."""
    from services import character_service
    
    print(f"Starting character inference for image {image_id}...")
    
    try:
        result = character_service.infer_character_for_image(image_id)
        print(f"Inference complete for image {image_id}")
        
        # Output result as JSON for parent process to read
        print(f"RESULT_JSON:{json.dumps(result)}")
        return result
    except Exception as e:
        print(f"Inference failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Character inference worker')
    parser.add_argument('--image-id', type=int, help='Specific image ID to process')
    args = parser.parse_args()
    
    if args.image_id:
        infer_single(args.image_id)
    else:
        infer_all()
    
    print("Inference worker exiting...")
    sys.exit(0)

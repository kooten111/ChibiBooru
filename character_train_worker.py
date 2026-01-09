#!/usr/bin/env python3
"""
Standalone character model training worker.

Runs as a separate process to train the character prediction model.
When complete, the process exits and all memory is freed.

Usage:
    python character_train_worker.py

The worker will:
1. Load all training data from the database
2. Calculate tag weights and pair weights
3. Save to character_model.db
4. Exit (freeing all memory)
"""

import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def train_model():
    """Train the character prediction model with progress reporting."""
    from services import character_service
    import sys
    
    print("PROGRESS:0:Loading training data...")
    sys.stdout.flush()
    
    # Get training data
    character_images = character_service.get_character_tagged_images()
    total_images = len(character_images)
    print(f"PROGRESS:10:Loaded {total_images} images")
    sys.stdout.flush()
    
    if total_images < 10:
        print("ERROR:Not enough training samples")
        sys.exit(1)
    
    print("PROGRESS:20:Calculating tag weights...")
    sys.stdout.flush()
    
    try:
        stats = character_service.train_model()
        print("PROGRESS:100:Training complete!")
        sys.stdout.flush()
        
        print(f"  Training samples: {stats.get('training_samples', 0)}")
        print(f"  Unique characters: {stats.get('unique_characters', 0)}")
        print(f"  Tag weights: {stats.get('tag_weights_count', 0)}")
        print(f"  Pair weights: {stats.get('pair_weights_count', 0)}")
        
        # Output stats as JSON for parent process to read
        print(f"STATS_JSON:{json.dumps(stats)}")
        sys.stdout.flush()
        return stats
    except Exception as e:
        print(f"ERROR:{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    train_model()
    print("Training worker exiting...")
    sys.exit(0)

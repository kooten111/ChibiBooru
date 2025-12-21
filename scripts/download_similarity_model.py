#!/usr/bin/env python3
"""
Download the SmilingWolf/wd-v1-4-convnext-tagger-v2 ONNX model for semantic similarity.
"""
import os
import sys
import urllib.request
from pathlib import Path

# URLs for the model files
MODEL_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnext-tagger-v2/resolve/main/model.onnx"
TAGS_URL = "https://huggingface.co/SmilingWolf/wd-v1-4-convnext-tagger-v2/resolve/main/selected_tags.csv"

# Target directory
MODELS_DIR = Path(__file__).parent.parent / "models" / "Similarity"
MODEL_PATH = MODELS_DIR / "model.onnx"
TAGS_PATH = MODELS_DIR / "selected_tags.csv"

def download_file(url: str, destination: Path, description: str):
    """Download a file with progress reporting."""
    print(f"Downloading {description}...")
    print(f"  From: {url}")
    print(f"  To: {destination}")

    try:
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, downloaded * 100 / total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r  Progress: {percent:.1f}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)", end='')

        urllib.request.urlretrieve(url, destination, progress_hook)
        print()
        print(f"  ✓ Successfully downloaded {description}")
        return True

    except Exception as e:
        print(f"\n  ✗ Error downloading {description}: {e}")
        return False

def main():
    print("=" * 70)
    print("Similarity Model Downloader (WD14-ConvNext)")
    print("=" * 70)
    
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    if MODEL_PATH.exists():
        print("⚠ Model file already exists!")
        response = input("Redownload? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Skipping download.")
            return

    download_file(MODEL_URL, MODEL_PATH, "model file")
    download_file(TAGS_URL, TAGS_PATH, "tags mapping")
    
    print("\n✓ Setup complete.")

if __name__ == "__main__":
    main()

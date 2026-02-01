#!/usr/bin/env python3
"""
Download the Camie Tagger v2 ONNX model files.

This script downloads the recommended AI tagger model from HuggingFace
and places it in the correct directory structure.
"""

import os
import sys
import urllib.request
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# URLs for the model files
MODEL_URL = "https://huggingface.co/Camais03/camie-tagger-v2/resolve/main/camie-tagger-v2.onnx"
METADATA_URL = "https://huggingface.co/Camais03/camie-tagger-v2/resolve/main/camie-tagger-v2-metadata.json"

# Target directory
MODELS_DIR = Path(__file__).parent.parent / "models" / "Tagger"
MODEL_PATH = MODELS_DIR / "model.onnx"
METADATA_PATH = MODELS_DIR / "metadata.json"


def download_file(url: str, destination: Path, description: str):
    """Download a file with progress reporting."""
    print(f"Downloading {description}...")
    print(f"  From: {url}")
    print(f"  To: {destination}")

    try:
        # Create a progress callback
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, downloaded * 100 / total_size)
                mb_downloaded = downloaded / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r  Progress: {percent:.1f}% ({mb_downloaded:.1f} MB / {mb_total:.1f} MB)", end='')

        # Download with progress
        urllib.request.urlretrieve(url, destination, progress_hook)
        print()  # New line after progress
        print(f"  ✓ Successfully downloaded {description}")
        return True

    except Exception as e:
        print(f"\n  ✗ Error downloading {description}: {e}")
        return False


def main():
    print("=" * 70)
    print("Camie Tagger v2 Downloader")
    print("=" * 70)
    print()

    # Create models directory if it doesn't exist
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Model directory: {MODELS_DIR}")
    print()

    # Check if files already exist
    if MODEL_PATH.exists() and METADATA_PATH.exists():
        print("⚠ Model files already exist!")
        print(f"  - {MODEL_PATH}")
        print(f"  - {METADATA_PATH}")
        print()
        response = input("Do you want to re-download and overwrite them? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Download cancelled.")
            return
        print()

    # Download model file
    success_model = download_file(MODEL_URL, MODEL_PATH, "model file (camie-tagger-v2.onnx)")
    print()

    # Download metadata file
    success_metadata = download_file(METADATA_URL, METADATA_PATH, "metadata file (camie-tagger-v2-metadata.json)")
    print()

    # Summary
    print("=" * 70)
    if success_model and success_metadata:
        print("✓ Download complete!")
        print()
        print("The tagger model has been installed successfully.")
        print("You can now use AI tagging for images without online metadata.")
        print()
        print("To use the tagger:")
        print("  1. Ensure you have installed: uv pip install -r requirements.txt")
        print("  2. Start the application: python app.py")
        print("  3. Images without online metadata will be tagged automatically")
    else:
        print("✗ Download failed!")
        print("Please try downloading manually from:")
        print(f"  Model: {MODEL_URL}")
        print(f"  Metadata: {METADATA_URL}")
        print()
        print(f"Place the files in: {MODELS_DIR}")
        print("  - Rename camie-tagger-v2.onnx to model.onnx")
        print("  - Rename camie-tagger-v2-metadata.json to metadata.json")
    print("=" * 70)


if __name__ == "__main__":
    main()

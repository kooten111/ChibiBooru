# generate_thumbnails.py
import os
from PIL import Image
from pathlib import Path
from tqdm import tqdm

IMAGE_DIR = "./static/images"
THUMB_DIR = "./static/thumbnails"
THUMB_SIZE = 1000

os.makedirs(THUMB_DIR, exist_ok=True)

def generate_thumbnail(image_path, thumb_path):
    """Generate a WebP thumbnail maintaining aspect ratio"""
    try:
        with Image.open(image_path) as img:
            # Convert RGBA to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            
            # Resize maintaining aspect ratio
            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.Resampling.LANCZOS)
            
            # Save as WebP
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            img.save(thumb_path, 'WEBP', quality=85, method=6)
            return True
    except Exception as e:
        print(f"Error processing {image_path}: {e}")
        return False

def main():
    image_files = []
    for root, _, files in os.walk(IMAGE_DIR):
        for file in files:
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                image_files.append(os.path.join(root, file))
    
    for img_path in tqdm(image_files, desc="Generating thumbnails"):
        rel_path = os.path.relpath(img_path, IMAGE_DIR)
        thumb_path = os.path.join(THUMB_DIR, os.path.splitext(rel_path)[0] + '.webp')
        
        if not os.path.exists(thumb_path):
            generate_thumbnail(img_path, thumb_path)
    
    print(f"Thumbnails generated in {THUMB_DIR}/")

if __name__ == "__main__":
    main()
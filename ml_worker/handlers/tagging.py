"""
Tagging handlers (Image and Video)
"""
import os
import shutil
import json
import logging
import subprocess
import tempfile
import numpy as np
from typing import Dict, Any

from ml_worker import models

logger = logging.getLogger(__name__)

def handle_tag_image(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tag_image request.

    Args:
        request_data: {image_path, model_path, threshold, character_threshold}

    Returns:
        Dict with tags and predictions
    """
    image_path = request_data['image_path']
    model_path = request_data['model_path']
    metadata_path = request_data.get('metadata_path')
    if not metadata_path:
        # Try common metadata file naming conventions
        model_dir = os.path.dirname(model_path)
        for name in ['metadata.json', 'model_metadata.json', os.path.basename(model_path).replace('.onnx', '_metadata.json')]:
            candidate = os.path.join(model_dir, name)
            if os.path.exists(candidate):
                metadata_path = candidate
                break
        if not metadata_path:
            metadata_path = model_path.replace('.onnx', '_metadata.json')  # Fallback
    threshold = request_data.get('threshold', 0.35)
    character_threshold = request_data.get('character_threshold', 0.85)

    logger.info(f"Tagging image: {os.path.basename(image_path)}")

    # Lazy load ONNX and torch
    import onnxruntime as ort
    import torchvision.transforms as transforms
    from PIL import Image

    # Load model if not already loaded
    if models.tagger_session is None:
        logger.info(f"Loading tagger model from {model_path}")

        try:
            with open(metadata_path, 'r') as f:
                models.tagger_metadata = json.load(f)
        except Exception:
            logger.warning(f"Could not load metadata from {metadata_path}, using defaults/empty")
            models.tagger_metadata = {'dataset_info': {'total_tags': 0, 'tag_mapping': {'idx_to_tag': {}, 'tag_to_category': {}}}, 'model_info': {'img_size': 448}}
            
        # Dynamic providers based on backend
        providers = models.get_onnx_providers()
        sess_options = models.get_onnx_session_options()
        models.tagger_session = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers)

        dataset_info = models.tagger_metadata.get('dataset_info', {})
        logger.info(f"Tagger model loaded. Found {dataset_info.get('total_tags', 'unknown')} tags.")

    # Preprocess image
    image_size = models.tagger_metadata.get('model_info', {}).get('img_size', 512)

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    try:
        with Image.open(image_path) as img:
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')

            width, height = img.size
            aspect_ratio = width / height

            if aspect_ratio > 1:
                new_width = image_size
                new_height = int(new_width / aspect_ratio)
            else:
                new_height = image_size
                new_width = int(new_height * aspect_ratio)

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            pad_color = (124, 116, 104)
            new_image = Image.new('RGB', (image_size, image_size), pad_color)
            new_image.paste(img, ((image_size - new_width) // 2, (image_size - new_height) // 2))

            img_numpy = transform(new_image).unsqueeze(0).numpy()
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {e}")
        raise ValueError(f"Failed to process image: {e}")

    # Run inference
    input_name = models.tagger_session.get_inputs()[0].name
    raw_outputs = models.tagger_session.run(None, {input_name: img_numpy})

    # Use refined predictions if available
    logits = raw_outputs[1] if len(raw_outputs) > 1 else raw_outputs[0]
    probs = 1.0 / (1.0 + np.exp(-logits))

    # Extract tags
    dataset_info = models.tagger_metadata['dataset_info']
    tag_mapping = dataset_info['tag_mapping']
    idx_to_tag = tag_mapping['idx_to_tag']
    tag_to_category = tag_mapping['tag_to_category']

    storage_threshold = request_data.get('storage_threshold', 0.50)
    display_threshold = threshold

    all_predictions = []
    tags_by_category = {
        "general": [], "character": [], "copyright": [],
        "artist": [], "meta": [], "species": []
    }

    indices = np.where(probs[0] >= storage_threshold)[0]

    for idx in indices:
        idx_str = str(idx)
        tag_name = idx_to_tag.get(idx_str)
        if not tag_name:
            continue

        # Skip rating tags
        if tag_name.startswith('rating:') or tag_name.startswith('rating_'):
            continue

        category = tag_to_category.get(tag_name, "general")
        confidence = float(probs[0][idx])

        all_predictions.append({
            'tag_name': tag_name,
            'category': category,
            'confidence': confidence
        })

        if confidence >= display_threshold:
            if category in tags_by_category:
                tags_by_category[category].append(tag_name)
            else:
                tags_by_category["general"].append(tag_name)

    return {
        "tags": tags_by_category,
        "all_predictions": all_predictions,
        "tagger_name": models.tagger_metadata.get('model_info', {}).get('name', 'Unknown')
    }


def handle_tag_video(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle tag_video request.
    Extracts frames using ffmpeg and tags them using internal tagger.
    """
    video_filepath = request_data['video_path']
    num_frames = request_data.get('num_frames', 5)
    
    # Reuse params for tagging
    model_path = request_data['model_path']
    threshold = request_data.get('threshold', 0.35)
    
    logger.info(f"Tagging video: {os.path.basename(video_filepath)} ({num_frames} frames)")
    
    # Check ffmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    ffprobe_path = shutil.which('ffprobe')
    
    if not ffmpeg_path or not ffprobe_path:
        raise RuntimeError("ffmpeg/ffprobe not found in worker environment")
        
    try:
        # Get duration
        duration_cmd = [
            ffprobe_path, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_filepath
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
        try:
             duration = float(duration_result.stdout.strip())
        except ValueError:
             logger.warning(f"Could not determine duration for {video_filepath}, assuming 0")
             duration = 0

        # Extract frames
        # Safety check for duration
        if duration <= 0:
             # Just try to grab one frame at 0
             frame_times = [0]
        else:
             frame_times = [duration * (i + 1) / (num_frames + 1) for i in range(num_frames)]
        
        all_tags_with_scores = {}
        
        for i, timestamp in enumerate(frame_times):
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                temp_frame_path = temp_frame.name
            
            try:
                subprocess.run([
                    ffmpeg_path, '-ss', str(timestamp), '-i', video_filepath,
                    '-vframes', '1', '-strict', 'unofficial', '-y', temp_frame_path
                ], check=True, capture_output=True)
                
                # Tag using internal handler function directly
                # We need to construct a request payload for handle_tag_image
                tag_request = {
                    "image_path": temp_frame_path,
                    "model_path": model_path,
                    "threshold": threshold,
                    "storage_threshold": request_data.get('storage_threshold', 0.50),
                    "character_threshold": request_data.get('character_threshold', 0.85),
                    "metadata_path": request_data.get('metadata_path')
                }
                
                result = handle_tag_image(tag_request)
                
                # Merge logic
                all_predictions = result.get('all_predictions', [])
                for pred in all_predictions:
                    confidence = pred['confidence']
                    
                    # Apply threshold BEFORE merging - use the same threshold as images
                    if confidence < threshold:
                        continue
                    
                    tag_name = pred['tag_name']
                    category = pred['category']
                    
                    if tag_name.startswith('rating:') or tag_name.startswith('rating_'):
                        continue
                    
                    key = (tag_name, category)
                    
                    if key in all_tags_with_scores:
                        all_tags_with_scores[key]['count'] += 1
                        all_tags_with_scores[key]['max_prob'] = max(all_tags_with_scores[key]['max_prob'], confidence)
                    else:
                        all_tags_with_scores[key] = {'count': 1, 'max_prob': confidence}
                        
            except Exception as e:
                logger.warning(f"Error tagging frame {i+1}: {e}")
                continue
            finally:
                if os.path.exists(temp_frame_path):
                    os.unlink(temp_frame_path)
                    
        # Final merge
        if not all_tags_with_scores:
            logger.warning("No tags found in any frame")
            return {"tags": {}, "tagger_name": "unknown"}
            
        tags_by_category = {"general": [], "character": [], "copyright": [], "artist": [], "meta": [], "species": []}

        for (tag_name, category), scores in all_tags_with_scores.items():
            if scores['count'] >= 2 or scores['max_prob'] >= 0.8:
                if category in tags_by_category:
                    tags_by_category[category].append(tag_name)
                else:
                    tags_by_category["general"].append(tag_name)
                    
        tagger_name = models.tagger_metadata.get('model_info', {}).get('name', 'Unknown') if models.tagger_metadata else "video"
            
        return {
            "tags": tags_by_category,
            "tagger_name": f"{tagger_name} (video)"
        }
        
    except Exception as e:
        logger.error(f"Error tagging video: {e}")
        raise

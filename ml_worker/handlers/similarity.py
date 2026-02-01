"""
Similarity computation handler
"""
import os
import logging
import json
import numpy as np
from typing import Dict, Any

from ml_worker import models

logger = logging.getLogger(__name__)

def handle_compute_similarity(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle compute_similarity request.

    Args:
        request_data: {image_path, model_path}

    Returns:
        Dict with embedding vector
    """
    image_path = request_data['image_path']
    model_path = request_data['model_path']

    logger.info(f"Computing similarity embedding: {os.path.basename(image_path)}")

    # Lazy load ONNX and torch
    import onnxruntime as ort
    import torchvision.transforms as transforms
    from PIL import Image

    # Load model if not already loaded
    if models.similarity_model is None:
        logger.info(f"Loading similarity model from {model_path}")

        # Dynamic providers based on backend
        providers = models.get_onnx_providers()
        sess_options = models.get_onnx_session_options()
            
        models.similarity_model = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers)
        logger.info("Similarity model loaded")

    # Preprocess image
    # Model expects 448x448 and NHWC format (Batch, Height, Width, Channels)
    image_size = 448

    transform = transforms.Compose([
        transforms.Resize((image_size, image_size), interpolation=transforms.InterpolationMode.BICUBIC),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])

    try:
        # Handle Video files by extracting a frame
        temp_frame_path = None
        target_path = image_path
        
        if image_path.lower().endswith(('.mp4', '.webm', '.gif', '.zip')):
            import shutil
            import subprocess
            import tempfile
            
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                try:
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_frame:
                        temp_frame_path = temp_frame.name
                    
                    # Extract frame at 1s or 0s
                    subprocess.run([
                        ffmpeg_path, '-ss', '0.0', '-i', image_path,
                        '-vframes', '1', '-strict', 'unofficial', '-y', temp_frame_path
                    ], check=True, capture_output=True)
                    
                    if os.path.exists(temp_frame_path) and os.path.getsize(temp_frame_path) > 0:
                        target_path = temp_frame_path
                        logger.info(f"Extracted frame for similarity: {target_path}")
                except Exception as e:
                    logger.warning(f"Failed to extract frame from video {image_path}: {e}")
                    # Fallthrough to try opening original (might work for gifs)

        with Image.open(target_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Produces (1, 3, 448, 448)
            img_tensor = transform(img).unsqueeze(0)
            
            # Transpose to (1, 448, 448, 3) for NHWC
            img_numpy = img_tensor.permute(0, 2, 3, 1).numpy()
            
        # Clean up temp file
        if temp_frame_path and os.path.exists(temp_frame_path):
            os.unlink(temp_frame_path)
            
    except Exception as e:
        if temp_frame_path and os.path.exists(temp_frame_path):
            os.unlink(temp_frame_path)
        logger.error(f"Error processing image {image_path}: {e}")
        raise ValueError(f"Failed to process image: {e}")

    # Run inference
    input_name = models.similarity_model.get_inputs()[0].name
    # Some models might have different output structure, but usually last hidden state or pooler output
    raw_outputs = models.similarity_model.run(None, {input_name: img_numpy})
    
    # Find the 1024-d embedding output (not the 9083-d classification)
    # Model outputs: predictions_sigmoid (9083), globalavgpooling (1024,1,1), predictions_norm (1024)
    embedding = None
    for out in raw_outputs:
        # Look for exactly 1024 dimensions (the embedding vector)
        flat = out.flatten() if len(out.shape) > 2 else out[0] if len(out.shape) == 2 else out
        if hasattr(flat, '__len__') and len(flat) == 1024:
            embedding = flat.astype(np.float32)
            break
            
    if embedding is None:
        logger.error(f"Could not find 1024-d embedding. Output shapes: {[o.shape for o in raw_outputs]}")
        # Build strict error message
        shapes = [o.shape for o in raw_outputs]
        raise ValueError(f"Model did not produce valid 1024-d embedding. Found shapes: {shapes}")

    # Normalize embedding (essential for cosine similarity to work with simple dot product/euclidean stats)
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return {
        "embedding": embedding.tolist()
    }

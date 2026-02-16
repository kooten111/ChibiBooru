"""
Similarity computation handler.

Supports multiple model types:
- 'siglip': SigLIP 2 (384x384, no normalization, 1152-d embeddings)
- 'tagger': Legacy WD tagger backbone (448x448, ImageNet normalization, 1024-d)
"""
import os
import logging
import numpy as np
from typing import Dict, Any

from ml_worker import models

logger = logging.getLogger(__name__)

# Cache for current model configuration
_current_model_path = None


def handle_compute_similarity(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle compute_similarity request.

    Args:
        request_data: {
            image_path: str,
            model_path: str,
            model_type: str (optional, 'siglip' or 'tagger', default 'siglip'),
            image_size: int (optional, default from model_type),
            embedding_dim: int (optional, expected output dimension)
        }

    Returns:
        Dict with embedding vector
    """
    global _current_model_path
    
    image_path = request_data['image_path']
    model_path = request_data['model_path']
    model_type = request_data.get('model_type', 'siglip').lower()
    
    # Get config from request or use defaults based on model type
    if model_type == 'siglip':
        image_size = request_data.get('image_size', 384)
        embedding_dim = request_data.get('embedding_dim', 1152)
    else:  # 'tagger' or legacy
        image_size = request_data.get('image_size', 448)
        embedding_dim = request_data.get('embedding_dim', 1024)

    logger.info(f"Computing {model_type} embedding ({embedding_dim}-d): {os.path.basename(image_path)}")

    # Lazy load ONNX and torch
    import onnxruntime as ort
    import torchvision.transforms as transforms
    from PIL import Image

    # Load model if not already loaded or if model path changed
    if models.similarity_model is None or _current_model_path != model_path:
        logger.info(f"Loading similarity model from {model_path}")

        # Dynamic providers based on backend
        providers = models.get_onnx_providers()
        sess_options = models.get_onnx_session_options()
        models.similarity_model = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers)
        _current_model_path = model_path
        logger.info(f"Similarity model loaded ({model_type})")

    # Build transform based on model type
    if model_type == 'siglip':
        # SigLIP: expects [0, 1] normalized RGB, no ImageNet normalization
        transform = transforms.Compose([
            transforms.Resize((image_size, image_size), interpolation=transforms.InterpolationMode.BICUBIC),
            transforms.ToTensor(),  # Converts to [0, 1] range
        ])
    else:
        # Tagger: expects ImageNet normalization
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
                    
                    subprocess.run([
                        ffmpeg_path, '-ss', '0.0', '-i', image_path,
                        '-vframes', '1', '-strict', 'unofficial', '-y', temp_frame_path
                    ], check=True, capture_output=True)
                    
                    if os.path.exists(temp_frame_path) and os.path.getsize(temp_frame_path) > 0:
                        target_path = temp_frame_path
                        logger.info(f"Extracted frame for similarity: {target_path}")
                except Exception as e:
                    logger.warning(f"Failed to extract frame from video {image_path}: {e}")

        try:
            with Image.open(target_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Transform to tensor
                img_tensor = transform(img).unsqueeze(0)
                
                # Model input format depends on type
                if model_type == 'siglip':
                    # SigLIP expects NCHW (standard PyTorch format)
                    img_numpy = img_tensor.numpy()
                else:
                    # Legacy tagger expects NHWC
                    img_numpy = img_tensor.permute(0, 2, 3, 1).numpy()
        except OSError as e:
            # Handle truncated or corrupted images by allowing PIL to load partial data
            if 'truncated' in str(e).lower() or 'corrupted' in str(e).lower():
                logger.warning(f"Image file is truncated/corrupted, attempting recovery: {image_path}")
                from PIL import ImageFile
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                
                try:
                    with Image.open(target_path) as img:
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        img_tensor = transform(img).unsqueeze(0)
                        
                        if model_type == 'siglip':
                            img_numpy = img_tensor.numpy()
                        else:
                            img_numpy = img_tensor.permute(0, 2, 3, 1).numpy()
                    
                    logger.info(f"Successfully recovered embedding from truncated image: {image_path}")
                except Exception as recovery_error:
                    logger.error(f"Failed to recover from truncated image {image_path}: {recovery_error}")
                    if temp_frame_path and os.path.exists(temp_frame_path):
                        os.unlink(temp_frame_path)
                    raise ValueError(f"Failed to process image (truncated/corrupted): {recovery_error}")
                finally:
                    ImageFile.LOAD_TRUNCATED_IMAGES = False
            else:
                if temp_frame_path and os.path.exists(temp_frame_path):
                    os.unlink(temp_frame_path)
                raise
            
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
    raw_outputs = models.similarity_model.run(None, {input_name: img_numpy})
    
    # Find the embedding output matching expected dimension
    embedding = None
    for out in raw_outputs:
        flat = out.flatten() if len(out.shape) > 2 else out[0] if len(out.shape) == 2 else out
        if hasattr(flat, '__len__') and len(flat) == embedding_dim:
            embedding = flat.astype(np.float32)
            break
    
    # If exact match not found, try to find any reasonable embedding
    if embedding is None:
        for out in raw_outputs:
            flat = out.flatten() if len(out.shape) > 2 else out[0] if len(out.shape) == 2 else out
            # Accept embeddings in typical range (512-2048)
            if hasattr(flat, '__len__') and 512 <= len(flat) <= 2048:
                embedding = flat.astype(np.float32)
                logger.warning(f"Expected {embedding_dim}-d, found {len(flat)}-d embedding")
                break
            
    if embedding is None:
        shapes = [o.shape for o in raw_outputs]
        logger.error(f"Could not find {embedding_dim}-d embedding. Output shapes: {shapes}")
        raise ValueError(f"Model did not produce valid embedding. Expected {embedding_dim}-d, found shapes: {shapes}")

    # Normalize embedding for cosine similarity
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    return {
        "embedding": embedding.tolist()
    }


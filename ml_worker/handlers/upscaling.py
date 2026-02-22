"""
Upscaling handler
"""
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any

from ml_worker import models
from ml_worker.backends import get_torch_device

logger = logging.getLogger(__name__)


def _is_recoverable_inference_error(error: RuntimeError) -> bool:
    message = str(error).lower()
    recoverable_markers = (
        'out of memory',
        'could not create a primitive',
        'dnnl',
        'oneapi',
        'xpu',
        'memory access',
    )
    return any(marker in message for marker in recoverable_markers)


def _clear_device_cache(torch_module, device_name: str) -> None:
    try:
        if device_name == 'cuda' and torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
        elif device_name == 'xpu' and hasattr(torch_module, 'xpu') and torch_module.xpu.is_available():
            torch_module.xpu.empty_cache()
        elif device_name == 'mps' and hasattr(torch_module, 'mps') and hasattr(torch_module.mps, 'empty_cache'):
            torch_module.mps.empty_cache()
    except Exception as cache_error:
        logger.debug(f"Cache clear skipped ({device_name}): {cache_error}")

def handle_upscale_image(request_data: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
    """
    Handle upscale_image request.

    Args:
        request_data: {image_path, model_name, output_path, device}

    Returns:
        Dict with success status and output path
    """
    image_path = request_data['image_path']

    # Reject animated images and videos — upscaling only works on static images
    _non_upscalable = ('.gif', '.apng', '.mp4', '.webm')
    if image_path.lower().endswith(_non_upscalable):
        raise ValueError(f"Cannot upscale animated/video file: {os.path.basename(image_path)}")

    model_name = request_data.get('model_name', 'RealESRGAN_x4plus_anime')
    output_path = request_data['output_path']
    device = request_data.get('device', 'auto')
    tile_size = max(32, int(request_data.get('tile_size', 256)))
    tile_pad = max(0, int(request_data.get('tile_pad', 32)))
    min_tile_size = max(32, int(request_data.get('min_tile_size', 64)))
    allow_cpu_fallback = bool(request_data.get('allow_cpu_fallback', True))

    logger.info(f"Upscaling image: {os.path.basename(image_path)}")

    # Lazy load torch and dependencies
    import torch
    from PIL import Image
    import numpy as np

    # Import RRDBNet architecture
    # Assuming ml_worker is run from project root or has it in path
    # If not, we might need to adjust sys.path but server.py does it generally
    if 'utils.rrdbnet_arch' not in sys.modules:
         # Try to import
         try:
             from utils.rrdbnet_arch import RRDBNet
         except ImportError:
             # Try appending parent parent?
             sys.path.insert(0, str(Path(__file__).parent.parent.parent))
             from utils.rrdbnet_arch import RRDBNet
    else:
        from utils.rrdbnet_arch import RRDBNet

    # Model configs
    MODEL_CONFIGS = {
        'RealESRGAN_x4plus': {'num_block': 23, 'num_feat': 64, 'num_grow_ch': 32},
        'RealESRGAN_x4plus_anime': {'num_block': 6, 'num_feat': 64, 'num_grow_ch': 32}
    }

    # Determine device strict mode
    # Backend environment is already setup by startup
    backend = os.environ.get('ML_WORKER_BACKEND')
    if not backend:
        logger.error("ML_WORKER_BACKEND not set")
        raise RuntimeError("ML_WORKER_BACKEND not set")
        
    # Import IPEX if available (not required with PyTorch nightly XPU)
    if backend == 'xpu':
        try:
            import intel_extension_for_pytorch as ipex
            logger.info("Intel Extension for PyTorch imported for Upscaler")
        except (ImportError, AttributeError, RuntimeError) as e:
            # IPEX not required with PyTorch nightly - XPU support is built-in
            # Also IPEX v2.8 crashes with AttributeError: module 'os' has no attribute 'exit' on version mismatch
            logger.warning(f"IPEX failed to import ({e}), using built-in XPU support")
            
    device = get_torch_device(backend)
    
    # CRITICAL: Strict Check - Fail immediately if device is CPU but backend is not
    if backend != 'cpu' and device == 'cpu':
        logger.error(f"CRITICAL FAILURE: Backend is configured as '{backend}' but torch detected device as '{device}'.")
        raise RuntimeError(f"Strict Mode Violation: Refusing to run on CPU when {backend} is requested.")
        
    models.upscaler_device = device

    # Load model if not already loaded
    if models.upscaler_model is None:
        logger.info(f"Loading upscaler model: {model_name} on {device}")

        model_config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS['RealESRGAN_x4plus'])
        model_dir = Path('./models/Upscaler')
        model_path = model_dir / f"{model_name}.pth"

        if not model_path.exists():
            # Try fallback to non-anime if anime requested but missing, or vice versa?
            if 'anime' in model_name:
                alt_model = 'RealESRGAN_x4plus'
                alt_path = model_dir / f"{alt_model}.pth"
                if alt_path.exists():
                    logger.warning(f"Model {model_name} not found. Falling back to {alt_model}")
                    model_path = alt_path
                    model_config = MODEL_CONFIGS[alt_model]
                else:
                    raise FileNotFoundError(f"Upscaler model not found: {model_path}")
            else:
                 raise FileNotFoundError(f"Upscaler model not found: {model_path}")

        models.upscaler_model = RRDBNet(
            num_in_ch=3, num_out_ch=3,
            num_feat=model_config['num_feat'],
            num_block=model_config['num_block'],
            num_grow_ch=model_config['num_grow_ch'],
            scale=4
        )

        loadnet = torch.load(str(model_path), map_location=torch.device('cpu'), weights_only=True)

        if 'params_ema' in loadnet:
            keyname = 'params_ema'
        elif 'params' in loadnet:
            keyname = 'params'
        else:
            keyname = None

        if keyname:
            models.upscaler_model.load_state_dict(loadnet[keyname], strict=True)
        else:
            models.upscaler_model.load_state_dict(loadnet, strict=True)

        models.upscaler_model.eval()
        models.upscaler_model.to(device)
        models.upscaler_device = device
    elif models.upscaler_device != device:
        logger.info(f"Moving upscaler model from {models.upscaler_device} to {device}")
        models.upscaler_model.to(device)
        models.upscaler_device = device

    # 1. Load image
    try:
        with Image.open(image_path) as img:
            original_width, original_height = img.size
            
            if img.mode == 'P':
                img = img.convert('RGB')
            elif img.mode == 'RGBA':
                img = img.convert('RGB')  # RealESRGAN usually expects RGB
                
            # Convert to tensor
            img_np = np.array(img).transpose(2, 0, 1) # HWC -> CHW
            img_np = img_np / 255.
            img_tensor_cpu = torch.from_numpy(img_np).float().unsqueeze(0)
    except OSError as e:
        # Handle truncated or corrupted images by allowing PIL to load partial data
        if 'truncated' in str(e).lower() or 'corrupted' in str(e).lower():
            logger.warning(f"Image file is truncated/corrupted, attempting recovery: {image_path}")
            from PIL import ImageFile
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            
            try:
                with Image.open(image_path) as img:
                    original_width, original_height = img.size
                    
                    if img.mode == 'P':
                        img = img.convert('RGB')
                    elif img.mode == 'RGBA':
                        img = img.convert('RGB')  # RealESRGAN usually expects RGB
                        
                    # Convert to tensor
                    img_np = np.array(img).transpose(2, 0, 1) # HWC -> CHW
                    img_np = img_np / 255.
                    img_tensor_cpu = torch.from_numpy(img_np).float().unsqueeze(0)
                
                logger.info(f"Successfully recovered upscaled image from truncated source: {image_path}")
            except Exception as recovery_error:
                logger.error(f"Failed to recover from truncated image {image_path}: {recovery_error}")
                raise ValueError(f"Failed to process image (truncated/corrupted): {recovery_error}")
            finally:
                ImageFile.LOAD_TRUNCATED_IMAGES = False
        else:
            raise

    # 2. Run Inference
    from ml_worker.utils import tiled_inference

    current_device = device
    current_tile_size = max(tile_size, min_tile_size)
    output = None
    last_error = None

    while current_tile_size >= min_tile_size:
        try:
            if models.upscaler_device != current_device:
                logger.info(f"Moving upscaler model from {models.upscaler_device} to {current_device}")
                models.upscaler_model.to(current_device)
                models.upscaler_device = current_device

            img_tensor = img_tensor_cpu.to(current_device)
            output = tiled_inference(
                models.upscaler_model,
                img_tensor,
                tile_size=current_tile_size,
                tile_pad=tile_pad,
                scale=4,
                device=current_device,
                progress_callback=progress_callback,
            )
            break
        except RuntimeError as e:
            last_error = e
            if not _is_recoverable_inference_error(e):
                raise

            _clear_device_cache(torch, current_device)

            if current_tile_size == min_tile_size:
                break

            next_tile_size = max(min_tile_size, current_tile_size // 2)
            logger.warning(
                f"Inference failed on {current_device} with tile size {current_tile_size}: {e}. "
                f"Retrying with tile size {next_tile_size}."
            )
            current_tile_size = next_tile_size

    if output is None and allow_cpu_fallback and current_device != 'cpu' and last_error is not None and _is_recoverable_inference_error(last_error):
        logger.warning(
            f"Recoverable inference failure on backend {current_device} after tile retries. "
            "Falling back to CPU for this request."
        )
        current_device = 'cpu'
        current_tile_size = max(min_tile_size, min(tile_size, 256))

        while current_tile_size >= min_tile_size:
            try:
                if models.upscaler_device != current_device:
                    models.upscaler_model.to(current_device)
                    models.upscaler_device = current_device

                img_tensor = img_tensor_cpu.to(current_device)
                output = tiled_inference(
                    models.upscaler_model,
                    img_tensor,
                    tile_size=current_tile_size,
                    tile_pad=tile_pad,
                    scale=4,
                    device=current_device,
                    progress_callback=progress_callback,
                )
                break
            except RuntimeError as e:
                last_error = e
                if not _is_recoverable_inference_error(e) or current_tile_size == min_tile_size:
                    break
                current_tile_size = max(min_tile_size, current_tile_size // 2)

    if output is None:
        raise last_error if last_error is not None else RuntimeError("Upscaler inference failed")

    # 3. Post-process
    output = output.data.squeeze().float().cpu().clamp_(0, 1).numpy()
    
    # CHW -> HWC
    output = np.transpose(output, (1, 2, 0))
    
    output_img = (output * 255.0).round().astype(np.uint8)
    output_pil = Image.fromarray(output_img)
    
    # Get upscaled dimensions
    upscaled_width, upscaled_height = output_pil.size
    
    # Ensure dir
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save with configured format
    output_format = request_data.get('output_format', 'png').lower().strip()
    output_quality = max(1, min(100, int(request_data.get('output_quality', 95))))
    
    if output_format == 'webp':
        output_pil.save(output_path, format='WEBP', quality=output_quality, method=4)
        logger.info(f"Saved upscaled image as WebP (quality={output_quality}): {os.path.basename(output_path)}")
    else:
        output_pil.save(output_path, format='PNG')
        logger.info(f"Saved upscaled image as PNG: {os.path.basename(output_path)}")
    
    return {
        "success": True, 
        "output_path": output_path,
        "original_size": [original_width, original_height],
        "upscaled_size": [upscaled_width, upscaled_height]
    }

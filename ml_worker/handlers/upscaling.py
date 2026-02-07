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

def handle_upscale_image(request_data: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
    """
    Handle upscale_image request.

    Args:
        request_data: {image_path, model_name, output_path, device}

    Returns:
        Dict with success status and output path
    """
    image_path = request_data['image_path']
    model_name = request_data.get('model_name', 'RealESRGAN_x4plus_anime')
    output_path = request_data['output_path']
    device = request_data.get('device', 'auto')

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

    # 1. Load image
    with Image.open(image_path) as img:
        if img.mode == 'P':
            img = img.convert('RGB')
        elif img.mode == 'RGBA':
            img = img.convert('RGB')  # RealESRGAN usually expects RGB
            
        # Convert to tensor
        img_np = np.array(img).transpose(2, 0, 1) # HWC -> CHW
        img_np = img_np / 255.
        img_tensor = torch.from_numpy(img_np).float().unsqueeze(0).to(device)

    # 2. Run Inference
    try:
        from ml_worker.utils import tiled_inference
        # Run inference (with tiling if needed)
        # Using a conservative tile size to avoid OOM
        output = tiled_inference(
            models.upscaler_model, 
            img_tensor, 
            tile_size=256, 
            tile_pad=32, 
            scale=4, 
            device=device,
            progress_callback=progress_callback
        )
    except RuntimeError as e:
        if "out of memory" in str(e):
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            # Retry with smaller tiles
            logger.warning("OOM detected, retrying with smaller tiles...")
            output = tiled_inference(
                models.upscaler_model, 
                img_tensor, 
                tile_size=128, 
                tile_pad=32, 
                scale=4, 
                device=device,
                progress_callback=progress_callback
            )
        else:
            raise e

    # 3. Post-process
    output = output.data.squeeze().float().cpu().clamp_(0, 1).numpy()
    
    # CHW -> HWC
    output = np.transpose(output, (1, 2, 0))
    
    output_img = (output * 255.0).round().astype(np.uint8)
    output_pil = Image.fromarray(output_img)
    
    # Ensure dir
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save as PNG (lossless for upscale result)
    output_pil.save(output_path)
    
    return {"success": True, "output_path": output_path}

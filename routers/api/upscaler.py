"""
Upscaler API Routes
Provides endpoints for upscaling images and managing upscaled versions
"""

from quart import request, jsonify
from . import api_blueprint
from utils import api_handler
import config


@api_blueprint.route('/upscale/status')
@api_handler()
async def get_upscaler_status():
    """Get upscaler status and dependency info."""
    from services.upscaler_service import get_upscaler_status
    return get_upscaler_status()


@api_blueprint.route('/upscale/check')
@api_handler()
async def check_upscale():
    """Check if an upscaled version exists for an image."""
    from services.upscaler_service import check_upscale_exists, get_upscale_url, get_upscaled_path
    
    filepath = request.args.get('filepath')
    if not filepath:
        raise ValueError("Missing filepath parameter")
    
    exists = check_upscale_exists(filepath)
    
    return {
        'filepath': filepath,
        'has_upscaled': exists,
        'upscaled_url': get_upscale_url(filepath) if exists else None
    }


@api_blueprint.route('/upscale', methods=['POST'])
@api_handler()
async def upscale_image():
    """Upscale an image using RealESRGAN."""
    from services.upscaler_service import upscale_image as do_upscale
    
    if not config.UPSCALER_ENABLED:
        raise ValueError("Upscaler is disabled. Enable UPSCALER_ENABLED in .env to use this feature.")
    
    data = await request.json
    filepath = data.get('filepath')
    force = data.get('force', False)
    
    if not filepath:
        raise ValueError("Missing filepath")
    
    result = await do_upscale(filepath, force=force)
    
    if not result['success'] and result['error'] != 'Already upscaled':
        raise ValueError(result['error'])
    
    return result


@api_blueprint.route('/upscale', methods=['DELETE'])
@api_handler()
async def delete_upscale():
    """Delete the upscaled version of an image."""
    from services.upscaler_service import delete_upscaled_image
    
    data = await request.json
    filepath = data.get('filepath')
    
    if not filepath:
        raise ValueError("Missing filepath")
    
    result = delete_upscaled_image(filepath)
    
    if not result['success']:
        raise ValueError(result['error'])
    
    return result


@api_blueprint.route('/upscale/dependencies')
@api_handler()
async def check_dependencies():
    """Check upscaler dependencies status."""
    from utils.gpu_detection import check_upscaler_dependencies, detect_gpu_hardware
    
    deps = check_upscaler_dependencies()
    gpu = detect_gpu_hardware()
    
    return {
        'enabled': config.UPSCALER_ENABLED,
        'ready': deps['ready'],
        'dependencies': deps,
        'gpu': gpu
    }


@api_blueprint.route('/upscale/install', methods=['POST'])
@api_handler()
async def install_dependencies():
    """
    Install upscaler dependencies.
    This is a potentially long-running operation.
    """
    from utils.gpu_detection import install_upscaler_dependencies
    import asyncio
    
    if not config.UPSCALER_ENABLED:
        raise ValueError("Upscaler is disabled. Enable UPSCALER_ENABLED in .env first.")
    
    data = await request.json or {}
    variant = data.get('variant', 'auto')
    
    # Run installation in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: install_upscaler_dependencies(variant))
    
    if not result['success']:
        raise ValueError(f"Installation failed: {'; '.join(result['errors'])}")
    
    return {
        'success': True,
        'messages': result['messages']
    }

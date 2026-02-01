"""
Shared utilities for ML worker
"""
import re
import math
import torch
import logging
from typing import List

logger = logging.getLogger(__name__)

# Constants for animation extraction
FRAME_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')


def natural_sort_key(s: str) -> List:
    """Sort key for natural sorting."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]


def is_valid_frame(filename: str) -> bool:
    """Check if a filename is a valid image frame."""
    if filename.startswith('.') or filename.startswith('__'):
        return False
    return filename.lower().endswith(FRAME_EXTENSIONS)


def tiled_inference(model, img, tile_size=512, tile_pad=32, scale=4, device='cpu'):
    """
    Run inference using seamless tiling.
    img: Tensor (1, C, H, W)
    """
    batch, channel, height, width = img.shape
    output_height = height * scale
    output_width = width * scale
    output_shape = (batch, channel, output_height, output_width)

    # Initialize output tensor
    output = torch.zeros(output_shape, device=device)

    # Number of tiles
    tiles_x = math.ceil(width / tile_size)
    tiles_y = math.ceil(height / tile_size)

    logger.info(f"Tiling: {tiles_x}x{tiles_y} tiles (Input tile: {tile_size}px, Pad: {tile_pad}px)")

    for y in range(tiles_y):
        for x in range(tiles_x):
            # 1. Determine Input Crop Coordinates (Input Space)
            # Core crop (without padding)
            ofs_x = x * tile_size
            ofs_y = y * tile_size
            
            # Input Pad limits (don't go out of bounds)
            input_start_x = max(ofs_x - tile_pad, 0)
            input_end_x = min(ofs_x + tile_size + tile_pad, width)
            input_start_y = max(ofs_y - tile_pad, 0)
            input_end_y = min(ofs_y + tile_size + tile_pad, height)

            # Input padding offsets (how much we actually padded relative to the core crop)
            pad_left = ofs_x - input_start_x
            pad_top = ofs_y - input_start_y
            
            # Crop Input
            input_tile = img[:, :, input_start_y:input_end_y, input_start_x:input_end_x]

            # 2. Run Inference
            with torch.no_grad():
                try:
                    output_tile = model(input_tile)
                except RuntimeError as e:
                    logger.error(f"Error processing tile ({x},{y}): {e}")
                    raise e

            # 3. Determine Output Crop Coordinates (Output Space)
            # The output tensor includes the padding, so we need to crop the VALID center area.
            
            # Corresponding valid output area in the final image
            output_start_x = ofs_x * scale
            output_end_x = min(ofs_x + tile_size, width) * scale
            output_start_y = ofs_y * scale
            output_end_y = min(ofs_y + tile_size, height) * scale

            # Crop offsets within the output_tile
            # We skip the 'pad_left * scale' pixels that correspond to the left padding
            tile_crop_start_x = pad_left * scale
            tile_crop_end_x = tile_crop_start_x + (output_end_x - output_start_x)
            
            tile_crop_start_y = pad_top * scale
            tile_crop_end_y = tile_crop_start_y + (output_end_y - output_start_y)

            # Place into final output
            output[:, :, output_start_y:output_end_y, output_start_x:output_end_x] = \
                output_tile[:, :, tile_crop_start_y:tile_crop_end_y, tile_crop_start_x:tile_crop_end_x]

    return output

from quart import Blueprint, send_from_directory
from urllib.parse import unquote
import os

static_blueprint = Blueprint('static_files', __name__)

@static_blueprint.route('/favicon.ico')
async def serve_favicon():
    """Serve favicon fallback for clients that request /favicon.ico."""
    return await send_from_directory('static', 'favicon.svg')

@static_blueprint.route('/thumbnails/<path:subpath>')
async def serve_thumbnail(subpath):
    """
    Custom route to serve thumbnails with proper URL decoding.
    Handles filenames with special characters (spaces, emojis, etc.)
    """
    # URL decode the path to handle special characters
    decoded_path = unquote(subpath)
    
    # Construct the full path to the thumbnail
    thumbnail_dir = os.path.join('static', 'thumbnails')
    
    # Send the file from the thumbnails directory
    # send_from_directory handles the path safely
    return await send_from_directory(thumbnail_dir, decoded_path)

@static_blueprint.route('/images/<path:subpath>')
async def serve_image(subpath):
    """
    Custom route to serve images with proper URL decoding.
    Handles filenames with special characters (spaces, emojis, etc.)
    """
    # URL decode the path to handle special characters
    decoded_path = unquote(subpath)
    
    # Construct the full path to the image
    image_dir = os.path.join('static', 'images')
    
    # Send the file from the images directory
    return await send_from_directory(image_dir, decoded_path)

@static_blueprint.route('/upscaled/<path:subpath>')
async def serve_upscaled_image(subpath):
    """
    Custom route to serve upscaled images with proper URL decoding.
    Handles filenames with special characters (spaces, emojis, etc.)
    """
    # URL decode the path to handle special characters
    decoded_path = unquote(subpath)
    
    # Construct the full path to the upscaled image
    upscaled_dir = os.path.join('static', 'upscaled')
    
    # Send the file from the upscaled directory
    return await send_from_directory(upscaled_dir, decoded_path)

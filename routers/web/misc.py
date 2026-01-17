"""
Miscellaneous routes: startup, tag categorization, implications, system, upload.
"""

from quart import render_template, request, jsonify, url_for
import os
import config
from database import models
from services import processing
from services import query_service
from utils.decorators import login_required
from werkzeug.utils import secure_filename


def register_routes(blueprint):
    """Register miscellaneous routes on the given blueprint."""
    
    @blueprint.route('/startup')
    async def startup():
        """Display startup/loading screen while app initializes."""
        # No authentication required - this is shown during startup
        return await render_template('startup.html', app_name=config.APP_NAME)

    @blueprint.route('/tag_categorize')
    @login_required
    async def tag_categorize():
        """Interactive tag categorization interface."""
        return await render_template('tag_categorize.html', app_name=config.APP_NAME)

    @blueprint.route('/implications')
    @login_required
    async def implications_manager():
        stats = query_service.get_enhanced_stats()
        return await render_template(
            'implications.html',
            stats=stats,
            query='',
            random_tags=[],
            app_name=config.APP_NAME
        )

    @blueprint.route('/system')
    @login_required
    async def system_page():
        """System management page with settings, status, actions, and logs."""
        stats = query_service.get_enhanced_stats()
        return await render_template(
            'system.html',
            stats=stats,
            app_name=config.APP_NAME
        )

    @blueprint.route('/upload', methods=['GET', 'POST'])
    @login_required
    async def upload_image():
        if request.method == 'POST':
            from utils.file_utils import ensure_bucket_dir, get_bucketed_path

            if 'file' not in await request.files:
                return jsonify({"error": "No file part"}), 400

            files = (await request.files).getlist('file')
            if not files or files[0].filename == '':
                return jsonify({"error": "No selected file"}), 400

            processed_count = 0
            last_processed_path = None
            for file in files:
                if file and file.filename:
                    filename = secure_filename(file.filename)

                    # Save to bucketed directory
                    bucket_dir = ensure_bucket_dir(filename, config.IMAGE_DIRECTORY)
                    filepath = os.path.join(bucket_dir, filename)
                    await file.save(filepath)

                    # Process the file (already in bucketed location, so don't move)
                    success, msg = processing.process_image_file(filepath, move_from_ingest=False)
                    if success:
                        processed_count += 1
                        # Keep track of the last successfully processed image's path
                        # Use bucketed path for URL
                        bucketed_path = get_bucketed_path(filename, "images")
                        last_processed_path = bucketed_path
                    else:
                        print(f"Failed to process {filename}: {msg}")

            if processed_count > 0:
                models.load_data_from_db()

            redirect_url = None
            # If any image was processed, generate a URL for the last one
            if last_processed_path:
                redirect_url = url_for('main.show_image', filepath=last_processed_path)

            return jsonify({
                "status": "success",
                "message": f"Successfully processed {processed_count} image(s).",
                "redirect_url": redirect_url
            })

        # GET request renders the upload page
        return await render_template(
            'upload.html',
            stats=query_service.get_enhanced_stats(),
            query='',
            random_tags=[],
            app_name=config.APP_NAME
        )

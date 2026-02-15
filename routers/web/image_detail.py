"""
Image detail and viewing routes.
"""

from quart import render_template, make_response
import config
from database import models
from services import query_service
from services.tag_display_service import prepare_tags_for_display
from utils import get_thumbnail_path
from utils.file_utils import normalize_image_path
from utils.decorators import login_required


def register_routes(blueprint):
    """Register image detail routes on the given blueprint."""
    
    @blueprint.route('/view/<path:filepath>')
    @login_required
    async def show_image(filepath):
        lookup_path = normalize_image_path(filepath)
        
        # Use the merged tags function to include high-confidence local tagger predictions
        from repositories.data_access import get_image_details_with_merged_tags
        from services import upscaler_service
        
        data = get_image_details_with_merged_tags(lookup_path)
        if not data:
            return "Image not found", 404

        # Check for upscaled version
        upscaled_image_url = upscaler_service.get_upscale_url(lookup_path)

        # REMOVED: stats = query_service.get_enhanced_stats()
        # Stats are now lazy-loaded via API endpoint for instant page rendering

        # Prepare all tag-related data using the tag display service
        tag_data = prepare_tags_for_display(data)

        # REMOVED: Family images and similar images queries
        # These are now lazy-loaded via API endpoint for instant page rendering
        # The main image can start loading while these are fetched asynchronously

        # REMOVED: tag_deltas = models.get_image_deltas(lookup_path)
        # Tag deltas are now lazy-loaded via API endpoint

        # Get thumbnail path for progressive loading
        thumbnail_path = get_thumbnail_path(filepath)

        # Get sidebar config fresh (not cached module-level values) so changes take effect without restart
        from services.config_service import load_config
        config_yml = load_config()
        sidebar_sources = str(config_yml.get('SIMILAR_SIDEBAR_SOURCES', 'both')).lower()
        sidebar_show_chips = config_yml.get('SIMILAR_SIDEBAR_SHOW_CHIPS', True)
        if isinstance(sidebar_show_chips, str):
            sidebar_show_chips = sidebar_show_chips.lower() in ('true', '1', 'yes')

        # Information panel default: collapsed unless INFORMATION_PANEL_DEFAULT_VISIBLE is True
        ip_visible = config_yml.get('INFORMATION_PANEL_DEFAULT_VISIBLE', getattr(config, 'INFORMATION_PANEL_DEFAULT_VISIBLE', False))
        information_panel_default_collapsed = not (
            ip_visible if isinstance(ip_visible, bool) else str(ip_visible).lower() in ('true', '1', 'yes')
        )

        html = await render_template(
            'image.html',
            filepath=filepath,
            thumbnail_path=thumbnail_path,
            tags=tag_data['tags_with_counts'],
            categorized_tags=tag_data['categorized_tags'],
            extended_grouped_tags=tag_data['extended_grouped_tags'],
            metadata=data.get('raw_metadata'),
            # REMOVED: family_images, related_images, stats, tag_deltas, image_pools
            # These are now loaded asynchronously via API for instant page rendering
            family_images=[],  # Loaded via JS from /api/image/.../similar
            related_images=[],  # Loaded via JS from /api/image/.../similar
            stats=None,  # Loaded via JS from /api/image/.../stats
            random_tags=[],
            data=data,
            app_name=config.APP_NAME,
            tag_deltas=[],  # Loaded via JS from /api/image/.../deltas
            merged_general_tags=tag_data['merged_general_tags'],  # Pass to template for potential styling
            upscaled_image_url=upscaled_image_url,
            image_pools=[],  # Loaded via JS from /api/image/.../pools
            implied_tag_names=tag_data['implied_tag_names'],  # Tags implied by implication rules
            similar_sidebar_sources=sidebar_sources,
            similar_sidebar_show_chips=sidebar_show_chips,
            information_panel_default_collapsed=information_panel_default_collapsed
        )
        
        # Add cache-busting headers for dynamic content
        response = await make_response(html)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        # Add ETag based on upscale status for automatic cache invalidation
        etag = upscaler_service.get_upscale_etag(lookup_path)
        response.headers['ETag'] = etag
        
        return response

    @blueprint.route('/similar-visual/<path:filepath>')
    @login_required
    async def similar_visual(filepath):
        """Visual similarity page with adjustable threshold."""
        from services import similarity_service
        from utils import get_thumbnail_path
        
        lookup_path = normalize_image_path(filepath)
        threshold = config.VISUAL_SIMILARITY_THRESHOLD
        exclude_family = True  # Default to excluding family
        
        # Get visually similar images
        similar_images = similarity_service.find_similar_images(
            lookup_path,
            threshold=threshold,
            limit=100,
            exclude_family=exclude_family
        )
        
        stats = query_service.get_enhanced_stats()
        thumbnail_path = get_thumbnail_path(filepath)
        
        html = await render_template(
            'similar_visual.html',
            filepath=filepath,
            thumbnail_path=thumbnail_path,
            images=similar_images,
            threshold=threshold,
            exclude_family=exclude_family,
            stats=stats,
            app_name=config.APP_NAME
        )
        
        # Add cache-busting headers for dynamic content
        response = await make_response(html)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @blueprint.route('/raw/<path:filepath>')
    @login_required
    async def show_raw_data(filepath):
        lookup_path = normalize_image_path(filepath)
        data = models.get_image_details(lookup_path)
        if not data or not data.get('raw_metadata'):
            return "Raw metadata not found", 404

        raw_metadata = data.get('raw_metadata')
        stats = query_service.get_enhanced_stats()

        html = await render_template(
            'raw_data.html',
            filepath=filepath,
            raw_data=raw_metadata,
            stats=stats,
            query='',
            random_tags=[],
            app_name=config.APP_NAME
        )
        
        # Add cache-busting headers for dynamic content
        response = await make_response(html)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

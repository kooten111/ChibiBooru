"""
Image detail and viewing routes.
"""

from quart import render_template
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

        stats = query_service.get_enhanced_stats()

        # Prepare all tag-related data using the tag display service
        tag_data = prepare_tags_for_display(data)

        # Fetch family images first to exclude them from similarity results
        parent_child_images = models.get_related_images(data.get('post_id'), data.get('parent_id'))
        parent_child_paths = set()
        for img in parent_child_images:
            img['match_type'] = img['type']  # 'parent' or 'child'
            img['thumb'] = get_thumbnail_path(img['path'])
            
            # Normalize path to include 'images/' prefix for consistency with similarity results
            # DB usually stores bare filename, but similarity/query services return 'images/filename'
            p = img['path']
            if not p.startswith('images/'):
                p = f"images/{p}"
            parent_child_paths.add(p)

        # Get similar images - load tag-based results immediately (fast)
        # FAISS/semantic results will be loaded asynchronously via JavaScript
        # This prevents page blocking while FAISS searches
        similar_images = query_service.find_related_by_tags(filepath, limit=40)
        
        # Filter out self-match and family
        similar_images = [
            img for img in similar_images
            if normalize_image_path(img['path']) != lookup_path and img['path'] not in parent_child_paths
        ]
        
        # Tag-only results - ensure correct labeling
        for img in similar_images:
            img['primary_source'] = 'tag'
        
        # Filter similar images to remove any that are already in the parent/child list
        # (Note: we already filtered them from 'mixed' lists above, but 'filtered_similar' variable is used for combination)
        filtered_similar = [img for img in similar_images if img['path'] not in parent_child_paths]

        # Combine the lists, parents/children first
        combined_related = parent_child_images + filtered_similar

        # Get tag deltas for this image
        tag_deltas = models.get_image_deltas(lookup_path)

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

        return await render_template(
            'image.html',
            filepath=filepath,
            thumbnail_path=thumbnail_path,
            tags=tag_data['tags_with_counts'],
            categorized_tags=tag_data['categorized_tags'],
            extended_grouped_tags=tag_data['extended_grouped_tags'],
            metadata=data.get('raw_metadata'),
            family_images=parent_child_images,  # Parent/child for floating badge
            related_images=filtered_similar,     # Only similar images in sidebar
            stats=stats,
            random_tags=[],
            data=data,
            app_name=config.APP_NAME,
            tag_deltas=tag_deltas,
            merged_general_tags=tag_data['merged_general_tags'],  # Pass to template for potential styling
            upscaled_image_url=upscaled_image_url,
            image_pools=models.get_pools_for_image(data['id']) if data and data.get('id') else [],
            implied_tag_names=tag_data['implied_tag_names'],  # Tags implied by implication rules
            similar_sidebar_sources=sidebar_sources,
            similar_sidebar_show_chips=sidebar_show_chips,
            information_panel_default_collapsed=information_panel_default_collapsed
        )

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
        
        return await render_template(
            'similar_visual.html',
            filepath=filepath,
            thumbnail_path=thumbnail_path,
            images=similar_images,
            threshold=threshold,
            exclude_family=exclude_family,
            stats=stats,
            app_name=config.APP_NAME
        )

    @blueprint.route('/raw/<path:filepath>')
    @login_required
    async def show_raw_data(filepath):
        lookup_path = normalize_image_path(filepath)
        data = models.get_image_details(lookup_path)
        if not data or not data.get('raw_metadata'):
            return "Raw metadata not found", 404

        raw_metadata = data.get('raw_metadata')
        stats = query_service.get_enhanced_stats()

        return await render_template(
            'raw_data.html',
            filepath=filepath,
            raw_data=raw_metadata,
            stats=stats,
            query='',
            random_tags=[],
            app_name=config.APP_NAME
        )

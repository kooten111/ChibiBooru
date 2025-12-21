# ChibiBooru UI Improvements - Implementation Guide

This document covers three major UI improvements. The detailed specifications have been moved to separate documents:

1. **[Image Viewer - Portrait-optimized layout](UI_Image_Viewer.md)**
   - Detailed plan for the image viewer (`image.html`).
   - Includes collapsible sidebars, focus mode, and improved floating actions.

2. **[Gallery - Quick filter sidebar](UI_Gallery.md)**
   - Detailed plan for the main gallery (`index.html`).
   - Includes quick filters, grid size toggle, and recent searches.

## Implementation Order

1. **Start with Gallery** - Most frequently used, biggest impact
2. **Then Image Viewer** - Improves the core viewing experience
3. **Finally Similarity Search** - More specialized feature

## Testing Checklist

For each page:

- [ ] Desktop (1920×1080+)
- [ ] Tablet (768-1024px)
- [ ] Mobile (< 768px)
- [ ] Keyboard navigation works
- [ ] State persists in localStorage
- [ ] No console errors
- [ ] Performance acceptable with 100+ items
#!/usr/bin/env python3
"""
Standalone script: given a ChibiBooru image URL, output its tags as a comma-delimited list.

Usage:
  python scripts/get_image_tags_from_url.py "https://your-booru.example.com/view/images/abc/photo.jpg"
  python scripts/get_image_tags_from_url.py "https://your-booru.example.com/view/photo.jpg"

Run from the ChibiBooru project root (so config and database paths resolve).
Uses the project venv if available.
"""

import sys
from urllib.parse import urlparse, unquote


def filepath_from_chibibooru_url(url: str) -> str:
    """Extract normalized filepath from a ChibiBooru image view URL."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    path = path.lstrip("/")

    # Route is /view/<path:filepath>
    if path.lower().startswith("view/"):
        path = path[5:]  # drop "view/"
    elif path.lower().startswith("view"):
        # "view" with no trailing slash but rest of path
        rest = path[4:].lstrip("/")
        path = rest
    else:
        raise ValueError("URL does not look like a ChibiBooru image view URL (expected path containing /view/...)")

    # Normalize: remove leading slash and optional "images/" prefix
    path = path.lstrip("/")
    if path.lower().startswith("images/"):
        path = path[7:]

    return path or None


def main():
    if len(sys.argv) < 2:
        print("Usage: get_image_tags_from_url.py <chibibooru_image_url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1].strip()
    if not url:
        print("Usage: get_image_tags_from_url.py <chibibooru_image_url>", file=sys.stderr)
        sys.exit(1)

    try:
        filepath = filepath_from_chibibooru_url(url)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not filepath:
        print("Could not extract filepath from URL.", file=sys.stderr)
        sys.exit(1)

    # Import after parsing so invalid URLs fail fast without loading project
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.chdir(project_root)

    from repositories.data_access import get_image_details_with_merged_tags

    data = get_image_details_with_merged_tags(filepath)
    if not data:
        print("Image not found.", file=sys.stderr)
        sys.exit(1)

    # Build full tag list: all_tags (space-separated) + any merged general tags not already present
    all_tags_str = (data.get("all_tags") or "").strip()
    tags = [t for t in all_tags_str.split() if t]

    merged = data.get("merged_general_tags") or []
    existing = set(tags)
    for t in merged:
        if t and t not in existing:
            tags.append(t)
            existing.add(t)

    print(", ".join(tags))


if __name__ == "__main__":
    main()

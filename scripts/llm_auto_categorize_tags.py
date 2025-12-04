#!/usr/bin/env python3
"""
Automated tag categorization using a local LLM via LM Studio.

This script fetches uncategorized tags from the database and uses a local
Mistral LLM running on LM Studio to automatically categorize them according
to the extended tag categorization schema.
"""

import sys
import os
import json
import requests
import sqlite3
from typing import Optional, List, Dict
from time import sleep

# Add parent directory to path to import from project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection
from services.tag_categorization_service import EXTENDED_CATEGORIES, TAG_CATEGORIES

# LM Studio API configuration
LM_STUDIO_URL = "http://192.168.1.122:1234/v1/chat/completions"
MODEL_NAME = "mistralai/ministral-3-14b-reasoning"  # Adjust if needed

# Category descriptions for the LLM
CATEGORY_GUIDE = """
## Extended Tag Categories (22 categories):

Group 1: Identity (Permanent traits)
- 00_Subject_Count: Count & Gender (1girl, solo, 1boy, 2girls)
- 01_Body_Physique: Permanent body traits (breasts, tail, animal_ears, muscular)
- 02_Body_Hair: Head hair only (long_hair, twintails, blonde_hair, braid)
- 03_Body_Face: Eye color & permanent face marks (blue_eyes, sharp_teeth, scar)
- 04_Body_Genitalia: NSFW Anatomy (nipples, penis, pussy, anus)

Group 2: Context (Temporary/Situational)
- 05_Attire_Main: Main outer clothing (shirt, dress, school_uniform, jacket)
- 06_Attire_Inner: Underwear/Swimwear (panties, bra, bikini, boxers)
- 07_Attire_Legwear: Socks & Hosiery (thighhighs, pantyhose, kneehighs)
- 08_Attire_Acc: Accessories worn (gloves, ribbon, glasses, hat)
- 09_Action: Active verbs (holding, eating, walking, grabbing)
- 10_Pose: Static body position & gaze (sitting, looking_at_viewer, standing, spread_legs)
- 11_Expression: Temporary emotion (blush, smile, crying, angry)
- 12_Sexual_Act: NSFW interaction (sex, vaginal, fellatio, masturbation)
- 13_Object: Props not worn (flower, weapon, phone, cup)
- 14_Setting: Background/Time/Location (simple_background, outdoors, bedroom, night)
- 21_Status: State of being (nude, wet, censored, clothed)

Group 3: Technical/Meta
- 15_Framing: Camera angle/Crop (upper_body, cowboy_shot, close-up, from_behind)
- 16_Focus: Specific part focus (foot_focus, solo_focus, face_focus)
- 17_Style_Art: Medium/Art style (monochrome, comic, sketch, realistic)
- 18_Style_Tech: Visual effects (blurry, chromatic_aberration, depth_of_field)
- 19_Meta_Attributes: General metadata (highres, absurdres, bad_anatomy, artist_name)
- 20_Meta_Text: Text & UI elements (speech_bubble, signature, watermark)
"""

SYSTEM_PROMPT = f"""You are a tag categorization expert for an image booru database. Your job is to categorize tags according to the extended categorization schema.

{CATEGORY_GUIDE}

When given a tag, respond with ONLY the category key (e.g., "09_Action" or "02_Body_Hair").
Do not include any explanation, just the category key.

Examples:
- "running" -> 09_Action
- "blonde_hair" -> 02_Body_Hair
- "smile" -> 11_Expression
- "upper_body" -> 15_Framing
- "1girl" -> 00_Subject_Count
- "blue_eyes" -> 03_Body_Face
- "school_uniform" -> 05_Attire_Main
- "outdoors" -> 14_Setting
"""


def categorize_tag_with_llm(tag_name: str, usage_count: int, max_retries: int = 3) -> Optional[str]:
    """
    Use the local LLM to categorize a single tag.

    Args:
        tag_name: Name of the tag to categorize
        usage_count: How many times this tag is used (for context)
        max_retries: Maximum number of retry attempts

    Returns:
        Category key or None if categorization fails
    """
    user_prompt = f"Tag: {tag_name}\nUsage count: {usage_count}\n\nCategory:"

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,  # Low temperature for consistent categorization
        "max_tokens": 50,
        "stop": ["\n", " "]  # Stop at newline or space
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(LM_STUDIO_URL, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()
            category = data['choices'][0]['message']['content'].strip()

            # Validate the category
            if category in TAG_CATEGORIES:
                return category
            else:
                print(f"  Warning: Invalid category '{category}' for tag '{tag_name}' (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    sleep(1)  # Brief pause before retry

        except requests.exceptions.RequestException as e:
            print(f"  Error communicating with LLM (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(2)  # Longer pause on connection error
        except (KeyError, json.JSONDecodeError) as e:
            print(f"  Error parsing LLM response (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(1)

    return None


def get_uncategorized_tags(limit: int = 100) -> List[Dict]:
    """Get uncategorized tags from the database."""
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                t.name,
                t.category,
                t.extended_category,
                COUNT(DISTINCT it.image_id) as usage_count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            WHERE t.extended_category IS NULL
            GROUP BY t.name, t.category, t.extended_category
            HAVING usage_count > 0
            ORDER BY usage_count DESC
            LIMIT ?
        """, (limit,))

        tags = []
        for row in cur.fetchall():
            tags.append({
                'name': row['name'],
                'current_category': row['category'],
                'usage_count': row['usage_count']
            })

        return tags


def set_tag_category(tag_name: str, category: str) -> bool:
    """Set the extended category for a tag in the database."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tags SET extended_category = ? WHERE name = ?",
                (category, tag_name)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"  Database error: {e}")
        return False


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description='Automatically categorize tags using a local LLM')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Number of tags to process per batch (default: 100)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum total number of tags to process (default: unlimited)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview categorizations without saving to database')
    parser.add_argument('--skip', type=int, default=0,
                        help='Skip the first N tags (useful for resuming)')

    args = parser.parse_args()

    print("=" * 70)
    print("Automated Tag Categorization using Local LLM")
    print("=" * 70)
    print(f"\nLM Studio URL: {LM_STUDIO_URL}")
    print(f"Batch size: {args.batch_size}")
    if args.limit:
        print(f"Total limit: {args.limit}")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be saved")
    if args.skip:
        print(f"Skipping first {args.skip} tags")
    print()

    # Test LLM connection
    print("Testing LLM connection...")
    try:
        test_response = requests.get(LM_STUDIO_URL.replace('/v1/chat/completions', '/v1/models'), timeout=5)
        test_response.raise_for_status()
        print("✓ LLM connection successful\n")
    except Exception as e:
        print(f"✗ Failed to connect to LLM: {e}")
        print("Make sure LM Studio is running at http://192.168.1.122:1234")
        return 1

    # Get uncategorized tags
    print(f"Fetching uncategorized tags...")
    tags = get_uncategorized_tags(limit=args.batch_size + args.skip)

    if not tags:
        print("No uncategorized tags found!")
        return 0

    # Apply skip
    if args.skip:
        tags = tags[args.skip:]

    # Apply limit
    if args.limit:
        tags = tags[:args.limit]

    total_tags = len(tags)
    print(f"Found {total_tags} tags to process\n")

    # Process tags
    successful = 0
    failed = 0
    skipped = 0

    for idx, tag_info in enumerate(tags, 1):
        tag_name = tag_info['name']
        usage_count = tag_info['usage_count']

        print(f"[{idx}/{total_tags}] Processing: {tag_name} (used {usage_count}x)")

        # Get category from LLM
        category = categorize_tag_with_llm(tag_name, usage_count)

        if category:
            # Get human-readable category name
            cat_display = next((c[1] for c in EXTENDED_CATEGORIES if c[0] == category), category)
            print(f"  ✓ Categorized as: {category} ({cat_display})")

            if not args.dry_run:
                if set_tag_category(tag_name, category):
                    successful += 1
                else:
                    failed += 1
                    print(f"  ✗ Failed to save to database")
            else:
                successful += 1
        else:
            print(f"  ✗ Failed to categorize")
            failed += 1

        # Brief pause to avoid overwhelming the LLM
        if idx < total_tags:
            sleep(0.1)

    # Summary
    print("\n" + "=" * 70)
    print("Categorization Complete")
    print("=" * 70)
    print(f"Total processed: {total_tags}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Success rate: {(successful/total_tags*100):.1f}%")

    if args.dry_run:
        print("\nDRY RUN - No changes were saved to the database")

    return 0


if __name__ == "__main__":
    exit(main())

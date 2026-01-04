#!/usr/bin/env python3
"""
Automated tag categorization using a local LLM via LM Studio.

This script fetches uncategorized tags from the ChibiBooru API and uses a local
Mistral LLM running on LM Studio to automatically categorize them according
to the extended tag categorization schema.
"""

import sys
import os
import json
import requests
from typing import Optional, List, Dict
from time import sleep

# API configuration (can be overridden via environment variables)
CHIBIBOORU_API_URL = os.environ.get('CHIBIBOORU_API_URL', 'http://localhost:5000/api')
LM_STUDIO_URL = os.environ.get('LM_STUDIO_URL', 'http://192.168.1.2:1234/v1/chat/completions')
MODEL_NAME = os.environ.get('LM_STUDIO_MODEL', 'mistralai/ministral-3-14b-reasoning')

# Load category definitions from API
TAG_CATEGORIES = None
EXTENDED_CATEGORIES = None

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

IMPORTANT: Respond with ONLY the exact category key from the list above. Common mistakes to avoid:
- There is NO "19_Meta_Text" category - use "20_Meta_Text" for text/UI elements
- Category 19 is "19_Meta_Attributes" (for metadata like highres, absurdres)
- Category 20 is "20_Meta_Text" (for text/speech bubbles/watermarks)

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
- "holding_weapon" -> 09_Action
- "sitting" -> 10_Pose
- "spread_legs" -> 10_Pose
- "cup" -> 13_Object
- "phone" -> 13_Object
- "speech_bubble" -> 20_Meta_Text
- "watermark" -> 20_Meta_Text
- "symbol" -> 20_Meta_Text
- "highres" -> 19_Meta_Attributes
- "nude" -> 21_Status
- "wet" -> 21_Status
- "thighhighs" -> 07_Attire_Legwear
- "gloves" -> 08_Attire_Acc
"""


def auto_correct_category(category: str) -> Optional[str]:
    """
    Auto-correct common LLM mistakes in category names.

    Args:
        category: The category string returned by the LLM

    Returns:
        Corrected category or None if cannot be corrected
    """
    # Common mistakes mapping
    corrections = {
        '19_Meta_Text': '20_Meta_Text',  # Most common mistake
        '06_Attire_Legwear': '07_Attire_Legwear',  # Sometimes confuses numbering
        '02_Body_Physique': '01_Body_Physique',  # Sometimes confuses numbering
    }

    # Try direct correction
    if category in corrections:
        return corrections[category]

    # Try fuzzy matching - if they got the name right but number wrong
    category_lower = category.lower()
    for valid_cat in TAG_CATEGORIES:
        valid_lower = valid_cat.lower()
        # Check if the text part matches (after the number prefix)
        if '_' in category and '_' in valid_cat:
            user_text = '_'.join(category.split('_')[1:]).lower()
            valid_text = '_'.join(valid_cat.split('_')[1:]).lower()
            if user_text == valid_text:
                return valid_cat

    return None


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

            # Try auto-correction
            corrected = auto_correct_category(category)
            if corrected:
                print(f"  Info: Auto-corrected '{category}' -> '{corrected}'")
                return corrected

            # If still invalid, log and retry
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


def load_categories():
    """Load category definitions from the API."""
    global TAG_CATEGORIES, EXTENDED_CATEGORIES

    try:
        response = requests.get(f"{CHIBIBOORU_API_URL}/tag_categorize/tags?limit=1", timeout=10)
        response.raise_for_status()
        data = response.json()

        TAG_CATEGORIES = data.get('categories', [])
        EXTENDED_CATEGORIES = data.get('extended_categories', [])

        return True
    except Exception as e:
        print(f"Failed to load categories from API: {e}")
        return False


def get_uncategorized_tags(limit: int = 100) -> List[Dict]:
    """Get uncategorized tags from the API."""
    try:
        response = requests.get(
            f"{CHIBIBOORU_API_URL}/tag_categorize/tags",
            params={'limit': limit},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        tags = []
        for tag in data.get('tags', []):
            tags.append({
                'name': tag['name'],
                'current_category': tag.get('current_category'),
                'usage_count': tag.get('usage_count', 0)
            })

        return tags
    except Exception as e:
        print(f"Failed to fetch uncategorized tags from API: {e}")
        return []


def set_tag_category(tag_name: str, category: str) -> bool:
    """Set the extended category for a tag via the API."""
    try:
        response = requests.post(
            f"{CHIBIBOORU_API_URL}/tag_categorize/set",
            json={'tag_name': tag_name, 'category': category},
            timeout=10
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"  API error: {e}")
        return False


def main():
    """Main execution function."""
    import argparse

    global CHIBIBOORU_API_URL

    parser = argparse.ArgumentParser(description='Automatically categorize tags using a local LLM')
    parser.add_argument('--api-url', type=str, default=CHIBIBOORU_API_URL,
                        help=f'ChibiBooru API base URL (default: {CHIBIBOORU_API_URL})')
    parser.add_argument('--batch-size', type=int, default=100,
                        help='Number of tags to process per batch (default: 100)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Maximum total number of tags to process (default: unlimited)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview categorizations without saving to database')
    parser.add_argument('--skip', type=int, default=0,
                        help='Skip the first N tags (useful for resuming)')

    args = parser.parse_args()

    # Update API URL if provided
    CHIBIBOORU_API_URL = args.api_url

    print("=" * 70)
    print("Automated Tag Categorization using Local LLM")
    print("=" * 70)
    print(f"\nChibiBooru API: {CHIBIBOORU_API_URL}")
    print(f"LM Studio URL: {LM_STUDIO_URL}")
    print(f"Batch size: {args.batch_size}")
    if args.limit:
        print(f"Total limit: {args.limit}")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be saved")
    if args.skip:
        print(f"Skipping first {args.skip} tags")
    print()

    # Test API connection
    print("Testing ChibiBooru API connection...")
    if not load_categories():
        print("✗ Failed to connect to ChibiBooru API")
        print(f"Make sure the server is running at {CHIBIBOORU_API_URL}")
        return 1
    print(f"✓ API connection successful - loaded {len(TAG_CATEGORIES)} categories\n")

    # Test LLM connection
    print("Testing LLM connection...")
    try:
        test_response = requests.get(LM_STUDIO_URL.replace('/v1/chat/completions', '/v1/models'), timeout=5)
        test_response.raise_for_status()
        print("✓ LLM connection successful\n")
    except Exception as e:
        print(f"✗ Failed to connect to LLM: {e}")
        print(f"Make sure LM Studio is running at {LM_STUDIO_URL.replace('/v1/chat/completions', '')}")
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

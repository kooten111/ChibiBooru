#!/usr/bin/env python3
"""
Augment default_tag_categorizations.json with the 50,000 most popular tags from danbooru_e621_merged.csv.
This script:
1. Parses the CSV file sorted by usage count
2. Takes the top 50,000 most popular tags
3. Identifies tags/aliases not yet in default_tag_categorizations.json
4. Uses the LLM to categorize new tags with concurrent requests
5. Merges results back into the JSON file
"""

import json
import csv
import os
import sys
import requests
from typing import Optional, Dict, List, Set, Tuple
from time import sleep
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================================
# CONFIGURATION & USAGE
# ============================================================================
# Environment variables:
#   LLM_CONCURRENT_WORKERS  - Number of concurrent LLM requests (default: 4)
#                             Higher values = faster but more server load
#                             Example: LLM_CONCURRENT_WORKERS=8 python scripts/augment.py
#   LM_STUDIO_URL           - LM Studio API endpoint (default: http://192.168.1.2:1234/v1/chat/completions)
#   LM_STUDIO_MODEL         - Model name (default: mistralai/ministral-3-14b-reasoning)
# ============================================================================

# Configuration
CSV_PATH = './data/danbooru_e621_merged.csv'
JSON_PATH = './data/default_tag_categorizations.json'
LM_STUDIO_URL = os.environ.get('LM_STUDIO_URL', 'http://192.168.1.2:1234/v1/chat/completions')
MODEL_NAME = os.environ.get('LM_STUDIO_MODEL', 'mistralai/ministral-3-14b-reasoning')
TOP_N_TAGS = 50000
CONCURRENT_WORKERS = int(os.environ.get('LLM_CONCURRENT_WORKERS', '4'))  # Number of concurrent LLM requests
CHECKPOINT_INTERVAL = int(os.environ.get('CHECKPOINT_INTERVAL', '100'))  # Save progress every N tags
PROGRESS_FILE = './data/augment_progress.json'  # Tracks completed categorizations for resume

# Valid categories
VALID_CATEGORIES = [
    "00_Subject_Count",
    "01_Body_Physique",
    "02_Body_Hair",
    "03_Body_Face",
    "04_Body_Genitalia",
    "05_Attire_Main",
    "06_Attire_Inner",
    "07_Attire_Legwear",
    "08_Attire_Acc",
    "09_Action",
    "10_Pose",
    "11_Expression",
    "12_Sexual_Act",
    "13_Object",
    "14_Setting",
    "15_Framing",
    "16_Focus",
    "17_Style_Art",
    "18_Style_Tech",
    "19_Meta_Attributes",
    "20_Meta_Text",
    "21_Status",
]

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
"""


def auto_correct_category(category: str) -> Optional[str]:
    """Auto-correct common LLM mistakes in category names."""
    corrections = {
        '19_Meta_Text': '20_Meta_Text',
        '06_Attire_Legwear': '07_Attire_Legwear',
        '02_Body_Physique': '01_Body_Physique',
    }
    
    if category in corrections:
        return corrections[category]
    
    # Fuzzy matching
    category_lower = category.lower()
    for valid_cat in VALID_CATEGORIES:
        valid_lower = valid_cat.lower()
        if '_' in category and '_' in valid_cat:
            user_text = '_'.join(category.split('_')[1:]).lower()
            valid_text = '_'.join(valid_cat.split('_')[1:]).lower()
            if user_text == valid_text:
                return valid_cat
    
    return None


def categorize_tag_with_llm(tag_name: str, usage_count: int, max_retries: int = 3) -> Optional[str]:
    """Use LLM to categorize a single tag."""
    user_prompt = f"Tag: {tag_name}\nUsage count: {usage_count}\n\nCategory:"
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 50,
        "stop": ["\n", " "]
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(LM_STUDIO_URL, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            category = data['choices'][0]['message']['content'].strip()
            
            if category in VALID_CATEGORIES:
                return category
            
            corrected = auto_correct_category(category)
            if corrected:
                print(f"    Info: Auto-corrected '{category}' -> '{corrected}'")
                return corrected
            
            print(f"    Warning: Invalid category '{category}' (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                sleep(1)
        
        except requests.exceptions.RequestException as e:
            print(f"    Error communicating with LLM (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(2)
        except (KeyError, json.JSONDecodeError) as e:
            print(f"    Error parsing response (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep(1)
    
    return None


def parse_csv_tags() -> List[tuple]:
    """Parse CSV and return sorted list of (tag_name, usage_count, aliases)."""
    tags = []
    
    if not os.path.exists(CSV_PATH):
        print(f"❌ CSV file not found: {CSV_PATH}")
        return []
    
    print(f"📖 Parsing CSV file: {CSV_PATH}")
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 3:
                tag_name = row[0].strip()
                try:
                    usage_count = int(row[2])
                except (ValueError, IndexError):
                    usage_count = 0
                
                aliases = []
                if len(row) >= 4 and row[3]:
                    # Remove quotes and split aliases
                    aliases_str = row[3].strip('"')
                    aliases = [a.strip() for a in aliases_str.split(',') if a.strip()]
                
                tags.append((tag_name, usage_count, aliases))
    
    # Sort by usage count descending
    tags.sort(key=lambda x: x[1], reverse=True)
    
    print(f"✓ Parsed {len(tags)} tags from CSV")
    return tags


def load_existing_json() -> Dict:
    """Load existing JSON file and return tags dict."""
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON file not found: {JSON_PATH}")
        return {'tags': {}, 'categories': VALID_CATEGORIES}
    
    print(f"📖 Loading existing JSON: {JSON_PATH}")
    
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"✓ Loaded {len(data.get('tags', {}))} existing categorizations")
    return data


def load_progress() -> Dict[str, str]:
    """Load progress file if it exists (for resuming interrupted runs)."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                progress = json.load(f)
            
            if progress:
                print(f"📋 Found existing progress with {len(progress)} completed categorizations")
                return progress
        except Exception as e:
            print(f"⚠ Failed to load progress file: {e}")
    
    return {}


def save_progress(categorizations: Dict[str, str]) -> bool:
    """Save progress checkpoint to allow resuming."""
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(categorizations, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"⚠ Failed to save progress: {e}")
        return False


def find_new_tags(csv_tags: List[tuple], existing_json: Dict, limit: int = 50000) -> List[tuple]:
    """Find primary tags in top 50k that aren't in the existing JSON."""
    existing_tags: Set[str] = set(existing_json.get('tags', {}).keys())
    new_tags = []
    
    # Only look at primary tags in the top 50k
    for tag_name, usage_count, aliases in csv_tags[:limit]:
        if tag_name not in existing_tags:
            new_tags.append((tag_name, usage_count, aliases))
    
    print(f"✓ Found {len(new_tags)} new primary tags not in existing JSON (from top {limit})")
    return new_tags


def categorize_new_tags(new_tags: List[tuple], existing_progress: Dict[str, str]) -> Dict[str, str]:
    """Categorize new tags using LLM with concurrent requests, including their aliases.
    
    Saves progress checkpoints periodically to allow resuming if interrupted.
    """
    categorizations = existing_progress.copy()  # Start with any existing progress
    skipped_from_progress = len(existing_progress)
    
    # Filter out tags already in progress
    remaining_tags = [
        (tag_name, usage_count, aliases)
        for tag_name, usage_count, aliases in new_tags
        if tag_name not in existing_progress
    ]
    
    total = len(new_tags)
    remaining = len(remaining_tags)
    
    if remaining == 0:
        print(f"\n✓ All {total} tags already categorized from previous session!")
        return categorizations
    
    print(f"\n🤖 Categorizing {remaining} remaining tags (skipped {skipped_from_progress} from progress)...")
    print(f"   LLM URL: {LM_STUDIO_URL}")
    print(f"   Concurrent workers: {CONCURRENT_WORKERS}")
    print(f"   Checkpoint interval: {CHECKPOINT_INTERVAL} tags\n")
    
    # Test LLM connection first
    try:
        test_response = requests.get(
            LM_STUDIO_URL.replace('/v1/chat/completions', '/v1/models'),
            timeout=5
        )
        test_response.raise_for_status()
        print("✓ LLM connection successful\n")
    except Exception as e:
        print(f"❌ Failed to connect to LLM: {e}")
        print(f"   Make sure LM Studio is running at {LM_STUDIO_URL.replace('/v1/chat/completions', '')}")
        return categorizations
    
    successful = 0
    failed = 0
    aliases_added = 0
    completed = 0
    
    # Create a mapping from future to tag info for result processing
    future_to_tag: Dict = {}
    
    print(f"📤 Submitting {remaining} tags for concurrent categorization...\n")
    
    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
        # Submit all remaining categorization tasks
        for idx, (tag_name, usage_count, aliases) in enumerate(remaining_tags):
            future = executor.submit(categorize_tag_with_llm, tag_name, usage_count)
            future_to_tag[future] = (idx, tag_name, usage_count, aliases)
        
        # Process results as they complete
        for future in as_completed(future_to_tag):
            idx, tag_name, usage_count, aliases = future_to_tag[future]
            completed += 1
            
            # Get the result
            try:
                category = future.result()
                
                if category:
                    categorizations[tag_name] = category
                    print(f"[{completed}/{remaining}] {tag_name} ({usage_count:,} uses) ✓ {category}", end="")
                    successful += 1
                    
                    # Also add all aliases with the same category
                    if aliases:
                        for alias in aliases:
                            categorizations[alias] = category
                        aliases_added += len(aliases)
                        print(f" + {len(aliases)} aliases", end="")
                    
                    print()
                else:
                    print(f"[{completed}/{remaining}] {tag_name} ({usage_count:,} uses) ❌ Failed")
                    failed += 1
            
            except Exception as e:
                print(f"[{completed}/{remaining}] {tag_name} ❌ Error: {e}")
                failed += 1
            
            # Save checkpoint periodically
            if completed % CHECKPOINT_INTERVAL == 0:
                print(f"\n💾 Saving checkpoint ({completed}/{remaining} completed)...")
                if save_progress(categorizations):
                    print(f"✓ Checkpoint saved\n")
    
    print(f"\n✓ Categorization Session Complete:")
    print(f"  Session: {successful} new tags + {aliases_added} aliases")
    print(f"  Cumulative total: {len(categorizations)} entries in progress")
    if failed > 0:
        print(f"  Failed: {failed}")
    
    # Save final state
    save_progress(categorizations)
    
    return categorizations


def merge_and_save(existing_json: Dict, new_categorizations: Dict) -> bool:
    """Merge new categorizations into JSON and save."""
    print(f"\n💾 Merging results...")
    
    tags_dict = existing_json.get('tags', {})
    
    # Add new categorizations
    tags_dict.update(new_categorizations)
    
    # Update metadata
    existing_json['tag_count'] = len(tags_dict)
    existing_json['export_date'] = datetime.now().isoformat()
    
    print(f"✓ Merged {len(new_categorizations)} new categorizations")
    print(f"✓ Total tags now: {len(tags_dict)}")
    
    # Verify all categories are present
    categories_used = set(tags_dict.values())
    unused_categories = set(VALID_CATEGORIES) - categories_used
    
    if unused_categories:
        print(f"⚠ Unused categories: {sorted(unused_categories)}")
    
    # Save to file
    print(f"\n📝 Saving to {JSON_PATH}...")
    
    try:
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(existing_json, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Successfully saved!")
        
        # Show file size
        file_size = os.path.getsize(JSON_PATH) / (1024 * 1024)
        print(f"   File size: {file_size:.2f} MB")
        
        return True
    
    except Exception as e:
        print(f"❌ Failed to save: {e}")
        return False


def main():
    """Main execution."""
    print("=" * 70)
    print("Augment Default Tag Categorizations from CSV")
    print("=" * 70)
    print(f"Goal: Ensure the top {TOP_N_TAGS:,} most popular tags are categorized")
    print(f"Concurrent workers: {CONCURRENT_WORKERS} (set LLM_CONCURRENT_WORKERS env var to change)")
    print(f"Checkpoint interval: {CHECKPOINT_INTERVAL} (set CHECKPOINT_INTERVAL env var to change)")
    print()
    
    # Parse CSV
    csv_tags = parse_csv_tags()
    if not csv_tags:
        return 1
    
    # Load existing JSON
    existing_json = load_existing_json()
    
    # Load progress from previous runs
    existing_progress = load_progress()
    
    # Get top 50k tags
    top_50k = {tag[0] for tag in csv_tags[:TOP_N_TAGS]}
    already_categorized = len(top_50k & set(existing_json.get('tags', {}).keys()))
    
    print(f"Coverage status: {already_categorized:,}/{TOP_N_TAGS:,} top tags already categorized")
    print()
    
    # Find new tags in top 50k
    new_tags = find_new_tags(csv_tags, existing_json, limit=TOP_N_TAGS)
    if not new_tags:
        print("✓ All top 50,000 tags already categorized!")
        
        # Clean up progress file if all tags are done
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print(f"✓ Cleaned up progress file")
        
        return 0
    
    # Categorize with LLM
    new_categorizations = categorize_new_tags(new_tags, existing_progress)
    if not new_categorizations:
        print("❌ No tags were successfully categorized")
        return 1
    
    # Merge and save
    if merge_and_save(existing_json, new_categorizations):
        # Clean up progress file on successful completion
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            print(f"✓ Cleaned up progress file")
        
        print("\n" + "=" * 70)
        print("✓ Augmentation complete!")
        print(f"✓ Top {TOP_N_TAGS:,} most popular tags now covered")
        print("=" * 70)
        return 0
    else:
        return 1


if __name__ == "__main__":
    exit(main())

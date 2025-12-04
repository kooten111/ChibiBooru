# Automated Tag Categorization with LLM

This script uses your local Mistral LLM (running on LM Studio) to automatically categorize tags according to the extended tag categorization schema.

## Prerequisites

1. **LM Studio running**: Make sure LM Studio is running with a model loaded at `http://192.168.1.122:1234`
2. **Python dependencies**: The script uses the existing project dependencies

## Basic Usage

```bash
# Categorize the 100 most frequently used uncategorized tags
python scripts/llm_auto_categorize_tags.py

# Preview what would happen without saving (dry run)
python scripts/llm_auto_categorize_tags.py --dry-run

# Process a specific number of tags
python scripts/llm_auto_categorize_tags.py --batch-size 50

# Set a maximum limit
python scripts/llm_auto_categorize_tags.py --limit 1000
```

## Advanced Options

### Dry Run Mode
Test the categorization without modifying the database:
```bash
python scripts/llm_auto_categorize_tags.py --dry-run --batch-size 20
```

### Resume Processing
If the script gets interrupted, you can skip already processed tags:
```bash
# Skip the first 100 tags
python scripts/llm_auto_categorize_tags.py --skip 100
```

### Process All Tags in Batches
Process a large number of tags in batches:
```bash
# Process 500 tags at a time
python scripts/llm_auto_categorize_tags.py --batch-size 500
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--batch-size N` | Number of tags to fetch per batch | 100 |
| `--limit N` | Maximum total tags to process | unlimited |
| `--dry-run` | Preview without saving to database | off |
| `--skip N` | Skip the first N tags (for resuming) | 0 |

## How It Works

1. **Fetches uncategorized tags** from the database (ordered by usage frequency)
2. **Sends each tag to the LLM** with context about the 22 extended categories
3. **Validates the response** to ensure it's a valid category
4. **Updates the database** with the categorized tag (unless in dry-run mode)

## Categories

The script categorizes tags into 22 extended categories:

**Identity (Permanent)**
- 00_Subject_Count - Count & Gender
- 01_Body_Physique - Body traits
- 02_Body_Hair - Hair properties
- 03_Body_Face - Eyes & face
- 04_Body_Genitalia - NSFW anatomy

**Context (Situational)**
- 05_Attire_Main - Main clothing
- 06_Attire_Inner - Underwear/swimwear
- 07_Attire_Legwear - Socks & hosiery
- 08_Attire_Acc - Accessories
- 09_Action - Active verbs
- 10_Pose - Body position
- 11_Expression - Emotions
- 12_Sexual_Act - NSFW interactions
- 13_Object - Props
- 14_Setting - Location/background
- 21_Status - State of being

**Technical/Meta**
- 15_Framing - Camera angle
- 16_Focus - Part focus
- 17_Style_Art - Art style
- 18_Style_Tech - Visual effects
- 19_Meta_Attributes - Metadata
- 20_Meta_Text - Text & UI

## Performance Tips

1. **Use batch processing**: Start with smaller batches to test, then increase
2. **Monitor LLM performance**: The script uses low temperature (0.1) for consistency
3. **Retry logic**: The script automatically retries failed categorizations up to 3 times
4. **Rate limiting**: Brief pauses between requests prevent overwhelming the LLM

## Troubleshooting

### Connection Error
```
✗ Failed to connect to LLM: ...
```
- Ensure LM Studio is running at http://192.168.1.122:1234
- Check that a model is loaded in LM Studio
- Verify network connectivity

### Invalid Categories
If the LLM returns invalid categories:
- The script will retry up to 3 times
- Consider adjusting the model or temperature settings in the script

### Database Locked
If you get database locked errors:
- Make sure no other processes are accessing the database
- The script uses proper connection handling to prevent locks

## Example Session

```bash
$ python scripts/llm_auto_categorize_tags.py --batch-size 20 --dry-run

======================================================================
Automated Tag Categorization using Local LLM
======================================================================

LM Studio URL: http://192.168.1.122:1234/v1/chat/completions
Batch size: 20
DRY RUN MODE - No changes will be saved

Testing LLM connection...
✓ LLM connection successful

Fetching uncategorized tags...
Found 20 tags to process

[1/20] Processing: blue_eyes (used 150x)
  ✓ Categorized as: 03_Body_Face (Body Face)
[2/20] Processing: running (used 89x)
  ✓ Categorized as: 09_Action (Action)
...

======================================================================
Categorization Complete
======================================================================
Total processed: 20
Successful: 19
Failed: 1
Success rate: 95.0%

DRY RUN - No changes were saved to the database
```

## Integration with Web UI

After running this script, the categorized tags will be visible in the web UI at:
http://192.168.1.5:5000/tag_categorize

The script updates the `extended_category` column in the database, which the web UI reads to display categorized tags.

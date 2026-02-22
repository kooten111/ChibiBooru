# Extended Categories Documentation

## Table of Contents
- [Overview](#overview)
- [Category Reference](#category-reference)
- [Manual Categorization](#manual-categorization)
- [LLM Auto-Categorization](#llm-auto-categorization)
- [Database Schema](#database-schema)
- [Display and Styling](#display-and-styling)
- [API Endpoints](#api-endpoints)
- [Export and Import](#export-and-import)

---

## Overview

The Extended Categories feature provides a **22-category extended system** for granular tag organization beyond ChibiBooru's standard 6-category system (character, copyright, artist, species, general, meta).

### Purpose

While the basic 6-category system works well for general organization, the Extended Categories system provides fine-grained categorization that:

- **Improves tag organization**: Groups similar tags together for easier browsing
- **Enhances search**: Enables more precise filtering and discovery
- **Supports AI models**: Provides structured data for training and inference
- **Facilitates tag management**: Makes it easier to identify and categorize new tags

### Basic vs Extended Categories

| System | Categories | Use Case |
|--------|-----------|----------|
| **Basic** | 6 categories | General metadata organization |
| **Extended** | 22 categories | Granular tag classification and AI training |

The two systems work together:
- **Basic `category`**: Primary categorization (character, copyright, etc.)
- **Extended `extended_category`**: Fine-grained sub-categorization within general tags

---

## Category Reference

The Extended Categories system provides 22 specialized categories organized into 3 main groups:

### Complete Category Table

| Category Key | Display Name | Shortcut | Description | Examples |
|-------------|--------------|----------|-------------|----------|
| `00_Subject_Count` | Subject Count | `0` | Count & Gender | 1girl, solo, 1boy, 2girls, group |
| `01_Body_Physique` | Body Physique | `1` | Permanent body traits | breasts, tail, animal_ears, muscular, horns |
| `02_Body_Hair` | Body Hair | `2` | Hair properties | long_hair, twintails, blonde_hair, braid, ponytail |
| `03_Body_Face` | Body Face | `3` | Eye color & permanent face marks | blue_eyes, sharp_teeth, red_eyes, scar, heterochromia |
| `04_Body_Genitalia` | Body Genitalia | `4` | NSFW Anatomy | nipples, penis, pussy, anus |
| `05_Attire_Main` | Attire Main | `5` | Main outer clothing | shirt, dress, school_uniform, jacket, kimono |
| `06_Attire_Inner` | Attire Inner | `6` | Underwear/Swimwear | panties, bra, bikini, boxers, lingerie |
| `07_Attire_Legwear` | Attire Legwear | `7` | Socks & Hosiery | thighhighs, pantyhose, kneehighs, stockings |
| `08_Attire_Acc` | Attire Accessories | `8` | Accessories worn | gloves, ribbon, glasses, hat, jewelry |
| `09_Action` | Action | `a` | Active verbs | holding, eating, walking, grabbing, running |
| `10_Pose` | Pose | `p` | Static body position & gaze | sitting, looking_at_viewer, standing, spread_legs, lying |
| `11_Expression` | Expression | `e` | Temporary emotion | blush, smile, crying, angry, embarrassed |
| `12_Sexual_Act` | Sexual Act | `x` | NSFW interaction | sex, vaginal, fellatio, masturbation, paizuri |
| `13_Object` | Object | `o` | Props not worn | flower, weapon, phone, cup, book |
| `14_Setting` | Setting | `s` | Background/Time/Location | simple_background, outdoors, bedroom, night, beach |
| `15_Framing` | Framing | `f` | Camera angle/Crop | upper_body, cowboy_shot, close-up, from_behind, full_body |
| `16_Focus` | Focus | `u` | Specific part focus | foot_focus, solo_focus, face_focus, breast_focus |
| `17_Style_Art` | Style Art | `y` | Medium/Art style | monochrome, comic, sketch, realistic, chibi |
| `18_Style_Tech` | Style Tech | `t` | Visual effects | blurry, chromatic_aberration, depth_of_field, motion_blur |
| `19_Meta_Attributes` | Meta Attributes | `q` | General metadata attributes | highres, absurdres, bad_anatomy, artist_name |
| `20_Meta_Text` | Meta Text | `w` | Text & UI elements | speech_bubble, signature, watermark, text, dialogue |
| `21_Status` | Status | `z` | State of being | nude, wet, censored, clothed, partially_visible |

### Category Groups

#### Group 1: Identity (Permanent Traits)
Categories `00-04` describe fundamental, permanent characteristics:
- **00_Subject_Count**: Number and gender of subjects
- **01_Body_Physique**: Unchanging physical features
- **02_Body_Hair**: Hair characteristics
- **03_Body_Face**: Facial features and eye color
- **04_Body_Genitalia**: NSFW anatomical features

#### Group 2: Context (Temporary/Situational)
Categories `05-14, 21` describe changeable aspects:
- **05-08**: Clothing and accessories
- **09-12**: Actions, poses, and expressions
- **13-14**: Objects and environment
- **21_Status**: Current state of being

#### Group 3: Technical/Meta
Categories `15-20` describe image properties:
- **15-16**: Camera and composition
- **17-18**: Art style and visual effects
- **19-20**: Metadata and text elements

---

## Manual Categorization

### Web Interface

Access the categorization interface at:
```
/tag_categorize
```

### Features

1. **Smart Tag Queue**
   - Tags sorted by usage frequency (most used first)
   - Shows sample images for context
   - Displays current category status

2. **Keyboard Shortcuts**
   - Numbers `0-9`: Quick category assignment
   - Letters `a, p, e, x, o, s, f, u, y, t, q, w, z`: Additional shortcuts
   - Efficient for bulk categorization

3. **Category Guide Sidebar**
   - Real-time reference for all 22 categories
   - Organized by logical groups
   - Shows keyboard shortcuts

4. **Progress Tracking**
   - Total tags in database
   - Categorized vs uncategorized count
   - Per-category statistics

### Workflow

1. **Navigate to categorization page**
   ```
   Main Menu → Tag Categorize
   ```

2. **Review tag information**
   - View tag name and usage count
   - Check sample images showing the tag
   - Consider co-occurring tags (if shown)

3. **Assign category**
   - Click category button OR
   - Press keyboard shortcut
   - Tag automatically moves to next

4. **Monitor progress**
   - Check stats summary at top
   - Focus on high-usage tags first
   - Use export to backup progress

### Best Practices

- **Start with high-usage tags**: Most impact on organization
- **Use sample images**: Visual context helps accurate categorization
- **Follow the groups**: Use the 3-group structure for guidance
- **Be consistent**: Check existing categorizations in your collection
- **Save progress**: Export periodically to backup your work

---

## LLM Auto-Categorization

### Overview

The `scripts/llm_auto_categorize_tags.py` script uses a local LLM (via LM Studio) to automatically categorize tags based on the Extended Categories schema.

### Prerequisites

1. **LM Studio** running locally
   - Default URL: `http://192.168.1.122:1234` (update IP address in script to match your installation)
   - Model: `mistralai/ministral-3-14b-reasoning` (or compatible)
   - Server must be running before script execution

2. **Python dependencies** (confirmed in `requirements.txt`)
   - `requests>=2.32.5`: HTTP client for LLM API

### Configuration

Edit the script to customize for your environment:

```python
# LM Studio API configuration
LM_STUDIO_URL = "http://192.168.1.122:1234/v1/chat/completions"  # Change IP to match your LM Studio server
MODEL_NAME = "mistralai/ministral-3-14b-reasoning"  # Change to match your loaded model
```

**Important**: Update the IP address (`192.168.1.122`) to match where your LM Studio instance is running:
- Local installation: `http://localhost:1234` or `http://127.0.0.1:1234`
- Remote server: `http://YOUR_SERVER_IP:1234`

### Command-Line Options

```bash
python scripts/llm_auto_categorize_tags.py [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--batch-size N` | 100 | Number of tags to process per batch |
| `--limit N` | unlimited | Maximum total tags to process |
| `--dry-run` | false | Preview categorizations without saving |
| `--skip N` | 0 | Skip first N tags (for resuming) |

### Usage Examples

**Basic auto-categorization:**
```bash
python scripts/llm_auto_categorize_tags.py --batch-size 100
```

**Dry run to preview:**
```bash
python scripts/llm_auto_categorize_tags.py --dry-run --limit 20
```

**Resume after interruption:**
```bash
python scripts/llm_auto_categorize_tags.py --skip 500
```

**Process specific number:**
```bash
python scripts/llm_auto_categorize_tags.py --limit 1000
```

### Auto-Correction Feature

The script automatically corrects common LLM mistakes:

| Common Mistake | Auto-Corrected To |
|----------------|-------------------|
| `19_Meta_Text` | `20_Meta_Text` |
| `06_Attire_Legwear` | `07_Attire_Legwear` |
| `02_Body_Physique` | `01_Body_Physique` |

Additionally, fuzzy matching handles cases where the LLM gets the category name right but uses wrong numbering.

### Performance

- **Speed**: ~0.1s delay between tags (to avoid overwhelming LLM)
- **Accuracy**: Typically 85-95% depending on tag complexity
- **Retry Logic**: Up to 3 attempts per tag with validation
- **Rate Limiting**: Built-in throttling to respect API limits

### Output

The script provides real-time feedback:

```
======================================================================
Automated Tag Categorization using Local LLM
======================================================================

LM Studio URL: http://192.168.1.122:1234/v1/chat/completions
Batch size: 100

Testing LLM connection...
✓ LLM connection successful

Fetching uncategorized tags...
Found 247 tags to process

[1/247] Processing: long_hair (used 1250x)
  ✓ Categorized as: 02_Body_Hair (Body Hair)
[2/247] Processing: blue_eyes (used 892x)
  ✓ Categorized as: 03_Body_Face (Body Face)
...

======================================================================
Categorization Complete
======================================================================
Total processed: 247
Successful: 235
Failed: 12
Success rate: 95.1%
```

### Troubleshooting

**Connection failed:**
- Verify LM Studio is running
- Check IP address in script matches your LM Studio server location
  - For local: Use `http://localhost:1234` or `http://127.0.0.1:1234`
  - For remote: Use `http://YOUR_SERVER_IP:1234`
- Ensure firewall allows connection on port 1234

**Low accuracy:**
- Try a different model (some models work better for categorization)
- Adjust temperature parameter in script (lower = more consistent)
- Review and manually fix incorrect categorizations

**Rate limit errors:**
- Reduce batch size (`--batch-size`)
- Increase delay between requests in script (modify `sleep(0.1)` value)

---

## Database Schema

### Tags Table

The `tags` table includes both basic and extended categorization:

```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    category TEXT,              -- Basic category (character, copyright, etc.)
    extended_category TEXT      -- Extended category (00_Subject_Count, etc.)
);

CREATE INDEX idx_tags_extended_category ON tags(extended_category);
```

### Column Details

| Column | Type | Description |
|--------|------|-------------|
| `category` | TEXT | Basic 6-category system (character, copyright, artist, species, general, meta) |
| `extended_category` | TEXT | Extended 22-category system |

### Relationship to Basic Categories

- **Basic categories** (`category` column): Used for primary organization
- **Extended categories** (`extended_category` column): Provides fine-grained sub-categorization
- **Independence**: A tag can have both or just one type of categorization
- **Typical usage**: Most general tags use extended categories; character/copyright use basic

### Example Data

```sql
-- Character tag (uses basic category only)
INSERT INTO tags (name, category, extended_category) 
VALUES ('hatsune_miku', 'character', NULL);

-- General tag (uses both)
INSERT INTO tags (name, category, extended_category) 
VALUES ('blue_hair', 'general', '02_Body_Hair');

-- Action tag (uses extended only)
INSERT INTO tags (name, category, extended_category) 
VALUES ('sitting', NULL, '10_Pose');
```

### Query Examples

**Get all tags in a specific extended category:**
```sql
SELECT name, COUNT(*) as usage
FROM tags t
JOIN image_tags it ON t.id = it.tag_id
WHERE t.extended_category = '02_Body_Hair'
GROUP BY name
ORDER BY usage DESC;
```

**Get categorization statistics:**
```sql
SELECT 
    extended_category,
    COUNT(*) as tag_count,
    SUM(usage_count) as total_usage
FROM tags t
JOIN (
    SELECT tag_id, COUNT(*) as usage_count
    FROM image_tags
    GROUP BY tag_id
) counts ON t.id = counts.tag_id
WHERE extended_category IS NOT NULL
GROUP BY extended_category
ORDER BY extended_category;
```

**Find uncategorized tags:**
```sql
SELECT name, COUNT(it.image_id) as usage
FROM tags t
LEFT JOIN image_tags it ON t.id = it.tag_id
WHERE extended_category IS NULL
    AND category = 'general'  -- Focus on general tags
GROUP BY name
ORDER BY usage DESC;
```

---

## Display and Styling

### Image Detail Page

On image detail pages (`/image/{filepath}`), tags are automatically grouped and displayed by their extended categories in the order defined in the extended category system.

### Tag Grouping

Tags are organized into collapsible sections by extended category:

```
┌─ Subject Count ──────────────┐
│ 1girl (15.2k)                │
│ solo (12.8k)                 │
└──────────────────────────────┘

┌─ Body Hair ──────────────────┐
│ long_hair (28.5k)            │
│ blue_hair (8.2k)             │
│ twintails (6.1k)             │
└──────────────────────────────┘

┌─ Expression ─────────────────┐
│ smile (22.1k)                │
│ blush (15.3k)                │
└──────────────────────────────┘
```

### Color Coding

Each extended category has a unique color for easy identification. Colors are defined in `static/css/components-bundle.css`:

| Category | Color | Hex |
|----------|-------|-----|
| Subject Count | Blue | `#3498db` |
| Body Physique | Pink | `#e91e63` |
| Body Hair | Purple | `#9b59b6` |
| Body Face | Teal | `#1abc9c` |
| Body Genitalia | Red | `#e74c3c` |
| Attire Main | Indigo | `#5c6bc0` |
| Attire Inner | Pink | `#ec407a` |
| Attire Legwear | Deep Purple | `#7e57c2` |
| Attire Accessories | Cyan | `#26c6da` |
| Action | Green | `#66bb6a` |
| Pose | Lime | `#9ccc65` |
| Expression | Yellow | `#ffeb3b` |
| Sexual Act | Dark Red | `#d32f2f` |
| Object | Brown | `#8d6e63` |
| Setting | Light Blue | `#29b6f6` |
| Status | Orange | `#ff9800` |
| Framing | Blue Grey | `#78909c` |
| Focus | Deep Orange | `#ff7043` |
| Style Art | Purple | `#ab47bc` |
| Style Tech | Cyan | `#00acc1` |
| Meta Attributes | Grey | `#757575` |
| Meta Text | Blue Grey | `#90a4ae` |
| Uncategorized | Light Grey | `#bdbdbd` |

### CSS Classes

The display uses specific CSS classes:

```css
.extended-sub-category {
    /* Container for each category group */
}

.extended-category-title {
    /* Category header with color coding */
}

.extended-sub-category.02-body-hair .extended-category-title {
    background-color: #9b59b6;  /* Purple for hair */
}
```

### Template Code

Extended categories are rendered in `templates/image.html`:

```html
{% for cat_key, cat_display_name in extended_category_order %}
    {% if cat_key in extended_grouped_tags %}
        <div class="extended-sub-category {{ cat_key|replace('_', '-')|lower }}">
            <div class="extended-category-title">{{ cat_display_name }}</div>
            {% for tag, count in extended_grouped_tags[cat_key] %}
                <div class="tag-item">
                    <a href="{{ url_for('main.home', query=tag) }}">{{ tag }}</a>
                    <span class="tag-count">{{ count }}</span>
                </div>
            {% endfor %}
        </div>
    {% endif %}
{% endfor %}
```

---

## API Endpoints

All API endpoints are prefixed with `/api/tag_categorize`.

### Get Statistics

**Endpoint:** `GET /api/tag_categorize/stats`

**Description:** Get statistics about tag categorization status

**Response:**
```json
{
  "total_tags": 5000,
  "categorized": 3200,
  "uncategorized": 1800,
  "meaningful_uncategorized": 450,
  "meaningful_categorized": 2850,
  "by_category": {
    "02_Body_Hair": 320,
    "03_Body_Face": 180,
    "09_Action": 420
  },
  "categories": ["00_Subject_Count", "01_Body_Physique", ...],
  "extended_categories": [
    ["00_Subject_Count", "Subject Count", "0", "Count & Gender..."],
    ...
  ]
}
```

---

### Get Uncategorized Tags

**Endpoint:** `GET /api/tag_categorize/tags`

**Query Parameters:**
- `limit` (integer, default: 100): Maximum number of tags to return

**Description:** Get uncategorized tags sorted by usage frequency

**Response:**
```json
{
  "tags": [
    {
      "name": "sitting",
      "usage_count": 1250,
      "sample_images": [
        "images/folder/image1.jpg",
        "images/folder/image2.jpg",
        "images/folder/image3.jpg"
      ],
      "current_category": "general"
    }
  ],
  "count": 100,
  "categories": ["00_Subject_Count", ...],
  "extended_categories": [...]
}
```

---

### Set Tag Category

**Endpoint:** `POST /api/tag_categorize/set`

**Description:** Set or update the extended category for a tag

**Request Body:**
```json
{
  "tag_name": "sitting",
  "category": "10_Pose"
}
```

**Response:**
```json
{
  "success": true,
  "old_category": null,
  "new_category": "10_Pose"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Invalid category. Must be one of: ..."
}
```

---

### Get Tag Details

**Endpoint:** `GET /api/tag_categorize/tag_details`

**Query Parameters:**
- `tag_name` (string, required): Name of the tag

**Description:** Get detailed information about a tag including suggestions

**Response:**
```json
{
  "name": "sitting",
  "category": "general",
  "usage_count": 1250,
  "suggested_category": "10_Pose",
  "cooccurring_tags": [
    {
      "name": "chair",
      "category": "general",
      "cooccurrence": 450
    }
  ]
}
```

---

### Bulk Categorize

**Endpoint:** `POST /api/tag_categorize/bulk`

**Description:** Categorize multiple tags at once

**Request Body:**
```json
{
  "categorizations": [
    {
      "tag_name": "sitting",
      "category": "10_Pose"
    },
    {
      "tag_name": "running",
      "category": "09_Action"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "success_count": 2,
  "error_count": 0,
  "errors": []
}
```

---

### Suggest Category

**Endpoint:** `GET /api/tag_categorize/suggest`

**Query Parameters:**
- `tag_name` (string, required): Name of the tag

**Description:** Get an automatic category suggestion based on patterns and co-occurrence

**Response:**
```json
{
  "tag_name": "sitting",
  "suggested_category": "10_Pose"
}
```

---

### Export Categorizations

**Endpoint:** `GET /api/tag_categorize/export`

**Query Parameters:**
- `categorized_only` (boolean, default: false): Only export categorized tags

**Description:** Export all tag categorizations as JSON file

**Response:** Downloads JSON file with structure:
```json
{
  "export_version": "1.0",
  "export_date": "2024-01-15T12:00:00.000000",
  "tag_count": 3200,
  "categorized_only": true,
  "categories": ["00_Subject_Count", ...],
  "tags": {
    "sitting": "10_Pose",
    "running": "09_Action",
    "blue_hair": "02_Body_Hair"
  }
}
```

---

### Import Categorizations

**Endpoint:** `POST /api/tag_categorize/import`

**Query Parameters:**
- `mode` (string, default: "merge"): Import mode
  - `merge`: Keep existing categorizations, only add new ones
  - `overwrite`: Replace all categorizations
  - `update`: Only update tags that already have categories

**Description:** Import tag categorizations from exported JSON

**Request Body:** (Same structure as export)
```json
{
  "export_version": "1.0",
  "export_date": "2024-01-15T12:00:00.000000",
  "tags": {
    "sitting": "10_Pose",
    "running": "09_Action"
  }
}
```

**Response:**
```json
{
  "success": true,
  "total": 2,
  "updated": 2,
  "skipped": 0,
  "errors": []
}
```

---

## Export and Import

### Export Functionality

The categorization interface provides export functionality to backup your categorization work.

**Access:**
- Web UI: Click "Export" button in Tag Categorize interface
- API: `GET /api/tag_categorize/export`

**Export Options:**
- **All tags**: Includes both categorized and uncategorized tags
- **Categorized only**: Only exports tags with extended categories assigned

**File Format:**
- JSON format
- Filename: `tag_categorizations_{timestamp}.json`
- Contains metadata and tag-to-category mappings

**Use Cases:**
- Backup categorization progress
- Share categorizations between installations
- Migrate categorizations during upgrades

### Import Functionality

Import previously exported categorizations.

**Access:**
- Web UI: Click "Import" button in Tag Categorize interface
- API: `POST /api/tag_categorize/import`

**Import Modes:**

1. **Merge (Default)**
   - Preserves existing categorizations
   - Only adds categorizations for uncategorized tags
   - Safe for incremental updates

2. **Overwrite**
   - Replaces all categorizations
   - Use when restoring from backup
   - **Warning**: Overwrites manual work

3. **Update**
   - Only updates tags that already have categories
   - Skips uncategorized tags
   - Use for refining existing categorizations

**Validation:**
- Checks category validity
- Verifies tags exist in database
- Reports errors for missing/invalid entries

**Best Practices:**
- Export regularly during manual categorization
- Use merge mode for collaborative workflows
- Test imports with dry-run first (export current state before importing)
- Keep export files versioned

---

## Related Documentation

- [Services Documentation](SERVICES.md#tag-categorization-service) - Tag Categorization Service API reference
- [Database Schema](DATABASE.md#tags) - Tags table structure
- [Routers Documentation](ROUTERS.md) - Web UI and API endpoint details
- [Architecture Overview](ARCHITECTURE.md) - System design and patterns

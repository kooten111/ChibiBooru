# HomeBooru

HomeBooru is a self-hosted web application for organizing and browsing your local image collection, designed to automatically fetch tags and metadata from various online sources, similar to popular image boorus. It combines a user-friendly interface with powerful backend tools to create a rich and searchable media library.

## 🌟 Features

  * **🖼️ Elegant Image Gallery:** A responsive, masonry-style layout for browsing your images with infinite scroll.
  * **🤖 Automated Tagging:** Automatically fetches detailed, categorized tags for your images from multiple sources:
      * **Direct Hash Search:** Finds metadata from **Danbooru** and **e621** using the image's MD5 hash.
      * **Reverse Image Search:** Uses **SauceNao** to find sources and metadata when direct hash matching fails.
      * **AI Tagging:** Includes a local, ONNX-based AI tagger as a fallback to analyze and tag images that have no online matches.
  * **📂 Comprehensive Metadata:** Gathers rich metadata, including artist, character, copyright, species, and general tags, as well as image dimensions, file size, and original sources.
  * **🔍 Powerful Search:**
      * Search by tags with autocomplete suggestions.
      * Advanced search filters like `source:danbooru`, `filename:cute_cat`, `.png`, and `has:children` to narrow down results.
  * **✏️ Full Tag Control:**
      * An intuitive in-line tag editor to add, remove, and recategorize tags.
      * Ability to switch between different metadata sources (e.g., switch from Danbooru's tags to e621's for the same image).
  * **🔗 Image Relationships:** Automatically detects and displays parent/child relationships between images.
  * **⚙️ System Management Panel:** A web UI with powerful tools to manage your library:
      * Scan for and process new images.
      * Generate thumbnails.
      * Find and remove duplicate files.
      * Clean the database of orphaned entries.
      * Rebuild tag data from source metadata.
  * **🔄 Background Monitoring:** An optional service that automatically watches your image directory for new files and processes them in the background.

-----

## 🚀 Getting Started

### Prerequisites

  * Python 3.8+
  * Git

### Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd Booru-main
    ```

2.  **Install dependencies:**
    It is highly recommended to use a virtual environment.

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install Flask Pillow requests numpy onnxruntime torchvision python-dotenv tqdm
    ```

3.  **Configuration:**
    Create a `.env` file in the root of the project by copying the example:

    ```bash
    cp .env.example .env
    ```

    Now, edit the `.env` file to add your API keys and customize settings:

    ```env
    # Required for reverse image search
    SAUCENAO_API_KEY="your_saucenao_api_key"

    # A secret key for accessing system management functions in the UI
    RELOAD_SECRET="a-very-secret-string"

    # Optional: Gelbooru API for authenticated requests
    GELBOORU_API_KEY=""
    GELBOORU_USER_ID=""

    # Optional: Name for the local AI tagger
    LOCAL_TAGGER_NAME="CamieTagger"
    ```

4.  **Place your images:**
    Move your image collection into the `static/images/` directory. You can create subdirectories to organize them.

5.  **Run the application:**

    ```bash
    python app.py
    ```

    The application will be available at `http://127.0.0.1:5000` by default.

-----

## 📖 Usage

### Initial Setup

1.  After running the application for the first time, open the web interface.
2.  Navigate to the **System** panel in the header.
3.  Enter the `RELOAD_SECRET` you set in your `.env` file.
4.  Click **"Scan & Process New Images"** to begin indexing your collection. The application will start fetching metadata for all your images. This may take a while for large collections.
5.  Once the initial scan is complete, you can optionally start the **Monitor** to have HomeBooru automatically process new images you add to the `static/images` folder.

### Searching

  * **Basic Tag Search:** Just type tags separated by spaces in the search bar (e.g., `1girl blue_hair`).
  * **Advanced Queries:**
      * `source:<name>`: Find images from a specific source (e.g., `source:danbooru`).
      * `filename:<text>`: Search for text within the image's filename.
      * `.<ext>`: Filter by file extension (e.g., `.png`, `.gif`).
      * `has:<parent|child>`: Find images that have a parent or child.

### Editing Tags

1.  Navigate to an image's detail page.
2.  Click the **"📝 Edit Tags"** button.
3.  An inline editor will appear, allowing you to add or remove tags within their specific categories.
4.  Click **"💾 Save Tags"** when you are done.

-----

## 📁 Project Structure

```
Booru-main/
├── static/
│   ├── css/         # Stylesheets
│   ├── js/          # JavaScript files
│   └── images/      # Your image collection goes here
├── templates/       # Flask HTML templates
├── utils/           # Utility scripts (deduplication, file handling)
├── services/        # Service layer for business logic
├── app.py           # Main Flask application
├── config.py        # Configuration settings
├── database.py      # Database schema and initialization
├── models.py        # Database models and data access layer
└── processing.py    # Core image processing and metadata fetching logic
```

## 🙏 Acknowledgements

This project relies on several fantastic services for providing tag data:

  * [suspicious link removed]
  * [suspicious link removed]
  * [SauceNao](https://saucenao.com/)
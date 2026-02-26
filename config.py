import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Nellis Auction
BASE_URL = "https://www.nellisauction.com"
SEARCH_URL = f"{BASE_URL}/search"
LOCATION = "Katy"
SHOPPING_LOCATION_ID = "5"  # Houston, TX (includes Katy + SW Houston)
SORT = "time_remaining_desc"
ITEMS_PER_PAGE = 120

# Scraper behavior
MIN_DELAY = 2.0  # seconds between page fetches
MAX_DELAY = 5.0
PAGE_LOAD_WAIT = 3.0  # seconds to wait after initial navigation

# Database
DB_PATH = os.path.join(BASE_DIR, "auction.db")

# Ollama
OLLAMA_MODEL = "qwen2.5:7b"

# Interests
INTERESTS_FILE = os.path.join(BASE_DIR, "interests.txt")
EXCLUDE_FILE = os.path.join(BASE_DIR, "exclude.txt")

# Reports
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
CRAZY_DEAL_MIN_RETAIL = 75.0
CRAZY_DEAL_MAX_RATIO = 0.08

# Product link
PRODUCT_URL_TEMPLATE = f"{BASE_URL}/product/{{product_id}}"

import re


def slugify(title: str, max_words: int = 12) -> str:
    """Generate a Nellis-style slug from title."""
    if not title:
        return ""
    # Remove special characters, keep alphanumeric, spaces, hyphens
    clean = re.sub(r"[^\w\s-]", "", title)
    words = clean.split()
    words = words[:max_words]
    if not words:
        return ""
    return "-".join(words)


def product_url(product_id: int, title: str) -> str:
    """Generate correct product URL with slug."""
    slug = slugify(title)
    if not slug:
        slug = "product"
    return f"{BASE_URL}/p/{slug}/{product_id}"

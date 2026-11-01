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

# Woot (separate pipeline: woot.py, woot_db.py, woot_classifier.py, woot_report.py)
WOOT_FEED_URL = "https://developer.woot.com/feed/All"
WOOT_DB_PATH = os.path.join(BASE_DIR, "woot.db")
WOOT_INTERESTS_FILE = os.path.join(BASE_DIR, "woot_interests.txt")
WOOT_STOCKUP_FILE = os.path.join(BASE_DIR, "woot_stockup.txt")
WOOT_EXCLUDE_FILE = os.path.join(BASE_DIR, "woot_exclude.txt")
# Woot list prices are inflated, so these are deliberately steep.
WOOT_CRAZY_MIN_LIST = 40.0
WOOT_CRAZY_MIN_DISCOUNT = 0.80
WOOT_CRAZY_MAX_ITEMS = 40
WOOT_STOCKUP_MIN_DISCOUNT = 0.40

# eBay watchlist (separate pipeline: ebay.py, ebay_db.py, ebay_report.py). Production Browse API.
# Terms in ebay_watch.txt are searched for auctions ending soon; no price check (see the file's header).
EBAY_API_BASE = "https://api.ebay.com"
EBAY_DB_PATH = os.path.join(BASE_DIR, "ebay.db")
EBAY_WATCH_FILE = os.path.join(BASE_DIR, "ebay_watch.txt")
EBAY_EXCLUDE_FILE = os.path.join(BASE_DIR, "ebay_exclude.txt")
# Names usable after "|" in ebay_watch.txt; a raw numeric eBay category ID works too.
EBAY_CATEGORIES = {"books": "267"}
EBAY_ZIP = "77494"            # Katy; sets shipping/location context
EBAY_WINDOW_HOURS = 168       # look a week ahead: rare terms (qidi) have few auctions
EBAY_MAX_BID = 250.0          # current-bid cap
EBAY_MAX_PER_QUERY = 200      # soonest-ending results kept per term; the rest roll in on later runs
EBAY_REQUEST_DELAY = 0.3      # seconds between API calls (default quota is ~5k/day)

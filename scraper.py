import json
import random
import time

from playwright.sync_api import sync_playwright

import config
import db


def build_search_url(page_num: int) -> str:
    """Build the Remix single fetch data endpoint URL for a given page number."""
    location = config.LOCATION
    sort = config.SORT
    size = config.ITEMS_PER_PAGE
    return (
        f"{config.BASE_URL}/search.data"
        f"?Location+Name={location}"
        f"&sortBy={sort}"
        f"&_p1=s%3A{size}%2Cn%3A{page_num}"
        f"&_routes=routes/search._index"
    )


def decode_turbo_stream(raw_text: str) -> dict:
    """Decode a Remix single-fetch turbo-stream JSON string into nested dicts/lists."""
    data = json.loads(raw_text) if isinstance(raw_text, str) else raw_text
    memo = {}

    def decode_ref(idx):
        if idx is None:
            return None
        if isinstance(idx, str):
            return idx
        if isinstance(idx, (int, float)):
            if idx == -1 or idx == -5:
                return None
            if idx < 0:
                return None
            if idx in memo:
                return memo[idx]
            val = data[int(idx)]
            memo[idx] = decode_node(val)
            return memo[idx]
        return decode_node(idx)

    def decode_node(node):
        if isinstance(node, dict):
            res = {}
            for k, v in node.items():
                if k.startswith("_") and k[1:].isdigit():
                    key_idx = int(k[1:])
                    key_str = data[key_idx]
                    res[key_str] = decode_ref(v)
                else:
                    res[k] = decode_node(v)
            return res
        elif isinstance(node, list):
            if len(node) == 2 and node[0] == "D":
                return node[1]
            return [decode_ref(item) for item in node]
        else:
            return node

    return decode_node(data[0])


def fetch_page(playwright_page, page_num: int) -> dict:
    """Fetch a single page of results via the Remix single fetch data endpoint."""
    url = build_search_url(page_num)
    raw_text = playwright_page.evaluate(f"""
        async () => {{
            const resp = await fetch("{url}");
            return await resp.text();
        }}
    """)
    decoded = decode_turbo_stream(raw_text)
    route_data = decoded.get("routes/search._index") or decoded.get("routes/search") or {}
    return route_data.get("data", {})


def random_delay():
    delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
    time.sleep(delay)


def scrape(full: bool = False):
    """
    Scrape items from Nellis Auction.

    full=True: scrape all pages (initial full scrape)
    full=False: incremental mode - stop when all items on a page already exist
    """
    db.init_db()

    mode = "FULL" if full else "INCREMENTAL"
    print(f"[scraper] Starting {mode} scrape...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # Navigate to site to establish cookies/session
        # Note: can't use networkidle — site uses SSE that never stops
        print("[scraper] Establishing browser session...")
        page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(config.PAGE_LOAD_WAIT)

        # Set location to Katy (Houston, TX shopping location ID 5)
        # The site defaults to Las Vegas — this POST switches the session
        print("[scraper] Setting location to Katy, TX...")
        page.evaluate("""
            async () => {
                const formData = new FormData();
                formData.append("shoppingLocationId", \"""" + config.SHOPPING_LOCATION_ID + """\");
                await fetch("/change-shopping-location", { method: "POST", body: formData });
            }
        """)
        time.sleep(1)

        total_new = 0
        total_updated = 0
        page_num = 0

        while True:
            print(f"[scraper] Fetching page {page_num}...", end=" ", flush=True)

            try:
                data = fetch_page(page, page_num)
            except Exception as e:
                print(f"ERROR: {e}")
                break

            products = data.get("products", [])
            if not products:
                print("no products returned, done.")
                break

            algolia = data.get("algolia", {})
            nb_pages = algolia.get("nbPages", 0)
            nb_hits = algolia.get("nbHits", 0)

            # Parse products
            parsed = [db.parse_product(p) for p in products]
            product_ids = [item["id"] for item in parsed]

            # Check how many already exist (for incremental stop condition)
            existing_ids = db.get_existing_ids(product_ids)
            new_on_page = len(product_ids) - len(existing_ids)

            # Upsert all items (updates prices/bids for existing ones)
            new_count = db.upsert_items(parsed)
            total_new += new_count
            total_updated += len(parsed) - new_count

            print(
                f"got {len(products)} items ({new_count} new, "
                f"{len(parsed) - new_count} updated) "
                f"[page {page_num + 1}/{nb_pages}, {nb_hits} total on site]"
            )

            # Incremental mode: stop if all items on this page already existed
            if not full and new_on_page == 0:
                print("[scraper] All items on this page already in DB, stopping incremental scrape.")
                break

            page_num += 1
            if page_num >= nb_pages:
                print("[scraper] Reached last page.")
                break

            random_delay()

        browser.close()

    # Expire closed auctions
    expired = db.expire_closed_items()
    if expired:
        print(f"[scraper] Expired {expired} closed auction items.")

    stats = db.get_stats()
    print(
        f"[scraper] Done. {total_new} new, {total_updated} updated. "
        f"DB now has {stats['total']} items "
        f"({stats['unclassified']} unclassified, {stats['interesting']} interesting)."
    )


if __name__ == "__main__":
    import sys
    full = "--full" in sys.argv
    scrape(full=full)

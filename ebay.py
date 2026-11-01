#!/usr/bin/env python3
"""eBay fetcher: Browse API searches for auctions ending soon with low bids, synced into ebay.db."""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import config
import ebay_db


def _load_env() -> dict:
    env = dict(os.environ)
    path = os.path.join(config.BASE_DIR, ".env")
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                name, sep, value = line.strip().partition("=")
                if sep:
                    env.setdefault(name.strip(), value.strip().strip("'\""))
    return env


def _request(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "AuctionScraper/1.0", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        hint = " (daily call quota hit?)" if e.code == 429 else ""
        raise RuntimeError(f"eBay API HTTP {e.code}{hint}: {e.read().decode()[:200]}") from e


def get_token() -> str:
    env = _load_env()
    try:
        app_id, cert_id = env["EBAY_PRO_APP_ID"], env["EBAY_PRO_CERT_ID"]
    except KeyError as k:
        raise RuntimeError(f"{k.args[0]} not set (environment or .env)") from None
    basic = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope",
    }).encode()
    tok = _request(f"{config.EBAY_API_BASE}/identity/v1/oauth2/token", body,
                   {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    return tok["access_token"]


def parse_watch_line(line: str) -> tuple[str, str | None]:
    """'warhammer | books' -> ('warhammer', '267'); 'qidi' -> ('qidi', None). Category is a name or numeric ID."""
    term, _, cat = line.partition("|")
    term, cat = term.strip(), cat.strip().lower()
    if not cat:
        return term, None
    if cat.isdigit():
        return term, cat
    if cat in config.EBAY_CATEGORIES:
        return term, config.EBAY_CATEGORIES[cat]
    raise ValueError(f"unknown category '{cat}' (known: {', '.join(config.EBAY_CATEGORIES)}, or use a numeric ID)")


def search(token: str, term: str, max_bid: float, hours: int, limit: int | None = None,
           category: str | None = None) -> list[dict]:
    """Auctions matching `term` (optionally within one eBay category), ending within `hours`,
    current bid <= max_bid, soonest first."""
    limit = limit or config.EBAY_MAX_PER_QUERY
    end_by = (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3DUS%2Czip%3D{config.EBAY_ZIP}",
    }
    found, offset = [], 0
    while len(found) < limit:
        params = {
            "q": term, "sort": "endingSoonest", "limit": min(200, limit - len(found)), "offset": offset,
            "filter": f"buyingOptions:{{AUCTION}},price:[..{max_bid:g}],priceCurrency:USD,itemEndDate:[..{end_by}]",
        }
        if category:
            params["category_ids"] = category
        res = _request(f"{config.EBAY_API_BASE}/buy/browse/v1/item_summary/search?" + urllib.parse.urlencode(params),
                       headers=headers)
        page = res.get("itemSummaries") or []
        found.extend(page)
        offset += len(page)
        if not page or offset >= res.get("total", 0):
            break
        time.sleep(config.EBAY_REQUEST_DELAY)
    return found


def _terms(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def scrape() -> int:
    terms = _terms(config.EBAY_WATCH_FILE)
    if not terms:
        print(f"[ebay] No terms in {config.EBAY_WATCH_FILE}")
        return 0
    token = get_token()
    new = fetched = 0
    for line in terms:
        try:
            term, category = parse_watch_line(line)
            results = search(token, term, config.EBAY_MAX_BID, config.EBAY_WINDOW_HOURS, category=category)
        except ValueError as e:
            print(f"[ebay] [{line}] skipped: {e}")
            continue
        except RuntimeError as e:
            print(f"[ebay] [{line}] {e}")
            if "429" in str(e):
                break
            continue
        items = [i for i in (ebay_db.parse_item(r, "watch", line) for r in results) if i]
        fetched += len(items)
        new += ebay_db.upsert_items(items)
        time.sleep(config.EBAY_REQUEST_DELAY)
    expired = ebay_db.expire_ended()
    print(f"[ebay] {len(terms)} terms, {fetched} listings seen, {new} new, {expired} expired")
    return new


if __name__ == "__main__":
    ebay_db.init_db()
    scrape()

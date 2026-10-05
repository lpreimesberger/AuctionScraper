#!/usr/bin/env python3
"""Woot fetcher: pulls the whole /feed/All catalog in one request and syncs it into woot.db."""
import json
import os
import urllib.error
import urllib.request

import config
import woot_db


def load_api_key() -> str:
    key = os.environ.get("WOOT_API_KEY")
    if key:
        return key
    env_path = os.path.join(config.BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                name, sep, value = line.strip().partition("=")
                if sep and name.strip() == "WOOT_API_KEY":
                    return value.strip().strip("'\"")
    raise RuntimeError("WOOT_API_KEY not set (environment or .env)")


def fetch_feed() -> list[dict]:
    """GET /feed/All with no page param, which returns every offer (~5k) in a single request."""
    req = urllib.request.Request(
        config.WOOT_FEED_URL,
        headers={"x-api-key": load_api_key(), "Accept": "application/json", "User-Agent": "AuctionScraper/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        hint = " (daily quota of 1000 requests hit?)" if e.code == 429 else ""
        raise RuntimeError(f"Woot API returned HTTP {e.code}{hint}") from e
    return data.get("Items") or []


def scrape() -> int:
    items = fetch_feed()
    offers = [woot_db.parse_offer(i) for i in items if i.get("OfferId") and not i.get("IsSoldOut")]
    new, removed = woot_db.sync_offers(offers)
    expired = woot_db.expire_ended()
    print(f"[woot] Fetched {len(items)} offers: {new} new, {removed + expired} removed")
    return new


if __name__ == "__main__":
    woot_db.init_db()
    scrape()

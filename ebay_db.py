import sqlite3
from datetime import datetime, timezone

import config


def get_connection():
    conn = sqlite3.connect(config.EBAY_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ebay_items (
            item_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source TEXT NOT NULL,            -- always 'watch' now; column kept for older DBs
            query TEXT,                      -- watchlist term that surfaced it
            current_bid REAL,
            bid_count INTEGER,
            shipping REAL,                   -- NULL = unknown/calculated
            condition TEXT,
            photo_url TEXT,
            url TEXT,
            end_date TEXT,
            first_seen TEXT DEFAULT (datetime('now')),
            notified INTEGER DEFAULT 0
        )
    """)
    # Seller names are user data we never use or persist; drop the column (and its values) from older DBs.
    if "seller" in {r["name"] for r in conn.execute("PRAGMA table_info(ebay_items)")}:
        try:
            conn.execute("ALTER TABLE ebay_items DROP COLUMN seller")
        except sqlite3.OperationalError:  # SQLite < 3.35 can't drop columns: at least wipe the values
            conn.execute("UPDATE ebay_items SET seller = NULL")
    conn.commit()
    conn.close()


def _num(d):
    try:
        return float(d["value"])
    except (TypeError, KeyError, ValueError):
        return None


def parse_item(summary: dict, source: str, query: str) -> dict | None:
    """Flatten a Browse API item summary. Auctions carry currentBidPrice; `price` may be absent."""
    bid = _num(summary.get("currentBidPrice")) if summary.get("currentBidPrice") else _num(summary.get("price"))
    if not summary.get("itemId") or bid is None:
        return None
    ship = None
    opts = summary.get("shippingOptions") or []
    if opts:
        ship = _num(opts[0].get("shippingCost"))
        if ship is None and opts[0].get("shippingCostType") == "FIXED":
            ship = 0.0
    return {
        "item_id": summary["itemId"],
        "title": (summary.get("title") or "").strip(),
        "source": source,
        "query": query,
        "current_bid": bid,
        "bid_count": summary.get("bidCount") or 0,
        "shipping": ship,
        "condition": summary.get("condition"),
        "photo_url": (summary.get("image") or {}).get("imageUrl"),
        "url": summary.get("itemWebUrl"),
        "end_date": summary.get("itemEndDate"),
    }


_COLS = ["item_id", "title", "source", "query", "current_bid", "bid_count", "shipping",
         "condition", "photo_url", "url", "end_date"]


def upsert_items(items: list[dict]) -> int:
    """Insert new items, refresh bids on known ones (notified state is kept). Returns the number of new items."""
    if not items:
        return 0
    conn = get_connection()
    before = conn.execute("SELECT COUNT(*) FROM ebay_items").fetchone()[0]
    refresh = ", ".join(f"{c}=excluded.{c}" for c in
                        ["title", "current_bid", "bid_count", "shipping", "condition", "photo_url", "url", "end_date"])
    conn.executemany(
        f"INSERT INTO ebay_items ({', '.join(_COLS)}) VALUES ({', '.join(':' + c for c in _COLS)}) "
        f"ON CONFLICT(item_id) DO UPDATE SET {refresh}",
        items,
    )
    after = conn.execute("SELECT COUNT(*) FROM ebay_items").fetchone()[0]
    conn.commit()
    conn.close()
    return after - before


def expire_ended() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    conn = get_connection()
    n = conn.execute("DELETE FROM ebay_items WHERE end_date IS NOT NULL AND end_date < ?", (now,)).rowcount
    conn.commit()
    conn.close()
    return n


def get_unnotified() -> list[dict]:
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM ebay_items WHERE notified = 0")]
    conn.close()
    return rows


def mark_notified(item_ids: list[str]):
    conn = get_connection()
    conn.executemany("UPDATE ebay_items SET notified = 1 WHERE item_id = ?", [(i,) for i in item_ids])
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM ebay_items").fetchone()[0]
    conn.close()
    return {"total": total}

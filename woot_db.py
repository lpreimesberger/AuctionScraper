import json
import sqlite3
from datetime import datetime, timezone

import config


def get_connection():
    conn = sqlite3.connect(config.WOOT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS woot_offers (
            offer_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            subtitle TEXT,
            condition TEXT,
            site TEXT,
            categories TEXT,
            list_min REAL,
            list_max REAL,
            sale_min REAL,
            sale_max REAL,
            photo_url TEXT,
            url TEXT,
            end_date TEXT,
            classified INTEGER DEFAULT 0,
            interest_match TEXT,
            first_seen TEXT DEFAULT (datetime('now')),
            notified INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def _price(entry, key):
    return entry.get(key) if isinstance(entry, dict) else None


def parse_offer(offer: dict) -> dict:
    """Flatten a Woot feed item into a DB row dict."""
    lp, sp = offer.get("ListPrice"), offer.get("SalePrice")
    return {
        "offer_id": offer["OfferId"],
        "title": (offer.get("Title") or "").strip(),
        "subtitle": offer.get("Subtitle"),
        "condition": (offer.get("Condition") or "").strip() or None,
        "site": offer.get("Site"),
        "categories": json.dumps(offer.get("Categories") or []),
        "list_min": _price(lp, "Minimum"),
        "list_max": _price(lp, "Maximum"),
        "sale_min": _price(sp, "Minimum"),
        "sale_max": _price(sp, "Maximum"),
        "photo_url": offer.get("Photo"),
        "url": offer.get("Url"),
        "end_date": offer.get("EndDate"),
    }


def discount(item: dict) -> float:
    """Fraction off list price (0.0 if either price is unknown). Uses the lowest sale price vs lowest list price."""
    lst, sale = item.get("list_min"), item.get("sale_min")
    if not lst or sale is None or lst <= 0:
        return 0.0
    return max(0.0, 1 - sale / lst)


def savings(item: dict) -> float:
    lst, sale = item.get("list_min"), item.get("sale_min")
    if not lst or sale is None:
        return 0.0
    return max(0.0, lst - sale)


_COLS = ["offer_id", "title", "subtitle", "condition", "site", "categories", "list_min",
         "list_max", "sale_min", "sale_max", "photo_url", "url", "end_date"]


def sync_offers(offers: list[dict]) -> tuple[int, int]:
    """Upsert the full current catalog and drop offers no longer in it.

    Returns (new, removed). Skips pruning when given nothing, so a bad fetch can't wipe the DB.
    """
    if not offers:
        return 0, 0
    conn = get_connection()
    before = conn.execute("SELECT COUNT(*) FROM woot_offers").fetchone()[0]
    update = ", ".join(f"{c}=excluded.{c}" for c in _COLS[1:])
    conn.executemany(
        f"INSERT INTO woot_offers ({', '.join(_COLS)}) VALUES ({', '.join(':' + c for c in _COLS)}) "
        f"ON CONFLICT(offer_id) DO UPDATE SET {update}",
        offers,
    )
    conn.execute("CREATE TEMP TABLE live (offer_id TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO live VALUES (?)", [(o["offer_id"],) for o in offers])
    removed = conn.execute(
        "DELETE FROM woot_offers WHERE offer_id NOT IN (SELECT offer_id FROM live)"
    ).rowcount
    after = conn.execute("SELECT COUNT(*) FROM woot_offers").fetchone()[0]
    conn.commit()
    conn.close()
    return after - before + removed, removed


def expire_ended() -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    n = conn.execute("DELETE FROM woot_offers WHERE end_date IS NOT NULL AND end_date < ?", (now,)).rowcount
    conn.commit()
    conn.close()
    return n


def get_unclassified() -> list[dict]:
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM woot_offers WHERE classified = 0")]
    conn.close()
    return rows


def mark_classified(offer_ids: list[str], interest: str | None = None):
    conn = get_connection()
    conn.executemany(
        "UPDATE woot_offers SET classified = 1, interest_match = ? WHERE offer_id = ?",
        [(interest, oid) for oid in offer_ids],
    )
    conn.commit()
    conn.close()


def get_unnotified() -> list[dict]:
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM woot_offers WHERE notified = 0")]
    conn.close()
    return rows


def mark_notified(offer_ids: list[str]):
    conn = get_connection()
    conn.executemany("UPDATE woot_offers SET notified = 1 WHERE offer_id = ?", [(i,) for i in offer_ids])
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM woot_offers").fetchone()[0]
    interesting = conn.execute("SELECT COUNT(*) FROM woot_offers WHERE interest_match IS NOT NULL").fetchone()[0]
    conn.close()
    return {"total": total, "interesting": interesting}

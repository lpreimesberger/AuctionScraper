import sqlite3
from datetime import datetime, timezone

import config


def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            retail_price REAL,
            current_price REAL,
            bid_count INTEGER,
            condition TEXT,
            functional TEXT,
            damage TEXT,
            rating REAL,
            close_time TEXT,
            photo_url TEXT,
            location_name TEXT,
            is_interesting INTEGER DEFAULT 0,
            interest_match TEXT,
            first_seen TEXT DEFAULT (datetime('now')),
            last_updated TEXT DEFAULT (datetime('now')),
            notified INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def parse_product(product: dict) -> dict:
    """Flatten a Nellis product JSON object into a DB row dict."""
    grade = product.get("grade") or {}

    def grade_field(key):
        entry = grade.get(key)
        return entry.get("description") if entry else None

    photos = product.get("photos") or []
    close_time_obj = product.get("closeTime") or {}
    location = product.get("location") or {}

    return {
        "id": product["id"],
        "title": product.get("title", ""),
        "retail_price": product.get("retailPrice"),
        "current_price": product.get("currentPrice"),
        "bid_count": product.get("bidCount"),
        "condition": grade_field("conditionType"),
        "functional": grade_field("functionalType"),
        "damage": grade_field("damageType"),
        "rating": grade.get("rating"),
        "close_time": close_time_obj.get("value"),
        "photo_url": photos[0]["url"] if photos else None,
        "location_name": location.get("name"),
    }


def upsert_items(items: list[dict]) -> int:
    """Batch upsert items. Returns count of new items inserted."""
    conn = get_connection()
    new_count = 0
    with conn:
        for item in items:
            cursor = conn.execute("SELECT id FROM items WHERE id = ?", (item["id"],))
            exists = cursor.fetchone() is not None

            conn.execute("""
                INSERT INTO items (id, title, retail_price, current_price, bid_count,
                                   condition, functional, damage, rating, close_time,
                                   photo_url, location_name, last_updated)
                VALUES (:id, :title, :retail_price, :current_price, :bid_count,
                        :condition, :functional, :damage, :rating, :close_time,
                        :photo_url, :location_name, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    current_price = excluded.current_price,
                    bid_count = excluded.bid_count,
                    close_time = excluded.close_time,
                    last_updated = datetime('now')
            """, item)

            if not exists:
                new_count += 1
    conn.close()
    return new_count


def item_exists(product_id: int) -> bool:
    conn = get_connection()
    cursor = conn.execute("SELECT 1 FROM items WHERE id = ?", (product_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_existing_ids(product_ids: list[int]) -> set[int]:
    """Check which of the given IDs already exist in the DB."""
    conn = get_connection()
    placeholders = ",".join("?" * len(product_ids))
    cursor = conn.execute(
        f"SELECT id FROM items WHERE id IN ({placeholders})", product_ids
    )
    existing = {row["id"] for row in cursor.fetchall()}
    conn.close()
    return existing


def expire_closed_items() -> int:
    """Delete items whose auction has closed. Returns count deleted."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cursor = conn.execute("DELETE FROM items WHERE close_time < ?", (now,))
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


def get_unclassified_items() -> list[dict]:
    """Get items that haven't been classified yet."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT id, title FROM items WHERE is_interesting = 0 AND interest_match IS NULL"
    )
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def mark_interesting(item_id: int, interest: str):
    conn = get_connection()
    conn.execute(
        "UPDATE items SET is_interesting = 1, interest_match = ? WHERE id = ?",
        (interest, item_id),
    )
    conn.commit()
    conn.close()


def mark_not_interesting(item_ids: list[int]):
    """Mark items as classified but not interesting."""
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    conn.execute(
        f"UPDATE items SET interest_match = 'none' WHERE id IN ({placeholders})",
        item_ids,
    )
    conn.commit()
    conn.close()


def get_report_items() -> list[dict]:
    """Get interesting items that haven't been reported yet."""
    conn = get_connection()
    cursor = conn.execute(
        """SELECT * FROM items
           WHERE is_interesting = 1 AND notified = 0
           ORDER BY interest_match, retail_price DESC"""
    )
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def mark_notified(item_ids: list[int]):
    if not item_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    conn.execute(
        f"UPDATE items SET notified = 1 WHERE id IN ({placeholders})", item_ids
    )
    conn.commit()
    conn.close()


def get_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    interesting = conn.execute(
        "SELECT COUNT(*) FROM items WHERE is_interesting = 1"
    ).fetchone()[0]
    unclassified = conn.execute(
        "SELECT COUNT(*) FROM items WHERE interest_match IS NULL"
    ).fetchone()[0]
    conn.close()
    return {"total": total, "interesting": interesting, "unclassified": unclassified}


def get_crazy_deals(min_retail: float = 50.0, max_ratio: float = 0.10) -> list[dict]:
    """Get items with very low bids relative to retail price."""
    conn = get_connection()
    # Find items where current_price is <= max_ratio * retail_price
    # AND retail_price >= min_retail
    # AND not already interesting (those are in the main report)
    # AND not already notified
    query = """
        SELECT * FROM items
        WHERE retail_price >= ?
          AND current_price <= (retail_price * ?)
          AND is_interesting = 0
          AND notified = 0
        ORDER BY (current_price / retail_price) ASC
    """
    cursor = conn.execute(query, (min_retail, max_ratio))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items

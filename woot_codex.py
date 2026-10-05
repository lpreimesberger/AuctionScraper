#!/usr/bin/env python3
"""Keyword codex for woot.db: what words/phrases show up across Woot offers, how often, and an example.

Usage: python woot_codex.py [--min-count 5] [--top 50] [--search TERM]
Writes reports/woot-keywords-{date}.csv (keyword, count, avg_discount_pct, example, example_url).
"""
import argparse
import csv
import os
import re
from collections import defaultdict
from datetime import datetime

import config
import woot_db

STOPWORDS = {
    "with", "for", "and", "the", "your", "you", "choice", "pack", "set", "pcs", "piece", "pieces",
    "of", "in", "to", "by", "a", "an", "or", "on", "at", "from", "inch", "new", "gen", "size",
    "color", "colors", "style", "styles", "assorted", "select", "various", "multiple", "options",
    "mens", "womens", "men", "women", "kids", "black", "white", "blue", "red", "grey", "gray",
}


def tokens(title: str) -> list[str]:
    words = re.findall(r"[a-z][a-z0-9'&+-]*", title.lower().replace("’", "'"))
    return [w.strip("'-") for w in words if len(w) > 2]


def keywords(title: str) -> set[str]:
    toks = tokens(title)
    out = {t for t in toks if t not in STOPWORDS}
    out |= {f"{a} {b}" for a, b in zip(toks, toks[1:]) if a not in STOPWORDS and b not in STOPWORDS}
    return out


def build(offers: list[dict]) -> list[dict]:
    stats = defaultdict(lambda: {"count": 0, "disc": [], "best": None})
    for o in offers:
        d = woot_db.discount(o)
        for kw in keywords(o["title"]):
            s = stats[kw]
            s["count"] += 1
            if o.get("list_min"):
                s["disc"].append(d)
            if s["best"] is None or d > woot_db.discount(s["best"]):
                s["best"] = o
    rows = []
    for kw, s in stats.items():
        rows.append({
            "keyword": kw,
            "count": s["count"],
            "avg_discount_pct": round(100 * sum(s["disc"]) / len(s["disc"])) if s["disc"] else "",
            "example": s["best"]["title"],
            "example_url": s["best"].get("url") or "",
        })
    return sorted(rows, key=lambda r: (-r["count"], r["keyword"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--min-count", type=int, default=5)
    ap.add_argument("--top", type=int, default=40, help="rows to print (CSV has all)")
    ap.add_argument("--search", help="only keywords containing this text")
    args = ap.parse_args()

    conn = woot_db.get_connection()
    offers = [dict(r) for r in conn.execute("SELECT * FROM woot_offers")]
    conn.close()
    if not offers:
        print("woot.db is empty; run ./run-woot.sh first")
        return
    rows = [r for r in build(offers) if r["count"] >= args.min_count]
    if args.search:
        rows = [r for r in rows if args.search.lower() in r["keyword"]]

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    path = os.path.join(config.REPORTS_DIR, f"woot-keywords-{datetime.now():%Y-%m-%d}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["keyword", "count", "avg_discount_pct", "example", "example_url"])
        w.writeheader()
        w.writerows(rows)

    print(f"{len(offers)} offers, {len(rows)} keywords (min count {args.min_count}) -> {path}\n")
    print(f"{'keyword':24s} {'count':>5s} {'avg%off':>7s}  example")
    for r in rows[:args.top]:
        print(f"{r['keyword']:24s} {r['count']:5d} {str(r['avg_discount_pct']):>7s}  {r['example'][:60]}")


if __name__ == "__main__":
    main()

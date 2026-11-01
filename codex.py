#!/usr/bin/env python3
"""
Keyword Codex & Database Scanner for AuctionScraper

Scans `auction.db` to:
1. Check current `interests.txt` keyword match counts (exact string vs regex rules in classifier.py).
2. Extract a Codex of top single words, 2-word & 3-word phrases from active DB items.
3. Search DB titles interactively for specific terms.
"""

import argparse
import re
import sqlite3
from collections import Counter
import config
from classifier import INTEREST_KEYWORDS

STOPWORDS = {
    "with", "for", "and", "the", "pack", "set", "pcs", "piece", "pieces", "size",
    "in", "of", "to", "x", "a", "an", "by", "ft", "black", "white", "blue", "red",
    "pair", "heavy", "duty", "pro", "mini", "small", "large", "inch", "mm", "lb",
    "lbs", "kit", "cover", "holder", "mount", "stand", "bag", "case", "box",
    "wireless", "portable", "led", "light", "new", "used", "grade", "item", "qty",
    "for", "with", "and", "the", "you", "your", "are", "is"
}


def load_interests():
    try:
        with open(config.INTERESTS_FILE) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []


def get_db_titles():
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM items")
    titles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return titles


def check_interests_counts(titles, interests):
    print("\n" + "=" * 75)
    print(f" CURRENT INTERESTS MATCH COUNT (Total DB Items: {len(titles)})")
    print("=" * 75)
    print(f"{'Interest Term':<25} | {'Exact String Match':<20} | {'Regex Rules Candidate Count':<25}")
    print("-" * 75)

    for interest in interests:
        # 1. Exact string match count
        exact_pattern = re.compile(r'\b' + re.escape(interest) + r'\b', re.IGNORECASE)
        exact_count = sum(1 for title in titles if exact_pattern.search(title))

        # 2. Regex rules candidate count from INTEREST_KEYWORDS
        rules = INTEREST_KEYWORDS.get(interest, [])
        if rules:
            rule_count = 0
            for title in titles:
                if any(re.search(p, title, re.IGNORECASE) for p in rules):
                    rule_count += 1
            rule_str = str(rule_count)
        else:
            rule_str = "No regex rules"

        print(f"{interest:<25} | {exact_count:<20} | {rule_str:<25}")


def generate_keyword_codex(titles, top_n=30):
    words = Counter()
    bigrams = Counter()
    trigrams = Counter()

    for title in titles:
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', title.lower())
        tokens = [w for w in cleaned.split() if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
        words.update(tokens)
        for i in range(len(tokens) - 1):
            bigrams[(tokens[i], tokens[i + 1])] += 1
        for i in range(len(tokens) - 2):
            trigrams[(tokens[i], tokens[i + 1], tokens[i + 2])] += 1

    print("\n" + "=" * 75)
    print(f" KEYWORD CODEX FROM DATABASE ({len(titles)} active items)")
    print("=" * 75)

    print(f"\n--- TOP SINGLE KEYWORDS (Top {top_n}) ---")
    for w, c in words.most_common(top_n):
        print(f"  {w:<25} ({c} items)")

    print(f"\n--- TOP 2-WORD PHRASES (Top {top_n}) ---")
    for b, c in bigrams.most_common(top_n):
        phrase = " ".join(b)
        print(f"  {phrase:<25} ({c} items)")

    print(f"\n--- TOP 3-WORD PHRASES (Top {top_n}) ---")
    for t, c in trigrams.most_common(top_n):
        phrase = " ".join(t)
        print(f"  {phrase:<25} ({c} items)")


def search_db_keyword(query):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, current_price, retail_price FROM items WHERE title LIKE ? LIMIT 20",
        (f"%{query}%",),
    )
    rows = cursor.fetchall()
    conn.close()

    print("\n" + "=" * 75)
    print(f" SEARCH RESULTS FOR '{query}' ({len(rows)} samples shown)")
    print("=" * 75)
    if not rows:
        print("  No items matching keyword found.")
    for row in rows:
        print(f"  [{row[0]}] ${row[2]} (Retail: ${row[3]}) - {row[1]}")


def main():
    parser = argparse.ArgumentParser(description="Scan local database for keywords & index codex")
    parser.add_argument("--interests", action="store_true", help="Check match counts for interests.txt")
    parser.add_argument("--codex", action="store_true", help="Extract top keywords/phrases from DB titles")
    parser.add_argument("--search", type=str, help="Search DB titles for a custom keyword")
    parser.add_argument("--top", type=int, default=30, help="Number of top entries to show (default: 30)")
    args = parser.parse_args()

    titles = get_db_titles()
    if not titles:
        print("No items found in database.")
        return

    # Default: run both interests check & codex if no specific flags
    if not any([args.interests, args.codex, args.search]):
        args.interests = True
        args.codex = True

    if args.interests:
        interests = load_interests()
        check_interests_counts(titles, interests)

    if args.codex:
        generate_keyword_codex(titles, top_n=args.top)

    if args.search:
        search_db_keyword(args.search)


if __name__ == "__main__":
    main()

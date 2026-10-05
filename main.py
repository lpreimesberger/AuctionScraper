#!/usr/bin/env python3
"""
AuctionScraper - Nellis Auction item finder

Usage:
    python main.py              # default: update + expire + classify + report
    python main.py --full       # full initial scrape (all pages)
    python main.py --update     # incremental scrape only
    python main.py --classify   # re-classify unclassified items
    python main.py --report     # generate report from existing data
    python main.py --woot       # Woot only: fetch + classify + report
"""

import argparse
import sys

import db


def run_woot():
    """Separate Woot pipeline (own DB + report). Never raises, so it can't break the Nellis run."""
    try:
        import woot, woot_classifier, woot_db, woot_report
        woot_db.init_db()
        woot.scrape()
        try:
            woot_classifier.classify()
        except Exception as e:
            print(f"[main] Woot classifier error (is Ollama running?): {e}")
        report_path = woot_report.generate_report()
        if report_path:
            print(f"\n  Open Woot report: file://{report_path}\n")
    except Exception as e:
        print(f"[main] Woot pipeline error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Nellis Auction Scraper & Classifier")
    parser.add_argument("--full", action="store_true", help="Full scrape (all pages)")
    parser.add_argument("--update", action="store_true", help="Incremental scrape only")
    parser.add_argument("--classify", action="store_true", help="Classify items only")
    parser.add_argument("--report", action="store_true", help="Generate report only")
    parser.add_argument("--woot", action="store_true", help="Woot pipeline only")
    args = parser.parse_args()

    db.init_db()

    # If no specific flags, run the full pipeline (incremental)
    run_all = not any([args.full, args.update, args.classify, args.report, args.woot])

    if args.woot:
        run_woot()
        return

    # Always expire closed auctions first
    if run_all or args.full or args.update:
        expired = db.expire_closed_items()
        if expired:
            print(f"[main] Expired {expired} closed auctions")
        stats = db.get_stats()
        print(f"[main] DB has {stats['total']} active items")

    if args.full:
        from scraper import scrape
        scrape(full=True)
    elif args.update or run_all:
        from scraper import scrape
        scrape(full=False)

    if args.classify or run_all:
        from classifier import classify
        try:
            classify()
        except Exception as e:
            print(f"[main] Classifier error (is Ollama running?): {e}")
            if not run_all:
                sys.exit(1)

    if args.report or run_all:
        from report import generate_report
        report_path = generate_report()
        if report_path:
            print(f"\n  Open report: file://{report_path}\n")

    if run_all:
        run_woot()


if __name__ == "__main__":
    main()

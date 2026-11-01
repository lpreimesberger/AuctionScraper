# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Automated scraper + classifier for Nellis Auction (nellisauction.com), Katy TX location. Scrapes ~22k auction items nightly, classifies them against a configurable interest list using a local LLM (Ollama), and generates an HTML report of matching items with links.

## Architecture

```
main.py              # CLI entry point: --full, --update, --classify, --report
├── scraper.py       # Playwright-based fetcher (browser context for bot evasion)
├── db.py            # SQLite layer (auction.db)
├── classifier.py    # Ollama batch classification against interests.txt
├── report.py        # HTML report generator → reports/
├── config.py        # All constants (URLs, delays, model, paths)
└── interests.txt    # One interest per line (user-editable)
```

## Key Technical Details

- **Nellis is a Remix / React Router app backed by Algolia.** The single-fetch data endpoint is:
  `GET /search.data?Location+Name=Katy&sortBy=time_remaining_desc&_p1=s%3A120%2Cn%3A{PAGE}&_routes=routes/search._index`
- Pagination: `_p1=s:120,n:{page_num}` (0-indexed, 120 items/page)
- Product links: `https://www.nellisauction.com/p/{slug}/{id}` (slug generated from first 12 words of title)
- They use Kaptcha bot detection — scraper uses Playwright (real Chromium) and `page.evaluate(fetch(...))` from within the browser context
- Product IDs are roughly auto-incrementing (currently in 89M-90M range)

## Commands

```bash
source venv/bin/activate

python main.py              # nightly pipeline: incremental scrape + classify + report
python main.py --full       # initial full scrape (all ~185 pages, takes ~10min)
python main.py --update     # incremental scrape only (stops at known items)
python main.py --classify   # re-classify unclassified items via Ollama
python main.py --report     # regenerate HTML report from DB

# Individual modules work standalone too:
python scraper.py --full
python classifier.py
python report.py
```

## Wrapper Scripts

For convenience, use these executable scripts:

```bash
./run.sh           # incremental scrape + classify + report (default pipeline)
./run-full.sh      # full scrape + classify + report
./run-update.sh    # incremental scrape only (no classify/report)
./run-classify.sh  # classify only (no scrape)
./run-report.sh    # generate report only
```

The nightly cron job uses `run_nightly.sh` (logs to `logs/`).

## Dependencies

- Python 3.12, venv at `./venv`
- `playwright` + `ollama` (see requirements.txt)
- Playwright Chromium: `playwright install chromium`
- Ollama must be running locally with a pulled model (default: `llama3.2:3b`)

## Data Flow

1. **Scrape** → Playwright fetches JSON pages → upserts into `auction.db`
2. **Expire** → DELETEs items where `close_time < now`
3. **Classify** → unclassified items sent to Ollama in batches of 20 → marks `is_interesting`
4. **Report** → interesting + un-notified items → `reports/report-{date}.html`

## Woot Pipeline (separate from Nellis)

`python main.py --woot` / `./run-woot.sh` runs it alone; the default `python main.py` (and so `run.sh` / `run_nightly.sh`) runs it after Nellis. A Woot failure never fails the Nellis run.

- `woot.py` (fetch) → `woot_db.py` (`woot.db`) → `woot_classifier.py` → `woot_report.py` → `reports/woot-{date}.html`
- API key: `WOOT_API_KEY` in `.env` (gitignored). `GET /feed/All` with no `page` returns the whole ~5k-offer catalog in one request (quota is 1000/day).
- Config lists: `woot_interests.txt` (Ollama-verified), `woot_stockup.txt` (keyword + discount, no LLM), `woot_exclude.txt`. Thresholds are `WOOT_*` in `config.py`.
- Woot list prices are heavily inflated (Invicta, Tucci watches...), so crazy deals are >=80% off list; junk brands go in `woot_exclude.txt`.
- Tests: `python -m unittest tests.test_woot`

## eBay Watchlist (separate from Nellis and Woot)

Run alone with `python main.py --ebay` / `./run-ebay.sh`; the default `python main.py` (and so `run.sh`) runs it after Woot, and both still run if Nellis throws.

- `ebay.py` (Browse API search) -> `ebay_db.py` (`ebay.db`) -> `ebay_report.py` -> `reports/ebay-{date}.html`. No Ollama.
- Keys: `EBAY_PRO_APP_ID` / `EBAY_PRO_CERT_ID` in `.env` (production keyset; sandbox only has fake listings). A new keyset 401s with `invalid_client` until the Marketplace Account Deletion exemption is done.
- Terms live in `ebay_watch.txt` (watchlist, no price check); `ebay_exclude.txt` hides title words. Thresholds are `EBAY_*` in `config.py`.
- Auctions have `currentBidPrice`, often no `price`. Seller names are deliberately NOT stored (the keyset exemption says no user data is persisted).
- Tried and removed: interest search + Ollama verify + comparable-listing price check ("deals"). eBay prices run above retail, so it surfaced noise.
- Tests: `python -m unittest tests.test_ebay`

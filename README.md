# AuctionScraper

Automated deal finders that turn three sources into one daily set of HTML reports, so you stop digging through listings by hand:

- **Nellis Auction** (Katy, TX location): scrapes ~22,000 live auction items nightly, classifies them against a configurable interest list using a local LLM (Ollama), and reports matches with direct links.
- **Woot**: pulls the whole catalog from the official API and reports interests, stock-up deals and steep discounts.
- **eBay watchlist**: searches the official Browse API for auctions ending soon on terms you choose (a game system, a printer brand, anything with no reliable price) and reports them grouped by term.

Each source has its own database, config lists and report. A failure in one never stops the others.

## Features

- Scrapes all active auction listings via Nellis's internal Algolia-backed JSON API
- Incremental updates: only fetches new items on subsequent runs
- Two-phase classification: fast regex pre-screening followed by LLM verification to reduce false positives
- Exclusion list to filter out categories you never want to see
- Highlights "crazy deals" — items at ≤8% of retail value (configurable)
- Self-contained HTML report with item links, prices, and current bid info
- Cron-friendly nightly pipeline with logging

## Requirements

- Python 3.12+
- Nellis: [Ollama](https://ollama.com) running locally with a pulled model, and Playwright Chromium
- Woot: a free API key (see [Woot](#woot))
- eBay: a developer account and production keys (see [eBay watchlist](#ebay-watchlist)). No Ollama needed.

You only need to set up the sources you want. Woot and eBay are skipped cleanly if their keys are missing.

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/lpreimesberger/AuctionScraper.git
cd AuctionScraper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Playwright's Chromium browser

```bash
playwright install chromium
```

### 3. Install and start Ollama

Download Ollama from [ollama.com](https://ollama.com), then pull the default model:

```bash
ollama pull qwen2.5:7b
```

Start the Ollama server (it usually runs as a background service after install):

```bash
ollama serve
```

You can change the model in `config.py` by editing `OLLAMA_MODEL`.

### 4. Configure your interests

Edit `interests.txt` — one keyword/phrase per line. The classifier will find auction items matching these categories:

```
tools
camping gear
power tools
generators
solar
Computers
```

Edit `exclude.txt` to add terms that should always be filtered out (e.g., `baby`, `jewelry`, `cosmetics`).

### 5. (Optional) Change location

The scraper defaults to **Katy, TX** (Nellis shopping location ID 5). To change to a different Nellis location, update `SHOPPING_LOCATION_ID` in `config.py`.

## Usage

### Run the full pipeline

```bash
source venv/bin/activate
python main.py
```

This runs: incremental scrape → expire closed auctions → classify new items → generate HTML report.

### Command-line flags

```bash
python main.py              # default pipeline (incremental scrape + classify + report)
python main.py --full       # full scrape of all pages (~185 pages, ~10 min first run)
python main.py --update     # incremental scrape only (no classify/report)
python main.py --classify   # re-classify unclassified items only
python main.py --report     # regenerate HTML report from existing data
python main.py --woot       # Woot only: fetch + classify + report
python main.py --ebay       # eBay watchlist only: fetch + report
```

The default `python main.py` runs Nellis, then Woot, then eBay. Woot and eBay still run if Nellis fails.

### Convenience scripts

```bash
./run.sh           # incremental scrape + classify + report
./run-full.sh      # full scrape + classify + report
./run-update.sh    # incremental scrape only
./run-classify.sh  # classify only
./run-report.sh    # generate report only
./run-woot.sh      # Woot only
./run-ebay.sh      # eBay watchlist only
```

### First run

On first run, do a full scrape to populate the database:

```bash
python main.py --full
```

Subsequent runs use incremental mode and stop as soon as they hit items already in the database.

## Woot

1. Get a free API key at [developer.woot.com](https://developer.woot.com) and put it in `.env` as `WOOT_API_KEY` (copy `.env.example`).
2. Edit the lists:
   - `woot_interests.txt`: keywords, verified by Ollama like Nellis
   - `woot_stockup.txt`: everyday items, matched by keyword and a minimum discount (no LLM)
   - `woot_exclude.txt`: junk brands to hide. Woot list prices are heavily inflated, so deliberately steep thresholds (`WOOT_*` in `config.py`) pick out the "crazy deals".
3. `python main.py --woot` writes `reports/woot-YYYY-MM-DD.html`.

The whole ~5,000-offer catalog comes back in one request, well within the 1,000/day quota.

## eBay watchlist

For things with no reliable price (collectible game books, a printer brand) where the pain is the searching. It lists auctions ending within a week, per term, soonest first. There is no price check and no LLM. We tried automatic deal-finding against comparable listings and it was mostly noise, since eBay is generally priced above retail.

1. **Get production keys.** Create a developer account at [developer.eBay.com](https://developer.ebay.com) and generate a **Production** keyset (sandbox keys won't work: the sandbox only contains fake test listings).
2. **Activate the keyset.** New production keysets are disabled until you deal with eBay's *Marketplace Account Deletion* requirement. In the developer portal, either subscribe an endpoint or request the exemption for apps that don't store eBay user data (that's this one: it stores item titles, prices and links, and never seller or buyer data). Until then every token request fails with `401 invalid_client`, even when the keys are correct. It can take a few minutes after you complete this.
3. **Add the keys** to `.env` as `EBAY_PRO_APP_ID` and `EBAY_PRO_CERT_ID` (see `.env.example`).
4. **Choose your searches** in `ebay_watch.txt`, one per line, and set `EBAY_ZIP` in `config.py` to your own zip code.
5. `python main.py --ebay` writes `reports/ebay-YYYY-MM-DD.html`.

A line is a plain search (`qidi`: every word must appear, any order, case ignored, no quotes) or a search limited to one category with `|`: `warhammer | books`. The category is a name from `EBAY_CATEGORIES` in `config.py` (just `books` so far; add more) or a raw numeric eBay category ID. Category searches catch listings that never use the obvious word (novels that don't say "book"), while plain searches catch things filed in the wrong category, so combining both works well.

Use `ebay_exclude.txt` to hide noisy title words. Each listing appears in a report only once, so open it right after you run. Terms with a lot of auctions are capped at the 200 that end soonest (`EBAY_MAX_PER_QUERY`); the rest roll in on later runs. Also in `config.py`: `EBAY_WINDOW_HOURS` (look-ahead, default one week) and `EBAY_MAX_BID`.

Notes if you hack on it: auctions come back from the Browse API with `currentBidPrice` and often no `price`; shipping can be missing for calculated-shipping listings. Review eBay's [API License Agreement](https://developer.ebay.com/join/api-license-agreement) before redistributing anything pulled from the API.

## Nightly Automation

Add to your crontab to run automatically at 2 AM:

```
0 2 * * * /path/to/AuctionScraper/run_nightly.sh
```

Logs are written to `logs/nightly-YYYY-MM-DD.log`.

## Project Structure

```
main.py           # CLI entry point
scraper.py        # Playwright-based fetcher (bypasses bot detection)
db.py             # SQLite layer (auction.db)
classifier.py     # Two-phase classifier: regex pre-screen + Ollama LLM verification
report.py         # HTML report generator → reports/
config.py         # All constants (URLs, delays, model, paths)
interests.txt     # Your interest categories (one per line)
exclude.txt       # Terms to always exclude (one per line)
run_nightly.sh    # Cron wrapper with logging

woot.py, woot_db.py, woot_classifier.py, woot_report.py   # Woot pipeline (woot.db)
woot_interests.txt, woot_stockup.txt, woot_exclude.txt    # Woot lists

ebay.py, ebay_db.py, ebay_report.py                       # eBay watchlist (ebay.db)
ebay_watch.txt, ebay_exclude.txt                          # eBay lists
.env.example                                              # API key names for Woot and eBay
tests/                                                    # python -m unittest discover tests
```

## How It Works

### Scraping

Nellis Auction is a Remix (React SSR) app backed by Algolia search with Kaptcha bot detection. The scraper uses Playwright to launch a real Chromium browser, establish a session, and then uses `page.evaluate(fetch(...))` to make API calls from within the browser context — inheriting the session cookies and bypassing bot checks.

The JSON data endpoint is Nellis's internal Remix loader:
```
GET /search?Location+Name=Katy&sortBy=time_remaining_desc&_p1=s:120,n:{PAGE}&_data=routes/search
```

### Classification

1. **Regex pre-screening**: Each unclassified item title is checked against keyword patterns for every interest category. Items that don't match any pattern are immediately marked as not interesting.
2. **LLM verification**: Candidate items are sent to Ollama in batches of 25. The LLM confirms which items truly match the interest (filtering false positives like "coffee table" when searching for "coffee").

### Report

An HTML file is generated in `reports/` containing all interesting items that haven't been reported yet, sorted by interest category. Items flagged as "crazy deals" (≤8% of retail price, retail ≥ $75) are highlighted.

## Configuration

All tunable constants live in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `LOCATION` | `"Katy"` | Nellis location name |
| `SHOPPING_LOCATION_ID` | `"5"` | Nellis location ID (5 = Houston/Katy) |
| `OLLAMA_MODEL` | `"qwen2.5:7b"` | Ollama model for classification |
| `MIN_DELAY` / `MAX_DELAY` | `2.0` / `5.0` sec | Random delay between page fetches |
| `CRAZY_DEAL_MIN_RETAIL` | `$75.00` | Minimum retail price for "crazy deal" flag |
| `CRAZY_DEAL_MAX_RATIO` | `0.08` | Max bid/retail ratio to qualify as "crazy deal" |
| `EBAY_ZIP` | `"77494"` | Your zip code (sets eBay shipping/location context) |
| `EBAY_WINDOW_HOURS` | `168` | How far ahead to look for ending auctions |
| `EBAY_MAX_BID` | `250.0` | Ignore auctions already bid above this |
| `EBAY_MAX_PER_QUERY` | `200` | Soonest-ending results kept per watchlist term |

## License

Apache 2.0 — see [LICENSE](LICENSE).

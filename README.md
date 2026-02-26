# AuctionScraper

Automated scraper, classifier, and report generator for [Nellis Auction](https://nellisauction.com) — specifically the Katy, TX location. Scrapes ~22,000 live auction items nightly, classifies them against a configurable interest list using a local LLM (Ollama), and generates an HTML report of matching items with direct links.

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
- [Ollama](https://ollama.com) running locally with a pulled model
- Playwright Chromium

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
```

### Convenience scripts

```bash
./run.sh           # incremental scrape + classify + report
./run-full.sh      # full scrape + classify + report
./run-update.sh    # incremental scrape only
./run-classify.sh  # classify only
./run-report.sh    # generate report only
```

### First run

On first run, do a full scrape to populate the database:

```bash
python main.py --full
```

Subsequent runs use incremental mode and stop as soon as they hit items already in the database.

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

## License

Apache 2.0 — see [LICENSE](LICENSE).

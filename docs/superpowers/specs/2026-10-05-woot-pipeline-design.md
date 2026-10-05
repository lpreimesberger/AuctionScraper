# Woot pipeline (separate from Nellis)

## Goal
Nightly Woot scan producing `reports/woot-{date}.html`, run from `run.sh` via `python main.py` (default pipeline) and `python main.py --woot` (Woot only).

## API facts (verified 2026-10-05)
- `GET https://developer.woot.com/feed/All`, header `x-api-key` (from `.env` `WOOT_API_KEY`).
- No `page` param returns the entire catalog (~5,000 offers, 3.5MB) in one request; `?page=N` returns 100/page (51 pages). Use the single call (1 req/night vs 1,000/day quota).
- Item fields: OfferId, Title, Subtitle, Condition (mostly null), ListPrice{Minimum,Maximum} (null for ~26%), SalePrice{Minimum,Maximum}, Categories, Site, Photo, Url, EndDate, IsSoldOut.
- List prices are heavily inflated (e.g. Invicta watches), so % off is only a loose signal.

## Design
Self-contained; does not touch `db.py` / `scraper.py` / `classifier.py` / `report.py`.
- `woot.py`: fetch + parse (stdlib `urllib`, tiny `.env` reader, no new deps), 429/error handling.
- `woot_db.py`: `woot.db`, table `woot_offers` keyed by OfferId; upsert; drop ended/sold-out; `notified` flag.
- `woot_classifier.py`: keyword prescreen + Ollama verify for `woot_interests.txt` (gadgets), honoring `woot_exclude.txt`.
- `woot_report.py`: `reports/woot-{date}.html`, three sections:
  1. Interesting: matches from `woot_interests.txt`.
  2. Stock-up: keyword match against `woot_stockup.txt` (socks, snacks, paper goods, ...) and >= 40% off list. No LLM.
  3. Crazy deals: >= 80% off list and list >= $40, minus excludes; top 40 by dollars saved.
- Thresholds in `config.py`. Discount = 1 - SalePrice.Minimum / ListPrice.Minimum. Offers with no ListPrice only appear under Interesting.
- Wiring: `main.py` gains `--woot` and runs Woot in the default pipeline after Nellis; a Woot failure must not fail the Nellis run. `run-woot.sh` for standalone.

## Testing
Parser and deal math unit-tested against a saved trimmed sample response; one live smoke run.

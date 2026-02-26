#!/usr/bin/env bash
# Nightly auction scraper run
# Add to crontab: 0 2 * * * /home/lpreimesberger/projects/AuctionScraper/run_nightly.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate
python main.py 2>&1 | tee -a "logs/nightly-$(date +%Y-%m-%d).log"

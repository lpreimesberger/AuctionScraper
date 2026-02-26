#!/usr/bin/env bash
# Run full scrape + classify + report

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting FULL scrape..."
python main.py --full
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
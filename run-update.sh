#!/usr/bin/env bash
# Run incremental scrape only (no classification or report)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting incremental scrape only..."
python main.py --update
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
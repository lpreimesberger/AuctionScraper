#!/usr/bin/env bash
# Generate HTML report from existing data

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Generating report..."
python main.py --report
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
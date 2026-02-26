#!/usr/bin/env bash
# Run classification only on unclassified items

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting classification..."
python main.py --classify
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done."
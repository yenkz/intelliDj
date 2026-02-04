#!/bin/sh
set -e

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

python -m pip install -r requirements.txt

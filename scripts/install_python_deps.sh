#!/bin/sh
set -e

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

if ! command -v poetry >/dev/null 2>&1; then
  python -m pip install poetry
fi

poetry install --no-root

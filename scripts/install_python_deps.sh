#!/bin/sh
set -e

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

uv sync --group dev

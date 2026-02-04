#!/bin/sh
set -e

LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "$0" .sh).log"
mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

SRC="$HOME/Soulseek/downloads/complete"
CFG="$HOME/.config/beets/config.yaml"
LOCK="/tmp/intellidj_beets.lock"

# Avoid overlapping runs
if [ -e "$LOCK" ]; then
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT
touch "$LOCK"

# Only run if there are audio files
if find "$SRC" -type f \( -iname "*.mp3" -o -iname "*.flac" -o -iname "*.wav" -o -iname "*.aiff" \) | grep -q .; then
  poetry run beet -c "$CFG" import -q -s "$SRC"
fi

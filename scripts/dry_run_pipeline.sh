#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "${BASH_SOURCE[0]}" .sh).log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

SPOTIFY_CSV="spotify_export.csv"
CANDIDATES_CSV="dj_candidates.csv"
DOWNLOADS_DIR="$HOME/Soulseek/downloads/complete"
BEETS_CONFIG="$HOME/.config/beets/config.yaml"
LIBRARY_DIR="$HOME/Music/DJ/library"
SKIP_TAGS=0
SKIP_BEETS=0
SKIP_LOUDNORM=0

usage() {
  cat <<'EOF'
Usage: scripts/dry_run_pipeline.sh [options]

Options:
  --csv <path>             Spotify CSV path (default: spotify_export.csv)
  --candidates <path>      Output candidates CSV (default: dj_candidates.csv)
  --downloads-dir <path>   slskd downloads directory (default: ~/Soulseek/downloads/complete)
  --beets-config <path>    beets config (default: ~/.config/beets/config.yaml)
  --library-dir <path>     library dir for loudnorm dry-run (default: ~/Music/DJ/library)
  --no-tags                Skip tag enrichment dry-run
  --no-beets               Skip beets import preview
  --no-loudnorm            Skip loudnorm dry-run
  -h, --help               Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --csv)
      SPOTIFY_CSV="$2"
      shift 2
      ;;
    --candidates)
      CANDIDATES_CSV="$2"
      shift 2
      ;;
    --downloads-dir)
      DOWNLOADS_DIR="$2"
      shift 2
      ;;
    --beets-config)
      BEETS_CONFIG="$2"
      shift 2
      ;;
    --library-dir)
      LIBRARY_DIR="$2"
      shift 2
      ;;
    --no-tags)
      SKIP_TAGS=1
      shift
      ;;
    --no-beets)
      SKIP_BEETS=1
      shift
      ;;
    --no-loudnorm)
      SKIP_LOUDNORM=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

echo "==> Dry-run pipeline"
echo "CSV: $SPOTIFY_CSV"
echo "Candidates: $CANDIDATES_CSV"
echo "Downloads: $DOWNLOADS_DIR"
echo "Beets config: $BEETS_CONFIG"
echo "Library: $LIBRARY_DIR"
echo ""

echo "==> Step 1: Generate candidates"
poetry run python csv_to_dj_pipeline.py --input "$SPOTIFY_CSV" --output "$CANDIDATES_CSV"

echo ""
echo "==> Step 2: slskd download (dry-run)"
poetry run python dj_to_slskd_pipeline.py --csv "$CANDIDATES_CSV" --dry-run

if [[ "$SKIP_TAGS" -eq 0 ]]; then
  echo ""
  echo "==> Step 3: Tag enrichment (dry-run)"
  poetry run python scripts/enrich_tags_from_spotify_csv.py \
    --csv "$SPOTIFY_CSV" \
    --input-dir "$DOWNLOADS_DIR" \
    --custom-tags \
    --dry-run
fi

if [[ "$SKIP_BEETS" -eq 0 ]]; then
  echo ""
  echo "==> Step 4: Beets import (preview)"
  poetry run beet -c "$BEETS_CONFIG" import -p -s "$DOWNLOADS_DIR"
fi

if [[ "$SKIP_LOUDNORM" -eq 0 ]]; then
  echo ""
  echo "==> Step 5: Loudnorm (dry-run)"
  scripts/normalize_loudness.sh --input-dir "$LIBRARY_DIR" --dry-run
fi

echo ""
echo "Done. Dry-run complete."

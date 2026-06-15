#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "${BASH_SOURCE[0]}" .sh).log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

SPOTIFY_CSV="spotify_export.csv"
SCAN_DIR=""
DOWNLOADS_DIR="$HOME/Soulseek/downloads/complete"
BEETS_CONFIG="$HOME/.config/beets/config.yaml"
LIBRARY_DIR="$HOME/Music/DJ/library"
DB_PATH="intellidj.db"
LABEL=""
SCOPE="new"
SKIP_TAGS=0
SKIP_BEETS=0
SKIP_LOUDNORM=0

usage() {
  cat <<'EOF'
Usage: scripts/dry_run_pipeline.sh [options]

Options:
  --csv <path>             Spotify CSV path (default: spotify_export.csv)
  --scan-dir <path>        Optional local scan directory before CSV import
  --db-path <path>         Lifecycle SQLite DB path (default: intellidj.db)
  --label <value>          Optional batch label for this run
  --scope <new|existing|all>  DB processing scope (default: new)
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
    --scan-dir)
      SCAN_DIR="$2"
      shift 2
      ;;
    --db-path)
      DB_PATH="$2"
      shift 2
      ;;
    --label)
      LABEL="$2"
      shift 2
      ;;
    --scope)
      SCOPE="$2"
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
echo "Scan dir: ${SCAN_DIR:-<none>}"
echo "DB: $DB_PATH"
echo "Label: ${LABEL:-<none>}"
echo "Scope: $SCOPE"
echo "Downloads: $DOWNLOADS_DIR"
echo "Beets config: $BEETS_CONFIG"
echo "Library: $LIBRARY_DIR"
echo ""

echo "==> Step 1-3: DB-first orchestrator dry-run"
CMD=(poetry run python scripts/run_pipeline.py --db-path "$DB_PATH" --csv "$SPOTIFY_CSV" --downloads-dir "$DOWNLOADS_DIR" --scope "$SCOPE" --dry-run --skip-enrich)
if [[ -n "$SCAN_DIR" ]]; then
  CMD+=(--scan-dir "$SCAN_DIR")
fi
if [[ -n "$LABEL" ]]; then
  CMD+=(--label "$LABEL")
fi
"${CMD[@]}"

if [[ "$SKIP_TAGS" -eq 0 ]]; then
  echo ""
  echo "==> Step 4: Tag enrichment (dry-run, DB metadata)"
  CMD=(poetry run python scripts/enrich_tags_from_spotify_csv.py \
    --db-path "$DB_PATH" \
    --input-dir "$DOWNLOADS_DIR" \
    --scope "$SCOPE" \
    --custom-tags \
    --dry-run)
  if [[ -n "$LABEL" ]]; then
    CMD+=(--label "$LABEL")
  fi
  "${CMD[@]}"
fi

if [[ "$SKIP_BEETS" -eq 0 ]]; then
  echo ""
  echo "==> Step 5: Beets import (preview)"
  CMD=(poetry run python scripts/run_beets_import.py --db-path "$DB_PATH" --beets-config "$BEETS_CONFIG" --input-dir "$DOWNLOADS_DIR" --scope "$SCOPE" --dry-run)
  if [[ -n "$LABEL" ]]; then
    CMD+=(--label "$LABEL")
  fi
  "${CMD[@]}"
fi

if [[ "$SKIP_LOUDNORM" -eq 0 ]]; then
  echo ""
  echo "==> Step 6: Loudnorm (dry-run)"
  scripts/normalize_loudness.sh --input-dir "$LIBRARY_DIR" --dry-run
fi

echo ""
echo "Done. Dry-run complete."

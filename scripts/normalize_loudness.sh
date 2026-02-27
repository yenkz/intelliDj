#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/log"
LOG_FILE="$LOG_DIR/$(basename "${BASH_SOURCE[0]}" .sh).log"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

INPUT_DIR=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/normalize_loudness.sh --input-dir <path> [--dry-run]

Environment variables:
  TARGET_LUFS  Integrated loudness target (default: -9)
  TARGET_TP    True peak target (default: -1.0)
  TARGET_LRA   Loudness range target (default: 9)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir)
      INPUT_DIR="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
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

if [[ -z "${INPUT_DIR}" ]]; then
  echo "Missing --input-dir"
  usage
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found on PATH."
  exit 1
fi

TARGET_LUFS="${TARGET_LUFS:--9}"
TARGET_TP="${TARGET_TP:--1.0}"
TARGET_LRA="${TARGET_LRA:-9}"

input_dir_expanded="${INPUT_DIR/#\~/$HOME}"

encode_args_for_ext() {
  local ext="$1"
  case "$ext" in
    .flac)
      echo "-c:a flac"
      ;;
    .mp3)
      echo "-c:a libmp3lame -q:a 2"
      ;;
    .wav)
      echo "-c:a pcm_s16le"
      ;;
    .aif|.aiff)
      echo "-c:a pcm_s16be"
      ;;
    *)
      echo ""
      ;;
  esac
}

normalized=0
skipped=0
errors=0
found=0

while IFS= read -r -d '' path; do
  found=1
  ext="${path##*.}"
  ext=".$(printf '%s' "$ext" | tr '[:upper:]' '[:lower:]')"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $path"
    continue
  fi

  analysis_output="$(ffmpeg -hide_banner -nostdin -i "$path" \
    -af "loudnorm=I=${TARGET_LUFS}:TP=${TARGET_TP}:LRA=${TARGET_LRA}:print_format=json" \
    -f null - 2>&1 || true)"

  if [[ -z "$analysis_output" ]]; then
    echo "[skip] no loudnorm analysis for: $path"
    ((skipped++))
    continue
  fi

  read -r measured_i measured_tp measured_lra measured_thresh offset < <(
    printf '%s' "$analysis_output" | python3 -c '
import json
import sys

text = sys.stdin.read()
start = text.rfind("{")
end = text.rfind("}")
if start < 0 or end < 0 or end <= start:
    print("", "", "", "", "")
    raise SystemExit(0)

try:
    data = json.loads(text[start:end + 1])
except Exception:
    print("", "", "", "", "")
    raise SystemExit(0)

print(
    data.get("input_i", ""),
    data.get("input_tp", ""),
    data.get("input_lra", ""),
    data.get("input_thresh", ""),
    data.get("target_offset", ""),
)
'
  )

  if [[ -z "$measured_i" || -z "$offset" ]]; then
    echo "[skip] incomplete loudnorm analysis for: $path"
    ((skipped++))
    continue
  fi

  dir="$(dirname "$path")"
  base="$(basename "$path")"
  tmp="${dir}/.${base}.loudnorm.tmp${ext}"

  encode_args="$(encode_args_for_ext "$ext")"

  if ! ffmpeg -hide_banner -nostdin -i "$path" -map_metadata 0 \
    -af "loudnorm=I=${TARGET_LUFS}:TP=${TARGET_TP}:LRA=${TARGET_LRA}:measured_I=${measured_i}:measured_TP=${measured_tp}:measured_LRA=${measured_lra}:measured_thresh=${measured_thresh}:offset=${offset}:linear=true:print_format=summary" \
    $encode_args "$tmp" 2>/dev/null; then
    echo "[error] loudnorm failed: $path"
    rm -f "$tmp"
    ((errors++))
    continue
  fi

  mv -f "$tmp" "$path"
  ((normalized++))
  echo "[ok] normalized: $path"
done < <(
  find "$input_dir_expanded" -type f \( \
    -iname '*.flac' -o -iname '*.mp3' -o -iname '*.wav' -o -iname '*.aif' -o -iname '*.aiff' \
  \) -print0
)

if [[ "$found" -eq 0 ]]; then
  echo "No audio files found in $input_dir_expanded"
  exit 0
fi

echo ""
echo "Done. normalized=${normalized} skipped=${skipped} errors=${errors}"

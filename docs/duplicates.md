# Duplicate Track Detection

Use `find_duplicate_tracks.py` to detect repeated tracks either:

- within one folder, or
- between two folders.

The script supports these actions:

- report only
- move duplicates to a review folder
- auto-delete duplicates

And these keep policies:

- keep best quality (`best`, default)
- keep newest (`newest`)
- keep oldest (`oldest`)

## UI usage (same look and feel as IntelliDj Pipeline)

Launch the dedicated duplicate finder UI:

```bash
make duplicates-ui
```

Or directly:

```bash
poetry run streamlit run ui/streamlit_duplicates_app.py
```

The UI includes:

- `Pipeline` + `Logs` tabs
- quick readiness checks for source/compare/review paths
- safe defaults (`report`/`dry-run`)
- export controls for CSV/JSON reports

### UI flow (recommended)

The UI is organized in this order:

0. **Select Action and Keep Policy**
- Choose `report`, `move`, or `delete`.
- Choose keep policy: `best`, `newest`, `oldest`.
- In report mode, optionally write CSV/JSON output file.

1. **Select Source and Compare Folders**
- Source is required.
- Compare is optional (if omitted, duplicates are searched within source only).
- In delete mode with compare enabled, choose where to delete from: `source` or `compare`.

2. **Safe Preview**
- Enable `dry-run` to preview decisions with no file changes.

3. **Matching Strategy**
- Choose `hybrid`, `hash`, or `metadata`.
- Tune `duration bucket seconds` for metadata grouping.

4. **Safety Parameters**
- Enable empty-folder cleanup after move/delete.
- Confirm destructive actions when dry-run is disabled.

### macOS path browsing

On macOS, the UI provides Finder-based **Browse** buttons for:

- source folder
- compare folder
- review folder
- report output file

## CLI usage

Basic report (single folder):

```bash
poetry run python scripts/find_duplicate_tracks.py --source-dir ~/Music/DJ/library
```

Compare two folders (cross-folder duplicates only):

```bash
poetry run python scripts/find_duplicate_tracks.py \
  --source-dir ~/Music/DJ/library \
  --compare-dir ~/Soulseek/downloads/complete
```

Export reports:

```bash
poetry run python scripts/find_duplicate_tracks.py \
  --source-dir ~/Music/DJ/library \
  --export-csv reports/duplicates.csv \
  --export-json reports/duplicates.json
```

Move duplicates to review folder:

```bash
poetry run python scripts/find_duplicate_tracks.py \
  --source-dir ~/Music/DJ/library \
  --action move \
  --review-dir ~/Music/DJ/review_duplicates \
  --keep-strategy best \
  --yes
```

Delete duplicates automatically:

```bash
poetry run python scripts/find_duplicate_tracks.py \
  --source-dir ~/Music/DJ/library \
  --action delete \
  --keep-strategy newest \
  --cleanup-empty-dirs \
  --yes
```

Safe preview (no file changes):

```bash
poetry run python scripts/find_duplicate_tracks.py \
  --source-dir ~/Music/DJ/library \
  --action delete \
  --keep-strategy newest \
  --dry-run
```

## Matching strategy

- `--match-mode hybrid` (default): combines file hash and metadata (artist/title/duration bucket).
- `--match-mode hash`: only identical file content.
- `--match-mode metadata`: metadata-based matching only.

When comparing two folders (`--compare-dir`), you can force which side to keep with:

- `--prefer-origin source`
- `--prefer-origin compare`

Tune metadata grouping with:

- `--duration-bucket-seconds` (default: `2`)

## Safety

- `move` and `delete` require `--yes` unless `--dry-run` is used.
- `report` never modifies files.
- Start with `--dry-run` and report export before destructive actions.
- `--cleanup-empty-dirs` (move/delete) removes empty parent folders under scanned roots.

## Makefile helper

```bash
make duplicates DUP_SOURCE=~/Music/DJ/library DUP_ACTION=report
```

Examples:

```bash
make duplicates DUP_SOURCE=~/Music/DJ/library DUP_ACTION=move DUP_REVIEW=~/Music/DJ/review_duplicates DUP_DRY_RUN=0
make duplicates DUP_SOURCE=~/Music/DJ/library DUP_ACTION=delete DUP_KEEP=oldest DUP_CLEANUP_EMPTY=1 DUP_DRY_RUN=0
make duplicates DUP_SOURCE=~/Music/DJ/library DUP_COMPARE=~/Soulseek/downloads/complete DUP_PREFER_ORIGIN=source
```

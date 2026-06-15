# DB-first Pipeline

`intellidj.db` is the source of truth. CSV is used only for ingestion (and optional export from DB).

## Independent Steps

1. Optional local scan:

   ```bash
   poetry run python scripts/scan_local_music.py --input-dir ~/Music --db-path intellidj.db --label my_set
   ```

2. Import Exportify CSV (English or Spanish column names both supported):

   ```bash
   poetry run python csv_to_dj_pipeline.py --input spotify_export.csv --db-path intellidj.db --label my_set
   ```

3. Queue slskd downloads from DB:

   ```bash
   poetry run python dj_to_slskd_pipeline.py --db-path intellidj.db --scope new --label my_set
   ```

   Or directly from a raw Exportify CSV (no pre-built `search_string` column required):

   ```bash
   poetry run python dj_to_slskd_pipeline.py --csv csv/my_export.csv
   ```

4. Stage downloads to inbox — flattens subfolders and renames files to `Artist - Title.ext` using embedded tags:

   ```bash
   # All completed downloads
   make stage-downloads

   # Only files modified since a given time today (HH:MM local, CEST or system tz)
   make stage-downloads SINCE=08:45

   # Scope to a subfolder, filter by time, move instead of copy, and deduplicate
   make stage-downloads SINCE=08:45 DLS_FOLDER="Artist Name" MOVE=1 DEDUPE=1
   ```

   Or run directly with full control:

   ```bash
   poetry run python scripts/move_downloads_to_inbox.py \
     --downloads-dir ~/Soulseek/downloads/complete \
     --since 08:45 \
     --folder "Artist Name" \
     --move \
     --dedupe
   ```

   **`--since`** accepts `HH:MM` (today at that local time) or `YYYY-MM-DD HH:MM`.

   **`--dedupe`** keeps the best copy per `Artist - Title` in priority order: FLAC > WAV/AIF > M4A > MP3, then largest file size. Duplicates are removed after staging.

   **`--no-rename`** skips renaming and keeps original filenames.

5. Enrich tags from DB metadata:

   ```bash
   poetry run python scripts/enrich_tags_from_spotify_csv.py --db-path intellidj.db --scope new --label my_set --input-dir ~/Soulseek/downloads/complete --custom-tags
   ```

6. Run beets import with DB state update:

   ```bash
   poetry run python scripts/run_beets_import.py --db-path intellidj.db --beets-config ~/.config/beets/config.yaml --input-dir ~/Soulseek/downloads/complete --scope new --label my_set
   ```

7. Fetch and embed artwork (thumbnails):

   ```bash
   poetry run python scripts/run_cover_art.py --db-path intellidj.db --beets-config ~/.config/beets/config.yaml --scope new --label my_set
   ```

8. Optional duplicates lifecycle:

   ```bash
   poetry run python scripts/find_duplicate_tracks.py --source-dir ~/Music/DJ/library --db-path intellidj.db
   ```

## Selection Controls

- `--scope new|existing|all`
- `--label <batch_label>`
- `--batch-id <id>`

Use these to run stages on only the latest ingestion, older inventory, or all records.

## End-to-end Runner

```bash
poetry run python scripts/run_pipeline.py \
  --db-path intellidj.db \
  --csv spotify_export.csv \
  --label my_set \
  --scope new \
  --run-beets \
  --run-cover-art \
  --downloads-dir ~/Soulseek/downloads/complete \
  --report-json reports/pipeline_report.json
```

Add `--dry-run` to simulate supported stages and still emit a report.

## Optional DB CSV Export

```bash
poetry run python scripts/export_db_csv.py --db-path intellidj.db --dataset tracks --scope all --out exports/tracks.csv
```

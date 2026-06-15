# Lifecycle Database (SQLite)

IntelliDj can track the full music lifecycle in a local SQLite database:

- local folder scan ingestion
- Exportify CSV ingestion (full row metadata)
- candidate generation and slskd queue state
- tag enrichment outcomes
- beets import stage state
- duplicate detection decisions (`report`, `move`, `delete`)

## Default Location

By default, the DB is created at:

- `./intellidj.db`

Override with environment variable:

```bash
export INTELLIDJ_DB_PATH=~/Music/intellidj.db
```

Or pass `--db-path` on supported scripts.

## Initialize Explicitly (Optional)

The DB is auto-created on first script run, but you can initialize it manually:

```bash
make init-db
```

Equivalent:

```bash
poetry run python scripts/init_intellidj_db.py --db-path ./intellidj.db
```

If you already have historical data in legacy tables (`playlist_entries`, `track_events`), backfill once:

```bash
make backfill-db DB_PATH=intellidj.db IMPORT_LABEL=legacy-backfill
```

## Scripts with DB Tracking

- `scripts/scan_local_music.py`
- `csv_to_dj_pipeline.py`
- `dj_to_slskd_pipeline.py`
- `scripts/enrich_tags_from_spotify_csv.py`
- `scripts/run_beets_import.py`
- `scripts/find_duplicate_tracks.py`

Each script writes:

- `pipeline_runs`
- `tracks`
- `track_events`
- `assets`
- `playlist_entries` (CSV review pipeline)
- `duplicate_decisions` (duplicate lifecycle)
- `ingestion_batches` (labels/source/import method)
- `track_ingestions` (track<->batch links)
- `exportify_tracks` (Exportify-shaped metadata table)
- `library_files` (scanned local files)
- `track_stage_state` (latest status per stage per track)

## DB-first Selectors

DB-first scripts support selectors to process only specific subsets:

- `--scope new|existing|all`
- `--label <batch_label>`
- `--batch-id <id>`

Typical pattern:

```bash
poetry run python dj_to_slskd_pipeline.py --db-path intellidj.db --scope new --label my_set
```

## Quick Query Examples

Most recent runs:

```bash
sqlite3 intellidj.db "SELECT id, script_name, status, started_at, ended_at, success_count, skipped_count, error_count FROM pipeline_runs ORDER BY id DESC LIMIT 10;"
```

Recent failed events:

```bash
sqlite3 intellidj.db "SELECT created_at, stage, status, message, file_path FROM track_events WHERE status LIKE '%error%' ORDER BY id DESC LIMIT 20;"
```

Duplicate decisions:

```bash
sqlite3 intellidj.db "SELECT group_id, role, action, path, target_path, reason, created_at FROM duplicate_decisions ORDER BY id DESC LIMIT 50;"
```

Latest ingestion batches:

```bash
sqlite3 intellidj.db "SELECT id, source_type, import_method, label, source_ref, created_at FROM ingestion_batches ORDER BY id DESC LIMIT 20;"
```

Current stage state counts:

```bash
sqlite3 intellidj.db "SELECT stage, status, COUNT(*) FROM track_stage_state GROUP BY stage, status ORDER BY stage, status;"
```

## Integrity Check

Verify that every file path recorded in the database still exists on disk:

```bash
make check-integrity
# or
poetry run python scripts/check_db_integrity.py
```

The script runs four checks:

| Check | What it detects |
| --- | --- |
| `library_files` | DB rows whose audio file path no longer exists on disk |
| `assets` | `library_file` asset records pointing to missing files |
| `completed_downloads` | Downloads marked `completed` but whose file is gone |
| `tracks_without_files` | Tracks in DB with no linked audio file (info only — may not have been downloaded yet) |

Pass `--scan-dirs` to also report audio files on disk that are not tracked in `library_files`:

```bash
poetry run python scripts/check_db_integrity.py --scan-dirs ~/Music/DJ/library ~/Music/DJ/inbox
# or via Makefile
make check-integrity INTEGRITY_DIRS="~/Music/DJ/library ~/Music/DJ/inbox"
```

Apply non-destructive fixes (mark orphan records as `missing`, reset completed downloads with no file back to `pending` for retry):

```bash
make check-integrity INTEGRITY_FIX=1
# or
poetry run python scripts/check_db_integrity.py --fix
```

The script exits with code `0` (no issues) or `1` (issues found), so it can be used in CI pipelines.

Quick query to see all `missing` library files after a fix run:

```bash
sqlite3 intellidj.db "SELECT path, artist_tag, title_tag FROM library_files WHERE status = 'missing' ORDER BY last_seen_at DESC;"
```

## Wipe DB (Start from Scratch)

Delete the database and recreate an empty schema:

```bash
make wipe-db
# or (with confirmation prompt)
poetry run python scripts/wipe_db.py
# or (skip prompt)
poetry run python scripts/wipe_db.py --yes
```

The script deletes the `.db` file along with any SQLite journal files (`-wal`, `-shm`) and immediately re-creates the schema, leaving a fresh empty database ready for use.

## DB-first Flow (CSV only for import, optional DB export)

Import CSV into DB:

```bash
poetry run python csv_to_dj_pipeline.py --input spotify_export.csv --db-path intellidj.db --label my_set
```

Queue downloads from DB (no candidates CSV handoff):

```bash
poetry run python dj_to_slskd_pipeline.py --db-path intellidj.db --scope new --label my_set
```

Optional export from DB to CSV:

```bash
poetry run python scripts/export_db_csv.py --db-path intellidj.db --dataset tracks --scope all --out exports/tracks.csv
```

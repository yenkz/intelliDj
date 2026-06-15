# slskd (Docker + API Downloads)

## Run slskd with Docker

1. Install Docker Desktop (macOS/Windows) or Docker Engine + Compose (Linux).

2. Start the container:

   ```bash
   docker compose up -d
   ```

3. Open the web UI at `http://localhost:5030`.

4. Copy `.env.example` to `.env` and set credentials (web UI + Soulseek).

5. Ensure `slskd_data/slskd.yml` contains your API key with `readwrite` role, then restart the container.

To stop:

```bash
docker compose down
```

## API Downloads

Use `dj_to_slskd_pipeline.py` to queue downloads from DB-ingested candidates.

1. Ensure dependencies are installed (`make install-python` or `poetry install`).

2. Load environment variables:

   ```bash
   set -a && source .env && set +a
   ```

   PowerShell:

   ```powershell
   Get-Content .env | ForEach-Object {
     if ($_ -match '^[^#].+=') {
       $name, $value = $_ -split '=', 2
       [Environment]::SetEnvironmentVariable($name, $value, 'Process')
     }
   }
   ```

3. Run the downloader (DB-first):

   ```bash
   poetry run python dj_to_slskd_pipeline.py --db-path intellidj.db --scope new --label my_set
   ```

   Or from a raw Exportify CSV (English or Spanish columns, no `search_string` column required):

   ```bash
   poetry run python dj_to_slskd_pipeline.py --csv csv/my_export.csv
   ```

Notes:

- The script stops each search after it finds results to clear the "in progress" status and make responses available.
- Use `--no-stop` to keep searches running.
- Use `--dry-run` to preview what would be queued without downloading.
- 500 errors from slskd on enqueue (e.g. peer disconnected) are caught and logged as skipped — the pipeline continues rather than crashing.

## Staging Downloads to Inbox

After downloads complete, move files from `~/Soulseek/downloads/complete` to the inbox, flattening subfolders and renaming to `Artist - Title.ext` using embedded tags:

```bash
make stage-downloads
```

Common options (via make variables):

| Variable | Default | Description |
| --- | --- | --- |
| `DLS_DIR` | `~/Soulseek/downloads/complete` | Source downloads directory |
| `SINCE` | _(all files)_ | Only files modified at or after `HH:MM` or `YYYY-MM-DD HH:MM` (local time) |
| `DLS_FOLDER` | _(all subfolders)_ | Restrict to a specific subfolder inside `DLS_DIR` |
| `MOVE` | `0` | Set to `1` to move instead of copy |
| `DEDUPE` | `0` | Set to `1` to remove lower-quality duplicates after staging |
| `DRY_RUN` | `0` | Set to `1` to preview actions without writing anything |

Examples:

```bash
# Stage everything downloaded since 08:45 this morning, move files
make stage-downloads SINCE=08:45 MOVE=1

# Stage a specific artist folder, deduplicate, move
make stage-downloads DLS_FOLDER="Idjut Boys" SINCE=08:45 MOVE=1 DEDUPE=1

# Dry-run preview
make stage-downloads SINCE=08:45 DRY_RUN=1
```

Deduplication priority: **FLAC > WAV/AIF > M4A > MP3**, then largest file size as tiebreaker.

Use `--no-rename` to keep original filenames instead of renaming.

## Optional: Spotify CSV Tag Enrichment

After downloads complete, you can re-apply Spotify metadata from DB:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --db-path intellidj.db --scope new --label my_set --input-dir ~/Soulseek/downloads/complete --custom-tags
```

Legacy CSV mode (deprecated):

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete --custom-tags
```

PowerShell:

```powershell
poetry run python .\scripts\enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir "$HOME/Soulseek/downloads/complete" --custom-tags
```

To diagnose skipped matches:

```bash
poetry run python scripts/enrich_tags_from_spotify_csv.py --db-path intellidj.db --scope new --label my_set --input-dir ~/Soulseek/downloads/complete --report tag_report.csv
```

PowerShell:

```powershell
poetry run python .\scripts\enrich_tags_from_spotify_csv.py --db-path intellidj.db --scope new --label my_set --input-dir "$HOME/Soulseek/downloads/complete" --report tag_report.csv
```

## Optional: Traktor/Rekordbox Playlists (M3U)

Generate style-based playlists after imports:

```bash
make playlists
```

## Ports

- `5030` (HTTP)
- `5031` (HTTPS, self-signed)
- `50300` (Soulseek inbound)

## Recommended Configuration (Example)

Below is a safe baseline configuration inspired by typical slskd setups. Replace the placeholders with your own values and keep secrets in `.env`.

```yaml
web:
  # web settings omitted for brevity

authentication:
  disabled: false
  username: ${SLSKD_USERNAME}
  password: ${SLSKD_PASSWORD}

api_keys:
  primary:
    key: ${SLSKD_API_KEY}
    role: readwrite
    cidr: 0.0.0.0/0,::/0

directories:
  downloads: /app/downloads
  incomplete: /app/incomplete

soulseek:
  address: vps.slsknet.org
  port: 2271
  username: ${SLSKD_SLSK_USERNAME}
  password: ${SLSKD_SLSK_PASSWORD}

# Optional: restrict or tune usage
global:
  upload:
    slots: 20
  download:
    slots: 500
```

Notes:

- Keep `authentication.disabled: false` and change the default web UI credentials.
- Use `readwrite` API keys for automation; avoid exposing the UI publicly.
- If you don't need remote config changes, set `SLSKD_REMOTE_CONFIGURATION=false`.
- On Windows, set `SLSKD_DOWNLOADS_DIR` in `.env` to a bind-mountable path like `C:/Users/<you>/Soulseek/downloads`.

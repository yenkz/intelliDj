# IntelliDj

DJing tools to select, download, organize, and enrich music for DJ workflows.

## Quickstart (macOS, end-to-end)

### Pre-requisites (for non-tech-geek users)

The following software needs to be installed before following the steps below:

- [Git](https://git-scm.com/install/mac)
- [Homebrew](https://brew.sh/)
- MacOS's developer tools ([xcode](https://apps.apple.com/us/app/xcode/id497799835?mt=12))

### Steps to follow

1. Clone the repo:
   ```bash
   git clone https://github.com/yenkz/intelliDj.git
   cd intelliDj
   ```
2. Install prerequisites (Docker Desktop + Poetry), then start Docker Desktop:
   ```bash
   make prereqs
   ```
   If anything is missing, install it and re-run `make prereqs`. See [Setup and prerequisites](docs/setup.md).
3. Install Python dependencies:
   ```bash
   make install-python
   ```
   (Uses Poetry under the hood.) Or use pip-only:
   ```bash
   make install-python-pip
   ```
   Optional: initialize the lifecycle DB explicitly (it auto-creates on first run):
   ```bash
   make init-db
   ```
4. Configure slskd and your API key (see [slskd setup](docs/slskd.md)):
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set `SLSKD_API_KEY` (see docs for slskd setup).
5. Start slskd (see [slskd setup](docs/slskd.md)):
   ```bash
   docker compose up -d
   ```

6. Choose how to run IntelliDj:

   **Option A: Streamlit UI (recommended for most users)**
   ```bash
   make ui
   ```
   Then open the local URL shown in terminal (usually `http://localhost:8501`) and run the workflow step-by-step from the UI.

   **Option B: CLI (script-by-script)**
   Continue with steps 7-12 below.

7. Export a Spotify playlist CSV (see [Spotify export](docs/spotify-export.md)).
8. (Optional) Scan an existing local folder into DB first:
   ```bash
   make scan-local SCAN_DIR=~/Music IMPORT_LABEL=my_set DB_PATH=intellidj.db
   ```
9. Import Exportify CSV into DB (source of truth):
   ```bash
   make import-csv-db EXPORTIFY_CSV=spotify_export.csv IMPORT_LABEL=my_set DB_PATH=intellidj.db
   ```
   Or direct CLI:
   ```bash
   poetry run python csv_to_dj_pipeline.py --input csv/Liked_Songs.csv --db-path intellidj.db --label my_set
   ```
   Optional DB export CSV:
   ```bash
   make export-db-csv CSV=exports/tracks.csv DB_PATH=intellidj.db PROCESS_SCOPE=all
   ```
10. Download tracks via slskd from DB (see [slskd setup](docs/slskd.md)):
   ```bash
   make slskd-download-db DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set
   ```
   Direct CLI:
   ```bash
   poetry run python dj_to_slskd_pipeline.py --db-path intellidj.db --scope new --label my_set
   ```
11. (Optional) Re-apply Spotify metadata before beets (see [Recommendations](docs/recommendations.md)):
   ```bash
   poetry run python scripts/enrich_tags_from_spotify_csv.py --db-path intellidj.db --scope new --label my_set --input-dir ~/Soulseek/downloads/complete --custom-tags
   ```
12. Import into your library with beets (create `~/.config/beets/config.yaml` first; see [Beets cleanup workflow](docs/beets.md)):
   ```bash
   make beets-import DB_PATH=intellidj.db DLS_DIR=~/Soulseek/downloads/complete PROCESS_SCOPE=new IMPORT_LABEL=my_set
   ```
13. Fetch and embed cover art thumbnails:
   ```bash
   make cover-art DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set
   ```
14. (Optional) Normalize loudness in-place (see [Recommendations](docs/recommendations.md)):
   ```bash
   scripts/normalize_loudness.sh --input-dir ~/Music/DJ/library
   ```

### End-to-end orchestration (DB-first)

Run a full pipeline with reporting (dry-run friendly):

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

## Optional Tools

### Duplicate Track Finder

Find duplicates within one folder or across two folders, then:

- report only
- move duplicates to a review folder
- delete duplicates (with safety checks)

Launch UI:

```bash
make duplicates-ui
```

Or run CLI:

```bash
poetry run python scripts/find_duplicate_tracks.py --source-dir ~/Music/DJ/library
```

Full guide: [Duplicate track detection](docs/duplicates.md)

## Quickstart (Windows 11 + PowerShell, end-to-end)

Use the dedicated guide: [Windows 11 PowerShell quickstart](docs/windows.md).

## Docs

- [Setup and prerequisites](docs/setup.md)
- [Windows 11 PowerShell quickstart](docs/windows.md)
- [Spotify export](docs/spotify-export.md)
- [slskd (Docker + API downloads)](docs/slskd.md)
- [Duplicate track detection](docs/duplicates.md)
- [Lifecycle database (SQLite)](docs/database.md)
- [Architecture diagram](docs/architecture.md)
- [DB-first pipeline](docs/pipeline.md)
- [Beets cleanup workflow](docs/beets.md)
- [Output format](docs/output-format.md)
- [Workflow diagram](diagram.md)
- [Recommendations](docs/recommendations.md)
- [Traktor automation](docs/traktor.md)
- [Rekordbox automation](docs/rekordbox.md)
- [Streamlit UI](docs/ui.md)

## Contributing

Contributions welcome! Please open issues for bugs or feature requests.

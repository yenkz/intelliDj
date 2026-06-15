# Setup and Prerequisites

## Requirements

- Python 3.10+
- Docker Desktop or Docker Engine + Compose (for slskd)

For a copy/paste native Windows flow, use the dedicated guide: [Windows 11 PowerShell quickstart](windows.md).

## Dependency Installation

Poetry (recommended):

```bash
make install-python
```

Windows PowerShell (recommended on Windows):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_python_deps.ps1
```

Pip-only (fallback):

```bash
make install-python-pip
```

Windows PowerShell pip-only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_python_deps_pip.ps1
```

If you want to run Poetry directly:

```bash
poetry install
```

Run scripts with Poetry:

```bash
poetry run python <script>.py
```

Run the Streamlit UI:

```bash
poetry run streamlit run ui/streamlit_app.py
```

## End-to-End Dry Run

Use the helper script to dry-run the pipeline without downloading or writing tags:

```bash
scripts/dry_run_pipeline.sh --csv spotify_export.csv --db-path intellidj.db --label my_set --scope new
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dry_run_pipeline.ps1 -Csv spotify_export.csv
```

## Poetry Basics (Beginner-Friendly)

Poetry creates a project-specific virtual environment so your dependencies don’t conflict with other Python projects.

Common commands:

- `poetry install` — create the virtual environment and install dependencies.
- `poetry run <command>` — run a command inside the Poetry environment.
- `poetry run python <script>.py` — run a script from this repo.
- `poetry shell` — open a shell that’s already inside the Poetry environment.
- `poetry env info` — show where the virtual environment lives.

Example:

```bash
poetry install
poetry run python csv_to_dj_pipeline.py
```

## Makefile Helpers

```bash
make prereqs
make install-docker
make install-python
make install-python-pip
make install-beets-deps
make init-db
make scan-local SCAN_DIR=~/Music DB_PATH=intellidj.db IMPORT_LABEL=my_set
make import-csv-db EXPORTIFY_CSV=spotify_export.csv DB_PATH=intellidj.db IMPORT_LABEL=my_set
make slskd-download-db DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set
make beets-import DB_PATH=intellidj.db DLS_DIR=~/Soulseek/downloads/complete PROCESS_SCOPE=new IMPORT_LABEL=my_set
make cover-art DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set
make pipeline-run DB_PATH=intellidj.db EXPORTIFY_CSV=spotify_export.csv IMPORT_LABEL=my_set RUN_BEETS=1 RUN_COVER_ART=1
make backfill-db DB_PATH=intellidj.db IMPORT_LABEL=legacy-backfill
```

## Make Basics (Beginner-Friendly)

The Makefile provides short aliases for longer commands.

Examples:

- `make prereqs` — check your environment and tell you what’s missing.
- `make install-python` — install Python deps using Poetry.
- `make install-python-pip` — install Python deps using pip.
- `make slskd-download CSV=Happy_Funky_House_aka_HFH.csv` — run the download step with a specific CSV.
- `make scan-local SCAN_DIR=~/Music DB_PATH=intellidj.db` — ingest an existing local folder before CSV import.
- `make import-csv-db EXPORTIFY_CSV=spotify_export.csv DB_PATH=intellidj.db IMPORT_LABEL=my_set` — ingest Exportify CSV into DB.
- `make slskd-download-db DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set` — queue downloads from DB selectors.
- `make export-db-csv CSV=exports/tracks.csv DB_PATH=intellidj.db` — optional CSV export from DB.
- `make cover-art DB_PATH=intellidj.db PROCESS_SCOPE=new IMPORT_LABEL=my_set` — fetch and embed artwork thumbnails.
- `make pipeline-run ...` — run the DB-first orchestrator script with report output (`RUN_BEETS=1 RUN_COVER_ART=1` to include those stages).
- `make backfill-db DB_PATH=intellidj.db` — migrate legacy `playlist_entries` into the new DB-first tables.
- `make playlists CSV=dj_candidates.csv` — generate playlists for a specific CSV.
- `make duplicates DUP_SOURCE=~/Music/DJ/library` — detect duplicates in a library (report-only by default).
- `make ui` — launch the Streamlit UI.
- `make duplicates-ui` — launch the duplicate finder UI.
- `make init-db` — initialize the local lifecycle SQLite database.

If `make` isn’t installed:

- macOS: install Command Line Tools with `xcode-select --install` (or `brew install make`).
- Linux: install `make` via your package manager.
- Windows: use the PowerShell scripts in `scripts/*.ps1` instead of `make`.

## Lifecycle DB Path

The default DB path is `./intellidj.db`.

- Override globally with `INTELLIDJ_DB_PATH`.
- Override per-run with `--db-path` on supported scripts.

See [Lifecycle database](database.md) for schema and query examples.

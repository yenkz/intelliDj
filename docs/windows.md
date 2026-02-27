# Windows 11 Quickstart (PowerShell)

This guide is for native Windows 11 usage (no WSL required).

## 1) Install prerequisites

Install these first:

- Git for Windows
- Python 3.10+ (from python.org, with Python launcher `py`)
- Docker Desktop for Windows (running)

Optional for audio normalization:

- ffmpeg (and add it to PATH)

## 2) Clone and open the project

Run in PowerShell:

```powershell
git clone https://github.com/yenkz/intelliDj.git
cd intelliDj
```

## 3) Install Python dependencies

Recommended:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_python_deps.ps1
```

Fallback (pip only):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_python_deps_pip.ps1
```

## 4) Configure environment

```powershell
Copy-Item .env.example .env
```

Open `.env` and set your values (`SLSKD_API_KEY`, credentials, etc.).

Set a Windows bind-mount path for downloads:

```powershell
Add-Content .env "SLSKD_DOWNLOADS_DIR=C:/Users/$env:USERNAME/Soulseek/downloads"
```

Create the downloads folder if needed:

```powershell
New-Item -ItemType Directory -Path "C:/Users/$env:USERNAME/Soulseek/downloads" -Force
```

## 5) Start slskd

```powershell
docker compose up -d
```

Open [http://localhost:5030](http://localhost:5030).

## 6) Choose how to run IntelliDj

### Option A: UI (recommended)

```powershell
poetry run streamlit run ui/streamlit_app.py
```

Then open the local URL shown in terminal (usually `http://localhost:8501`) and run the workflow from the UI.

### Option B: CLI (script-by-script)

Generate candidate tracks:

```powershell
poetry run python csv_to_dj_pipeline.py
```

By default this writes `spotify_export_dj_candidates.csv` (or `<input_stem>_dj_candidates.csv` if you pass `--input`).

Queue downloads in slskd:

```powershell
poetry run python dj_to_slskd_pipeline.py --csv spotify_export_dj_candidates.csv
```

Optional metadata enrichment:

```powershell
poetry run python .\scripts\enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir "$HOME/Soulseek/downloads/complete" --custom-tags
```

Optional beets import:

```powershell
poetry run beet -c "$HOME/.config/beets/config.yaml" import -s "$HOME/Soulseek/downloads/complete"
```

Optional loudness normalization:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\normalize_loudness.ps1 -InputDir "$HOME/Music/DJ/library"
```

## 7) Dry run (safe preview)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dry_run_pipeline.ps1 -Csv spotify_export.csv
```

## Troubleshooting

- `poetry` not found:
  - Run `py -m pip install poetry`
  - Restart PowerShell

- Script execution policy errors:
  - Use `-ExecutionPolicy Bypass` as shown in commands above.

- Docker bind mount fails:
  - Ensure `.env` includes `SLSKD_DOWNLOADS_DIR` with forward slashes, for example:
    - `C:/Users/<you>/Soulseek/downloads`
  - Ensure the folder exists.

- `docker compose` command missing:
  - Open Docker Desktop and wait until it is fully started.

- `ffmpeg` not found:
  - Install ffmpeg and make sure `ffmpeg.exe` is on your PATH.

## Optional automation (Task Scheduler)

Run imports every 5 minutes:

- Program/script: `powershell.exe`
- Arguments: `-ExecutionPolicy Bypass -File C:\path\to\intelliDj\scripts\beets_import.ps1`

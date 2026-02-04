# IntelliDj

DJing core tools to select, download, organize and enrich the music we love.

## Overview

IntelliDj processes your Spotify playlists (exported manually) to generate curated track lists optimized for DJ sets. It cleans metadata and classifies tracks by musical style for seamless mixing.

## Features

- **Manual Spotify Export**: Uses CSVs exported from your playlists
- **Audio Analysis**: Uses BPM, energy, and danceability already present in the export
- **Metadata Cleaning**: Removes "extended", "radio", and bracketed variants from track names for cleaner searches
- **Style Classification**: Automatically categorizes tracks into DJ-friendly styles (Warm/Deep, Deep/Minimal, Tech/Peak, Groovy House)
- **CSV Output**: Generates a sorted CSV file ready for import into DJ software

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yenkz/intelliDj.git
   cd intelliDj
   ```

2. **Install dependencies**:
   ```bash
   pip install pandas
   ```


## Spotify Export Setup

To access your Spotify data without the API, export your playlists as CSV using Exportify:

1. Go to https://exportify.net/
2. Export your playlist(s) as CSV
3. Save the export as `spotify_export.csv` in the project root (or update `INPUT_FILE` in `csv_to_dj_pipeline.py`)

## Usage

Run the pipeline script:
```bash
python csv_to_dj_pipeline.py
```

This will:
- Read your exported playlist CSV
- Clean track names and infer styles
- Output `dj_candidates.csv` with tracks sorted by style then BPM

## First Run Checklist

1. Export your Spotify playlist(s) to `spotify_export.csv` via Exportify.
2. Copy `.env.example` to `.env` and set your `slskd` + Soulseek credentials.
3. Start slskd with `docker-compose up -d`.

## Automate slskd Downloads (API)

To queue downloads directly from `dj_candidates.csv`, use the `dj_to_slskd_pipeline.py` script.

1. Install the slskd API client:
   ```bash
   pip install slskd-api typing_extensions
   ```
2. Ensure `.env` includes `SLSKD_API_KEY` and `SLSKD_HOST`. Leave `SLSKD_URL_BASE` empty unless you have a custom reverse proxy path.
   - The API key must have `readwrite` role to enqueue downloads.
3. Run:
   ```bash
   set -a && source .env && set +a
   python dj_to_slskd_pipeline.py --csv dj_candidates.csv
   ```
   - The script stops each search after it finds results to clear the “in progress” status and make responses available. Use `--no-stop` to keep searches running.
   - Use `--dry-run` to preview what would be queued without downloading.

Make sure the API key is also configured in slskd (with `readwrite` role), either:
- In `slskd_data/slskd.yml` under `api_keys`, then restart the container, or
- From the slskd web UI (API keys section).

## Running slskd (Docker)

This repo includes a `docker-compose.yml` to run `slskd` locally.

1. Install Docker Desktop (which includes Docker Compose):
   - macOS/Windows: download and install Docker Desktop from the official Docker site.
   - Linux: install Docker Engine and the `docker-compose` plugin from your distro packages.
2. Ensure Docker is running.
3. Start the container:
   ```bash
   docker-compose up -d
   ```
4. Open the web UI at `http://localhost:5030`.
5. Copy `.env.example` to `.env` and fill in your credentials (web UI + Soulseek).
6. Configuration lives in `slskd_data/slskd.yml` (mounted into the container). Sensitive values are read from env vars.

Required env vars (see `.env.example`):
- `SLSKD_USERNAME` / `SLSKD_PASSWORD` (web UI)
- `SLSKD_SLSK_USERNAME` / `SLSKD_SLSK_PASSWORD` (Soulseek)
- `SLSKD_API_KEY` (optional, API access)

Additional notes from the official slskd Docker-Compose guide:
- slskd uses ports `5030` (HTTP) and `5031` (HTTPS with a self-signed certificate), and listens on `50300` for incoming Soulseek connections. If you need inbound connectivity, map `50300:50300` in `docker-compose.yml`.
- You can access the web UI over HTTP (`5030`) or HTTPS (`5031`).
- Default web UI credentials are `slskd` / `slskd`. Change these if the instance is internet facing.
- `SLSKD_REMOTE_CONFIGURATION=true` allows changing config from the web UI; consider disabling it if exposed publicly.
- The upstream compose example uses `restart: always`. Add it if you want the container to come back after reboots.

Reference: [slskd Docker-Compose guide](https://github.com/slskd/slskd?tab=readme-ov-file#with-docker-compose).

To stop the container:
```bash
docker-compose down
```

## Output Format

The generated CSV (`dj_candidates.csv`) contains these columns:
- `artist`: Track artist
- `track`: Cleaned track title
- `playlist_source`: Original playlist name
- `bpm_est`: Estimated BPM (rounded to nearest integer)
- `energy`: Energy level (0.0-1.0, 2 decimal places)
- `danceability`: Danceability score (0.0-1.0, 2 decimal places)
- `style`: Inferred musical style
- `search_string`: Combined "Artist - Track" for easy searching

Tracks are deduplicated and sorted for optimal DJ workflow.

## Requirements

- Python 3.6+
- Docker (desktop and compose) but it's explained above

## Contributing

Contributions welcome! Please open issues for bugs or feature requests.

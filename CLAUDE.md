# IntelliDj — Claude Instructions

## Project Overview

IntelliDj is a DJ music workflow automation toolkit. It processes Spotify playlists (via OAuth API or Exportify CSV export), searches and downloads tracks via Soulseek (slskd), enriches metadata, imports into a beets music library, and exports curated playlists for Traktor and Rekordbox.

**Core pipeline:**
Spotify playlist (OAuth or CSV) → metadata cleaning & style inference → Soulseek search/download → metadata enrichment → beets import → M3U playlist export

## Tech Stack

- **Language:** Python 3.10+
- **UI:** Streamlit (`ui/`)
- **Package manager:** uv (`pyproject.toml`)
- **Music library:** beets
- **Download backend:** slskd (Soulseek) via Docker
- **Key libraries:** pandas, mutagen, slskd-api, python-dotenv, requests, spotipy
- **Testing:** pytest, pytest-cov

## Common Commands

```bash
# Install dependencies
make install-python

# Run tests
make test
make test-cov          # with coverage report

# Launch the main Streamlit UI
make ui

# Launch the duplicate finder UI
make duplicates-ui

# Export M3U playlists by style
make playlists

# Trigger Soulseek downloads
make slskd-download
```

## Architecture

### Key Files

| File | Purpose |
|---|---|
| `intellidj_db.py` | SQLite state machine — all pipeline state, tracks, downloads, events |
| `intellidj_common.py` | Shared config loading, logging, env helpers |
| `intellidj/spotify.py` | Pure functions: `clean_track_name`, `normalize_artist`, `infer_style`, `build_candidates_dataframe` |
| `intellidj/slskd.py` | Pure functions: HTTP retry, file scoring, search response parsing |
| `intellidj/tagger.py` | Pure functions: tag read/write, fuzzy matching, ISRC/duration helpers |
| `csv_to_dj_pipeline.py` | Pipeline 1: Clean Spotify CSV, infer styles, write to DB |
| `dj_to_slskd_pipeline.py` | Pipeline 2: Search & download tracks via slskd API, updates `downloads` state machine |
| `scripts/spotify_import.py` | Import a Spotify playlist directly via OAuth (no Exportify CSV needed) |
| `scripts/enrich_tags_from_spotify_csv.py` | Enrich audio file tags from Spotify metadata |
| `scripts/export_m3u_by_style.py` | Generate M3U playlist files grouped by style |
| `scripts/find_duplicate_tracks.py` | Detect duplicate tracks in the music library |
| `ui/streamlit_app.py` | Main workflow web UI |
| `ui/streamlit_duplicates_app.py` | Duplicate finder web UI |
| `tests/` | pytest test suite |

### Data Flow

```
Spotify playlist
  → (OAuth) scripts/spotify_import.py
  → (CSV)   csv_to_dj_pipeline.py
  →  intellidj_db.py (tracks, ingestion_batches, track_stage_state)
  →  dj_to_slskd_pipeline.py  →  downloads table (PENDING→SEARCHING→FOUND→COMPLETED/FAILED)
  →  downloaded audio files
  →  enrich_tags_from_spotify_csv.py  →  tagged files
  →  beets import  →  organized music library
  →  export_m3u_by_style.py  →  M3U playlists (Traktor/Rekordbox)
```

### Downloads State Machine

The `downloads` table tracks each download with these statuses:

`pending` → `searching` → `found` → `downloading` → `completed`
                       ↘ `not_found`
                       ↘ `failed` (retry if `retry_count < max_retries`)

Key `IntelliDJDB` methods: `create_download()`, `update_download()`, `get_downloads_for_retry()`, `get_failed_downloads()`.

## Critical Patterns

### Track Name Cleaning

Always use `clean_track_name()` (in `intellidj/spotify.py`) before search or processing:

```python
junk_patterns = [
    r"\(.*extended.*\)",
    r"\(.*original.*\)",
    r"\(.*radio.*\)",
    r"\(.*remaster.*\)",
    r"\[.*\]",
    r"- extended.*",
    r"- original.*",
]
```

### Style Inference

Use `infer_style(genres, bpm, energy)` (in `intellidj/spotify.py`) for consistent style classification:

- `"garage"` or `"break"` in genres → `"Garage / Breaky"`
- `"minimal"` or `"micro"` in genres → `"Minimal / Micro"`
- `"tech house"` in genres → `"Tech House"`
- `"deep"` in genres or `energy < 0.6` → `"Deep House"`
- `bpm >= 126` and `energy >= 0.65` → `"Peak House"`
- Default → `"House / Groovy"`

### Candidates DataFrame Format

Output columns from `build_candidates_dataframe()`: `artist`, `track`, `bpm`, `energy`, `danceability`, `style`, `label`, `genres`, `search_string`

- Sort by `style`, then `bpm`
- Deduplicate on `search_string`
- Round: `bpm` → int, `energy`/`danceability` → 2 decimal places

## Environment Setup

Copy `.env.example` to `.env` and configure:

```bash
# Soulseek / slskd
SLSKD_USERNAME=slskd
SLSKD_PASSWORD=change_me
SLSKD_SLSK_USERNAME=your_soulseek_username
SLSKD_SLSK_PASSWORD=your_soulseek_password
SLSKD_API_KEY=change_me_long_random
SLSKD_HOST=http://localhost:5030

# Spotify OAuth (for scripts/spotify_import.py)
# Register an app at https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Start slskd via Docker:

```bash
docker compose up -d
```

## Coding Conventions

- Use pandas DataFrames for all track data manipulation
- Lowercase for internal processing, title case for display output
- Genre/style focus: house and techno, energy-based style mapping
- Pure utility functions live in `intellidj/` submodules; scripts are thin wrappers
- All file I/O uses UTF-8 encoding explicitly
- Use `python-dotenv` for all environment variable loading
- DB is the source of truth — use `IntelliDJDB` for all state, not CSV files

## Testing

Tests live in `tests/` and mirror the main module structure. Run with:

```bash
make test
```

Pytest markers available: `slow`, `integration`, `unit`, `e2e` (configured in `pytest.ini`).

When adding new functionality, add corresponding tests in the appropriate `tests/test_*.py` file.

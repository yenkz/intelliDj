# IntelliDj — Claude Instructions

## Project Overview

IntelliDj is a DJ music workflow automation toolkit. It processes Spotify playlist exports, searches and downloads tracks via Soulseek (slskd), enriches metadata, imports into a beets music library, and exports curated playlists for Traktor and Rekordbox.

**Core pipeline:**
Spotify CSV export → metadata cleaning & style inference → Soulseek search/download → metadata enrichment → beets import → M3U playlist export

## Tech Stack

- **Language:** Python 3.10+
- **UI:** Streamlit (`ui/`)
- **Package manager:** Poetry (`pyproject.toml`)
- **Music library:** beets
- **Download backend:** slskd (Soulseek) via Docker
- **Key libraries:** pandas, mutagen, slskd-api, python-dotenv, requests
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
| `csv_to_dj_pipeline.py` | Pipeline 1: Clean Spotify CSV, infer styles, produce `dj_candidates.csv` |
| `dj_to_slskd_pipeline.py` | Pipeline 2: Search & download tracks via slskd API |
| `scripts/enrich_tags_from_spotify_csv.py` | Enrich audio file tags from Spotify metadata |
| `scripts/export_m3u_by_style.py` | Generate M3U playlist files grouped by style |
| `scripts/find_duplicate_tracks.py` | Detect duplicate tracks in the music library |
| `ui/streamlit_app.py` | Main workflow web UI |
| `ui/streamlit_duplicates_app.py` | Duplicate finder web UI |
| `tests/` | pytest test suite |

### Data Flow

```
Spotify export (CSV)
  → csv_to_dj_pipeline.py  →  dj_candidates.csv
  → dj_to_slskd_pipeline.py  →  downloaded audio files
  → enrich_tags_from_spotify_csv.py  →  tagged files
  → beets import  →  organized music library
  → export_m3u_by_style.py  →  M3U playlists (Traktor/Rekordbox)
```

## Critical Patterns

### Track Name Cleaning

Always use `clean_track_name()` before search or processing:

```python
junk_patterns = [
    r"\(.*extended.*\)",
    r"\(.*original.*\)",
    r"\(.*radio.*\)",
    r"\[.*\]",
    r"- extended.*",
    r"- original.*",
]
```

### Style Inference

Use `infer_style(energy, tempo)` for consistent style classification:

- `< 122 BPM` → `"Warm / Deep"`
- `122–125 BPM + energy < 0.6` → `"Deep / Minimal"`
- `≥ 125 BPM + energy ≥ 0.6` → `"Tech / Peak"`
- Default → `"Groovy House"`

### CSV Output Format

Columns: `artist`, `track`, `playlist_source`, `bpm_est`, `energy`, `danceability`, `style`, `search_string`

- Sort by `style`, then `bpm_est`
- Deduplicate on `search_string`
- Round: `bpm_est` → int, `energy`/`danceability` → 2 decimal places

## Environment Setup

Copy `.env.example` to `.env` and configure:

```bash
SLSKD_USERNAME=slskd
SLSKD_PASSWORD=change_me
SLSKD_SLSK_USERNAME=your_soulseek_username
SLSKD_SLSK_PASSWORD=your_soulseek_password
SLSKD_API_KEY=change_me_long_random
SLSKD_HOST=http://localhost:5030
```

Start slskd via Docker:

```bash
docker compose up -d
```

## Coding Conventions

- Use pandas DataFrames for all track data manipulation
- Lowercase for internal processing, title case for display output
- Genre/style focus: house and techno, energy-based style mapping
- Keep pipelines as standalone scripts — avoid deep abstraction layers
- All file I/O uses UTF-8 encoding explicitly
- Use `python-dotenv` for all environment variable loading

## Testing

Tests live in `tests/` and mirror the main module structure. Run with:

```bash
make test
```

Pytest markers available: `slow`, `integration`, `unit`, `e2e` (configured in `pytest.ini`).

When adding new functionality, add corresponding tests in the appropriate `tests/test_*.py` file.

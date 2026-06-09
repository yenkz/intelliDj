# IntelliDj

CLI toolkit to select, download, organize, and enrich music for DJ workflows.

**Core pipeline:**
Spotify CSV export → style inference → Soulseek search/download (slskd) → tag enrichment → beets library import → M3U playlist export

## Quickstart

### Prerequisites

- [Git](https://git-scm.com/install/mac)
- [Docker](https://docs.docker.com/get-docker/) (for slskd)
- [Poetry](https://python-poetry.org/docs/#installation)
- Python 3.10+

macOS users: also install [Homebrew](https://brew.sh/) and Xcode command-line tools.

### Install

```bash
git clone https://github.com/yenkz/intelliDj.git
cd intelliDj
make install-python
```

### Configure slskd

```bash
cp .env.example .env
# Edit .env — set SLSKD_API_KEY, SLSKD_SLSK_USERNAME, SLSKD_SLSK_PASSWORD
docker compose up -d
```

See [slskd setup](docs/slskd.md) for full details.

---

## Usage

All commands are available via the `intellidj` binary (installed by Poetry):

```
intellidj --help
```

Global options available on every command:

| Option | Description |
|---|---|
| `--env FILE` | Path to `.env` file (default: `.env` in CWD) |
| `--host URL` | Override `SLSKD_HOST` |
| `--api-key TEXT` | Override `SLSKD_API_KEY` |
| `--quiet` | Suppress per-item output, show summary only |
| `--json` | Emit newline-delimited JSON (for scripting) |
| `--log-file FILE` | Append all output to a log file |

---

### 1. Generate candidates from a Spotify export

Export a playlist from Spotify ([how-to](docs/spotify-export.md)), then:

```bash
intellidj candidates spotify_export.csv
# → writes spotify_export_dj_candidates.csv
```

```bash
intellidj candidates spotify_export.csv --output my_candidates.csv --limit 50
```

With `--dry-run`, prints one `Artist - Track` search string per line to stdout — useful for piping:

```bash
intellidj candidates spotify_export.csv --dry-run | intellidj download --stdin
```

---

### 2. Download tracks via slskd

```bash
# From a candidates CSV
intellidj download --csv dj_candidates.csv

# Single track
intellidj download --artist "Bicep" --track "Glue"

# Plain text file (one "Artist - Track" per line)
intellidj download --list my_tracklist.txt

# Pipe from candidates
intellidj candidates spotify_export.csv --dry-run | intellidj download --stdin

# Dry-run: search but don't queue
intellidj download --csv dj_candidates.csv --dry-run
```

Key options: `--limit N`, `--search-timeout-ms`, `--response-limit`, `--debug`

---

### 3. Enrich audio tags from Spotify metadata

After downloads complete, write ID3/FLAC tags from the Spotify CSV:

```bash
intellidj enrich --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete
```

```bash
# Write extra Spotify fields (energy, danceability, key…)
intellidj enrich --csv spotify_export.csv --custom-tags

# Preview matches without writing tags
intellidj enrich --csv spotify_export.csv --dry-run --report /tmp/match_report.csv
```

---

### 4. Import into beets

Create `~/.config/beets/config.yaml` first ([beets guide](docs/beets.md)), then:

```bash
make beets-import
# or directly:
beet -c ~/.config/beets/config.yaml import -s ~/Soulseek/downloads/complete
```

---

### 5. Export M3U playlists by style

```bash
intellidj playlist --csv dj_candidates.csv --library-dir ~/Music/DJ/library
# → writes playlists/Deep_House.m3u, playlists/Tech_House.m3u, etc.
```

---

### 6. Normalize loudness (optional)

```bash
scripts/normalize_loudness.sh --input-dir ~/Music/DJ/library
```

---

### Run the full pipeline in one command

```bash
intellidj run --csv spotify_export.csv
# or dry-run first:
intellidj run --csv spotify_export.csv --dry-run
```

Skip individual steps with `--skip-candidates`, `--skip-download`, `--skip-enrich`, `--skip-playlist`.

---

## Duplicate track finder

Detect duplicates by file hash, metadata, or both — then report, move, or delete:

```bash
# Report only (safe default)
intellidj dedupe ~/Music/DJ/library

# Cross-folder: find duplicates between library and downloads
intellidj dedupe ~/Music/DJ/library --compare-dir ~/Soulseek/downloads/complete --dry-run

# Move duplicates to a review folder, keep best quality copy
intellidj dedupe ~/Music/DJ/library --action move --review-dir ~/review --yes

# Export a CSV report
intellidj dedupe ~/Music/DJ/library --export-csv report.csv
```

Full guide: [Duplicate track detection](docs/duplicates.md)

---

## Makefile shortcuts

```bash
make candidates          # intellidj candidates $(CSV)
make download            # intellidj download --csv $(CANDIDATES_CSV)
make enrich              # intellidj enrich --csv $(CSV) --input-dir $(DOWNLOADS_DIR)
make playlist            # intellidj playlist ...
make dedupe              # intellidj dedupe $(DUP_SOURCE) ...
make run                 # intellidj run --csv $(CSV)
make beets-import        # run beets import via shell script
make test                # run pytest
make test-cov            # run pytest with coverage
```

Override variables inline: `make download CANDIDATES_CSV=my_candidates.csv LIMIT=20`

---

## Windows

Use the dedicated guide: [Windows 11 PowerShell quickstart](docs/windows.md).

---

## Docs

- [Setup and prerequisites](docs/setup.md)
- [Windows 11 PowerShell quickstart](docs/windows.md)
- [Spotify export](docs/spotify-export.md)
- [slskd (Docker + API downloads)](docs/slskd.md)
- [Duplicate track detection](docs/duplicates.md)
- [Beets cleanup workflow](docs/beets.md)
- [Output format](docs/output-format.md)
- [Recommendations](docs/recommendations.md)
- [Traktor automation](docs/traktor.md)
- [Rekordbox automation](docs/rekordbox.md)

## Contributing

Contributions welcome. Open issues for bugs or feature requests.

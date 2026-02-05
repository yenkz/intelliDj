# IntelliDj

DJing tools to select, download, organize, and enrich music for DJ workflows.

## Quickstart (macOS, end-to-end)

### Pre-requisites (for non-tech-geek users)

The following software needs to be installed before following the steps below:

- Git
- MacOS's developer tools (xcode)

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
4. Configure slskd and your API key (see [slskd setup](docs/slskd.md)):
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set `SLSKD_API_KEY` (see docs for slskd setup).
5. Start slskd (see [slskd setup](docs/slskd.md)):
   ```bash
   docker-compose up -d
   ```
6. Export a Spotify playlist CSV as `spotify_export.csv` (see [Spotify export](docs/spotify-export.md)).
7. Generate download candidates (see [Output format](docs/output-format.md)):
   ```bash
   poetry run python csv_to_dj_pipeline.py
   ```
8. Load your `.env` into the current shell:
   ```bash
   set -a && source .env && set +a
   ```
9. Download tracks via slskd (see [slskd setup](docs/slskd.md)):
   ```bash
   poetry run python dj_to_slskd_pipeline.py --csv dj_candidates.csv
   ```
10. (Optional) Re-apply Spotify metadata before beets (see [Recommendations](docs/recommendations.md)):
   ```bash
   poetry run python scripts/enrich_tags_from_spotify_csv.py --csv spotify_export.csv --input-dir ~/Soulseek/downloads/complete --custom-tags
   ```
11. Import into your library with beets (create `~/.config/beets/config.yaml` first; see [Beets cleanup workflow](docs/beets.md)):
   ```bash
   poetry run beet -c ~/.config/beets/config.yaml import -s ~/Soulseek/downloads/complete
   ```
12. (Optional) Normalize loudness in-place (see [Recommendations](docs/recommendations.md)):
   ```bash
   scripts/normalize_loudness.sh --input-dir ~/Music/DJ/library
   ```

## Docs

- [Setup and prerequisites](docs/setup.md)
- [Spotify export](docs/spotify-export.md)
- [slskd (Docker + API downloads)](docs/slskd.md)
- [Beets cleanup workflow](docs/beets.md)
- [Output format](docs/output-format.md)
- [Workflow diagram](diagram.md)
- [Recommendations](docs/recommendations.md)
- [Traktor automation](docs/traktor.md)
- [Rekordbox automation](docs/rekordbox.md)
- [Streamlit UI](docs/ui.md)

## Contributing

Contributions welcome! Please open issues for bugs or feature requests.

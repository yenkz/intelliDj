# IntelliDj

DJing tools to select, download, organize, and enrich music for DJ workflows.

## Quickstart

1. Clone the repo:
   ```bash
   git clone https://github.com/yenkz/intelliDj.git
   cd intelliDj
   ```
2. Install dependencies:
   ```bash
   make install-python
   ```
   (Uses Poetry under the hood.) Or use pip-only:
   ```bash
   make install-python-pip
   ```
3. Export a Spotify playlist CSV as `spotify_export.csv` (see docs).
4. Run the CSV pipeline:
   ```bash
   poetry run python csv_to_dj_pipeline.py
   ```

## Docs

- [Setup and prerequisites](docs/setup.md)
- [Spotify export](docs/spotify-export.md)
- [slskd (Docker + API downloads)](docs/slskd.md)
- [Beets cleanup workflow](docs/beets.md)
- [Output format](docs/output-format.md)
- [Workflow diagram](docs/diagram.md)
- [Recommendations](docs/recommendations.md)

## Contributing

Contributions welcome! Please open issues for bugs or feature requests.

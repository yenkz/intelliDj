# Setup and Prerequisites

## Requirements

- Python 3.10+
- Docker Desktop or Docker Engine + Compose (for slskd)

## Dependency Installation

Poetry (recommended):

```bash
make install-python
```

Pip-only (fallback):

```bash
make install-python-pip
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
scripts/dry_run_pipeline.sh --csv spotify_export.csv
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
```

## Make Basics (Beginner-Friendly)

The Makefile provides short aliases for longer commands.

Examples:

- `make prereqs` — check your environment and tell you what’s missing.
- `make install-python` — install Python deps using Poetry.
- `make install-python-pip` — install Python deps using pip.
- `make slskd-download CSV=Happy_Funky_House_aka_HFH.csv` — run the download step with a specific CSV.
- `make playlists CSV=dj_candidates.csv` — generate playlists for a specific CSV.
- `make ui` — launch the Streamlit UI.

If `make` isn’t installed:

- macOS: install Command Line Tools with `xcode-select --install` (or `brew install make`).
- Linux: install `make` via your package manager.

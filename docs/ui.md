# Streamlit UI (Local)

If you prefer a point-and-click interface, use the Streamlit UI to run the pipeline step-by-step.

## Install

Make sure dependencies are installed:

```bash
make install-python
```

## Run the UI

```bash
make ui
```

## What it does

The UI provides:

- A `Pipeline` tab with guided steps.
- A `Quick Status` section that validates required files/directories and API key presence.
- A `Logs` tab that centralizes command output, exit codes, and executed commands.
- Sidebar configuration for paths and step options.

Pipeline steps:

1. Load the Spotify CSV into the project.
2. Generate candidates CSV.
3. Download via slskd.
4. Enrich tags from the Spotify CSV.
5. Import into beets.
6. Normalize loudness.

## Candidates filename behavior

By default, the UI auto-generates the candidates filename from the Spotify CSV path:

- Input: `spotify_export.csv`
- Output: `spotify_export_dj_candidates.csv`

Disable **Auto candidates filename from Spotify CSV** in the sidebar if you want to set a custom output path manually.

## Notes

- Steps are enabled/disabled based on prerequisites (for example, missing files or missing `SLSKD_API_KEY`).
- Commands run from the repo root and can be executed independently.

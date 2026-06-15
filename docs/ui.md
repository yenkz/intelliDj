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
2. (Optional) Scan local music folder into DB.
3. Import Spotify CSV into DB (source of truth).
4. Download via slskd from DB.
5. Enrich tags from DB metadata.
6. Import into beets (wrapped to record DB stage state).
7. Fetch + embed cover art (beets fetchart/embedart).
8. Normalize loudness.

Step 4/5 are DB-first:

- uses `intellidj.db` with selectors:
  - `scope`: `new`, `existing`, `all`
  - optional `batch label`
  - optional `batch id`

Step 3 can optionally export a candidates CSV for external tooling, but DB remains the source of truth.

On macOS, Step 2 includes a **Select folder with Finder** button to pick the local scan directory without typing the path.

## Notes

- Steps are enabled/disabled based on prerequisites (for example, missing files or missing `SLSKD_API_KEY`).
- Commands run from the repo root and can be executed independently.

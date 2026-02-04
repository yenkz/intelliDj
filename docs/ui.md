# Streamlit UI (Local)

If you prefer a point-and-click interface, use the Streamlit UI to run the pipeline step-by-step.

## Install

Make sure dependencies are installed:

```bash
make install-python
```

## Run the UI

```bash
poetry run streamlit run ui/streamlit_app.py
```

## What it does

The UI guides you through:

1. Load the Spotify CSV into the project.
2. Generate `dj_candidates.csv`.
3. Download via slskd.
4. Enrich tags from the Spotify CSV.
5. Import into beets.
6. Normalize loudness.

You can configure paths in the sidebar and run each step independently.

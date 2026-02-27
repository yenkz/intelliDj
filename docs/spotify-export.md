# Spotify Export

Export your Spotify playlists as CSV using Exportify.

Steps:

1. Go to https://exportify.net/
2. Export your playlist(s) as CSV
3. Save the export as `spotify_export.csv` in the project root

If you want a different name or location, pass it with:

```bash
poetry run python csv_to_dj_pipeline.py --input path/to/your_export.csv
```

# Output Format

The generated candidates CSV contains these columns:

- `artist`: Track artist
- `track`: Cleaned track title
- `bpm`: Estimated BPM (rounded to nearest integer)
- `energy`: Energy level (0.0-1.0, 2 decimal places)
- `danceability`: Danceability score (0.0-1.0, 2 decimal places)
- `style`: Inferred musical style
- `label`: Record label from Spotify export
- `genres`: Genres from Spotify export
- `search_string`: Combined "Artist - Track" for easy searching

Tracks are deduplicated and sorted for optimal DJ workflow.

## Output filename behavior

If you do not pass `--output`, the default is derived from input:

- Input: `spotify_export.csv`
- Output: `spotify_export_dj_candidates.csv`

For custom input files:

```bash
poetry run python csv_to_dj_pipeline.py --input csv/Liked_Songs.csv
```

Output will be:

- `csv/Liked_Songs_dj_candidates.csv`

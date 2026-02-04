# Output Format

The generated CSV (`dj_candidates.csv`) contains these columns:

- `artist`: Track artist
- `track`: Cleaned track title
- `playlist_source`: Original playlist name
- `bpm_est`: Estimated BPM (rounded to nearest integer)
- `energy`: Energy level (0.0-1.0, 2 decimal places)
- `danceability`: Danceability score (0.0-1.0, 2 decimal places)
- `style`: Inferred musical style
- `search_string`: Combined "Artist - Track" for easy searching

Tracks are deduplicated and sorted for optimal DJ workflow.

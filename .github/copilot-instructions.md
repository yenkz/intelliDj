# IntelliDj Copilot Instructions

## Project Overview
IntelliDj is a DJing tool that processes Spotify playlists to generate curated track lists for DJ sets. The core pipeline (`spotify_to_dj_pipeline.py`) fetches user playlists, extracts audio features, cleans track metadata, infers musical styles, and outputs a sorted CSV of DJ candidates.

## Architecture
- **Single-script pipeline**: End-to-end processing from Spotify API to CSV output
- **Data flow**: Spotify playlists → audio features extraction → metadata cleaning → style classification → BPM-sorted CSV
- **Key dependencies**: Spotipy (Spotify API), Pandas (data manipulation)

## Critical Patterns

### Track Name Cleaning
Remove "extended", "original", "radio" variants and brackets for cleaner search strings:
```python
junk_patterns = [
    r"\(.*extended.*\)",
    r"\(.*original.*\)",
    r"\(.*radio.*\)",
    r"\[.*\]",
    r"- extended.*",
    r"- original.*",
]
```
Always apply `clean_track_name()` to track titles before processing.

### Style Inference
Classify tracks based on tempo and energy thresholds:
- `< 122 BPM`: "Warm / Deep"
- `122-125 BPM + energy < 0.6`: "Deep / Minimal"  
- `≥ 125 BPM + energy ≥ 0.6`: "Tech / Peak"
- Default: "Groovy House"

Use `infer_style(energy, tempo)` for consistent categorization.

### Output Format
CSV columns: `artist`, `track`, `playlist_source`, `bpm_est`, `energy`, `danceability`, `style`, `search_string`
- Sort by `style` then `bpm_est`
- Deduplicate on `search_string`

## Developer Workflow
- **Setup**: Configure Spotify app credentials for OAuth (scopes: `playlist-read-private playlist-read-collaborative`)
- **Run**: `python spotify_to_dj_pipeline.py` (outputs `dj_candidates.csv`)
- **No build/test process**: Direct script execution
- **Debugging**: Check Spotify API responses and audio features validity

## Conventions
- Use Pandas DataFrames for track data manipulation
- Round numeric features: tempo (int), energy/danceability (2 decimals)
- Lowercase initial cleaning, then title case for display
- Focus on house/techno genres with energy-based style mapping
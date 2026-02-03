# IntelliDj

DJing core tools to select, download, organize and enrich the music we love.

## Overview

IntelliDj processes your Spotify playlists to generate curated track lists optimized for DJ sets. It extracts audio features, cleans metadata, and classifies tracks by musical style for seamless mixing.

## Features

- **Spotify Integration**: Fetches tracks from your private and collaborative playlists
- **Audio Analysis**: Extracts BPM, energy, and danceability using Spotify's audio features API
- **Metadata Cleaning**: Removes "extended", "radio", and bracketed variants from track names for cleaner searches
- **Style Classification**: Automatically categorizes tracks into DJ-friendly styles (Warm/Deep, Deep/Minimal, Tech/Peak, Groovy House)
- **CSV Output**: Generates a sorted CSV file ready for import into DJ software

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yenkz/intelliDj.git
   cd intelliDj
   ```

2. **Install dependencies**:
   ```bash
   pip install spotipy pandas
   ```

3. **Set up Spotify API credentials** (see below).

## Spotify API Setup

To access your Spotify data, you need to create a Spotify app:

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Note your **Client ID** and **Client Secret**
4. Set the redirect URI to `http://localhost:8080` (or any local URL)
5. Set environment variables:
   ```bash
   export SPOTIPY_CLIENT_ID='your_client_id'
   export SPOTIPY_CLIENT_SECRET='your_client_secret'
   export SPOTIPY_REDIRECT_URI='http://localhost:8080'
   ```

The script will prompt for authorization on first run.

## Usage

Run the pipeline script:
```bash
python spotify_to_dj_pipeline.py
```

This will:
- Fetch your playlists (up to 50)
- Process each track's audio features
- Clean track names and infer styles
- Output `dj_candidates.csv` with tracks sorted by style then BPM

## Output Format

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

## Requirements

- Python 3.6+
- Spotify Premium account (for API access)
- Internet connection for API calls

## Contributing

Contributions welcome! Please open issues for bugs or feature requests.

## License

[Add license here]

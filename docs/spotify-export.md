# Spotify Playlist Ingestion

There are two ways to get a Spotify playlist into IntelliDJ. The **Exportify CSV** path is
recommended; the **OAuth direct import** path exists but is limited by Spotify API deprecations.

---

## Path A — Exportify CSV (recommended)

Export your playlist as a CSV using [exportify.app](https://exportify.app), then import it with
`csv_to_dj_pipeline.py`. This path provides full metadata including BPM, energy, danceability,
and genres because exportify.app was registered before Spotify's November 2024 deprecations.

### Steps

1. Go to [exportify.app](https://exportify.app) and log in with your Spotify account.
2. Export the playlist as CSV.
3. Save the file as `spotify_export.csv` in the project root (or pass a custom path with `--input`).
4. Run the pipeline:

```bash
poetry run python csv_to_dj_pipeline.py --input spotify_export.csv --db-path intellidj.db --label my_set
```

Or via Make:

```bash
make import-csv-db EXPORTIFY_CSV=spotify_export.csv IMPORT_LABEL=my_set DB_PATH=intellidj.db
```

---

## Path B — Spotify OAuth direct import (limited)

`scripts/spotify_import.py` authenticates directly via Spotify OAuth and fetches playlist tracks
without needing an Exportify export. However, two critical endpoints have been deprecated by
Spotify and are no longer available for apps registered after November 2024:

| Endpoint | Removed | Impact |
| --- | --- | --- |
| `GET /v1/audio-features` | November 2024 | BPM, energy, danceability are all 0 |
| `GET /v1/artists` (batch) | [February 2026](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security) | Genres are empty |

As a result, `infer_style()` always falls back to `"House / Groovy"` for every track, and
download candidates cannot be prioritised by energy or BPM.

A [SoundNet RapidAPI](https://rapidapi.com/soundnet-soundnet-default/api/track-analysis) fallback
is wired in for BPM/energy/danceability when `RAPIDAPI_KEY` is set in `.env`, but the free tier
has a very limited monthly quota (~50 requests).

### When to use this path

Use it only if you need to avoid the manual Exportify export step and are willing to accept:

- Zero BPM/energy/danceability (or upgrade the RapidAPI plan)
- Empty genres → all tracks inferred as `"House / Groovy"`

### Usage

```bash
# Set credentials in .env first:
# SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
# RAPIDAPI_KEY (optional — SoundNet fallback for audio features)

poetry run python scripts/spotify_import.py \
  --playlist https://open.spotify.com/playlist/<id> \
  --db-path intellidj.db \
  --label my_set
```

---

## Comparison

| | Exportify CSV | OAuth direct |
| --- | --- | --- |
| BPM / energy / danceability | Full (Spotify data) | Requires paid SoundNet API key, OR free post-download Essentia enrichment (`make enrich-bpm`) |
| Genres | Full | Empty (deprecated endpoint) |
| Style inference | Accurate | Falls back to "House / Groovy" |
| Manual step required | Yes (export CSV) | No |
| Spotify credentials needed | Login to exportify.app | App Client ID + Secret in `.env` |

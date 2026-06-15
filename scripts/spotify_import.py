#!/usr/bin/env python3
"""
scripts/spotify_import.py — Import a Spotify playlist directly via OAuth API.

Eliminates the manual Exportify CSV export step. Reads playlist tracks and
audio features, converts them to the same format as an Exportify CSV, then
calls csv_to_dj_pipeline.main() to ingest into the DB.

Prerequisites:
    pip install spotipy>=2.23.0
    Register an app at https://developer.spotify.com/dashboard
    Set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI in .env

Usage:
    python scripts/spotify_import.py --playlist https://open.spotify.com/playlist/...
    python scripts/spotify_import.py --playlist 37i9dQZF1DX... --dry-run
    python scripts/spotify_import.py --playlist <id> --output candidates.csv --check-library
"""
import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    raise SystemExit(
        "spotipy is not installed. Run: pip install 'spotipy>=2.23.0'"
    )

import pandas as pd

from intellidj_common import (
    add_common_config_arg,
    cfg_get,
    coalesce,
    load_env_file,
    load_project_config,
    resolve_db_path,
    setup_script_logging,
)
import csv_to_dj_pipeline


_SCOPES = "playlist-read-private playlist-read-collaborative user-library-read"


def authenticate(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> spotipy.Spotify:
    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def _extract_playlist_id(playlist_url_or_id: str) -> str:
    if "open.spotify.com/playlist/" in playlist_url_or_id:
        part = playlist_url_or_id.split("open.spotify.com/playlist/")[1]
        return part.split("?")[0].strip("/")
    return playlist_url_or_id.strip()


def get_playlist_tracks(
    sp: spotipy.Spotify,
    playlist_url_or_id: str,
    *,
    rapidapi_key: str | None = None,
) -> list[dict]:
    playlist_id = _extract_playlist_id(playlist_url_or_id)

    # Use sp.playlist() + sp.next() to avoid the deprecated /tracks endpoint
    # (blocked for apps created after Nov 2024; /items endpoint still works).
    tracks = []
    page = sp.playlist(playlist_id).get("items") or {}
    while page:
        for item in page.get("items") or []:
            track = item.get("item") or item.get("track")
            if not track or not track.get("id"):
                continue
            tracks.append(track)
        if not page.get("next"):
            break
        page = sp.next(page)

    if not tracks:
        return []

    # Fetch audio features in batches of 100
    # Note: Spotify removed this endpoint for apps created after Nov 2024.
    # On 403 we fall back to SoundNet if a RAPIDAPI_KEY is available.
    features_map: dict[str, dict] = {}
    spotify_features_failed = False
    track_ids = [t["id"] for t in tracks]
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i : i + 100]
        try:
            features = sp.audio_features(batch)
        except spotipy.SpotifyException as exc:
            if exc.http_status == 403:
                print("⚠️  Audio features unavailable (Spotify deprecated). Trying SoundNet fallback...")
                spotify_features_failed = True
                break
            raise
        for feat in features or []:
            if feat and feat.get("id"):
                features_map[feat["id"]] = feat

    if spotify_features_failed and rapidapi_key:
        from intellidj.audio_features import fetch_soundnet_features
        print(f"🎵 Fetching audio features via SoundNet for {len(track_ids)} tracks...")
        soundnet_ok = 0
        soundnet_quota_hit = False
        for idx, tid in enumerate(track_ids, 1):
            result = fetch_soundnet_features(tid, rapidapi_key)
            if result and any(result.values()):
                features_map[tid] = result
                soundnet_ok += 1
                if soundnet_ok == 1:
                    print(f"   Sample response: {result}")
            elif result is None and soundnet_ok == 0 and idx >= 3:
                # Three consecutive failures at the start → likely quota exhausted
                print("   ⚠️  SoundNet quota likely exhausted — stopping early. Upgrade your RapidAPI plan.")
                soundnet_quota_hit = True
                break
            if idx % 10 == 0 or idx == len(track_ids):
                print(f"   {idx}/{len(track_ids)} done")
        if not soundnet_quota_hit:
            if soundnet_ok == 0:
                print("   ⚠️  SoundNet returned no features — check RAPIDAPI_KEY and quota")
            else:
                print(f"   ✅ {soundnet_ok}/{len(track_ids)} tracks got audio features from SoundNet")
    elif spotify_features_failed:
        print("ℹ️  Set RAPIDAPI_KEY to enable SoundNet audio features fallback.")

    # Fetch artist genres in batches of 50
    artist_ids = list({a["id"] for t in tracks for a in t.get("artists", []) if a.get("id")})
    genres_map: dict[str, list[str]] = {}
    for i in range(0, len(artist_ids), 50):
        batch = artist_ids[i : i + 50]
        try:
            result = sp.artists(batch)
        except spotipy.SpotifyException as exc:
            if exc.http_status == 403:
                print("⚠️  Artist genres unavailable for this app (Spotify restricted endpoint). Genres will be empty.")
                break
            raise
        for artist in result.get("artists") or []:
            if artist and artist.get("id"):
                genres_map[artist["id"]] = artist.get("genres") or []

    # Merge everything
    enriched = []
    for track in tracks:
        feat = features_map.get(track["id"]) or {}
        artist_objs = track.get("artists") or []
        all_genres = []
        for a in artist_objs:
            all_genres.extend(genres_map.get(a.get("id", ""), []))
        enriched.append({
            "track": track,
            "features": feat,
            "genres": list(dict.fromkeys(all_genres)),  # deduplicate, preserve order
        })

    return enriched


def tracks_to_dataframe(tracks: list[dict]) -> pd.DataFrame:
    rows = []
    for item in tracks:
        track = item["track"]
        feat = item["features"]
        genres = item["genres"]

        artist_names = "; ".join(a["name"] for a in track.get("artists") or [])
        track_name = track.get("name", "")
        duration_ms = track.get("duration_ms") or 0
        isrc = (track.get("external_ids") or {}).get("isrc", "")
        album = (track.get("album") or {}).get("name", "")
        release_date = (track.get("album") or {}).get("release_date", "")

        tempo = float(feat.get("tempo") or 0)
        energy = float(feat.get("energy") or 0)
        danceability = float(feat.get("danceability") or 0)

        rows.append({
            "Artist Name(s)": artist_names,
            "Track Name": track_name,
            "Album Name": album,
            "Release Date": release_date,
            "Duration (ms)": duration_ms,
            "ISRC": isrc,
            "Tempo": tempo,
            "Energy": energy,
            "Danceability": danceability,
            "Genres": "; ".join(genres),
            "Record Label": "",
            "Track URI": f"spotify:track:{track.get('id', '')}",
        })

    return pd.DataFrame(rows)


def main() -> None:
    setup_script_logging(__file__)
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Import a Spotify playlist via OAuth API into IntelliDJ DB"
    )
    add_common_config_arg(parser)
    parser.add_argument(
        "--playlist",
        required=True,
        help="Spotify playlist URL or ID",
    )
    parser.add_argument("--db-path", default=None, help="SQLite path")
    parser.add_argument("--label", default=None, help="Optional batch label")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write candidates CSV",
    )
    parser.add_argument(
        "--check-library",
        action="store_true",
        default=False,
        help="Before marking a track as a download candidate, check if it already exists in the local library DB",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview; do not write to DB",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)

    client_id = coalesce(os.getenv("SPOTIFY_CLIENT_ID"), cfg_get(config, "spotify.client_id"))
    client_secret = coalesce(os.getenv("SPOTIFY_CLIENT_SECRET"), cfg_get(config, "spotify.client_secret"))
    redirect_uri = coalesce(
        os.getenv("SPOTIFY_REDIRECT_URI"),
        cfg_get(config, "spotify.redirect_uri"),
        "http://127.0.0.1:8888/callback",
    )
    db_path = resolve_db_path(args.db_path, config)
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))

    if not client_id or not client_secret:
        raise SystemExit(
            "Missing Spotify credentials.\n"
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your .env file.\n"
            "Register an app at https://developer.spotify.com/dashboard"
        )

    print(f"Authenticating with Spotify...")
    sp = authenticate(str(client_id), str(client_secret), str(redirect_uri))

    rapidapi_key = coalesce(
        os.getenv("RAPIDAPI_KEY"),
        cfg_get(config, "audio_features.rapidapi_key") or None,
    )

    print(f"Fetching playlist: {args.playlist}")
    enriched = get_playlist_tracks(sp, args.playlist, rapidapi_key=rapidapi_key)

    if not enriched:
        raise SystemExit("No tracks found in the playlist.")

    print(f"Found {len(enriched)} tracks. Fetching audio features and genres...")
    df = tracks_to_dataframe(enriched)

    if args.dry_run:
        print(f"[dry-run] {len(df)} tracks would be imported:")
        for _, row in df.iterrows():
            print(f"  {row['Artist Name(s)']} — {row['Track Name']} ({row['Tempo']:.0f} BPM, energy={row['Energy']:.2f})")
        return

    # Write a temp CSV so csv_to_dj_pipeline.main() can read it
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tmp:
        df.to_csv(tmp, index=False)
        tmp_path = tmp.name

    try:
        csv_to_dj_pipeline.main(
            input_file=tmp_path,
            output_file=args.output,
            db_path=db_path,
            label=label,
            import_method="spotify_oauth",
            dry_run=False,
            check_library=args.check_library,
        )
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    main()

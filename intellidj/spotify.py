"""
intellidj.spotify — Spotify/Exportify CSV parsing and style inference utilities.

Pure functions for cleaning track names, normalizing artists, inferring DJ styles,
and building a candidates DataFrame from Exportify CSV data.
"""
import re

import pandas as pd


def clean_track_name(name):
    junk = [
        r"\(.*extended.*\)",
        r"\(.*original.*\)",
        r"\(.*radio.*\)",
        r"\(.*remaster.*\)",
        r"\[.*\]",
        r"- extended.*",
        r"- original.*",
    ]
    cleaned = str(name)
    for j in junk:
        cleaned = re.sub(j, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def simplify_for_search(name):
    """Aggressively strip remix/version/edit/feat info for Soulseek search.

    This produces a minimal query that maximises the chance of finding results.
    The full track name is still used for relevance scoring after results arrive.
    """
    extra_junk = [
        r"\(feat\.?\s+[^)]*\)",       # (feat. POWERS)
        r"\(ft\.?\s+[^)]*\)",         # (ft. Someone)
        r"feat\.?\s+.+",              # feat. Someone (no parens)
        r"ft\.?\s+.+",                # ft. Someone (no parens)
        r"-\s+.+\s+remix\b.*",        # - Ross from Friends Remix
        r"-\s+.+\s+edit\b.*",         # - The Knocks Sunrise Edit
        r"-\s+.+\s+mix\b.*",          # - C.L.A.W.S Day Mix
        r"-\s+.+\s+version\b.*",      # - Lucid Version
        r"-\s+.+\s+dub\b.*",          # - Dub Mix
        r"-\s+.+\s+rework\b.*",       # - Rework
        r"-\s+.+\s+bootleg\b.*",      # - Bootleg
        r"-\s+\w+\s+remix\b.*",       # - Someone Remix (single word)
        r"-\s+\w+\s+version\b.*",     # - Lucid Version (single word)
        r"\(.*remix.*\)",             # (Someone Remix)
        r"\(.*edit.*\)",              # (Someone Edit)
        r"\(.*version.*\)",           # (Lucid Version)
        r"\(.*mix\)",                 # (Day Mix)
        r"\(.*dub\)",                 # (Dub)
        r"\(.*rework.*\)",            # (Rework)
        r"\(.*bootleg.*\)",           # (Bootleg)
    ]
    cleaned = clean_track_name(name)
    for j in extra_junk:
        cleaned = re.sub(j, "", cleaned, flags=re.IGNORECASE)
    # collapse whitespace and trailing punctuation
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -–—")
    return cleaned


def normalize_artist(artist):
    # Soulseek suele fallar con múltiples artistas
    return artist.split(";")[0].strip()


def infer_style(genres, bpm, energy):
    g = str(genres).lower()

    if "garage" in g or "break" in g:
        return "Garage / Breaky"
    if "minimal" in g or "micro" in g:
        return "Minimal / Micro"
    if "tech house" in g:
        return "Tech House"
    if "deep" in g or energy < 0.6:
        return "Deep House"
    if bpm >= 126 and energy >= 0.65:
        return "Peak House"
    return "House / Groovy"


def build_candidates_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    columns = [
        "artist",
        "track",
        "bpm",
        "energy",
        "danceability",
        "style",
        "label",
        "genres",
        "search_string",
    ]

    for _, row in df.iterrows():
        artist_raw = row["Artist Name(s)"]
        artist = normalize_artist(artist_raw)

        track = clean_track_name(row["Track Name"])

        bpm = round(row["Tempo"])
        energy = round(row["Energy"], 2)
        danceability = round(row["Danceability"], 2)
        genres = row["Genres"]
        label = row["Record Label"]

        style = infer_style(genres, bpm, energy)

        rows.append({
            "artist": artist,
            "track": track,
            "bpm": bpm,
            "energy": energy,
            "danceability": danceability,
            "style": style,
            "label": label,
            "genres": genres,
            "search_string": f"{artist} - {track}",
        })

    out = pd.DataFrame(rows, columns=columns)

    out.drop_duplicates(subset=["search_string"], inplace=True)
    out.sort_values(by=["style", "bpm"], inplace=True)
    return out

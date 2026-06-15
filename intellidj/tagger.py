"""
intellidj.tagger — Audio tag reading, writing, and fuzzy matching utilities.

Pure functions for normalizing text, matching audio files to metadata rows,
extracting tags/ISRC/duration, and writing enriched tags to MP3/FLAC files.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TBPM, TDRC, TCON, TIT2, TPE1, TPUB, TSRC, TXXX


def normalize(text: str) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"\(.*?\)|\[.*?\]|\{.*?\}", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r"^\d{1,3}\s*[-._]\s*", "", name)
    name = re.sub(r"^\d{1,3}\s+", "", name)
    return name


def artist_list(artist_raw: str) -> list[str]:
    if not artist_raw:
        return []
    parts = [p.strip() for p in artist_raw.split(";") if p.strip()]
    return parts or [artist_raw.strip()]


def generate_keys(row: dict) -> set[str]:
    track = str(row.get("Track Name", "")).strip()
    artists = artist_list(str(row.get("Artist Name(s)", "")))
    if not artists:
        return set()

    artist_primary = artists[0]
    keys = set()

    base = f"{artist_primary} - {track}"
    keys.add(normalize(base))

    if len(artists) > 1:
        keys.add(normalize(f"{' & '.join(artists)} - {track}"))

    track_clean = re.sub(r"\s*-\s*.*(remix|mix|edit|version|rework)\b.*", "", track, flags=re.IGNORECASE)
    if track_clean and track_clean != track:
        keys.add(normalize(f"{artist_primary} - {track_clean}"))

    return {k for k in keys if k}


def generate_title_keys(row: dict) -> set[str]:
    track = str(row.get("Track Name", "")).strip()
    if not track:
        return set()
    keys = set()
    keys.add(normalize(track))
    track_clean = re.sub(r"\s*-\s*.*(remix|mix|edit|version|rework)\b.*", "", track, flags=re.IGNORECASE)
    if track_clean and track_clean != track:
        keys.add(normalize(track_clean))
    return {k for k in keys if k}


def best_match(file_key: str, candidates: list[tuple[str, dict]], min_score: float, return_best: bool = False):
    best = None
    best_score = 0.0
    best_key = None
    for k, row in candidates:
        if k == file_key:
            return row, 1.0, k
        score = SequenceMatcher(None, file_key, k).ratio()
        if score > best_score:
            best_score = score
            best = row
            best_key = k
    if best and best_score >= min_score:
        return best, best_score, best_key
    if return_best:
        return best, best_score, best_key
    return None, 0.0, None


def best_match_with_duration(
    file_key: str,
    candidates: list[tuple[str, dict]],
    min_score: float,
    duration_ms: int | None,
    tolerance_ms: int,
):
    if duration_ms is None:
        return best_match(file_key, candidates, min_score, return_best=True)
    # Prefer candidates within duration tolerance
    filtered = []
    for k, row in candidates:
        try:
            row_ms = int(float(row.get("Duration (ms)")))
        except Exception:
            row_ms = None
        if row_ms is None:
            continue
        if abs(row_ms - duration_ms) <= tolerance_ms:
            filtered.append((k, row))
    if filtered:
        return best_match(file_key, filtered, min_score, return_best=True)
    # Fallback to full list if nothing matched duration
    return best_match(file_key, candidates, min_score, return_best=True)


def extract_artist_title_from_filename(stem: str) -> tuple[str | None, str | None]:
    name = clean_filename(stem)
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return artist.strip() or None, title.strip() or None
    return None, name.strip() or None


def extract_tags(path: Path) -> tuple[str | None, str | None]:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return None, None
    if not audio or not audio.tags:
        return None, None
    artist = None
    title = None
    if "artist" in audio.tags:
        artist = audio.tags.get("artist", [None])[0]
    if "title" in audio.tags:
        title = audio.tags.get("title", [None])[0]
    return artist, title


def extract_isrc(path: Path) -> str | None:
    try:
        audio = MutagenFile(path, easy=False)
    except Exception:
        return None
    if not audio or not audio.tags:
        return None
    # FLAC/Vorbis
    if hasattr(audio.tags, "get"):
        val = audio.tags.get("ISRC")
        if val:
            if isinstance(val, list):
                return str(val[0])
            return str(val)
    # ID3
    if isinstance(audio.tags, ID3):
        frame = audio.tags.get("TSRC")
        if isinstance(frame, TSRC) and frame.text:
            return str(frame.text[0])
    return None


def normalize_isrc(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    return normalized or None


def extract_duration_ms(path: Path) -> int | None:
    try:
        audio = MutagenFile(path, easy=False)
    except Exception:
        return None
    if not audio or not getattr(audio, "info", None):
        return None
    length = getattr(audio.info, "length", None)
    if length is None:
        return None
    return int(round(float(length) * 1000))


def extract_row_duration_ms(row: dict) -> int | None:
    value = row.get("Duration (ms)") or row.get("Duration")
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def set_tags_mp3(path: Path, row: dict, custom: bool) -> None:
    audio = MutagenFile(path, easy=False)
    if audio is None:
        raise RuntimeError("Unsupported file")
    if audio.tags is None:
        audio.tags = ID3()

    artists = artist_list(str(row.get("Artist Name(s)", "")))
    title = str(row.get("Track Name", ""))
    album = str(row.get("Album Name", ""))
    date = str(row.get("Release Date", ""))
    genre = str(row.get("Genres", ""))
    label = str(row.get("Record Label", ""))
    bpm = row.get("Tempo")
    isrc = normalize_isrc(row.get("ISRC") or row.get("isrc"))

    audio.tags.setall("TPE1", [TPE1(encoding=3, text=artists)])
    audio.tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    if album:
        audio.tags.setall("TALB", [TALB(encoding=3, text=album)])
    if date:
        audio.tags.setall("TDRC", [TDRC(encoding=3, text=date)])
    if genre:
        audio.tags.setall("TCON", [TCON(encoding=3, text=genre)])
    if label:
        audio.tags.setall("TPUB", [TPUB(encoding=3, text=label)])
    if bpm:
        audio.tags.setall("TBPM", [TBPM(encoding=3, text=str(bpm))])
    if isrc:
        audio.tags.setall("TSRC", [TSRC(encoding=3, text=isrc)])

    if custom:
        def txxx(desc, value):
            audio.tags.setall(f"TXXX:{desc}", [TXXX(encoding=3, desc=desc, text=str(value))])

        txxx("SPOTIFY_URI", row.get("Track URI", ""))
        txxx("ENERGY", row.get("Energy", ""))
        txxx("DANCEABILITY", row.get("Danceability", ""))
        txxx("KEY", row.get("Key", ""))
        txxx("LOUDNESS", row.get("Loudness", ""))
        txxx("VALENCE", row.get("Valence", ""))
        txxx("INSTRUMENTALNESS", row.get("Instrumentalness", ""))

    audio.save()


def set_tags_flac(path: Path, row: dict, custom: bool) -> None:
    audio = FLAC(path)

    artists = artist_list(str(row.get("Artist Name(s)", "")))
    title = str(row.get("Track Name", ""))
    album = str(row.get("Album Name", ""))
    date = str(row.get("Release Date", ""))
    genre = str(row.get("Genres", ""))
    label = str(row.get("Record Label", ""))
    bpm = row.get("Tempo")
    isrc = normalize_isrc(row.get("ISRC") or row.get("isrc"))

    audio["ARTIST"] = artists
    audio["TITLE"] = [title]
    if album:
        audio["ALBUM"] = [album]
    if date:
        audio["DATE"] = [date]
    if genre:
        audio["GENRE"] = [genre]
    if label:
        audio["LABEL"] = [label]
    if bpm:
        audio["BPM"] = [str(bpm)]
    if isrc:
        audio["ISRC"] = [isrc]

    if custom:
        def setc(key, value):
            if value is not None and value != "":
                audio[key] = [str(value)]

        setc("SPOTIFY_URI", row.get("Track URI", ""))
        setc("ENERGY", row.get("Energy", ""))
        setc("DANCEABILITY", row.get("Danceability", ""))
        setc("KEY", row.get("Key", ""))
        setc("LOUDNESS", row.get("Loudness", ""))
        setc("VALENCE", row.get("Valence", ""))
        setc("INSTRUMENTALNESS", row.get("Instrumentalness", ""))

    audio.save()


def write_tags(path: Path, row: dict, custom: bool) -> None:
    ext = path.suffix.lower()
    if ext == ".mp3" or ext == ".aif" or ext == ".aiff" or ext == ".wav":
        set_tags_mp3(path, row, custom)
    elif ext == ".flac":
        set_tags_flac(path, row, custom)
    else:
        raise RuntimeError(f"Unsupported extension: {ext}")

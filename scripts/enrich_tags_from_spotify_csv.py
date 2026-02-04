#!/usr/bin/env python3
import argparse
import csv
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TPE1, TIT2, TALB, TDRC, TCON, TPUB, TBPM, TXXX
from mutagen.flac import FLAC


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


def best_match(file_key: str, candidates: list[tuple[str, dict]], min_score: float):
    best = None
    best_score = 0.0
    for k, row in candidates:
        if k == file_key:
            return row, 1.0
        score = SequenceMatcher(None, file_key, k).ratio()
        if score > best_score:
            best_score = score
            best = row
    if best and best_score >= min_score:
        return best, best_score
    return None, 0.0


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich downloaded audio tags using spotify_export.csv")
    parser.add_argument("--csv", default="spotify_export.csv", help="Path to spotify_export.csv")
    parser.add_argument("--input-dir", default=os.path.expanduser("~/Soulseek/downloads/complete"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=0.86)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--custom-tags", action="store_true", help="Write custom tags like energy/danceability")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    # Build lookup list
    candidates = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys = generate_keys(row)
            for k in keys:
                candidates.append((k, row))

    input_dir = Path(args.input_dir).expanduser()
    files = []
    for ext in ("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff"):
        files.extend(input_dir.rglob(ext))

    if args.limit:
        files = files[: args.limit]

    matched = 0
    skipped = 0
    errors = 0

    for path in files:
        key = normalize(clean_filename(path.stem))
        row, score = best_match(key, candidates, args.min_score)
        if not row:
            skipped += 1
            continue

        if args.dry_run:
            print(f"[dry-run] {path.name} -> {row.get('Artist Name(s)')} - {row.get('Track Name')} (score={score:.2f})")
            matched += 1
            continue

        try:
            write_tags(path, row, args.custom_tags)
            matched += 1
        except Exception as exc:
            errors += 1
            print(f"[error] {path.name}: {exc}")

    print(f"\nDone. matched={matched} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    main()

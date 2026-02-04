#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TPE1, TIT2, TALB, TDRC, TCON, TPUB, TBPM, TXXX, TSRC
from mutagen.flac import FLAC


def _setup_logging() -> None:
    script_path = Path(__file__).resolve()
    repo_root = None
    for parent in [script_path.parent] + list(script_path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            repo_root = parent
            break
    if repo_root is None:
        repo_root = script_path.parent
    log_dir = repo_root / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{script_path.stem}.log"
    log_file = log_path.open("a", encoding="utf-8")

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for stream in self.streams:
                stream.write(data)
                stream.flush()

        def flush(self):
            for stream in self.streams:
                stream.flush()

    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)


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


def best_match_with_duration(file_key: str, candidates: list[tuple[str, dict]], min_score: float, duration_ms: int | None, tolerance_ms: int):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich downloaded audio tags using spotify_export.csv")
    parser.add_argument("--csv", default="spotify_export.csv", help="Path to spotify_export.csv")
    parser.add_argument("--input-dir", default=os.path.expanduser("~/Soulseek/downloads/complete"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=0.86)
    parser.add_argument("--min-score-title", type=float, default=0.78)
    parser.add_argument("--duration-tolerance-ms", type=int, default=2000)
    parser.add_argument("--no-duration", action="store_true", help="Do not use duration for matching")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--custom-tags", action="store_true", help="Write custom tags like energy/danceability")
    parser.add_argument("--report", help="Write a CSV report for matches and skips")
    parser.add_argument("--no-tags", action="store_true", help="Do not use existing file tags for matching")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    # Build lookup list
    candidates = []
    title_candidates = []
    isrc_map = {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            isrc = normalize_isrc(row.get("ISRC") or row.get("isrc"))
            if isrc:
                isrc_map[isrc] = row
            keys = generate_keys(row)
            for k in keys:
                candidates.append((k, row))
            tkeys = generate_title_keys(row)
            for k in tkeys:
                title_candidates.append((k, row))

    input_dir = Path(args.input_dir).expanduser()
    files = []
    for ext in ("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff"):
        files.extend(input_dir.rglob(ext))

    if args.limit:
        files = files[: args.limit]

    matched = 0
    skipped = 0
    errors = 0

    report_rows = []

    for path in files:
        artist_tag = title_tag = None
        if not args.no_tags:
            artist_tag, title_tag = extract_tags(path)
        file_isrc = normalize_isrc(extract_isrc(path))
        file_duration_ms = None if args.no_duration else extract_duration_ms(path)

        # Build keys
        artist_from_name, title_from_name = extract_artist_title_from_filename(path.stem)
        artist = artist_tag or artist_from_name
        title = title_tag or title_from_name

        file_key = normalize(f"{artist} - {title}") if artist and title else normalize(clean_filename(path.stem))
        title_key = normalize(title) if title else None

        row = None
        score = 0.0
        best_key = None
        match_type = "artist_title"

        if file_isrc:
            row = isrc_map.get(file_isrc)
            if row:
                score = 1.0
                best_key = file_isrc
                match_type = "isrc"

        if not row:
            row, score, best_key = best_match_with_duration(
                file_key,
                candidates,
                args.min_score,
                file_duration_ms,
                args.duration_tolerance_ms,
            )
            match_type = "artist_title"
            if not row or score < args.min_score:
                row = None

        if not row and title_key:
            row, score, best_key = best_match_with_duration(
                title_key,
                title_candidates,
                args.min_score_title,
                file_duration_ms,
                args.duration_tolerance_ms,
            )
            match_type = "title_only"
            if not row or score < args.min_score_title:
                row = None

        if not row:
            skipped += 1
            report_rows.append({
                "file": str(path),
                "match": "none",
                "score": f"{score:.2f}",
                "file_key": file_key,
                "title_key": title_key or "",
                "best_key": best_key or "",
                "file_isrc": file_isrc or "",
                "file_duration_ms": file_duration_ms or "",
                "matched_duration_ms": "",
                "duration_diff_ms": "",
                "matched_artist": "",
                "matched_title": "",
                "matched_album": "",
                "reason": "no_match",
            })
            continue

        row_duration_ms = extract_row_duration_ms(row)
        duration_diff_ms = ""
        if file_duration_ms is not None and row_duration_ms is not None:
            duration_diff_ms = str(abs(file_duration_ms - row_duration_ms))

        if args.dry_run:
            print(f"[dry-run] {path.name} -> {row.get('Artist Name(s)')} - {row.get('Track Name')} (score={score:.2f})")
            matched += 1
            report_rows.append({
                "file": str(path),
                "match": match_type,
                "score": f"{score:.2f}",
                "file_key": file_key,
                "title_key": title_key or "",
                "best_key": best_key or "",
                "file_isrc": file_isrc or "",
                "file_duration_ms": file_duration_ms or "",
                "matched_duration_ms": row_duration_ms or "",
                "duration_diff_ms": duration_diff_ms,
                "matched_artist": row.get("Artist Name(s)", ""),
                "matched_title": row.get("Track Name", ""),
                "matched_album": row.get("Album Name", ""),
                "reason": "dry_run",
            })
            continue

        try:
            write_tags(path, row, args.custom_tags)
            matched += 1
            report_rows.append({
                "file": str(path),
                "match": match_type,
                "score": f"{score:.2f}",
                "file_key": file_key,
                "title_key": title_key or "",
                "best_key": best_key or "",
                "file_isrc": file_isrc or "",
                "file_duration_ms": file_duration_ms or "",
                "matched_duration_ms": row_duration_ms or "",
                "duration_diff_ms": duration_diff_ms,
                "matched_artist": row.get("Artist Name(s)", ""),
                "matched_title": row.get("Track Name", ""),
                "matched_album": row.get("Album Name", ""),
                "reason": "written",
            })
        except Exception as exc:
            errors += 1
            print(f"[error] {path.name}: {exc}")
            report_rows.append({
                "file": str(path),
                "match": match_type,
                "score": f"{score:.2f}",
                "file_key": file_key,
                "title_key": title_key or "",
                "best_key": best_key or "",
                "file_isrc": file_isrc or "",
                "file_duration_ms": file_duration_ms or "",
                "matched_duration_ms": row_duration_ms or "",
                "duration_diff_ms": duration_diff_ms,
                "matched_artist": row.get("Artist Name(s)", ""),
                "matched_title": row.get("Track Name", ""),
                "matched_album": row.get("Album Name", ""),
                "reason": f"error:{exc}",
            })

    if args.report:
        report_path = Path(args.report)
        with report_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "file",
                    "match",
                    "score",
                    "file_key",
                    "title_key",
                    "best_key",
                    "file_isrc",
                    "file_duration_ms",
                    "matched_duration_ms",
                    "duration_diff_ms",
                    "matched_artist",
                    "matched_title",
                    "matched_album",
                    "reason",
                ],
            )
            writer.writeheader()
            writer.writerows(report_rows)

    print(f"\nDone. matched={matched} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    _setup_logging()
    main()

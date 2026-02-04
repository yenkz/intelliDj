#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sys
import unicodedata
from pathlib import Path

from mutagen import File as MutagenFile


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
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_filename(stem: str) -> str:
    stem = stem.strip()
    stem = re.sub(r"^\d{1,3}\s*[-._]\s*", "", stem)
    stem = re.sub(r"^\d{1,3}\s+", "", stem)
    return stem


def extract_tags(path: Path):
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


def build_index(library_dir: Path):
    index = {}
    title_index = {}
    files = []
    for ext in ("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff"):
        files.extend(library_dir.rglob(ext))

    for path in files:
        artist, title = extract_tags(path)
        keys = set()
        title_keys = set()

        if artist and title:
            keys.add(normalize(f"{artist} - {title}"))
            title_keys.add(normalize(title))

        stem = clean_filename(path.stem)
        if " - " in stem:
            a, t = stem.split(" - ", 1)
            keys.add(normalize(f"{a} - {t}"))
            title_keys.add(normalize(t))
        else:
            keys.add(normalize(stem))
            title_keys.add(normalize(stem))

        for k in keys:
            index.setdefault(k, []).append(path)
        for k in title_keys:
            title_index.setdefault(k, []).append(path)

    return index, title_index


def sanitize_filename(name: str) -> str:
    name = name.strip().replace("/", "-")
    name = re.sub(r"[^a-zA-Z0-9._ -]+", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description="Export M3U playlists by style from dj_candidates.csv")
    parser.add_argument("--csv", default="dj_candidates.csv")
    parser.add_argument("--library-dir", default=os.path.expanduser("~/Music/DJ/library"))
    parser.add_argument("--out-dir", default="playlists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    library_dir = Path(args.library_dir).expanduser()
    if not library_dir.exists():
        raise SystemExit(f"Library not found: {library_dir}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    index, title_index = build_index(library_dir)

    playlists = {}
    matched = 0
    skipped = 0

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            style = (row.get("style") or "Unknown").strip() or "Unknown"
            artist = (row.get("artist") or "").strip()
            title = (row.get("track") or "").strip()

            key = normalize(f"{artist} - {title}") if artist and title else normalize(title)
            paths = index.get(key) or []
            if not paths and title:
                paths = title_index.get(normalize(title)) or []

            if not paths:
                skipped += 1
                continue

            # Prefer first match
            path = paths[0]
            playlists.setdefault(style, []).append(path)
            matched += 1

    for style, paths in playlists.items():
        name = sanitize_filename(style).replace(" ", "_") or "Unknown"
        m3u_path = out_dir / f"{name}.m3u"
        if args.dry_run:
            print(f"[dry-run] {m3u_path} ({len(paths)} tracks)")
            continue
        with m3u_path.open("w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            for p in paths:
                f.write(str(p) + "\n")

    print(f"\nDone. matched={matched} skipped={skipped} styles={len(playlists)}")


if __name__ == "__main__":
    _setup_logging()
    main()

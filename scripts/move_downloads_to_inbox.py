#!/usr/bin/env python3
"""
Move completed slskd downloads to the staging inbox for further processing.

This script creates a clear boundary between raw downloads and the processing
pipeline (tag enrichment → beets import → library). Files are copied (or moved
with --move) and tracked in the DB with stage: inbox / status: staged.

Usage:
    python scripts/move_downloads_to_inbox.py
    python scripts/move_downloads_to_inbox.py --move --fingerprint
    python scripts/move_downloads_to_inbox.py --dry-run
"""
import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from intellidj_common import (
    add_common_config_arg,
    add_common_selector_args,
    cfg_get,
    coalesce,
    load_env_file,
    load_project_config,
    resolve_db_path,
    resolve_inbox_dir,
    setup_script_logging,
)
from intellidj_db import IntelliDJDB, make_track_key

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a", ".ogg", ".opus"}

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


def _sanitize(name: str) -> str:
    return _INVALID_CHARS.sub("_", name).strip(". ") or "unknown"


def _normalized_dest(artist: str | None, title: str | None, suffix: str, inbox: Path) -> Path:
    """Build inbox/<Artist> - <Title>.ext; fall back to None if tags missing."""
    if not artist or not title:
        return None  # type: ignore[return-value]
    name = f"{_sanitize(artist)} - {_sanitize(title)}{suffix}"
    dest = inbox / name
    # Avoid collisions with a numeric suffix
    if dest.exists():
        stem, counter = dest.stem, 1
        while dest.exists():
            dest = inbox / f"{stem} ({counter}){suffix}"
            counter += 1
    return dest


_FORMAT_RANK = {".flac": 0, ".wav": 1, ".aif": 1, ".aiff": 1, ".m4a": 2, ".mp3": 3, ".ogg": 4, ".opus": 4}


def _file_quality_key(path: Path) -> tuple:
    """Lower is better: (format_rank, -size_bytes)."""
    rank = _FORMAT_RANK.get(path.suffix.lower(), 99)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return (rank, -size)


def _base_stem(path: Path) -> str:
    """Strip trailing ' (N)' collision suffixes to recover the canonical stem."""
    return re.sub(r"\s+\(\d+\)$", "", path.stem)


def _dedupe_staged(staged_paths: list[Path], dry_run: bool) -> int:
    """For files staged in this run, keep the best copy of each Artist - Title; remove the rest."""
    from collections import defaultdict
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in staged_paths:
        if dry_run or p.exists():
            groups[_base_stem(p).lower()].append(p)

    removed = 0
    for stem, paths in groups.items():
        if len(paths) < 2:
            continue
        paths.sort(key=_file_quality_key)
        keeper, *dupes = paths
        for dup in dupes:
            print(f"  [dedupe] keep={keeper.name}  remove={dup.name}")
            if not dry_run:
                dup.unlink()
            removed += 1
    return removed


def _parse_since(value: str) -> datetime:
    """Parse --since value. Accepts HH:MM (today) or YYYY-MM-DD HH:MM."""
    for fmt in ("%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%H:%M":
                now = datetime.now()
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Cannot parse --since '{value}'. Use HH:MM or YYYY-MM-DD HH:MM."
    )


def _discover_audio_files(
    directory: Path,
    folder: str | None = None,
    since: datetime | None = None,
) -> list[Path]:
    search_root = directory / folder if folder else directory
    if folder and not search_root.exists():
        raise SystemExit(f"ERROR: folder not found: {search_root}")
    files = []
    for path in sorted(search_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        if since is not None:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            if mtime < since:
                continue
        files.append(path)
    return files


def _extract_tags(path: Path) -> tuple[str | None, str | None, str | None]:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path), easy=True)
        if audio is None:
            return None, None, None
        artist = (audio.get("artist") or [None])[0]
        title = (audio.get("title") or [None])[0]
        album = (audio.get("album") or [None])[0]
        return artist, title, album
    except Exception:
        return None, None, None


def _extract_technical(path: Path) -> tuple[int | None, int | None, int | None, int | None]:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path))
        if audio is None or not hasattr(audio, "info"):
            return None, None, None, None
        info = audio.info
        duration_ms = int(info.length * 1000) if hasattr(info, "length") else None
        bitrate = int(getattr(info, "bitrate", 0) // 1000) or None
        sample_rate = int(getattr(info, "sample_rate", 0)) or None
        bit_depth = int(getattr(info, "bits_per_sample", 0)) or None
        return duration_ms, bitrate, sample_rate, bit_depth
    except Exception:
        return None, None, None, None


def main() -> None:
    setup_script_logging(__file__)
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Move completed slskd downloads to the staging inbox."
    )
    add_common_config_arg(parser)
    add_common_selector_args(parser, include_scope=False)
    parser.add_argument("--downloads-dir", default=None, help="Source slskd downloads directory")
    parser.add_argument("--inbox-dir", default=None, help="Destination staging inbox directory")
    parser.add_argument("--folder", default=None, help="Only process a specific subfolder inside downloads-dir")
    parser.add_argument("--since", type=_parse_since, default=None, metavar="HH:MM or 'YYYY-MM-DD HH:MM'",
                        help="Only process files modified at or after this time (local). E.g. 08:45 or '2026-03-18 08:45'")
    parser.add_argument("--db-path", default=None, help="Path to intellidj.db")
    parser.add_argument(
        "--move",
        action="store_true",
        default=False,
        help="Move files instead of copying (default: copy for safety)",
    )
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        default=False,
        help="Compute Chromaprint fingerprints for each staged file",
    )
    parser.add_argument(
        "--no-rename",
        action="store_true",
        default=False,
        help="Keep original filename instead of renaming to 'Artist - Title.ext'",
    )
    parser.add_argument(
        "--dedupe",
        action="store_true",
        default=False,
        help="After staging, remove lower-quality duplicates (same Artist - Title). Prefers FLAC > WAV > M4A > MP3, then larger file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without writing to DB or disk")
    args = parser.parse_args()

    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    label = args.label or cfg_get(config, "pipeline.label") or None

    downloads_dir = Path(
        coalesce(
            args.downloads_dir,
            os.getenv("INTELLIDJ_DOWNLOADS_DIR"),
            cfg_get(config, "paths.downloads_dir"),
            "~/Soulseek/downloads/complete",
        )
    ).expanduser().resolve()

    inbox_dir = Path(resolve_inbox_dir(args.inbox_dir, config)).expanduser().resolve()

    if not downloads_dir.exists():
        print(f"ERROR: downloads directory does not exist: {downloads_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        inbox_dir.mkdir(parents=True, exist_ok=True)

    print(f"Source:      {downloads_dir}")
    print(f"Destination: {inbox_dir}")
    print(f"Mode:        {'move' if args.move else 'copy'}")
    if args.folder:
        print(f"Folder:      {args.folder}")
    if args.since:
        print(f"Since:       {args.since.strftime('%Y-%m-%d %H:%M')} (local)")
    if args.dry_run:
        print("(dry-run — no changes will be made)")

    files = _discover_audio_files(downloads_dir, folder=args.folder, since=args.since)
    if not files:
        print("No audio files found matching the given filters.")
        return

    print(f"Found {len(files)} audio file(s).")

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="move_downloads_to_inbox.py",
        input_path=str(downloads_dir),
        output_path=str(inbox_dir),
        options={"label": label, "batch_id": args.batch_id, "move": args.move, "dry_run": args.dry_run},
    )

    batch_id = args.batch_id
    if batch_id is None:
        batch_id_row = db.get_latest_batch(label=label) if label else db.get_latest_batch()
        if batch_id_row:
            batch_id = int(batch_id_row["id"])
    if batch_id is None:
        batch_id = db.create_ingestion_batch(
            source_type="slskd_download",
            label=label,
            source_ref=str(downloads_dir),
        )

    staged = 0
    skipped = 0
    errors = 0
    staged_paths: list[Path] = []

    fp_module = None
    if args.fingerprint and not args.dry_run:
        try:
            import intellidj_fingerprint as fp_module
        except ImportError:
            print("WARNING: intellidj_fingerprint not found; skipping fingerprinting.", file=sys.stderr)
            fp_module = None

    for src_path in files:
        # Extract tags from source to determine destination filename
        artist, title, album = _extract_tags(src_path)

        if args.no_rename:
            dest_path = inbox_dir / src_path.name
        else:
            dest_path = _normalized_dest(artist, title, src_path.suffix.lower(), inbox_dir)
            if dest_path is None:
                # No usable tags — fall back to original name
                print(f"  [no tags] keeping original name: {src_path.name}")
                dest_path = inbox_dir / src_path.name

        # Skip if already in inbox
        if dest_path.exists():
            print(f"  skip (already in inbox): {dest_path.name}")
            skipped += 1
            continue

        if args.dry_run:
            label_ = f"{src_path.name} → {dest_path.name}" if dest_path.name != src_path.name else src_path.name
            print(f"  [dry-run] {'move' if args.move else 'copy'}: {label_}")
            staged_paths.append(dest_path)
            skipped += 1
            continue

        try:
            if args.move:
                shutil.move(str(src_path), str(dest_path))
            else:
                shutil.copy2(str(src_path), str(dest_path))
        except Exception as exc:
            print(f"  ERROR transferring {src_path.name}: {exc}", file=sys.stderr)
            errors += 1
            continue

        duration_ms, bitrate, sample_rate, bit_depth = _extract_technical(dest_path)

        # Try to link to an existing track via tags
        track_id: int | None = None
        if artist or title:
            track_key = make_track_key(artist=artist, title=title, duration_ms=duration_ms)
            track_id = db.get_track_id_by_key(track_key)
            if track_id is None:
                track_id = db.upsert_track(
                    track_key=track_key,
                    artist=artist,
                    title=title,
                    album=album,
                    duration_ms=duration_ms,
                    source_search_string=f"{artist} - {title}" if artist and title else None,
                )

        db.upsert_library_file(
            path=str(dest_path),
            filename=dest_path.name,
            extension=dest_path.suffix.lower(),
            size_bytes=dest_path.stat().st_size,
            duration_ms=duration_ms,
            bitrate_kbps=bitrate,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            artist_tag=artist,
            title_tag=title,
            album_tag=album,
            batch_id=batch_id,
            track_id=track_id,
            source_type="slskd_download",
            status="staged",
        )

        db.upsert_asset(
            run_id=run_id,
            track_id=track_id,
            asset_type="inbox_file",
            path=str(dest_path),
            origin=str(src_path),
            status="staged",
            size_bytes=dest_path.stat().st_size,
        )

        if track_id:
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="inbox",
                status="staged",
                run_id=run_id,
                batch_id=batch_id,
                method="move" if args.move else "copy",
                details={"source": str(src_path)},
            )
            db.add_event(
                run_id=run_id,
                track_id=track_id,
                stage="inbox",
                status="staged",
                message=f"{'Moved' if args.move else 'Copied'} to inbox: {dest_path.name}",
                file_path=str(dest_path),
            )

        if fp_module is not None:
            lf_row = db.get_library_file_by_path(str(dest_path))
            if lf_row:
                try:
                    fp_str, fp_dur = fp_module.fingerprint_file(dest_path)
                    if fp_str and fp_dur is not None:
                        db.upsert_fingerprint(
                            library_file_id=int(lf_row["id"]),
                            track_id=track_id,
                            fpcalc_fingerprint=fp_str,
                            fpcalc_duration_sec=fp_dur,
                            status="computed",
                        )
                        if track_id:
                            db.upsert_track_stage_state(
                                track_id=track_id,
                                stage="fingerprint",
                                status="computed",
                                run_id=run_id,
                                batch_id=batch_id,
                            )
                except RuntimeError:
                    pass  # fpcalc not installed; silently skip

        action = "moved" if args.move else "copied"
        label_ = f"{src_path.name} → {dest_path.name}" if dest_path.name != src_path.name else src_path.name
        print(f"  {action}: {label_}")
        staged_paths.append(dest_path)
        staged += 1

    removed = 0
    if args.dedupe and staged_paths:
        print(f"\nDeduplicating {len(staged_paths)} staged file(s)...")
        removed = _dedupe_staged(staged_paths, dry_run=args.dry_run)
        if removed == 0:
            print("  No duplicates found.")

    db.finish_run(
        run_id,
        status="success",
        total_count=staged + skipped + errors,
        success_count=staged,
        skipped_count=skipped,
        error_count=errors,
    )
    db.close()

    print(f"\nDone. staged={staged}, skipped={skipped}, errors={errors}, dupes_removed={removed}")


if __name__ == "__main__":
    main()

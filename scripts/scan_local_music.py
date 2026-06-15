#!/usr/bin/env python3
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_common import (
    add_common_config_arg,
    cfg_get,
    coalesce,
    load_env_file,
    load_project_config,
    resolve_db_path,
    setup_script_logging,
)
from intellidj_db import IntelliDJDB, make_track_key


AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a")

def _extract_tags(path: Path) -> tuple[str | None, str | None, str | None]:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        return None, None, None
    if not audio or not audio.tags:
        return None, None, None
    artist = audio.tags.get("artist", [None])[0] if "artist" in audio.tags else None
    title = audio.tags.get("title", [None])[0] if "title" in audio.tags else None
    album = audio.tags.get("album", [None])[0] if "album" in audio.tags else None
    return artist, title, album


def _extract_technical(path: Path) -> tuple[int | None, int | None, int | None, int | None]:
    try:
        audio = MutagenFile(path, easy=False)
    except Exception:
        return None, None, None, None
    if not audio or not getattr(audio, "info", None):
        return None, None, None, None
    info = audio.info
    duration_ms = int(round(float(getattr(info, "length", 0.0)) * 1000)) if getattr(info, "length", None) else None
    bitrate = int(round(float(getattr(info, "bitrate", 0.0)) / 1000)) if getattr(info, "bitrate", None) else None
    sample_rate = int(getattr(info, "sample_rate")) if getattr(info, "sample_rate", None) else None
    bit_depth = int(getattr(info, "bits_per_sample")) if getattr(info, "bits_per_sample", None) else None
    return duration_ms, bitrate, sample_rate, bit_depth


def _extract_from_filename(path: Path) -> tuple[str | None, str | None]:
    stem = path.stem
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        return artist.strip() or None, title.strip() or None
    return None, stem.strip() or None


def _discover_files(input_dir: Path) -> list[Path]:
    files = []
    for ext in AUDIO_EXTENSIONS:
        files.extend(input_dir.rglob(f"*{ext}"))
        files.extend(input_dir.rglob(f"*{ext.upper()}"))
    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan a local music folder and ingest tracks into intellidj.db")
    add_common_config_arg(parser)
    parser.add_argument("--input-dir", required=False, default=None, help="Folder to scan for audio files")
    parser.add_argument("--db-path", default=None, help="SQLite path (default: INTELLIDJ_DB_PATH or ./intellidj.db)")
    parser.add_argument("--label", default=None, help="Optional batch label")
    parser.add_argument("--import-method", default=None, help="Import method label")
    parser.add_argument("--limit", type=int, default=None, help="Optional max files to scan")
    parser.add_argument("--dry-run", action="store_true", help="Preview scan without writing DB")
    parser.add_argument(
        "--fingerprint",
        action="store_true",
        default=False,
        help="Compute Chromaprint fingerprints for all scanned files after indexing (requires fpcalc on PATH)",
    )
    parser.add_argument(
        "--acoustid-api-key",
        default=None,
        help="AcoustID API key for cloud lookup after fingerprinting (or set ACOUSTID_API_KEY env var)",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)

    input_dir_value = coalesce(args.input_dir, cfg_get(config, "paths.scan_dir"))
    if not input_dir_value:
        raise SystemExit("Missing --input-dir (or set paths.scan_dir in intellidj.toml).")
    input_dir = Path(os.path.expanduser(str(input_dir_value))).resolve()
    db_path = resolve_db_path(args.db_path, config)
    label_arg = coalesce(args.label, cfg_get(config, "pipeline.label"))
    import_method = str(coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "local_scan"))
    if not input_dir.is_dir():
        raise SystemExit(f"Input directory not found: {input_dir}")

    files = _discover_files(input_dir)
    if args.limit is not None:
        files = files[: args.limit]
    if not files:
        raise SystemExit(f"No supported audio files found in: {input_dir}")

    if args.dry_run:
        print(f"[dry-run] found {len(files)} audio files in {input_dir}")
        for sample in files[:5]:
            print(f"[dry-run] sample: {sample}")
        if args.fingerprint:
            print("[dry-run] --fingerprint requested but skipped in dry-run mode")
        return

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="scan_local_music.py",
        input_path=str(input_dir),
        options={
            "label": label_arg,
            "import_method": import_method,
            "limit": args.limit,
            "dry_run": args.dry_run,
            "db_path": db_path,
        },
    )
    label = label_arg or f"localscan-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    batch_id = db.create_ingestion_batch(
        source_type="local_scan",
        import_method=import_method,
        label=label,
        source_ref=str(input_dir),
    )

    indexed = 0
    errors = 0
    new_tracks = 0
    existing_tracks = 0
    pipeline_status = "success"

    try:
        for idx, path in enumerate(files):
            artist, title, album = _extract_tags(path)
            if not artist or not title:
                artist_from_name, title_from_name = _extract_from_filename(path)
                artist = artist or artist_from_name
                title = title or title_from_name
            duration_ms, bitrate_kbps, sample_rate, bit_depth = _extract_technical(path)

            search_string = f"{artist} - {title}" if artist and title else title or path.stem
            track_key = make_track_key(
                artist=artist,
                title=title,
                search_string=search_string,
                duration_ms=duration_ms,
            )
            existing_track_id = db.get_track_id_by_key(track_key)
            track_id = db.upsert_track(
                track_key=track_key,
                artist=artist,
                title=title,
                album=album,
                duration_ms=duration_ms,
                source_search_string=search_string,
            )
            if existing_track_id is None:
                new_tracks += 1
            else:
                existing_tracks += 1

            db.upsert_track_ingestion(
                track_id=track_id,
                batch_id=batch_id,
                source_type="local_scan",
                import_method=import_method,
                row_index=idx,
                is_new_track=existing_track_id is None,
            )
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="local_scan",
                status="discovered",
                run_id=run_id,
                batch_id=batch_id,
                method=import_method,
                details={"path": str(path)},
            )
            db.upsert_library_file(
                batch_id=batch_id,
                track_id=track_id,
                path=str(path),
                filename=path.name,
                extension=path.suffix.lower().lstrip("."),
                size_bytes=int(path.stat().st_size),
                duration_ms=duration_ms,
                bitrate_kbps=bitrate_kbps,
                sample_rate=sample_rate,
                bit_depth=bit_depth,
                artist_tag=artist,
                title_tag=title,
                album_tag=album,
                source_type="local_scan",
                status="indexed",
            )
            db.update_track_status(track_id, status="imported", file_path=str(path))
            db.upsert_asset(
                run_id=run_id,
                track_id=track_id,
                asset_type="library_file",
                path=str(path),
                status="indexed",
                size_bytes=int(path.stat().st_size),
                extra={
                    "duration_ms": duration_ms,
                    "bitrate_kbps": bitrate_kbps,
                    "sample_rate": sample_rate,
                    "bit_depth": bit_depth,
                },
            )
            db.add_event(
                run_id=run_id,
                track_id=track_id,
                stage="local_scan",
                status="indexed",
                message=search_string,
                file_path=str(path),
            )
            indexed += 1

        if args.fingerprint and indexed > 0:
            from intellidj_fingerprint import _fpcalc_path, fingerprint_directory

            exe = _fpcalc_path(config)
            if exe:
                acoustid_key = coalesce(
                    args.acoustid_api_key,
                    os.getenv("ACOUSTID_API_KEY"),
                    cfg_get(config, "fingerprint.acoustid_api_key") or None,
                )
                fp_run_id = db.start_run(
                    script_name="scan_local_music.py:fingerprint",
                    input_path=str(input_dir),
                    options={"label": label, "batch_id": batch_id},
                )
                fp_stats = fingerprint_directory(
                    input_dir,
                    db,
                    run_id=fp_run_id,
                    batch_id=batch_id,
                    acoustid_api_key=acoustid_key,
                    fpcalc=exe,
                )
                db.finish_run(
                    fp_run_id,
                    status="success",
                    total_count=fp_stats["computed"] + fp_stats["skipped"] + fp_stats["failed"],
                    success_count=fp_stats["computed"],
                    skipped_count=fp_stats["skipped"],
                    error_count=fp_stats["failed"],
                )
                print(
                    f"Fingerprinting done. computed={fp_stats['computed']}, "
                    f"skipped={fp_stats['skipped']}, failed={fp_stats['failed']}"
                )
            else:
                print(
                    "WARNING: --fingerprint requested but fpcalc not found. "
                    "Install Chromaprint (brew install chromaprint).",
                    file=sys.stderr,
                )
    except Exception:
        pipeline_status = "error"
        errors += 1
        raise
    finally:
        db.finish_run(
            run_id=run_id,
            status=pipeline_status,
            total_count=len(files),
            success_count=indexed,
            skipped_count=0,
            error_count=errors,
            notes=f"batch_id={batch_id}; label={label}; new_tracks={new_tracks}; existing_tracks={existing_tracks}",
        )
        db.close()

    print(
        f"Done. indexed={indexed}, errors={errors}, "
        f"new_tracks={new_tracks}, existing_tracks={existing_tracks}, batch_id={batch_id}, label={label}"
    )


if __name__ == "__main__":
    setup_script_logging(__file__)
    load_env_file()
    main()

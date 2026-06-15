#!/usr/bin/env python3
"""
Chromaprint + AcoustID fingerprinting utilities for IntelliDJ.

System requirement:
    fpcalc binary must be on PATH.
    macOS:  brew install chromaprint
    Linux:  apt install libchromaprint-tools

Optional Python dependency for AcoustID cloud lookup:
    pip install pyacoustid
    Requires an API key from https://acoustid.org/login

Standalone usage:
    python intellidj_fingerprint.py --input-dir ~/Music/DJ/library --db-path intellidj.db
    python intellidj_fingerprint.py --input-dir ~/Music/DJ/inbox --label my-batch --dry-run
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import acoustid  # type: ignore

    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a", ".ogg", ".opus"}


def _fpcalc_path(config: Optional[dict] = None) -> Optional[str]:
    if config:
        custom = (config.get("fingerprint") or {}).get("fpcalc_path") or ""
        if custom:
            return str(Path(custom).expanduser())
    return shutil.which("fpcalc")


def fingerprint_file(path: Path, *, fpcalc: Optional[str] = None) -> tuple[Optional[str], Optional[float]]:
    """
    Run fpcalc on a single audio file.

    Returns (fingerprint_string, duration_sec) on success.
    Returns (None, None) on any failure.
    Raises RuntimeError if fpcalc binary cannot be found at all.
    """
    exe = fpcalc or shutil.which("fpcalc")
    if not exe:
        raise RuntimeError(
            "fpcalc not found. Install Chromaprint:\n"
            "  macOS:  brew install chromaprint\n"
            "  Linux:  apt install libchromaprint-tools"
        )
    try:
        result = subprocess.run(
            [exe, "-raw", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None, None
        duration_sec: Optional[float] = None
        fingerprint: Optional[str] = None
        for line in result.stdout.strip().splitlines():
            if line.startswith("DURATION="):
                try:
                    duration_sec = float(line.split("=", 1)[1])
                except ValueError:
                    pass
            elif line.startswith("FINGERPRINT="):
                fingerprint = line.split("=", 1)[1].strip()
        return fingerprint, duration_sec
    except subprocess.TimeoutExpired:
        return None, None
    except Exception:
        return None, None


def lookup_acoustid(
    fingerprint: str,
    duration_sec: float,
    api_key: str,
) -> Optional[dict[str, Any]]:
    """
    Query the AcoustID web service with a Chromaprint fingerprint.

    Returns a dict {acoustid_id, score, title, artist} for the best match,
    or None if no match or the pyacoustid package is not installed.
    """
    if not ACOUSTID_AVAILABLE or not api_key:
        return None
    try:
        results = acoustid.lookup(
            api_key,
            fingerprint,
            int(duration_sec),
            meta="recordings",
        )
        for score, acoustid_id, title, artist in acoustid.parse_lookup_result(results):
            return {
                "acoustid_id": acoustid_id,
                "score": float(score),
                "title": title,
                "artist": artist,
            }
    except Exception:
        return None
    return None


def is_in_library(
    path: Path,
    db: Any,
    *,
    fpcalc: Optional[str] = None,
    duration_tolerance_sec: float = 5.0,
) -> tuple[bool, Optional[str]]:
    """
    Fingerprint the given file and check if it already exists in the library DB.

    Returns:
        (True, "/path/to/existing/file") if a matching fingerprint is found
        (False, None) if not found or fingerprinting fails
    """
    fp, duration = fingerprint_file(path, fpcalc=fpcalc)
    if not fp or duration is None:
        return False, None
    existing = db.find_matching_fingerprint(fp, duration, duration_tolerance_sec=duration_tolerance_sec)
    if existing:
        return True, str(existing["path"])
    return False, None


def fingerprint_directory(
    input_dir: Path,
    db: Any,
    *,
    run_id: int,
    batch_id: Optional[int] = None,
    limit: Optional[int] = None,
    acoustid_api_key: Optional[str] = None,
    fpcalc: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Fingerprint all unfingerprinted library_files rows whose path is under input_dir.

    Writes results to library_fingerprints table.
    Returns summary dict: {computed, skipped, failed}.
    """
    files = db.get_unfingerprinted_library_files(batch_id=batch_id, limit=limit)
    input_dir_resolved = Path(input_dir).expanduser().resolve()

    stats = {"computed": 0, "skipped": 0, "failed": 0}

    for row in files:
        file_path = Path(str(row["path"])).expanduser().resolve()
        # Only process files under the given input directory
        try:
            file_path.relative_to(input_dir_resolved)
        except ValueError:
            stats["skipped"] += 1
            continue

        if not file_path.exists():
            stats["skipped"] += 1
            continue

        if dry_run:
            print(f"  [dry-run] would fingerprint: {file_path}")
            stats["skipped"] += 1
            continue

        fp, duration = fingerprint_file(file_path, fpcalc=fpcalc)
        track_id = row["track_id"] if row["track_id"] else None

        if fp and duration is not None:
            acoustid_result = lookup_acoustid(fp, duration, acoustid_api_key or "") if acoustid_api_key else None
            db.upsert_fingerprint(
                library_file_id=int(row["id"]),
                track_id=track_id,
                fpcalc_fingerprint=fp,
                fpcalc_duration_sec=duration,
                acoustid_id=acoustid_result["acoustid_id"] if acoustid_result else None,
                acoustid_score=acoustid_result["score"] if acoustid_result else None,
                acoustid_title=acoustid_result["title"] if acoustid_result else None,
                acoustid_artist=acoustid_result["artist"] if acoustid_result else None,
                status="computed",
            )
            if track_id:
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="fingerprint",
                    status="computed",
                    run_id=run_id,
                    batch_id=batch_id,
                    details={"fpcalc_duration_sec": duration},
                )
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="fingerprint",
                    status="computed",
                    message=f"Fingerprinted: {file_path.name}",
                    file_path=str(file_path),
                )
            stats["computed"] += 1
            print(f"  fingerprinted: {file_path.name}")
        else:
            db.upsert_fingerprint(
                library_file_id=int(row["id"]),
                track_id=track_id,
                fpcalc_fingerprint=None,
                fpcalc_duration_sec=None,
                status="failed",
            )
            if track_id:
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="fingerprint",
                    status="failed",
                    run_id=run_id,
                    batch_id=batch_id,
                )
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="fingerprint",
                    status="failed",
                    message=f"fpcalc failed: {file_path.name}",
                    file_path=str(file_path),
                )
            stats["failed"] += 1
            print(f"  failed:        {file_path.name}", file=sys.stderr)

    return stats


def main() -> None:
    from intellidj_common import (
        add_common_config_arg,
        add_common_selector_args,
        cfg_get,
        coalesce,
        load_env_file,
        load_project_config,
        resolve_db_path,
        resolve_inbox_dir,
        resolve_scope,
        setup_script_logging,
    )
    from intellidj_db import IntelliDJDB

    setup_script_logging(__file__)
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Compute Chromaprint fingerprints for local library files and store in DB."
    )
    add_common_config_arg(parser)
    add_common_selector_args(parser, include_scope=False)
    parser.add_argument("--input-dir", default=None, help="Directory to fingerprint (default: library_dir from config)")
    parser.add_argument("--db-path", default=None, help="Path to intellidj.db")
    parser.add_argument("--limit", type=int, default=None, help="Max number of files to fingerprint")
    parser.add_argument("--acoustid-api-key", default=None, help="AcoustID API key (or set ACOUSTID_API_KEY env var)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be fingerprinted without writing to DB")
    args = parser.parse_args()

    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    label = args.label or cfg_get(config, "pipeline.label") or None

    input_dir_raw = coalesce(
        args.input_dir,
        cfg_get(config, "paths.library_dir"),
        os.path.expanduser("~/Music/DJ/library"),
    )
    input_dir = Path(str(input_dir_raw)).expanduser().resolve()

    if not input_dir.exists():
        print(f"ERROR: input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    acoustid_key = coalesce(
        args.acoustid_api_key,
        os.getenv("ACOUSTID_API_KEY"),
        cfg_get(config, "fingerprint.acoustid_api_key") or None,
    )

    exe = _fpcalc_path(config)
    if not exe:
        print(
            "ERROR: fpcalc not found. Install Chromaprint:\n"
            "  macOS:  brew install chromaprint\n"
            "  Linux:  apt install libchromaprint-tools",
            file=sys.stderr,
        )
        sys.exit(1)

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="intellidj_fingerprint.py",
        input_path=str(input_dir),
        options={"label": label, "batch_id": args.batch_id, "dry_run": args.dry_run},
    )

    batch_id = args.batch_id
    if batch_id is None and label:
        latest = db.get_latest_batch(label=label)
        if latest:
            batch_id = int(latest["id"])

    print(f"Fingerprinting files under: {input_dir}")
    if args.dry_run:
        print("(dry-run mode — no DB writes)")

    try:
        stats = fingerprint_directory(
            input_dir,
            db,
            run_id=run_id,
            batch_id=batch_id,
            limit=args.limit,
            acoustid_api_key=acoustid_key,
            fpcalc=exe,
            dry_run=args.dry_run,
        )
        db.finish_run(
            run_id,
            status="success",
            total_count=stats["computed"] + stats["skipped"] + stats["failed"],
            success_count=stats["computed"],
            skipped_count=stats["skipped"],
            error_count=stats["failed"],
        )
        print(
            f"\nDone. computed={stats['computed']}, "
            f"skipped={stats['skipped']}, failed={stats['failed']}"
        )
    except Exception as exc:
        db.finish_run(run_id, status="error", notes=str(exc))
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()

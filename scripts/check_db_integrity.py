#!/usr/bin/env python3
"""
scripts/check_db_integrity.py — DB / filesystem integrity checker.

Compares DB records that reference file paths against the actual filesystem and
reports any inconsistencies (orphan DB records, completed downloads whose file
is gone, tracks with no file at all).

Usage:
    python scripts/check_db_integrity.py [--fix] [--scan-dirs DIR ...]

Exit code: 0 if no issues, 1 if issues found (regardless of --fix).
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

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
from intellidj_db import IntelliDJDB, utc_now

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a"}


@dataclass
class CheckResult:
    name: str
    description: str
    total_checked: int = 0
    issues: list[dict] = field(default_factory=list)
    fixed: int = 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_library_files(db: IntelliDJDB, *, fix: bool) -> CheckResult:
    """library_files rows whose path no longer exists on disk."""
    result = CheckResult(
        name="library_files",
        description="Audio files tracked in library_files that are missing from disk",
    )
    rows = db.conn.execute(
        "SELECT id, path, artist_tag, title_tag, status FROM library_files WHERE status != 'missing'"
    ).fetchall()
    result.total_checked = len(rows)

    missing_ids = []
    for row in rows:
        if not Path(row["path"]).exists():
            result.issues.append({
                "id": row["id"],
                "path": row["path"],
                "artist": row["artist_tag"],
                "title": row["title_tag"],
                "current_status": row["status"],
            })
            missing_ids.append(row["id"])

    if fix and missing_ids:
        now = utc_now()
        db.conn.executemany(
            "UPDATE library_files SET status = 'missing', last_seen_at = ? WHERE id = ?",
            [(now, rid) for rid in missing_ids],
        )
        db.conn.commit()
        result.fixed = len(missing_ids)

    return result


def check_assets(db: IntelliDJDB, *, fix: bool) -> CheckResult:
    """assets rows (type=library_file) whose path no longer exists on disk."""
    result = CheckResult(
        name="assets",
        description="Asset records (type=library_file) that are missing from disk",
    )
    rows = db.conn.execute(
        "SELECT id, path, track_id, status FROM assets WHERE asset_type = 'library_file' AND status != 'missing'"
    ).fetchall()
    result.total_checked = len(rows)

    missing_ids = []
    for row in rows:
        if not Path(row["path"]).exists():
            result.issues.append({
                "id": row["id"],
                "path": row["path"],
                "track_id": row["track_id"],
                "current_status": row["status"],
            })
            missing_ids.append(row["id"])

    if fix and missing_ids:
        now = utc_now()
        db.conn.executemany(
            "UPDATE assets SET status = 'missing', last_seen_at = ? WHERE id = ?",
            [(now, rid) for rid in missing_ids],
        )
        db.conn.commit()
        result.fixed = len(missing_ids)

    return result


def check_completed_downloads(db: IntelliDJDB, *, fix: bool) -> CheckResult:
    """downloads marked completed whose download_path no longer exists on disk."""
    result = CheckResult(
        name="completed_downloads",
        description="Completed downloads whose file is no longer on disk",
    )
    rows = db.conn.execute(
        """
        SELECT d.id, d.download_path, d.search_string, d.retry_count, d.max_retries,
               t.artist, t.title
        FROM downloads d
        LEFT JOIN tracks t ON t.id = d.track_id
        WHERE d.status = 'completed'
          AND d.download_path IS NOT NULL
          AND d.download_path != ''
        """
    ).fetchall()
    result.total_checked = len(rows)

    missing_ids = []
    for row in rows:
        if not Path(row["download_path"]).exists():
            result.issues.append({
                "id": row["id"],
                "search_string": row["search_string"],
                "download_path": row["download_path"],
                "artist": row["artist"],
                "title": row["title"],
                "retry_count": row["retry_count"],
                "max_retries": row["max_retries"],
            })
            missing_ids.append(row["id"])

    if fix and missing_ids:
        now = utc_now()
        db.conn.executemany(
            """
            UPDATE downloads
               SET status = 'pending',
                   retry_count = retry_count + 1,
                   last_error  = 'download_path missing from disk (integrity check)',
                   updated_at  = ?
             WHERE id = ?
            """,
            [(now, did) for did in missing_ids],
        )
        db.conn.commit()
        result.fixed = len(missing_ids)

    return result


def check_tracks_without_files(db: IntelliDJDB) -> CheckResult:
    """Tracks in DB with no library_files row linked (informational, no fix)."""
    result = CheckResult(
        name="tracks_without_files",
        description="Tracks in DB with no library_files record (not yet downloaded or scanned)",
    )
    rows = db.conn.execute(
        """
        SELECT t.id, t.artist, t.title, t.source_search_string
        FROM tracks t
        WHERE NOT EXISTS (
            SELECT 1 FROM library_files lf WHERE lf.track_id = t.id
        )
        ORDER BY t.id
        """
    ).fetchall()
    result.total_checked = db.conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]

    for row in rows:
        result.issues.append({
            "id": row["id"],
            "artist": row["artist"],
            "title": row["title"],
            "search_string": row["source_search_string"],
        })

    return result


def check_tracks_file_path(db: IntelliDJDB, *, fix: bool) -> CheckResult:
    """tracks.file_path entries that no longer exist on disk."""
    result = CheckResult(
        name="tracks_file_path",
        description="Tracks whose file_path no longer exists on disk",
    )
    rows = db.conn.execute(
        """
        SELECT id, artist, title, status, file_path FROM tracks
        WHERE status NOT IN ('imported', 'not_found', 'file_missing')
          AND file_path IS NOT NULL
        """
    ).fetchall()
    result.total_checked = len(rows)

    missing_ids = []
    for row in rows:
        if not Path(row["file_path"]).exists():
            result.issues.append({
                "id": row["id"],
                "artist": row["artist"],
                "title": row["title"],
                "path": row["file_path"],
                "current_status": row["status"],
            })
            missing_ids.append(row["id"])

    if fix and missing_ids:
        db.conn.executemany(
            "UPDATE tracks SET status = 'file_missing' WHERE id = ?",
            [(mid,) for mid in missing_ids],
        )
        db.conn.commit()
        result.fixed = len(missing_ids)

    return result


def check_untracked_files(scan_dirs: list[Path]) -> CheckResult:
    """Audio files on disk in scan_dirs that are not in library_files."""
    result = CheckResult(
        name="untracked_files",
        description="Audio files on disk not tracked in library_files",
    )
    # We can't run the DB check here efficiently without loading all paths,
    # so we return the raw files and let the caller cross-reference.
    # This check is purely informational — caller handles DB lookup.
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for ext in AUDIO_EXTENSIONS:
            for f in scan_dir.rglob(f"*{ext}"):
                result.issues.append({"path": str(f)})
            for f in scan_dir.rglob(f"*{ext.upper()}"):
                result.issues.append({"path": str(f)})
    return result


def check_untracked_files_vs_db(db: IntelliDJDB, scan_dirs: list[Path]) -> CheckResult:
    """Audio files on disk in scan_dirs that are not in library_files."""
    result = CheckResult(
        name="untracked_files",
        description="Audio files on disk not tracked in library_files",
    )
    if not scan_dirs:
        return result

    known_paths: set[str] = {
        row["path"]
        for row in db.conn.execute("SELECT path FROM library_files").fetchall()
    }

    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for ext in AUDIO_EXTENSIONS:
            for f in list(scan_dir.rglob(f"*{ext}")) + list(scan_dir.rglob(f"*{ext.upper()}")):
                path_str = str(f.resolve())
                if path_str not in known_paths:
                    result.issues.append({"path": path_str})

    result.total_checked = result.issue_count + len(known_paths)
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_SEP = "─" * 60


def _status_icon(count: int) -> str:
    return "✓" if count == 0 else "✗"


def print_result(result: CheckResult, *, verbose: bool = False) -> None:
    icon = _status_icon(result.issue_count)
    fixed_note = f" ({result.fixed} fixed)" if result.fixed else ""
    print(f"\n{icon} {result.name}: {result.issue_count} issue(s) / {result.total_checked} checked{fixed_note}")
    print(f"  {result.description}")
    if result.issues:
        limit = 10
        for item in result.issues[:limit]:
            if "path" in item and "artist" in item:
                label = f"{item.get('artist') or '?'} — {item.get('title') or '?'}"
                print(f"    [{item['id']}] {label}")
                print(f"         {item['path']}")
            elif "path" in item:
                print(f"    {item['path']}")
            elif "search_string" in item:
                label = item.get("search_string") or f"{item.get('artist')} — {item.get('title')}"
                print(f"    [{item['id']}] {label}")
                print(f"         {item.get('download_path', '')}")
            else:
                label = f"{item.get('artist') or '?'} — {item.get('title') or '?'}"
                print(f"    [{item['id']}] {label}")
        if result.issue_count > limit:
            print(f"    ... and {result.issue_count - limit} more")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check integrity between the IntelliDJ database and the local filesystem."
    )
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path (default: INTELLIDJ_DB_PATH or ./intellidj.db)")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply non-destructive fixes: mark missing library_files/assets as 'missing', "
             "reset completed downloads with no file back to 'pending', "
             "set tracks.status='file_missing' for stale file_path entries.",
    )
    parser.add_argument(
        "--scan-dirs",
        nargs="+",
        metavar="DIR",
        default=[],
        help="Additional directories to scan for untracked audio files.",
    )
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)

    # Collect dirs to scan for untracked files
    scan_dirs: list[Path] = []
    for raw in args.scan_dirs:
        p = Path(raw).expanduser().resolve()
        scan_dirs.append(p)
    # Also pick up configured dirs if no explicit scan-dirs given
    if not scan_dirs:
        for key in ("paths.library_dir", "paths.inbox_dir", "paths.scan_dir"):
            val = cfg_get(config, key)
            if val:
                p = Path(str(val)).expanduser().resolve()
                if p.is_dir():
                    scan_dirs.append(p)

    db = IntelliDJDB(db_path)

    print(f"IntelliDJ DB Integrity Check")
    print(f"DB: {db_path}")
    if args.fix:
        print("Mode: FIX (non-destructive fixes will be applied)")
    else:
        print("Mode: dry-run (use --fix to apply fixes)")
    print(_SEP)

    results: list[CheckResult] = []

    r1 = check_library_files(db, fix=args.fix)
    results.append(r1)
    print_result(r1)

    r2 = check_assets(db, fix=args.fix)
    results.append(r2)
    print_result(r2)

    r3 = check_completed_downloads(db, fix=args.fix)
    results.append(r3)
    print_result(r3)

    r4 = check_tracks_without_files(db)
    results.append(r4)
    print_result(r4)

    r5 = check_tracks_file_path(db, fix=args.fix)
    results.append(r5)
    print_result(r5)

    if scan_dirs:
        r5 = check_untracked_files_vs_db(db, scan_dirs)
        results.append(r5)
        print_result(r5)

    db.close()

    print(f"\n{_SEP}")
    total_issues = sum(r.issue_count for r in results)
    total_fixed = sum(r.fixed for r in results)
    if total_issues == 0:
        print("All checks passed — database is consistent with the filesystem.")
        return 0

    print(f"Found {total_issues} issue(s) across {len(results)} checks.", end="")
    if total_fixed:
        print(f" Fixed {total_fixed}.")
    else:
        print(" Run with --fix to apply non-destructive fixes.")

    if r3.issue_count and not args.fix:
        print(
            "\nNote: completed downloads with missing files can be reset to 'pending'\n"
            "with --fix, allowing them to be retried by dj_to_slskd_pipeline.py.\n"
            "You may also need to reset track_stage_state for 'slskd_queue' manually\n"
            "if the pipeline skips those tracks."
        )

    return 1


if __name__ == "__main__":
    setup_script_logging(__file__)
    load_env_file()
    sys.exit(main())

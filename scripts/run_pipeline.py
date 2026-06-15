#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_common import (
    add_common_config_arg,
    cfg_get,
    coalesce,
    load_project_config,
    resolve_db_path,
    resolve_inbox_dir,
    resolve_scope,
    setup_script_logging,
)


def run_step(name: str, cmd: list[str], cwd: Path) -> dict:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )
    finished = time.time()
    return {
        "name": name,
        "cmd": cmd,
        "exit_code": proc.returncode,
        "duration_sec": round(finished - started, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run IntelliDJ pipeline end-to-end with DB-first orchestration")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path")
    parser.add_argument("--csv", default=None, help="Optional Exportify CSV input for ingest step")
    parser.add_argument("--scan-dir", default=None, help="Optional local folder scan step before CSV import")
    parser.add_argument("--downloads-dir", default=None)
    parser.add_argument("--label", default=None, help="Optional shared batch label")
    parser.add_argument("--scope", choices=["new", "existing", "all"], default=None)
    parser.add_argument("--dry-run", action="store_true", help="Propagate dry-run to all supported steps")
    parser.add_argument("--skip-scan", action="store_true")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--run-beets", action="store_true")
    parser.add_argument("--beets-config", default=None)
    parser.add_argument("--run-cover-art", action="store_true", help="Run beets fetchart+embedart stage")
    parser.add_argument("--cover-art-force", action="store_true", help="Force redownload artwork in cover-art stage")
    parser.add_argument("--skip-cover-art-embed", action="store_true", help="Fetch artwork only; skip embedart")
    parser.add_argument("--run-duplicates", action="store_true")
    parser.add_argument("--library-dir", default=None)
    parser.add_argument("--report-json", default="pipeline_report.json", help="Write pipeline execution report")
    # New flags
    parser.add_argument("--run-fingerprint", action="store_true", help="Fingerprint scanned files after local scan")
    parser.add_argument("--check-library", action="store_true", help="Check local library during CSV import")
    parser.add_argument("--skip-if-in-library", action="store_true", help="Skip downloads for tracks already in library")
    parser.add_argument("--inbox-dir", default=None, help="Staging inbox directory between downloads and beets")
    parser.add_argument("--run-move-to-inbox", action="store_true", help="Move downloads to inbox before enriching")
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    scope = resolve_scope(args.scope, config, default="new")
    downloads_dir = str(coalesce(args.downloads_dir, cfg_get(config, "paths.downloads_dir"), os.path.expanduser("~/Soulseek/downloads/complete")))
    inbox_dir = resolve_inbox_dir(args.inbox_dir, config)
    beets_config = str(coalesce(args.beets_config, cfg_get(config, "paths.beets_config"), os.path.expanduser("~/.config/beets/config.yaml")))
    library_dir = str(coalesce(args.library_dir, cfg_get(config, "paths.library_dir"), os.path.expanduser("~/Music/DJ/library")))
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    # The effective directory for enrichment and beets import
    effective_process_dir = inbox_dir if args.run_move_to_inbox else downloads_dir

    repo_root = Path(__file__).resolve().parents[1]
    py = sys.executable
    results: list[dict] = []

    if args.scan_dir and not args.skip_scan:
        cmd = [
            py,
            "scripts/scan_local_music.py",
            "--input-dir",
            args.scan_dir,
            "--db-path",
            db_path,
        ]
        if label:
            cmd += ["--label", label]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.run_fingerprint and not args.dry_run:
            cmd.append("--fingerprint")
        results.append(run_step("scan_local_music", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("scan_local_music step failed")

    if args.run_fingerprint and not args.scan_dir and not args.dry_run:
        # Standalone fingerprint step (no scan, just fingerprint existing library files)
        cmd = [
            py,
            "intellidj_fingerprint.py",
            "--input-dir",
            library_dir,
            "--db-path",
            db_path,
        ]
        if label:
            cmd += ["--label", label]
        results.append(run_step("fingerprint_library", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("fingerprint_library step failed")

    if args.csv and not args.skip_import:
        cmd = [
            py,
            "csv_to_dj_pipeline.py",
            "--input",
            args.csv,
            "--db-path",
            db_path,
        ]
        if label:
            cmd += ["--label", label]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.check_library:
            cmd.append("--check-library")
        results.append(run_step("import_exportify_csv", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("import_exportify_csv step failed")

    if not args.skip_download:
        cmd = [
            py,
            "dj_to_slskd_pipeline.py",
            "--db-path",
            db_path,
            "--scope",
            scope,
        ]
        if label:
            cmd += ["--label", label]
        if args.dry_run:
            cmd.append("--dry-run")
        if args.skip_if_in_library:
            cmd.append("--skip-if-in-library")
        results.append(run_step("queue_slskd_downloads", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("queue_slskd_downloads step failed")

    if args.run_move_to_inbox and not args.dry_run:
        cmd = [
            py,
            "scripts/move_downloads_to_inbox.py",
            "--downloads-dir",
            downloads_dir,
            "--inbox-dir",
            inbox_dir,
            "--db-path",
            db_path,
        ]
        if label:
            cmd += ["--label", label]
        results.append(run_step("move_to_inbox", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("move_to_inbox step failed")

    if not args.skip_enrich:
        cmd = [
            py,
            "scripts/enrich_tags_from_spotify_csv.py",
            "--db-path",
            db_path,
            "--input-dir",
            effective_process_dir,
            "--scope",
            scope,
        ]
        if label:
            cmd += ["--label", label]
        if args.dry_run:
            cmd.append("--dry-run")
        results.append(run_step("enrich_tags", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("enrich_tags step failed")

    if args.run_beets:
        cmd = [
            py,
            "scripts/run_beets_import.py",
            "--db-path",
            db_path,
            "--beets-config",
            beets_config,
            "--input-dir",
            effective_process_dir,
            "--scope",
            scope,
        ]
        if label:
            cmd += ["--label", label]
        if args.dry_run:
            cmd.append("--dry-run")
        results.append(run_step("beets_import", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("beets_import step failed")

    if args.run_cover_art:
        cmd = [
            py,
            "scripts/run_cover_art.py",
            "--db-path",
            db_path,
            "--scope",
            scope,
            "--beets-config",
            beets_config,
        ]
        if label:
            cmd += ["--label", label]
        if args.cover_art_force:
            cmd.append("--force")
        if args.skip_cover_art_embed:
            cmd.append("--skip-embed")
        results.append(run_step("cover_art", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("cover_art step failed")

    if args.run_duplicates:
        cmd = [
            py,
            "scripts/find_duplicate_tracks.py",
            "--source-dir",
            library_dir,
            "--action",
            "report",
            "--db-path",
            db_path,
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        results.append(run_step("find_duplicates", cmd, repo_root))
        if results[-1]["exit_code"] != 0:
            _write_report(args.report_json, results)
            raise SystemExit("find_duplicates step failed")

    _write_report(args.report_json, results)
    for step in results:
        print(f"[{step['name']}] exit={step['exit_code']} duration={step['duration_sec']}s")
    print(f"Pipeline completed. Report: {args.report_json}")


def _write_report(path: str, results: list[dict]) -> None:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "steps": results,
        "ok": all(step["exit_code"] == 0 for step in results),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    setup_script_logging(__file__)
    main()

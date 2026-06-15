#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from intellidj_db import IntelliDJDB
from intellidj_common import (
    add_common_config_arg,
    add_common_selector_args,
    cfg_get,
    coalesce,
    load_project_config,
    resolve_db_path,
    resolve_scope,
    setup_script_logging,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run beets import and record lifecycle stage state")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path")
    parser.add_argument("--beets-config", default=None)
    parser.add_argument("--input-dir", default=None)
    add_common_selector_args(parser, include_scope=True)
    parser.add_argument("--dry-run", action="store_true", help="Use beets preview mode (-p)")
    parser.add_argument("--import-method", default=None)
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    beets_config = str(coalesce(args.beets_config, cfg_get(config, "paths.beets_config"), os.path.expanduser("~/.config/beets/config.yaml")))
    input_dir = str(coalesce(args.input_dir, cfg_get(config, "paths.downloads_dir"), os.path.expanduser("~/Soulseek/downloads/complete")))
    scope = resolve_scope(args.scope, config, default="new")
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    import_method = str(coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "beets_import"))

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="run_beets_import.py",
        input_path=input_dir,
        options={
            "scope": scope,
            "batch_id": args.batch_id,
            "label": label,
            "dry_run": args.dry_run,
            "beets_config": beets_config,
            "import_method": import_method,
        },
    )
    pipeline_status = "success"

    cmd = ["beet", "-c", beets_config, "import", "-s", input_dir]
    if args.dry_run:
        cmd.insert(-1, "-p")

    try:
        proc = subprocess.run(cmd, text=True)
        if proc.returncode != 0:
            pipeline_status = "error"
            raise SystemExit(proc.returncode)

        tracks = db.get_tracks_by_scope(
            scope=scope,
            batch_id=args.batch_id,
            label=label,
            source_type="exportify_csv",
            require_search_string=False,
        )
        for track in tracks:
            db.upsert_track_stage_state(
                track_id=int(track["id"]),
                stage="beets_import",
                status="import_previewed" if args.dry_run else "imported",
                run_id=run_id,
                batch_id=args.batch_id,
                method=import_method,
                details={"input_dir": input_dir, "beets_config": beets_config},
            )
            if not args.dry_run:
                db.update_track_status(int(track["id"]), status="in_library")

        db.finish_run(
            run_id,
            status="success",
            total_count=len(tracks),
            success_count=len(tracks),
            skipped_count=0,
            error_count=0,
        )
    except Exception:
        db.finish_run(
            run_id,
            status=pipeline_status,
            total_count=0,
            success_count=0,
            skipped_count=0,
            error_count=1,
        )
        raise
    finally:
        db.close()


if __name__ == "__main__":
    setup_script_logging(__file__)
    main()

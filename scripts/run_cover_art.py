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


def run_cmd(cmd: list[str]) -> int:
    proc = subprocess.run(cmd, text=True)
    return int(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run beets fetchart+embedart and record DB stage state")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path")
    parser.add_argument("--beets-config", default=None)
    add_common_selector_args(parser, include_scope=True)
    parser.add_argument("--force", action="store_true", help="Force re-download artwork for albums with existing art")
    parser.add_argument("--skip-embed", action="store_true", help="Only fetch art; do not embed")
    parser.add_argument("--import-method", default=None)
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    beets_config = str(coalesce(args.beets_config, cfg_get(config, "paths.beets_config"), os.path.expanduser("~/.config/beets/config.yaml")))
    scope = resolve_scope(args.scope, config, default="new")
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    force = bool(args.force or bool(cfg_get(config, "cover_art.force", False)))
    skip_embed = bool(args.skip_embed or bool(cfg_get(config, "cover_art.skip_embed", False)))
    import_method = str(coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "beets_cover_art"))

    db = IntelliDJDB(db_path)
    run_id = db.start_run(
        script_name="run_cover_art.py",
        input_path=beets_config,
        options={
            "scope": scope,
            "batch_id": args.batch_id,
            "label": label,
            "force": force,
            "skip_embed": skip_embed,
            "import_method": import_method,
        },
    )
    pipeline_status = "success"

    fetch_cmd = ["beet", "-c", beets_config, "fetchart"]
    if force:
        fetch_cmd.append("-f")
    fetch_cmd.append("-q")

    tracks = db.get_tracks_by_scope(
        scope=scope,
        batch_id=args.batch_id,
        label=label,
        source_type="exportify_csv",
        require_search_string=False,
    )

    try:
        rc = run_cmd(fetch_cmd)
        if rc != 0:
            pipeline_status = "error"
            raise SystemExit(rc)

        if not skip_embed:
            rc = run_cmd(["beet", "-c", beets_config, "embedart", "-y"])
            if rc != 0:
                pipeline_status = "error"
                raise SystemExit(rc)

        status = "art_fetched" if skip_embed else "art_embedded"
        for track in tracks:
            db.upsert_track_stage_state(
                track_id=int(track["id"]),
                stage="cover_art",
                status=status,
                run_id=run_id,
                batch_id=args.batch_id,
                method=import_method,
                details={"beets_config": beets_config, "force": force},
            )
        db.add_event(
            run_id=run_id,
            track_id=None,
            stage="cover_art",
            status=status,
            message=f"fetchart force={force} skip_embed={skip_embed}",
            details={"scope": scope, "batch_id": args.batch_id, "label": label},
        )
        db.finish_run(
            run_id,
            status="success",
            total_count=len(tracks),
            success_count=len(tracks),
            skipped_count=0,
            error_count=0,
        )
        print(f"Done. cover_art status={status} tracks={len(tracks)}")
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

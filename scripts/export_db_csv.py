#!/usr/bin/env python3
import argparse
import csv
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
)


def export_exportify_rows(db: IntelliDJDB, out_path: Path, batch_id: int | None, label: str | None, scope: str) -> int:
    _, rows = db.get_exportify_rows(batch_id=batch_id, label=label, scope=scope)
    if not rows:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Track URI", "Track Name", "Album Name", "Artist Name(s)"])
        return 0
    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def export_tracks(db: IntelliDJDB, out_path: Path, scope: str, batch_id: int | None, label: str | None) -> int:
    rows = db.get_tracks_by_scope(scope=scope, batch_id=batch_id, label=label, source_type="exportify_csv")
    fieldnames = ["id", "artist", "title", "album", "isrc", "duration_ms", "source_search_string", "source_csv"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in fieldnames})
    return len(rows)


def export_candidates(db: IntelliDJDB, out_path: Path, scope: str, batch_id: int | None, label: str | None) -> int:
    rows = db.get_pending_download_queries_v2(scope=scope, batch_id=batch_id, label=label)
    fieldnames = ["track_id", "search_string"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for track_id, search_string in rows:
            writer.writerow({"track_id": track_id, "search_string": search_string})
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export DB datasets to CSV")
    add_common_config_arg(parser)
    parser.add_argument("--db-path", default=None, help="SQLite path (default: INTELLIDJ_DB_PATH or ./intellidj.db)")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument(
        "--dataset",
        choices=["exportify", "tracks", "candidates"],
        default="tracks",
        help="Which dataset to export",
    )
    add_common_selector_args(parser, include_scope=True)
    args = parser.parse_args()
    config = load_project_config(args.config)
    db_path = resolve_db_path(args.db_path, config)
    scope = resolve_scope(args.scope, config, default="all")
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db = IntelliDJDB(db_path)
    try:
        if args.dataset == "exportify":
            count = export_exportify_rows(db, out_path, args.batch_id, label, scope)
        elif args.dataset == "candidates":
            count = export_candidates(db, out_path, scope, args.batch_id, label)
        else:
            count = export_tracks(db, out_path, scope, args.batch_id, label)
    finally:
        db.close()

    print(f"Exported {count} rows to {out_path}")


if __name__ == "__main__":
    main()

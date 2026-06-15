#!/usr/bin/env python3
import argparse
import csv
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
from intellidj_db import IntelliDJDB, make_track_key
from intellidj.tagger import (
    artist_list,
    best_match_with_duration,
    extract_artist_title_from_filename,
    extract_duration_ms,
    extract_isrc,
    extract_row_duration_ms,
    extract_tags,
    generate_keys,
    generate_title_keys,
    normalize,
    normalize_isrc,
    write_tags,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich downloaded audio tags using Spotify metadata from CSV or lifecycle DB")
    add_common_config_arg(parser)
    parser.add_argument(
        "--csv",
        default=None,
        help="(Deprecated) Path to spotify_export.csv. Prefer DB metadata mode (--scope/--label/--batch-id).",
    )
    parser.add_argument("--input-dir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--min-score-title", type=float, default=None)
    parser.add_argument("--duration-tolerance-ms", type=int, default=None)
    parser.add_argument("--no-duration", action="store_true", help="Do not use duration for matching")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--custom-tags", action="store_true", help="Write custom tags like energy/danceability")
    parser.add_argument("--report", help="Write a CSV report for matches and skips")
    parser.add_argument("--no-tags", action="store_true", help="Do not use existing file tags for matching")
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite path for lifecycle tracking (default: INTELLIDJ_DB_PATH or ./intellidj.db)",
    )
    add_common_selector_args(parser, include_scope=True)
    parser.add_argument("--import-method", default=None, help="Method label stored in stage state")
    args = parser.parse_args()
    config = load_project_config(args.config)

    db_path = resolve_db_path(args.db_path, config)
    scope = resolve_scope(args.scope, config, default="new")
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    min_score = float(coalesce(args.min_score, cfg_get(config, "matching.min_score"), 0.86))
    min_score_title = float(coalesce(args.min_score_title, cfg_get(config, "matching.min_score_title"), 0.78))
    duration_tolerance_ms = int(coalesce(args.duration_tolerance_ms, cfg_get(config, "matching.duration_tolerance_ms"), 2000))
    input_dir_value = str(
        coalesce(
            args.input_dir,
            cfg_get(config, "paths.downloads_dir"),
            os.path.expanduser("~/Soulseek/downloads/complete"),
        )
    )
    import_method = str(coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "tag_enrichment"))

    db = IntelliDJDB(db_path)
    csv_path: Path | None = None
    source_label: str | None = None
    metadata_rows: list[dict] = []
    selected_batch_id: int | None = args.batch_id

    if args.csv:
        print("[warn] --csv mode is deprecated; prefer DB metadata mode with --scope/--label/--batch-id.")
        csv_path = Path(args.csv)
        if not csv_path.exists():
            db.close()
            raise SystemExit(f"CSV not found: {csv_path}")
        source_label = str(csv_path)
        with csv_path.open(newline="", encoding="utf-8") as f:
            metadata_rows = list(csv.DictReader(f))
    else:
        selected_batch_id, metadata_rows = db.get_exportify_rows(
            batch_id=args.batch_id,
            label=label,
            scope=scope,
        )
        source_label = f"db:batch={selected_batch_id};scope={scope};label={label or ''}"
        if not metadata_rows:
            db.close()
            raise SystemExit(
                "No metadata rows found in lifecycle DB for the selected scope. Run Step 2 first or pass --csv."
            )

    # Build lookup list
    candidates = []
    title_candidates = []
    isrc_map = {}
    for row in metadata_rows:
        isrc = normalize_isrc(row.get("ISRC") or row.get("isrc"))
        if isrc:
            isrc_map[isrc] = row
        keys = generate_keys(row)
        for k in keys:
            candidates.append((k, row))
        tkeys = generate_title_keys(row)
        for k in tkeys:
            title_candidates.append((k, row))

    input_dir = Path(input_dir_value).expanduser()
    files = []
    for ext in ("*.mp3", "*.flac", "*.wav", "*.aif", "*.aiff"):
        files.extend(input_dir.rglob(ext))

    if args.limit:
        files = files[: args.limit]

    run_id = db.start_run(
        script_name="enrich_tags_from_spotify_csv.py",
        input_path=source_label,
        options={
            "source_mode": "csv" if csv_path else "db",
            "source_label": source_label,
            "scope": scope,
            "label": label,
            "batch_id": selected_batch_id,
            "import_method": import_method,
            "input_dir": str(input_dir),
            "dry_run": args.dry_run,
            "min_score": min_score,
            "min_score_title": min_score_title,
            "duration_tolerance_ms": duration_tolerance_ms,
            "no_duration": args.no_duration,
            "limit": args.limit,
            "custom_tags": args.custom_tags,
            "report": args.report,
            "no_tags": args.no_tags,
            "db_path": db_path,
        },
    )
    pipeline_status = "success"

    matched = 0
    skipped = 0
    errors = 0

    report_rows = []

    try:
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

            file_track_key = make_track_key(
                artist=artist,
                title=title,
                isrc=file_isrc,
                search_string=file_key,
                duration_ms=file_duration_ms,
            )
            file_track_id = db.upsert_track(
                track_key=file_track_key,
                artist=artist,
                title=title,
                isrc=file_isrc,
                duration_ms=file_duration_ms,
                source_search_string=file_key,
                source_csv=source_label,
            )
            try:
                size_bytes = int(path.stat().st_size)
            except Exception:
                size_bytes = None
            db.upsert_asset(
                run_id=run_id,
                track_id=file_track_id,
                asset_type="downloaded_file",
                path=str(path),
                status="seen",
                size_bytes=size_bytes,
            )

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
                    min_score,
                    file_duration_ms,
                    duration_tolerance_ms,
                )
                match_type = "artist_title"
                if not row or score < min_score:
                    row = None

            if not row and title_key:
                row, score, best_key = best_match_with_duration(
                    title_key,
                    title_candidates,
                    min_score_title,
                    file_duration_ms,
                    duration_tolerance_ms,
                )
                match_type = "title_only"
                if not row or score < min_score_title:
                    row = None

            if not row:
                skipped += 1
                db.add_event(
                    run_id=run_id,
                    track_id=file_track_id,
                    stage="tag_enrichment",
                    status="skipped_no_match",
                    message=str(path),
                    details={"file_key": file_key, "title_key": title_key, "score": score},
                    file_path=str(path),
                )
                db.upsert_track_stage_state(
                    track_id=file_track_id,
                    stage="tag_enrichment",
                    status="skipped_no_match",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"file_key": file_key, "title_key": title_key, "score": score, "file": str(path)},
                )
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

            row_artist = row.get("Artist Name(s)", "")
            row_title = row.get("Track Name", "")
            row_album = row.get("Album Name", "")
            row_isrc = normalize_isrc(row.get("ISRC") or row.get("isrc"))
            row_duration_ms = extract_row_duration_ms(row)
            duration_diff_ms = ""
            if file_duration_ms is not None and row_duration_ms is not None:
                duration_diff_ms = str(abs(file_duration_ms - row_duration_ms))

            row_search_string = f"{row_artist} - {row_title}".strip(" -")
            matched_track_key = make_track_key(
                artist=row_artist,
                title=row_title,
                isrc=row_isrc,
                search_string=row_search_string,
                duration_ms=row_duration_ms,
            )
            matched_track_id = db.upsert_track(
                track_key=matched_track_key,
                artist=row_artist,
                title=row_title,
                album=row_album,
                isrc=row_isrc,
                duration_ms=row_duration_ms,
                source_search_string=row_search_string,
                source_csv=source_label,
            )
            db.add_event(
                run_id=run_id,
                track_id=matched_track_id,
                stage="tag_enrichment",
                status="matched",
                message=str(path),
                details={"match_type": match_type, "score": score},
                file_path=str(path),
            )
            db.upsert_track_stage_state(
                track_id=matched_track_id,
                stage="tag_enrichment",
                status="matched",
                run_id=run_id,
                batch_id=selected_batch_id,
                method=import_method,
                details={"match_type": match_type, "score": score, "file": str(path)},
            )

            if args.dry_run:
                print(f"[dry-run] {path.name} -> {row_artist} - {row_title} (score={score:.2f})")
                matched += 1
                db.add_event(
                    run_id=run_id,
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="matched_dry_run",
                    message=str(path),
                    details={"match_type": match_type, "score": score},
                    file_path=str(path),
                )
                db.upsert_track_stage_state(
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="matched_dry_run",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"match_type": match_type, "score": score, "file": str(path)},
                )
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
                    "matched_artist": row_artist,
                    "matched_title": row_title,
                    "matched_album": row_album,
                    "reason": "dry_run",
                })
                continue

            try:
                write_tags(path, row, args.custom_tags)
                matched += 1
                db.add_event(
                    run_id=run_id,
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="tags_written",
                    message=str(path),
                    details={"match_type": match_type, "score": score},
                    file_path=str(path),
                )
                db.upsert_track_stage_state(
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="tags_written",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"match_type": match_type, "score": score, "file": str(path)},
                )
                db.upsert_asset(
                    run_id=run_id,
                    track_id=matched_track_id,
                    asset_type="tagged_file",
                    path=str(path),
                    status="tagged",
                    size_bytes=size_bytes,
                )
                db.update_track_status(
                    matched_track_id, status="tagged", file_path=str(path)
                )
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
                    "matched_artist": row_artist,
                    "matched_title": row_title,
                    "matched_album": row_album,
                    "reason": "written",
                })
            except Exception as exc:
                errors += 1
                print(f"[error] {path.name}: {exc}")
                db.add_event(
                    run_id=run_id,
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="error",
                    message=str(exc),
                    details={"match_type": match_type, "score": score},
                    file_path=str(path),
                )
                db.upsert_track_stage_state(
                    track_id=matched_track_id,
                    stage="tag_enrichment",
                    status="error",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"match_type": match_type, "score": score, "error": str(exc), "file": str(path)},
                )
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
                    "matched_artist": row_artist,
                    "matched_title": row_title,
                    "matched_album": row_album,
                    "reason": f"error:{exc}",
                })
    except Exception:
        pipeline_status = "error"
        raise
    finally:
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

        db.finish_run(
            run_id,
            status=pipeline_status,
            total_count=len(files),
            success_count=matched,
            skipped_count=skipped,
            error_count=errors,
        )
        db.close()

    print(f"\nDone. matched={matched} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    setup_script_logging(__file__)
    main()

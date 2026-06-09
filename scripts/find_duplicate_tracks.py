#!/usr/bin/env python3
# Shim — logic now lives in intellidj.library.dedupe
from intellidj.library.dedupe import (  # noqa: F401
    TrackFile,
    Decision,
    UnionFind,
    AUDIO_EXTENSIONS,
    normalize_text,
    compute_sha256,
    extract_track,
    collect_tracks,
    metadata_key,
    detect_duplicate_groups,
    is_lossless,
    quality_key,
    choose_keeper,
    choose_keeper_with_preference,
    prune_empty_parents,
    unique_destination,
    apply_action,
    export_csv_rows,
    export_json_rows,
)

if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from intellidj.library.dedupe import (
        collect_tracks, detect_duplicate_groups, apply_action,
        export_csv_rows, export_json_rows,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--compare-dir")
    parser.add_argument("--match-mode", choices=["hash", "metadata", "hybrid"], default="hybrid")
    parser.add_argument("--duration-bucket-seconds", type=int, default=2)
    parser.add_argument("--action", choices=["report", "move", "delete"], default="report")
    parser.add_argument("--keep-strategy", choices=["best", "newest", "oldest"], default="best")
    parser.add_argument("--review-dir")
    parser.add_argument("--prefer-origin", choices=["source", "compare"])
    parser.add_argument("--cleanup-empty-dirs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--export-csv")
    parser.add_argument("--export-json")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    compare_dir = Path(args.compare_dir).expanduser().resolve() if args.compare_dir else None
    cross_compare = compare_dir is not None and compare_dir != source_dir

    if args.action == "move" and not args.review_dir:
        raise SystemExit("--review-dir required for --action move")
    if args.prefer_origin and not cross_compare:
        raise SystemExit("--prefer-origin requires --compare-dir")
    if args.action in {"move", "delete"} and not args.dry_run and not args.yes:
        raise SystemExit("Use --yes or --dry-run to confirm destructive action")

    include_hash = args.match_mode in {"hash", "hybrid"}
    tracks = collect_tracks(source_dir, origin="source", include_hash=include_hash)
    if compare_dir and cross_compare:
        tracks.extend(collect_tracks(compare_dir, origin="compare", include_hash=include_hash))

    groups = detect_duplicate_groups(
        tracks, match_mode=args.match_mode,
        duration_bucket_seconds=args.duration_bucket_seconds,
        cross_compare_only=cross_compare,
    )
    print(f"Scanned: {len(tracks)} tracks, {len(groups)} duplicate groups")

    review_dir = Path(args.review_dir).expanduser().resolve() if args.review_dir else None
    decisions = apply_action(
        groups, action=args.action, keep_strategy=args.keep_strategy,
        prefer_origin=args.prefer_origin, review_dir=review_dir,
        prune_roots=[p for p in [source_dir, compare_dir] if p],
        cleanup_empty_dirs=args.cleanup_empty_dirs, dry_run=args.dry_run,
    )
    if args.export_csv:
        export_csv_rows(Path(args.export_csv), decisions)
    if args.export_json:
        export_json_rows(Path(args.export_json), decisions)

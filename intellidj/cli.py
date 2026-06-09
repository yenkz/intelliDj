import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from typing_extensions import Annotated

app = typer.Typer(
    name="intellidj",
    help="DJ music download and library management toolkit.",
    no_args_is_help=True,
    add_completion=True,
)

# Shared state populated by the global callback
_state: dict = {}


def _configure_logging(quiet: bool, json_output: bool, log_file: Optional[str]) -> None:
    level = logging.WARNING if quiet else logging.INFO
    handlers: list[logging.Handler] = []

    if not json_output:
        try:
            from rich.logging import RichHandler
            handlers.append(RichHandler(show_path=False, markup=False))
        except ImportError:
            handlers.append(logging.StreamHandler(sys.stderr))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers, force=True)


@app.callback()
def _global(
    ctx: typer.Context,
    env: Annotated[Optional[str], typer.Option("--env", help="Path to .env file")] = None,
    host: Annotated[Optional[str], typer.Option("--host", help="slskd host URL (overrides SLSKD_HOST)")] = None,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="slskd API key (overrides SLSKD_API_KEY)")] = None,
    quiet: Annotated[bool, typer.Option("--quiet/--no-quiet", help="Suppress per-item output")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit NDJSON per item")] = False,
    log_file: Annotated[Optional[str], typer.Option("--log-file", help="Append logs to this file")] = None,
) -> None:
    from intellidj.config import resolve_settings
    _configure_logging(quiet, json_output, log_file)
    settings = resolve_settings(env_file=env, host=host, api_key=api_key)
    _state["settings"] = settings
    _state["quiet"] = quiet
    _state["json"] = json_output


# ---------------------------------------------------------------------------
# candidates
# ---------------------------------------------------------------------------

@app.command()
def candidates(
    input_file: Annotated[str, typer.Argument(help="Spotify export CSV")] = "spotify_export.csv",
    output: Annotated[Optional[str], typer.Option("--output", "-o", help="Output candidates CSV")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print search strings to stdout instead of writing file")] = False,
    limit: Annotated[Optional[int], typer.Option("--limit", help="Process only first N rows")] = None,
) -> None:
    """Process a Spotify CSV export into a DJ candidates CSV."""
    from intellidj.pipeline.candidates import (
        build_candidates_dataframe,
        default_output_for_input,
    )
    import pandas as pd

    if not Path(input_file).exists():
        typer.echo(f"Error: input file not found: {input_file}", err=True)
        raise typer.Exit(1)

    df = pd.read_csv(input_file)
    required = ["Artist Name(s)", "Track Name", "Tempo", "Energy", "Danceability", "Genres", "Record Label"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        typer.echo(f"Error: missing columns: {', '.join(missing)}", err=True)
        raise typer.Exit(1)

    df = df.copy()
    for col in ["Artist Name(s)", "Track Name", "Genres", "Record Label"]:
        df[col] = df[col].fillna("").astype(str)
    for col in ["Tempo", "Energy", "Danceability"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    empty = (df["Artist Name(s)"].str.strip() == "") | (df["Track Name"].str.strip() == "")
    df = df[~empty]

    if limit:
        df = df.head(limit)

    out = build_candidates_dataframe(df)

    if dry_run:
        for _, row in out.iterrows():
            typer.echo(row["search_string"])
        return

    output_file = output or default_output_for_input(input_file)
    out.to_csv(output_file, index=False)
    typer.echo(f"Generated {output_file} ({len(out)} tracks)")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

@app.command()
def download(
    csv: Annotated[Optional[str], typer.Option("--csv", help="Candidates CSV with search_string column")] = None,
    list_file: Annotated[Optional[str], typer.Option("--list", help="Text file with one 'Artist - Track' per line")] = None,
    artist: Annotated[Optional[str], typer.Option("--artist", help="Artist name (use with --track)")] = None,
    track: Annotated[Optional[str], typer.Option("--track", help="Track title (use with --artist)")] = None,
    stdin: Annotated[bool, typer.Option("--stdin", help="Read search strings from stdin")] = False,
    limit: Annotated[Optional[int], typer.Option("--limit", help="Process only first N entries")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Search but do not enqueue downloads")] = False,
    search_timeout_ms: Annotated[int, typer.Option("--search-timeout-ms")] = 90000,
    response_limit: Annotated[int, typer.Option("--response-limit")] = 100,
    file_limit: Annotated[int, typer.Option("--file-limit")] = 10000,
    no_stop: Annotated[bool, typer.Option("--no-stop", help="Do not stop searches after queuing")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Print raw slskd API response shapes")] = False,
) -> None:
    """Search slskd and queue downloads from various input sources."""
    import types as _types
    import sys as _sys

    # slskd_api must be importable; inject shim only if missing (tests)
    if "slskd_api" not in _sys.modules:
        pass  # real runtime — let the import fail with a useful message if absent

    from intellidj.pipeline.downloader import (
        _load_env,
        build_api_base,
        build_search_queries,
        execute_search,
        load_search_strings,
        pick_best_file,
        retry_with_backoff,
        DEFAULT_HOST,
        DEFAULT_URL_BASE,
    )
    try:
        import slskd_api as _slskd_api
    except ImportError:
        typer.echo("Error: slskd-api package is not installed.", err=True)
        raise typer.Exit(1)

    _load_env()

    # Validate input source before checking credentials
    sources = [x for x in [csv, list_file, (artist and track), stdin] if x]
    if len(sources) > 1:
        typer.echo("Error: provide only one input source (--csv, --list, --artist+--track, or --stdin).", err=True)
        raise typer.Exit(1)

    queries: list[str] = []

    if csv:
        queries = load_search_strings(csv, limit)
    elif list_file:
        lines = Path(list_file).read_text(encoding="utf-8").splitlines()
        queries = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
        if limit:
            queries = queries[:limit]
    elif artist and track:
        queries = [f"{artist} - {track}"]
    elif stdin:
        queries = [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]
        if limit:
            queries = queries[:limit]
    else:
        if not sys.stdin.isatty():
            queries = [l.strip() for l in sys.stdin if l.strip() and not l.startswith("#")]
            if limit:
                queries = queries[:limit]
        else:
            typer.echo("Error: provide an input source: --csv, --list, --artist+--track, or pipe to stdin.", err=True)
            raise typer.Exit(1)

    if not queries:
        typer.echo("No queries to process.", err=True)
        raise typer.Exit(1)

    settings = _state.get("settings")
    api_key = (settings.slskd_api_key if settings else "") or os.getenv("SLSKD_API_KEY", "")
    host = (settings.slskd_host if settings else "") or os.getenv("SLSKD_HOST", DEFAULT_HOST)

    if not api_key:
        typer.echo("Error: SLSKD_API_KEY is not set. Add it to .env or pass --api-key.", err=True)
        raise typer.Exit(1)

    url_base = os.getenv("SLSKD_URL_BASE", DEFAULT_URL_BASE)
    if url_base.strip() == "/api/v0":
        url_base = ""

    slskd = _slskd_api.SlskdClient(host, api_key, url_base)
    api_base = build_api_base(host)

    # Build a simple args-like namespace for execute_search
    import argparse
    _args = argparse.Namespace(
        search_timeout_ms=search_timeout_ms,
        response_limit=response_limit,
        file_limit=file_limit,
        no_stop=no_stop,
        dry_run=dry_run,
        debug=debug,
    )

    queued = 0
    skipped = 0

    for query in queries:
        search_variants = build_search_queries(query)
        user = None
        file_info = None

        for i, search_text in enumerate(search_variants):
            if i > 0:
                typer.echo(f"[retry] trying simplified query: {search_text}")
            responses = execute_search(slskd, api_base, api_key, search_text, _args, debug=debug)
            user, file_info = pick_best_file(responses, query)
            if user and file_info:
                break

        if not user or not file_info:
            typer.echo(f"[skip] no results for: {query}")
            skipped += 1
            continue

        payload = [{"filename": file_info.get("filename"), "size": file_info.get("size")}]

        if dry_run:
            typer.echo(f"[dry-run] {user}: {payload[0]['filename']}")
            queued += 1
            continue

        ok = retry_with_backoff(
            lambda: slskd.transfers.enqueue(user, payload),
            label="slskd.transfers.enqueue",
        )
        if ok:
            typer.echo(f"[queued] {user}: {payload[0]['filename']}")
            queued += 1
        else:
            typer.echo(f"[skip] enqueue failed for: {query}")
            skipped += 1

    typer.echo(f"\nDone. queued={queued}, skipped={skipped}")
    if queued == 0 and skipped > 0:
        raise typer.Exit(2)


# ---------------------------------------------------------------------------
# enrich
# ---------------------------------------------------------------------------

@app.command()
def enrich(
    csv: Annotated[str, typer.Option("--csv", help="Spotify export CSV")] = "spotify_export.csv",
    input_dir: Annotated[str, typer.Option("--input-dir")] = "~/Soulseek/downloads/complete",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    min_score: Annotated[float, typer.Option("--min-score")] = 0.86,
    min_score_title: Annotated[float, typer.Option("--min-score-title")] = 0.78,
    duration_tolerance_ms: Annotated[int, typer.Option("--duration-tolerance-ms")] = 2000,
    no_duration: Annotated[bool, typer.Option("--no-duration")] = False,
    limit: Annotated[Optional[int], typer.Option("--limit")] = None,
    custom_tags: Annotated[bool, typer.Option("--custom-tags")] = False,
    report: Annotated[Optional[str], typer.Option("--report", help="Write match report to CSV")] = None,
    no_tags: Annotated[bool, typer.Option("--no-tags")] = False,
) -> None:
    """Fuzzy-match downloaded audio files to Spotify CSV and write tags."""
    from intellidj.library.enrich import run_enrich
    import argparse

    _args = argparse.Namespace(
        csv=csv,
        input_dir=input_dir,
        dry_run=dry_run,
        min_score=min_score,
        min_score_title=min_score_title,
        duration_tolerance_ms=duration_tolerance_ms,
        no_duration=no_duration,
        limit=limit,
        custom_tags=custom_tags,
        report=report,
        no_tags=no_tags,
    )
    run_enrich(_args)


# ---------------------------------------------------------------------------
# playlist
# ---------------------------------------------------------------------------

@app.command()
def playlist(
    csv: Annotated[str, typer.Option("--csv")] = "dj_candidates.csv",
    library_dir: Annotated[str, typer.Option("--library-dir")] = "~/Music/DJ/library",
    out_dir: Annotated[str, typer.Option("--out-dir")] = "playlists",
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Export M3U playlists by style from candidates CSV and local library."""
    from intellidj.library.playlist import run_playlist
    import argparse

    _args = argparse.Namespace(
        csv=csv,
        library_dir=library_dir,
        out_dir=out_dir,
        dry_run=dry_run,
    )
    run_playlist(_args)


# ---------------------------------------------------------------------------
# dedupe
# ---------------------------------------------------------------------------

@app.command()
def dedupe(
    source_dir: Annotated[str, typer.Argument(help="Primary directory to scan")],
    compare_dir: Annotated[Optional[str], typer.Option("--compare-dir")] = None,
    match_mode: Annotated[str, typer.Option("--match-mode", help="hash|metadata|hybrid")] = "hybrid",
    duration_bucket_seconds: Annotated[int, typer.Option("--duration-bucket-seconds")] = 2,
    action: Annotated[str, typer.Option("--action", help="report|move|delete")] = "report",
    keep_strategy: Annotated[str, typer.Option("--keep-strategy", help="best|newest|oldest")] = "best",
    review_dir: Annotated[Optional[str], typer.Option("--review-dir")] = None,
    prefer_origin: Annotated[Optional[str], typer.Option("--prefer-origin", help="source|compare")] = None,
    cleanup_empty_dirs: Annotated[bool, typer.Option("--cleanup-empty-dirs")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm destructive actions")] = False,
    export_csv: Annotated[Optional[str], typer.Option("--export-csv")] = None,
    export_json: Annotated[Optional[str], typer.Option("--export-json")] = None,
) -> None:
    """Detect and optionally remove duplicate audio files."""
    from intellidj.library.dedupe import (
        collect_tracks,
        detect_duplicate_groups,
        apply_action,
        export_csv_rows,
        export_json_rows,
    )

    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        typer.echo(f"Error: source directory not found: {src}", err=True)
        raise typer.Exit(1)

    cmp_dir = None
    cross_compare = False
    if compare_dir:
        cmp_dir = Path(compare_dir).expanduser().resolve()
        if not cmp_dir.is_dir():
            typer.echo(f"Error: compare directory not found: {cmp_dir}", err=True)
            raise typer.Exit(1)
        cross_compare = cmp_dir != src

    if action == "move" and not review_dir:
        typer.echo("Error: --review-dir is required when --action move", err=True)
        raise typer.Exit(1)
    if prefer_origin and not cross_compare:
        typer.echo("Error: --prefer-origin requires --compare-dir with a different folder", err=True)
        raise typer.Exit(1)
    if action in {"move", "delete"} and not dry_run and not yes:
        typer.echo("Error: refusing to modify files without --yes or --dry-run", err=True)
        raise typer.Exit(1)

    include_hash = match_mode in {"hash", "hybrid"}
    tracks = collect_tracks(src, origin="source", include_hash=include_hash)
    if cmp_dir and cross_compare:
        tracks.extend(collect_tracks(cmp_dir, origin="compare", include_hash=include_hash))

    if not tracks:
        typer.echo("No supported audio files found.")
        raise typer.Exit(2)

    groups = detect_duplicate_groups(
        tracks,
        match_mode=match_mode,
        duration_bucket_seconds=duration_bucket_seconds,
        cross_compare_only=cross_compare,
    )

    typer.echo(f"Scanned tracks: {len(tracks)}")
    typer.echo(f"Duplicate groups: {len(groups)}")

    if not groups:
        typer.echo("No duplicates detected.")
        return

    rev_dir = Path(review_dir).expanduser().resolve() if review_dir else None
    decisions = apply_action(
        groups,
        action=action,
        keep_strategy=keep_strategy,
        prefer_origin=prefer_origin,
        review_dir=rev_dir,
        prune_roots=[p for p in [src, cmp_dir] if p is not None],
        cleanup_empty_dirs=cleanup_empty_dirs,
        dry_run=dry_run,
    )

    duplicate_count = sum(1 for d in decisions if d.role == "duplicate")
    typer.echo(f"Duplicates found: {duplicate_count}")
    if action == "move":
        n = sum(1 for d in decisions if d.action == "move")
        state = "would move" if dry_run else "moved"
        typer.echo(f"Duplicates {state}: {n}")
    elif action == "delete":
        n = sum(1 for d in decisions if d.action == "delete")
        state = "would delete" if dry_run else "deleted"
        typer.echo(f"Duplicates {state}: {n}")
    else:
        typer.echo("Report-only mode selected; no files modified.")

    if export_csv:
        export_csv_rows(Path(export_csv).expanduser().resolve(), decisions)
        typer.echo(f"CSV report written: {export_csv}")
    if export_json:
        export_json_rows(Path(export_json).expanduser().resolve(), decisions)
        typer.echo(f"JSON report written: {export_json}")


# ---------------------------------------------------------------------------
# run (pipeline orchestrator)
# ---------------------------------------------------------------------------

@app.command()
def run(
    csv: Annotated[str, typer.Option("--csv", help="Input Spotify CSV")] = "spotify_export.csv",
    candidates_file: Annotated[Optional[str], typer.Option("--candidates", help="Override candidates output path")] = None,
    downloads_dir: Annotated[Optional[str], typer.Option("--downloads-dir")] = None,
    library_dir: Annotated[Optional[str], typer.Option("--library-dir")] = None,
    skip_candidates: Annotated[bool, typer.Option("--skip-candidates")] = False,
    skip_download: Annotated[bool, typer.Option("--skip-download")] = False,
    skip_enrich: Annotated[bool, typer.Option("--skip-enrich")] = False,
    skip_playlist: Annotated[bool, typer.Option("--skip-playlist")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    limit: Annotated[Optional[int], typer.Option("--limit")] = None,
) -> None:
    """Run the full pipeline: candidates → download → enrich → playlist."""
    from intellidj.pipeline.candidates import build_candidates_dataframe, default_output_for_input
    import pandas as pd
    import argparse

    settings = _state.get("settings")
    _dl_dir = downloads_dir or (settings.downloads_dir if settings else "~/Soulseek/downloads/complete")
    _lib_dir = library_dir or (settings.library_dir if settings else "~/Music/DJ/library")

    cand_file = candidates_file or default_output_for_input(csv)

    # Step 1: candidates
    if not skip_candidates:
        typer.echo("\n[1/4] Generating candidates CSV...")
        if not Path(csv).exists():
            typer.echo(f"Error: input CSV not found: {csv}", err=True)
            raise typer.Exit(1)
        df = pd.read_csv(csv)
        required = ["Artist Name(s)", "Track Name", "Tempo", "Energy", "Danceability", "Genres", "Record Label"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            typer.echo(f"Error: missing columns: {', '.join(missing)}", err=True)
            raise typer.Exit(1)
        df = df.copy()
        for col in ["Artist Name(s)", "Track Name", "Genres", "Record Label"]:
            df[col] = df[col].fillna("").astype(str)
        for col in ["Tempo", "Energy", "Danceability"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        empty = (df["Artist Name(s)"].str.strip() == "") | (df["Track Name"].str.strip() == "")
        df = df[~empty]
        out = build_candidates_dataframe(df)
        if dry_run:
            typer.echo(f"  [dry-run] would write {cand_file} ({len(out)} tracks)")
        else:
            out.to_csv(cand_file, index=False)
            typer.echo(f"  Generated {cand_file} ({len(out)} tracks)")
    else:
        typer.echo("\n[1/4] Skipping candidates (--skip-candidates)")

    # Step 2: download
    if not skip_download:
        typer.echo("\n[2/4] Queuing downloads...")
        if dry_run:
            typer.echo(f"  [dry-run] would run: intellidj download --csv {cand_file}")
        else:
            _args = argparse.Namespace(
                search_timeout_ms=90000, response_limit=100, file_limit=10000,
                no_stop=False, dry_run=False, debug=False, limit=limit,
            )
            from intellidj.pipeline.downloader import run_downloads
            run_downloads(cand_file, _args)
    else:
        typer.echo("\n[2/4] Skipping download (--skip-download)")

    # Step 3: enrich
    if not skip_enrich:
        typer.echo("\n[3/4] Enriching tags...")
        if dry_run:
            typer.echo(f"  [dry-run] would run: intellidj enrich --csv {csv} --input-dir {_dl_dir}")
        else:
            from intellidj.library.enrich import run_enrich
            _args = argparse.Namespace(
                csv=csv, input_dir=_dl_dir, dry_run=False,
                min_score=0.86, min_score_title=0.78, duration_tolerance_ms=2000,
                no_duration=False, limit=None, custom_tags=False, report=None, no_tags=False,
            )
            run_enrich(_args)
    else:
        typer.echo("\n[3/4] Skipping enrich (--skip-enrich)")

    # Step 4: playlist
    if not skip_playlist:
        typer.echo("\n[4/4] Exporting playlists...")
        if dry_run:
            typer.echo(f"  [dry-run] would run: intellidj playlist --csv {cand_file} --library-dir {_lib_dir}")
        else:
            from intellidj.library.playlist import run_playlist
            _args = argparse.Namespace(
                csv=cand_file, library_dir=_lib_dir, out_dir="playlists", dry_run=False,
            )
            run_playlist(_args)
    else:
        typer.echo("\n[4/4] Skipping playlist (--skip-playlist)")

    typer.echo("\nDone.")

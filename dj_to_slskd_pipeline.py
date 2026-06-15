#!/usr/bin/env python3
import argparse
import csv
import os
import random
import time
import uuid
from typing import Dict, List, Tuple

import typing

from intellidj_common import (
    add_common_config_arg,
    add_common_selector_args,
    cfg_get,
    coalesce,
    load_env_file,
    load_project_config,
    resolve_db_path,
    resolve_scope,
    setup_script_logging,
)
from intellidj_db import IntelliDJDB, make_track_key
from intellidj.slskd import (
    DEFAULT_HOST,
    DEFAULT_URL_BASE,
    build_api_base,
    build_search_queries,
    fetch_search_responses,
    iter_files,
    normalize_responses,
    parse_search_string,
    pick_best_file,
    relevance_score,
    retry_with_backoff,
    score_file,
)
# slskd_api expects typing.NotRequired (py3.11+). Provide a shim for py3.10.
if not hasattr(typing, "NotRequired"):
    try:
        from typing_extensions import NotRequired  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SystemExit(
            "Python <3.11 detected. Install typing_extensions: "
            "pip install typing_extensions"
        ) from exc
    typing.NotRequired = NotRequired  # type: ignore[attr-defined]

import slskd_api

_CSV_ARTIST_COLS = ["Artist Name(s)", "Artist Name", "Nombre(s) del artista"]
_CSV_TRACK_COLS = ["Track Name", "Song Name", "Nombre de la canción"]


def load_search_strings(csv_path: str, limit: int | None) -> List[str]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "search_string" in fieldnames:
            rows = [row["search_string"].strip() for row in reader if row.get("search_string")]
        else:
            artist_col = next((c for c in _CSV_ARTIST_COLS if c in fieldnames), None)
            track_col = next((c for c in _CSV_TRACK_COLS if c in fieldnames), None)
            if not artist_col or not track_col:
                raise ValueError(
                    "CSV must include a 'search_string' column, or artist/track columns "
                    f"({_CSV_ARTIST_COLS} / {_CSV_TRACK_COLS})"
                )
            from intellidj.spotify import clean_track_name, normalize_artist
            rows = []
            for row in reader:
                artist = normalize_artist(row.get(artist_col, "").strip())
                track = clean_track_name(row.get(track_col, "").strip())
                if artist and track:
                    rows.append(f"{artist} - {track}")
    if limit is not None:
        return rows[:limit]
    return rows


def _is_in_library(db: IntelliDJDB, track_id: int) -> bool:
    """Return True if a library_files row already exists for this track."""
    row = db.conn.execute(
        """
        SELECT id FROM library_files
        WHERE track_id = ?
          AND status IN ('indexed', 'staged', 'in_library')
        LIMIT 1
        """,
        (int(track_id),),
    ).fetchone()
    return row is not None


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue slskd downloads from DB candidates or an optional CSV")
    add_common_config_arg(parser)
    parser.add_argument(
        "--csv",
        default=None,
        help="(Deprecated) Path to candidates CSV. Prefer DB selectors (--scope/--label/--batch-id).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows processed")
    parser.add_argument("--search-timeout-ms", type=int, default=None, help="Search timeout (ms)")
    parser.add_argument("--response-limit", type=int, default=None, help="Max user responses")
    parser.add_argument("--file-limit", type=int, default=None, help="Max files in results")
    parser.add_argument("--dry-run", action="store_true", help="Do not enqueue downloads")
    parser.add_argument("--debug", action="store_true", help="Print response structure for troubleshooting")
    parser.add_argument("--no-stop", action="store_true", help="Do not stop searches after queuing a download")
    parser.add_argument(
        "--skip-if-in-library",
        action="store_true",
        default=False,
        help="Skip queuing a download if the track already has a library_files row in the DB",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite path for lifecycle tracking (default: INTELLIDJ_DB_PATH or ./intellidj.db)",
    )
    add_common_selector_args(parser, include_scope=True)
    parser.add_argument("--import-method", default=None, help="Method label stored in stage state")
    args = parser.parse_args()
    config = load_project_config(args.config)

    scope = resolve_scope(args.scope, config, default="new")
    db_path = resolve_db_path(args.db_path, config)
    label = coalesce(args.label, cfg_get(config, "pipeline.label"))
    search_timeout_ms = int(coalesce(args.search_timeout_ms, cfg_get(config, "slskd.search_timeout_ms"), 90000))
    response_limit = int(coalesce(args.response_limit, cfg_get(config, "slskd.response_limit"), 100))
    file_limit = int(coalesce(args.file_limit, cfg_get(config, "slskd.file_limit"), 10000))
    import_method = str(coalesce(args.import_method, cfg_get(config, "pipeline.import_method"), "slskd_api"))

    host = os.getenv("SLSKD_HOST", str(cfg_get(config, "slskd.host", DEFAULT_HOST)))
    url_base = os.getenv("SLSKD_URL_BASE", str(cfg_get(config, "slskd.url_base", DEFAULT_URL_BASE)))
    # slskd_api already prefixes /api/v0 internally; avoid double-prefix.
    if url_base.strip() == "/api/v0":
        url_base = ""
    api_key = os.getenv("SLSKD_API_KEY")

    if not api_key:
        raise SystemExit("Missing SLSKD_API_KEY in environment. Set it in .env.")

    slskd = slskd_api.SlskdClient(host, api_key, url_base)
    api_base = build_api_base(host)

    db = IntelliDJDB(db_path)
    source_mode = "csv" if args.csv else "db"
    if args.csv:
        print("[warn] --csv mode is deprecated; prefer DB-first mode with --scope/--label/--batch-id.")
    selected_batch_id = args.batch_id
    if source_mode == "db" and selected_batch_id is None:
        latest_batch = db.get_latest_batch(source_type="exportify_csv", label=label)
        if latest_batch:
            selected_batch_id = int(latest_batch["id"])
    if args.csv:
        search_items: List[Tuple[int | None, str]] = [(None, q) for q in load_search_strings(args.csv, args.limit)]
        input_path = args.csv
    else:
        search_items = db.get_pending_download_queries_v2(
            limit=args.limit,
            scope=scope,
            batch_id=selected_batch_id,
            label=label,
        )
        if not search_items:
            # Fallback to legacy event-based pending query resolution.
            search_items = db.get_pending_download_queries(args.limit)
        input_path = str(db.path)
    if not search_items:
        db.close()
        if args.csv:
            raise SystemExit("No search_string rows found.")
        raise SystemExit("No pending candidate tracks found in DB.")

    run_id = db.start_run(
        script_name="dj_to_slskd_pipeline.py",
        input_path=input_path,
        options={
            "source_mode": source_mode,
            "scope": scope,
            "label": label,
            "batch_id": selected_batch_id,
            "import_method": import_method,
            "limit": args.limit,
            "search_timeout_ms": search_timeout_ms,
            "response_limit": response_limit,
            "file_limit": file_limit,
            "dry_run": args.dry_run,
            "no_stop": args.no_stop,
            "db_path": db_path,
        },
    )
    pipeline_status = "success"
    error_count = 0

    queued = 0
    skipped = 0

    try:
        def _run_search(search_text):
            """Run a single slskd search for ``search_text`` and return responses."""
            search_id = str(uuid.uuid4())
            search_resp = retry_with_backoff(
                lambda: slskd.searches.search_text(
                    searchText=search_text,
                    id=search_id,
                    fileLimit=file_limit,
                    responseLimit=response_limit,
                    searchTimeout=search_timeout_ms,
                ),
                label="slskd.searches.search_text",
            )
            # slskd may return its own token/id; prefer them if present
            search_token = None
            search_id_actual = search_id
            if isinstance(search_resp, dict):
                search_id_actual = search_resp.get("id") or search_id_actual
                search_token = search_resp.get("token") or search_resp.get("id")
            if not search_token:
                search_token = search_id_actual
            # Prefer UUID token for state/response calls when available
            state_id = search_token
            if isinstance(search_token, int):
                state_id = search_id_actual

            # Give the server a moment to populate results
            time.sleep(3)

            # Poll for responses as soon as they appear (no need to wait for completion)
            responses = []
            raw_responses = None
            state_obj = None
            stop_issued = False
            deadline = time.time() + max(search_timeout_ms / 1000.0, 1.0)
            while time.time() < deadline:
                # Try direct REST endpoint for responses (more reliable than wrapper)
                try:
                    responses = fetch_search_responses(api_base, api_key, search_id_actual)
                except Exception:
                    responses = []
                if responses:
                    break

                state_obj = retry_with_backoff(
                    lambda: slskd.searches.state(state_id, includeResponses=True),
                    label="slskd.searches.state",
                )
                if isinstance(state_obj, dict):
                    # If we have counts but no inline responses yet, stop the search to finalize results.
                    if (not args.no_stop) and (not stop_issued) and state_obj.get("responseCount", 0) and not state_obj.get("isComplete", False):
                        try:
                            retry_with_backoff(
                                lambda: slskd.searches.stop(state_id),
                                label="slskd.searches.stop",
                            )
                            stop_issued = True
                        except Exception:
                            pass

                    responses = normalize_responses(state_obj.get("responses"))
                    if responses:
                        break

                    # If counts exist but no inline responses, try responses endpoint with id/token
                    if state_obj.get("responseCount", 0):
                        try:
                            raw_responses = retry_with_backoff(
                                lambda: slskd.searches.search_responses(state_id),
                                label="slskd.searches.search_responses",
                            )
                            responses = normalize_responses(raw_responses)
                        except Exception:
                            raw_responses = None
                            responses = []
                        if responses:
                            break

                        # As a fallback, try state/responses using the alternate identifier
                        if search_token != state_id:
                            try:
                                alt_state = retry_with_backoff(
                                    lambda: slskd.searches.state(search_token, includeResponses=True),
                                    label="slskd.searches.state (alt)",
                                )
                                if isinstance(alt_state, dict):
                                    responses = normalize_responses(alt_state.get("responses"))
                                    state_obj = alt_state
                            except Exception:
                                pass
                            if not responses:
                                try:
                                    alt_responses = retry_with_backoff(
                                        lambda: slskd.searches.search_responses(search_token),
                                        label="slskd.searches.search_responses (alt)",
                                    )
                                    responses = normalize_responses(alt_responses)
                                except Exception:
                                    pass
                            if responses:
                                break
                time.sleep(2)

            if args.debug and (not responses):
                print(f"[debug] timed out waiting for responses after {search_timeout_ms}ms")

            # If completed but responses still empty, try fallback endpoints once.
            if not responses:
                try:
                    raw_responses = retry_with_backoff(
                        lambda: slskd.searches.search_responses(state_id),
                        label="slskd.searches.search_responses (final)",
                    )
                    responses = normalize_responses(raw_responses)
                except Exception:
                    raw_responses = None

            if args.debug:
                if isinstance(search_resp, dict):
                    print(f"[debug] search_resp keys: {sorted(search_resp.keys())}")
                print(f"[debug] search_id: {search_id_actual}")
                print(f"[debug] search_token: {search_token}")
                print(f"[debug] state_id: {state_id}")
                print(f"[debug] raw response type: {type(raw_responses)}")
                if isinstance(raw_responses, list):
                    print(f"[debug] raw response length: {len(raw_responses)}")
                if isinstance(state_obj, dict):
                    print(f"[debug] state keys: {sorted(state_obj.keys())}")
                    print(f"[debug] state counts: responses={state_obj.get('responseCount')} files={state_obj.get('fileCount')}")
                    print(f"[debug] state complete: {state_obj.get('isComplete')}")
                    resp_val = state_obj.get("responses")
                    if isinstance(resp_val, list):
                        print(f"[debug] state responses len: {len(resp_val)}")
                    else:
                        print(f"[debug] state responses type: {type(resp_val)}")
                if responses:
                    sample = responses[0]
                    print(f"[debug] response keys: {sorted(sample.keys())}")
                    files = iter_files(sample)
                    print(f"[debug] first response files: {len(files)}")
                else:
                    if isinstance(raw_responses, dict):
                        print(f"[debug] raw response keys: {sorted(raw_responses.keys())}")

            return responses

        for existing_track_id, query in search_items:
            track_id = existing_track_id
            if track_id is None:
                artist, title = parse_search_string(query)
                track_key = make_track_key(artist=artist, title=title, search_string=query)
                track_id = db.upsert_track(
                    track_key=track_key,
                    artist=artist,
                    title=title,
                    source_search_string=query,
                    source_csv=args.csv,
                )

            if args.skip_if_in_library and track_id and _is_in_library(db, track_id):
                print(f"  [skip] already in library: {query}")
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_queue",
                    status="skipped_in_library",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"reason": "already_in_library"},
                )
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="slskd_queue",
                    status="skipped_in_library",
                    message=f"Track already in local library: {query}",
                )
                skipped += 1
                continue

            db.add_event(
                run_id=run_id,
                track_id=track_id,
                stage="slskd_search",
                status="search_started",
                message=query,
            )
            db.upsert_track_stage_state(
                track_id=track_id,
                stage="slskd_search",
                status="search_started",
                run_id=run_id,
                batch_id=selected_batch_id,
                method=import_method,
                details={"query": query},
            )
            dl_id = db.create_download(
                track_id=track_id,
                batch_id=selected_batch_id,
                run_id=run_id,
                search_string=query,
            )
            db.update_download(dl_id, status="searching")
            db.update_track_status(track_id, status="downloading")

            # Search with progressively simpler queries; stop at first hit.
            responses = []
            user = None
            file_info = None
            for _variant_index, _search_text in enumerate(build_search_queries(query)):
                if _variant_index > 0:
                    print(f"[retry] trying simplified query: {_search_text}")
                responses = _run_search(_search_text)
                user, file_info = pick_best_file(responses, query)
                if user and file_info:
                    break

            if not user or not file_info:
                print(f"[skip] no results for: {query}")
                skipped += 1
                db.update_download(dl_id, status="not_found")
                db.update_track_status(track_id, status="not_found")
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="slskd_search",
                    status="search_no_results",
                    message=query,
                )
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_search",
                    status="search_no_results",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"query": query},
                )
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_not_found",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"query": query},
                )
                continue

            payload = [{"filename": file_info.get("filename"), "size": file_info.get("size")}]
            _, file_score, _ = score_file(file_info, query)
            db.update_download(
                dl_id,
                status="found",
                source_user=user,
                source_file=str(payload[0]["filename"]),
                score=float(file_score),
            )

            if args.dry_run:
                print(f"[dry-run] {user}: {payload[0]['filename']}")
                queued += 1
                db.update_download(dl_id, status="completed")
                db.update_track_status(track_id, status="downloading")
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_dry_run_queued",
                    message=payload[0]["filename"],
                    details={"username": user},
                    file_path=payload[0]["filename"],
                )
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_dry_run_queued",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"query": query, "username": user, "filename": payload[0]["filename"]},
                )
                continue

            enqueue_error = None
            try:
                ok = retry_with_backoff(
                    lambda: slskd.transfers.enqueue(user, payload),
                    label="slskd.transfers.enqueue",
                )
            except Exception as exc:
                ok = False
                enqueue_error = str(exc)
            if ok:
                print(f"[queued] {user}: {payload[0]['filename']}")
                queued += 1
                db.update_download(dl_id, status="completed")
                db.update_track_status(track_id, status="downloading")
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_queued",
                    message=payload[0]["filename"],
                    details={"username": user},
                    file_path=payload[0]["filename"],
                )
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_queued",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"query": query, "username": user, "filename": payload[0]["filename"]},
                )
                db.upsert_asset(
                    run_id=run_id,
                    track_id=track_id,
                    asset_type="download_candidate",
                    path=str(payload[0]["filename"]),
                    origin=user,
                    status="queued",
                    size_bytes=int(payload[0]["size"]) if payload[0]["size"] else None,
                )
                # Stop the search to clear "in progress" status in UI
                if not args.no_stop:
                    try:
                        retry_with_backoff(
                            lambda: slskd.searches.stop(state_id),
                            label="slskd.searches.stop (post enqueue)",
                        )
                    except Exception:
                        pass
            else:
                print(f"[skip] enqueue failed for: {query}")
                skipped += 1
                db.update_download(dl_id, status="failed", last_error=enqueue_error or "enqueue returned falsy")
                db.add_event(
                    run_id=run_id,
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_enqueue_failed",
                    message=query,
                )
                db.upsert_track_stage_state(
                    track_id=track_id,
                    stage="slskd_queue",
                    status="download_enqueue_failed",
                    run_id=run_id,
                    batch_id=selected_batch_id,
                    method=import_method,
                    details={"query": query},
                )
    except Exception:
        pipeline_status = "error"
        error_count += 1
        raise
    finally:
        db.finish_run(
            run_id,
            status=pipeline_status,
            total_count=len(search_items),
            success_count=queued,
            skipped_count=skipped,
            error_count=error_count,
        )
        db.close()

    print(f"\nDone. queued={queued}, skipped={skipped}")


if __name__ == "__main__":
    setup_script_logging(__file__)
    load_env_file(os.getenv("INTELLIDJ_ENV", ".env"), override=False)
    main()

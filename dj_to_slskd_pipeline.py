#!/usr/bin/env python3
import argparse
import csv
import os
import random
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Tuple

import typing
import requests
from dotenv import load_dotenv

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

DEFAULT_HOST = "http://localhost:5030"
DEFAULT_URL_BASE = "/api/v0"
DEFAULT_RETRIES = int(os.getenv("SLSKD_RETRY_ATTEMPTS", "3"))
DEFAULT_RETRY_BACKOFF = float(os.getenv("SLSKD_RETRY_BACKOFF", "0.5"))
DEFAULT_RETRY_MAX_DELAY = float(os.getenv("SLSKD_RETRY_MAX_DELAY", "8"))


def _setup_logging() -> None:
    script_path = Path(__file__).resolve()
    repo_root = None
    for parent in [script_path.parent] + list(script_path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            repo_root = parent
            break
    if repo_root is None:
        repo_root = script_path.parent
    log_dir = repo_root / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{script_path.stem}.log"
    log_file = log_path.open("a", encoding="utf-8")

    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for stream in self.streams:
                stream.write(data)
                stream.flush()

        def flush(self):
            for stream in self.streams:
                stream.flush()

    sys.stdout = Tee(sys.stdout, log_file)
    sys.stderr = Tee(sys.stderr, log_file)


def _load_env() -> None:
    env_path = os.getenv("INTELLIDJ_ENV", ".env")
    load_dotenv(env_path, override=False)


def build_api_base(host: str) -> str:
    base = host.rstrip("/")
    if base.endswith("/api/v0"):
        base = base[: -len("/api/v0")]
    return base


def _should_retry_http(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        status = response.status_code if response is not None else None
        if status is None:
            return True
        if status in (408, 409, 429):
            return True
        return 500 <= status < 600
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    return True


def retry_with_backoff(
    func,
    *,
    label: str,
    retries: int = DEFAULT_RETRIES,
    base_delay: float = DEFAULT_RETRY_BACKOFF,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    should_retry=_should_retry_http,
):
    attempt = 0
    while True:
        try:
            return func()
        except Exception as exc:
            if attempt >= retries or (should_retry and not should_retry(exc)):
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay += random.uniform(0, base_delay)
            print(f"[warn] {label} failed ({exc}); retrying in {delay:.1f}s")
            time.sleep(delay)
            attempt += 1


def fetch_search_responses(base_url: str, api_key: str, search_id: str) -> List[Dict]:
    url = f"{base_url}/api/v0/searches/{search_id}/responses"
    headers = {"X-API-KEY": api_key}
    r = retry_with_backoff(
        lambda: requests.get(url, headers=headers, timeout=10),
        label="requests.get search_responses",
    )
    if r.status_code == 404:
        return []
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def load_search_strings(csv_path: str, limit: int | None) -> List[str]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "search_string" not in reader.fieldnames:
            raise ValueError("CSV must include a 'search_string' column")
        rows = [row["search_string"].strip() for row in reader if row.get("search_string")]
    if limit is not None:
        return rows[:limit]
    return rows


def score_file(file_info: Dict) -> Tuple[int, int]:
    name = str(file_info.get("filename", "")).lower()
    ext = str(file_info.get("extension", "")).lower()
    size = int(file_info.get("size") or 0)

    score = 0
    if name.endswith(".flac") or ext == "flac":
        score += 100
    if "flac" in name:
        score += 20
    if name.endswith(".mp3") or ext == "mp3":
        score += 5
    if "320" in name:
        score += 10

    return score, size


def normalize_responses(raw) -> List[Dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "responses" in raw and isinstance(raw["responses"], list):
            return raw["responses"]
        if "items" in raw and isinstance(raw["items"], list):
            return raw["items"]
    return []




def iter_files(response: Dict) -> List[Dict]:
    for key in ("files", "fileInfos", "results", "file_results"):
        files = response.get(key)
        if isinstance(files, list):
            return files
    return []


def pick_best_file(responses: List[Dict]) -> Tuple[str, Dict] | Tuple[None, None]:
    best_user = None
    best_file = None
    best_score = (-1, -1)

    for response in responses:
        username = response.get("username")
        files = iter_files(response)
        for f in files:
            score = score_file(f)
            if score > best_score:
                best_score = score
                best_user = username
                best_file = f

    if not best_user or not best_file:
        return None, None

    return best_user, best_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue slskd downloads from dj_candidates.csv")
    parser.add_argument("--csv", default="dj_candidates.csv", help="Path to dj_candidates.csv")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of rows processed")
    parser.add_argument("--search-timeout-ms", type=int, default=90000, help="Search timeout (ms)")
    parser.add_argument("--response-limit", type=int, default=100, help="Max user responses")
    parser.add_argument("--file-limit", type=int, default=10000, help="Max files in results")
    parser.add_argument("--dry-run", action="store_true", help="Do not enqueue downloads")
    parser.add_argument("--debug", action="store_true", help="Print response structure for troubleshooting")
    parser.add_argument("--no-stop", action="store_true", help="Do not stop searches after queuing a download")
    args = parser.parse_args()

    host = os.getenv("SLSKD_HOST", DEFAULT_HOST)
    url_base = os.getenv("SLSKD_URL_BASE", DEFAULT_URL_BASE)
    # slskd_api already prefixes /api/v0 internally; avoid double-prefix.
    if url_base.strip() == "/api/v0":
        url_base = ""
    api_key = os.getenv("SLSKD_API_KEY")

    if not api_key:
        raise SystemExit("Missing SLSKD_API_KEY in environment. Set it in .env.")

    slskd = slskd_api.SlskdClient(host, api_key, url_base)
    api_base = build_api_base(host)

    searches = load_search_strings(args.csv, args.limit)
    if not searches:
        raise SystemExit("No search_string rows found.")

    queued = 0
    skipped = 0

    for query in searches:
        search_id = str(uuid.uuid4())
        search_resp = retry_with_backoff(
            lambda: slskd.searches.search_text(
                searchText=query,
                id=search_id,
                fileLimit=args.file_limit,
                responseLimit=args.response_limit,
                searchTimeout=args.search_timeout_ms,
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
        deadline = time.time() + max(args.search_timeout_ms / 1000.0, 1.0)
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
            print(f"[debug] timed out waiting for responses after {args.search_timeout_ms}ms")

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

        user, file_info = pick_best_file(responses)
        if not user or not file_info:
            print(f"[skip] no results for: {query}")
            skipped += 1
            continue

        payload = [{"filename": file_info.get("filename"), "size": file_info.get("size")}]

        if args.dry_run:
            print(f"[dry-run] {user}: {payload[0]['filename']}")
            queued += 1
            continue

        ok = retry_with_backoff(
            lambda: slskd.transfers.enqueue(user, payload),
            label="slskd.transfers.enqueue",
        )
        if ok:
            print(f"[queued] {user}: {payload[0]['filename']}")
            queued += 1
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

    print(f"\nDone. queued={queued}, skipped={skipped}")


if __name__ == "__main__":
    _setup_logging()
    _load_env()
    main()

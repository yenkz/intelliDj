# Shim — logic now lives in intellidj.pipeline.downloader
from intellidj.pipeline.downloader import (  # noqa: F401
    build_api_base,
    _should_retry_http,
    retry_with_backoff,
    fetch_search_responses,
    load_search_strings,
    _normalize_for_match,
    relevance_score,
    AUDIO_EXTENSIONS,
    score_file,
    normalize_responses,
    iter_files,
    pick_best_file,
    build_search_queries,
    execute_search,
    run_downloads,
    _load_env,
    DEFAULT_HOST,
    DEFAULT_URL_BASE,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_MAX_DELAY,
)
import requests  # noqa: F401 — tests monkeypatch mod.requests

if __name__ == "__main__":
    import argparse
    from intellidj.pipeline.downloader import _load_env, run_downloads

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="dj_candidates.csv")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--search-timeout-ms", type=int, default=90000)
    parser.add_argument("--response-limit", type=int, default=100)
    parser.add_argument("--file-limit", type=int, default=10000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-stop", action="store_true")
    _load_env()
    args = parser.parse_args()
    run_downloads(args.csv, args)
